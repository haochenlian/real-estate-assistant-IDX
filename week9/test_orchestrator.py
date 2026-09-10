"""Tests for the Week 9 multi-agent orchestrator.

Covers intent classification, routing to every agent, mixed requests running in
parallel, failure handling, and the helpers that connect earlier weeks. Uses a
stand-in model and stand-in agents/queries, so no API key or database is needed.
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(__file__))

import orchestrator as orch
from conversation import clear_session          # Week 4, on the path via orchestrator
from orchestrator import (classify_intent, orchestrate, extract_city, to_listing_fields,
                          build_candidates_query, price_direction, INTENTS, FALLBACK)


def fixed_llm(label):
    """A stand-in model that always replies with the same text."""
    return lambda prompt: label


def recording_agents():
    """Stand-in agents that record how they were called."""
    calls = []

    def make(name):
        def agent(query, user_id, **kwargs):
            calls.append((name, kwargs))
            return {"agent": name, "text": f"{name} answer"}
        return agent
    return {name: make(name) for name in orch.AGENTS}, calls


class patched:
    """Temporarily replace functions inside the orchestrator module."""
    def __init__(self, **replacements):
        self.replacements, self.saved = replacements, {}

    def __enter__(self):
        for name, value in self.replacements.items():
            self.saved[name] = getattr(orch, name)
            setattr(orch, name, value)

    def __exit__(self, *exc):
        for name, value in self.saved.items():
            setattr(orch, name, value)


def fresh_user(name):
    """A user id with no saved session (Week 4 keeps sessions in memory)."""
    clear_session(name)
    return name


ROW = {"L_ListingID": "L1", "L_Address": "12 Oak St", "L_City": "Irvine",
       "price": 1_200_000, "beds": 3, "baths": 2, "sqft": 1500, "DaysOnMarket": 10,
       "LA1_UserFirstName": "Ann", "LA1_UserLastName": "Lee"}


# ---- intent classification ----------------------------------------------
def test_classifier_accepts_every_label():
    for label in INTENTS:
        assert classify_intent("q", fixed_llm(label)) == label


def test_classifier_cleans_case_and_punctuation():
    assert classify_intent("q", fixed_llm(" Market.\n")) == "market"
    assert classify_intent("q", fixed_llm('"knowledge"')) == "knowledge"


def test_classifier_rejects_anything_unexpected():
    assert classify_intent("q", fixed_llm("I think this is search")) == "unknown"
    assert classify_intent("q", fixed_llm("weather")) == "unknown"
    assert classify_intent("q", fixed_llm("")) == "unknown"
    assert classify_intent("q", fixed_llm(None)) == "unknown"


def test_classifier_prompt_includes_message_and_all_labels():
    seen = []
    classify_intent("What does DOM mean?", lambda p: seen.append(p) or "knowledge")
    prompt = seen[0]
    assert "What does DOM mean?" in prompt
    for label in INTENTS:
        assert label in prompt


# ---- routing -------------------------------------------------------------
def test_each_intent_reaches_its_own_agent():
    for intent in orch.AGENTS:
        agents, calls = recording_agents()
        result = orchestrate("q", "u", llm=fixed_llm(intent), agents=agents)
        assert [name for name, _ in calls] == [intent]
        assert result["intent"] == intent
        assert result["text"] == f"{intent} answer"


def test_mixed_runs_search_and_market_and_merges():
    agents, calls = recording_agents()
    result = orchestrate("q", "u", llm=fixed_llm("mixed"), agents=agents)
    assert sorted(name for name, _ in calls) == ["market", "search"]
    assert result["agents"] == ["search", "market"]
    assert "search answer" in result["text"] and "market answer" in result["text"]


def test_mixed_agents_run_at_the_same_time():
    # Each agent waits until the other has started. Run one after the other,
    # the first would wait out the 2-second timeout and fail.
    barrier = threading.Barrier(2, timeout=2)

    def waits(name):
        def agent(query, user_id, **kwargs):
            barrier.wait()
            return {"agent": name, "text": f"{name} ok"}
        return agent
    agents = {"search": waits("search"), "market": waits("market")}
    result = orchestrate("q", "u", llm=fixed_llm("mixed"), agents=agents)
    assert result["text"] == "search ok\n\nmarket ok"


def test_mixed_search_does_not_stop_to_ask_questions():
    agents, calls = recording_agents()
    orchestrate("q", "u", llm=fixed_llm("mixed"), agents=agents)
    assert dict(calls)["search"] == {"follow_up": False}


def test_unknown_intent_gets_fallback_and_calls_no_agent():
    agents, calls = recording_agents()
    result = orchestrate("q", "u", llm=fixed_llm("weather"), agents=agents)
    assert calls == []
    assert result["intent"] == "unknown" and result["text"] == FALLBACK


def test_failing_agent_does_not_crash_the_chat():
    agents, _ = recording_agents()

    def broken(query, user_id, **kwargs):
        raise ConnectionError("database down")
    agents["search"] = broken
    single = orchestrate("q", "u", llm=fixed_llm("search"), agents=agents)
    assert "problem" in single["text"]
    mixed = orchestrate("q", "u", llm=fixed_llm("mixed"), agents=agents)
    assert "problem" in mixed["text"] and "market answer" in mixed["text"]


def test_real_mixed_request_prepares_database_before_threads():
    events = []

    def agent(name):
        def run(query, user_id, **kwargs):
            events.append(name)
            return {"agent": name, "text": name}
        return run
    real_looking = dict(orch.AGENTS, search=agent("search"), market=agent("market"))
    with patched(AGENTS=real_looking, prepare_database=lambda: events.append("prepare")):
        orchestrate("q", fresh_user("p1"), llm=fixed_llm("mixed"))
    assert events[0] == "prepare"
    assert sorted(events[1:]) == ["market", "search"]


def test_stand_in_agents_never_touch_the_database():
    prepared = []
    agents, _ = recording_agents()
    with patched(prepare_database=lambda: prepared.append(True)):
        orchestrate("q", "u", llm=fixed_llm("mixed"), agents=agents)
    assert prepared == []


# ---- helpers that connect earlier weeks ----------------------------------
def test_city_found_even_with_a_question_mark():
    assert extract_city("What is the average price per sqft in Pasadena?", fresh_user("c1")) == "Pasadena"


def test_city_falls_back_to_the_session():
    uid = fresh_user("c2")
    orch.get_session(uid).city = "Irvine"
    assert extract_city("Are prices going up?", uid) == "Irvine"


def test_week3_rows_get_week7_field_names():
    mapped = to_listing_fields(ROW)
    assert mapped["L_SystemPrice"] == 1_200_000
    assert mapped["L_Keyword2"] == 3
    assert mapped["LM_Int2_3"] == 1500
    assert mapped["L_City"] == "Irvine"


def test_candidates_query_is_parameterized_and_banded():
    evil = "Irvine'; DROP TABLE rets_property; --"
    sql, params = build_candidates_query(evil, 1_000_000, "L1")
    assert evil not in sql and evil in params
    assert sql.count("%s") == len(params)
    assert params[1:5] == ["L1", 700_000, 1_300_000, 1_000_000]


# ---- price trend ---------------------------------------------------------
def trend(*prices, start=1):
    return [{"month": f"2026-{start + i:02d}", "avg_price": p} for i, p in enumerate(prices)]


def test_prices_rising():
    result = price_direction(trend(100, 100, 100, 120, 120, 120), today="2026-09")
    assert result["direction"] == "rising" and result["change_pct"] == 20.0


def test_prices_falling_and_flat():
    assert price_direction(trend(100, 100, 100, 90, 90, 90), today="2026-09")["direction"] == "falling"
    assert price_direction(trend(100, 100, 100, 101, 101, 101), today="2026-09")["direction"] == "flat"


def test_future_months_are_ignored():
    data = trend(100, 100, 100, 120, 120, 120) + [{"month": "2072-06", "avg_price": 9_999_999}]
    assert price_direction(data, today="2026-09")["change_pct"] == 20.0


def test_too_few_months_is_reported():
    assert price_direction(trend(100, 110), today="2026-09")["direction"] == "not enough data"


# ---- individual agents (database and model replaced) ----------------------
def test_search_agent_remembers_results():
    uid = fresh_user("s1")
    with patched(search_active_listings=lambda filters, limit=5: [ROW]):
        result = orch.property_search_agent("3 bed condos in Irvine under $1.5M", uid)
    assert "12 Oak St" in result["text"]
    assert orch.get_session(uid).last_results == [ROW]


def test_search_agent_asks_for_missing_details():
    uid = fresh_user("s2")
    with patched(search_active_listings=lambda *a, **k: [ROW]):
        result = orch.property_search_agent("homes in Irvine", uid)
    assert result["listings"] == [] and "budget" in result["text"].lower()


def test_mixed_search_goes_ahead_with_just_a_city():
    uid = fresh_user("s3")
    with patched(search_active_listings=lambda filters, limit=5: [ROW]):
        result = orch.property_search_agent("affordable homes in Irvine", uid, follow_up=False)
    assert "12 Oak St" in result["text"]


def test_market_agent_reports_trend():
    summary = {"sold_count": 10, "avg_close_price": 1_000_000, "avg_price_per_sqft": 800,
               "avg_dom": 30, "list_to_close_pct": 101.0}
    rising = [{"month": m, "avg_price": p} for m, p in
              [("2026-01", 100), ("2026-02", 100), ("2026-03", 100),
               ("2026-04", 120), ("2026-05", 120), ("2026-06", 120)]]
    with patched(market_summary=lambda city: summary, price_trend=lambda city: rising):
        result = orch.market_stats_agent("Are prices rising in Pasadena?", fresh_user("m1"))
    assert "Pasadena" in result["text"] and "rising (+20.0%)" in result["text"]


def test_market_agent_asks_for_a_city():
    result = orch.market_stats_agent("Are prices rising?", fresh_user("m2"))
    assert "which city" in result["text"].lower()


def test_recommend_needs_a_search_first():
    result = orch.recommendation_agent("show me similar ones", fresh_user("r1"))
    assert "search for homes first" in result["text"].lower()


def test_recommend_scores_candidates_and_checks_price():
    uid = fresh_user("r2")
    orch.get_session(uid).last_results = [ROW]
    similar = dict(ROW, L_ListingID="L2", L_Address="14 Oak St", price=1_220_000, sqft=1550)

    def fake_sql(sql, params):
        return [{"avg_ppsf": 800.0, "comp_count": 12}] if "avg_ppsf" in sql else [similar]
    with patched(run_sql=fake_sql):
        result = orch.recommendation_agent("similar homes?", uid)
    assert "14 Oak St" in result["text"] and "60/60" in result["text"]
    assert "in line with comparable sales" in result["text"]


def test_rag_agent_returns_answer_with_sources():
    answer = {"answer": "DOM is days on market.", "sources": ["glossary.md"]}
    with patched(get_rag_index=lambda: [], answer_question=lambda q, index: answer):
        result = orch.rag_agent("What does DOM mean?", "k1")
    assert "DOM is days on market." in result["text"] and "glossary.md" in result["text"]


TESTS = [test_classifier_accepts_every_label, test_classifier_cleans_case_and_punctuation,
         test_classifier_rejects_anything_unexpected,
         test_classifier_prompt_includes_message_and_all_labels,
         test_each_intent_reaches_its_own_agent, test_mixed_runs_search_and_market_and_merges,
         test_mixed_agents_run_at_the_same_time, test_mixed_search_does_not_stop_to_ask_questions,
         test_unknown_intent_gets_fallback_and_calls_no_agent,
         test_failing_agent_does_not_crash_the_chat,
         test_real_mixed_request_prepares_database_before_threads,
         test_stand_in_agents_never_touch_the_database,
         test_city_found_even_with_a_question_mark, test_city_falls_back_to_the_session,
         test_week3_rows_get_week7_field_names, test_candidates_query_is_parameterized_and_banded,
         test_prices_rising, test_prices_falling_and_flat, test_future_months_are_ignored,
         test_too_few_months_is_reported,
         test_search_agent_remembers_results, test_search_agent_asks_for_missing_details,
         test_mixed_search_goes_ahead_with_just_a_city,
         test_market_agent_reports_trend, test_market_agent_asks_for_a_city,
         test_recommend_needs_a_search_first, test_recommend_scores_candidates_and_checks_price,
         test_rag_agent_returns_answer_with_sources]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
