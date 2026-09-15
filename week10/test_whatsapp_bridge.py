"""Tests for the Week 10 WhatsApp bridge.

Covers WhatsApp formatting for every agent, saving and restoring sessions
between messages, and the failure paths. Uses stand-in orchestrator results,
so no API key, database, or WhatsApp connection is needed.
"""

import contextlib
import io
import os
import sys
import tempfile
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

import whatsapp_bridge as bridge
from whatsapp_bridge import (format_for_whatsapp, reply_to, save_session, load_session,
                             session_path, main, APOLOGY, GREETING)
from conversation import sessions, get_session, clear_session   # Week 4, via the bridge's path

bridge.SESSION_DIR = tempfile.mkdtemp(prefix="idx-sessions-")   # never touch real sessions
bridge.LOG_PATH = os.path.join(tempfile.mkdtemp(prefix="idx-log-"), "bridge.log")

ROW = {"L_ListingID": "L1", "L_Address": "12 Oak St", "L_City": "Irvine",
       "price": 1_200_000, "beds": 3, "baths": Decimal("2.0"), "sqft": 1500, "DaysOnMarket": 10}


def result(*parts):
    return {"intent": "x", "agents": [p["agent"] for p in parts],
            "text": "\n\n".join(p["text"] for p in parts), "parts": list(parts)}


def fresh(user):
    clear_session(user)
    with contextlib.suppress(FileNotFoundError):
        os.remove(session_path(user))
    return user


# ---- formatting ----------------------------------------------------------
def test_search_results_become_whatsapp_cards():
    part = {"agent": "search", "text": "Homes ...", "listings": [ROW]}
    text = format_for_whatsapp(result(part), "homes in Irvine", "f1")
    assert "*Homes for sale in Irvine*" in text
    assert "🏠 *12 Oak St, Irvine*" in text
    assert "💰 $1,200,000 | 🛏 3bd/2ba | 📐 1500 sqft" in text
    assert "📅 10 days on market" in text


def test_search_hint_is_kept_in_italics():
    part = {"agent": "search", "listings": [ROW],
            "text": "Homes ...\n(Tell me a budget and property type to narrow these down.)"}
    text = format_for_whatsapp(result(part), "q", "f2")
    assert text.endswith("_Tell me a budget and property type to narrow these down._")


def test_follow_up_question_passes_through():
    part = {"agent": "search", "text": "What's your budget (maximum price)?", "listings": []}
    assert format_for_whatsapp(result(part), "q", "f3") == "What's your budget (maximum price)?"


SUMMARY = {"sold_count": 498, "avg_close_price": 1539977.0, "avg_price_per_sqft": 823.0,
           "avg_dom": Decimal("39.6"), "list_to_close_pct": 103.0}


def test_market_answers_the_trend_first():
    months = [{"month": m, "avg_ppsf": p} for m, p in
              [("2026-01", 737), ("2026-02", 824), ("2026-03", 840), ("2026-04", 850), ("2026-05", 828)]]
    part = {"agent": "market", "text": "...", "summary": SUMMARY,
            "trend": {"direction": "flat", "change_pct": 0.8, "recent_ppsf": 839, "prior_ppsf": 832,
                      "recent_months": "2026-04 to 2026-05", "prior_months": "2026-02 to 2026-03",
                      "months": months, "data_through": "2026-06-15"}}
    text = format_for_whatsapp(result(part), "Are prices rising in Pasadena?", fresh("f4"))
    assert text.split("\n")[0] == "➖ *Pasadena prices are roughly flat* (+0.8% per sqft)"
    assert "Monthly $/sqft (2026): Jan $737 · Feb $824 · Mar $840 · Apr $850 · May $828" in text
    assert "_Complete months only; data through 2026-06-15._" in text
    assert "📊 *Pasadena market*" in text and "• Price per sqft: $823" in text
    assert "• Avg days on market: 39.6" in text and "at or above asking" in text


def test_market_without_enough_months_says_so():
    part = {"agent": "market", "text": "...", "summary": SUMMARY,
            "trend": {"direction": "not enough data", "change_pct": None, "months": [],
                      "data_through": "2026-06-15"}}
    text = format_for_whatsapp(result(part), "What's the market like in Pasadena?", fresh("f4b"))
    assert text.startswith("_Not enough complete months to tell a price trend. Data through 2026-06-15._")


def test_market_without_data_passes_through():
    part = {"agent": "market", "text": "Which city's market would you like to know about?"}
    assert format_for_whatsapp(result(part), "q", "f5") == part["text"]


def test_recommendations_show_scores_and_price_check():
    uid = fresh("f6")
    get_session(uid).last_results = [ROW]
    similar = dict(ROW, L_Address="14 Oak St", price=1_220_000)
    part = {"agent": "recommend", "text": "...", "recommendations": [(similar, 60.0)],
            "price_check": {"comp_price": 1_200_000, "delta_pct": 0.0, "comp_count": 12,
                            "verdict": "in line with comparable sales"}}
    text = format_for_whatsapp(result(part), "similar?", uid)
    assert "✨ *Homes similar to 12 Oak St* ($1,200,000)" in text
    assert "🏠 *14 Oak St, Irvine*" in text and "⭐ match 60/60" in text
    assert "💡 *Price check:* in line with comparable sales. 12 similar-sized sales" in text


def test_recommend_before_search_passes_through():
    part = {"agent": "recommend", "text": "Search for homes first, then ask me for similar ones."}
    assert format_for_whatsapp(result(part), "q", "f7") == part["text"]


def test_knowledge_sources_move_to_an_italic_line():
    part = {"agent": "knowledge", "text": "DOM is days on market.\n(Sources: glossary.md)",
            "sources": ["glossary.md"]}
    text = format_for_whatsapp(result(part), "q", "f8")
    assert text == "DOM is days on market.\n\n_Sources: glossary.md_"


def test_email_error_and_unknown_keep_their_text():
    email = {"agent": "email", "text": "Email drafting isn't available yet."}
    broken = {"agent": "search", "error": "ConnectionError()", "text": "Sorry, the search agent ran into a problem."}
    assert format_for_whatsapp(result(email), "q", "f9") == email["text"]
    assert format_for_whatsapp(result(broken), "q", "f9") == broken["text"]
    unknown = {"intent": "unknown", "agents": [], "text": "I'm not sure how to help.", "parts": []}
    assert format_for_whatsapp(unknown, "q", "f9") == "I'm not sure how to help."


def test_mixed_reply_contains_both_parts():
    search = {"agent": "search", "text": "...", "listings": [ROW]}
    market = {"agent": "market", "text": "Which city's market would you like to know about?"}
    text = format_for_whatsapp(result(search, market), "q", "f10")
    assert "🏠 *12 Oak St, Irvine*" in text and text.endswith(market["text"])


# ---- sessions between messages -------------------------------------------
def test_session_survives_a_new_process():
    uid = fresh("s1")
    session = get_session(uid)
    session.city, session.max_price, session.last_results = "Irvine", 1_500_000, [ROW]
    save_session(uid)
    sessions.clear()                          # what a new Python process starts with
    load_session(uid)
    restored = get_session(uid)
    assert restored.city == "Irvine" and restored.max_price == 1_500_000
    assert restored.last_results[0]["L_Address"] == "12 Oak St"
    assert restored.last_results[0]["baths"] == 2.0      # Decimal saved as a number


def test_session_file_is_private():
    uid = fresh("s5")
    get_session(uid).city = "Irvine"
    save_session(uid)
    assert os.stat(session_path(uid)).st_mode & 0o777 == 0o600


def test_missing_or_corrupt_session_file_starts_fresh():
    uid = fresh("s2")
    load_session(uid)
    assert uid not in sessions
    os.makedirs(bridge.SESSION_DIR, exist_ok=True)
    with open(session_path(uid), "w") as fh:
        fh.write("{not json")
    load_session(uid)
    assert uid not in sessions


def test_unknown_saved_fields_are_ignored():
    uid = fresh("s3")
    os.makedirs(bridge.SESSION_DIR, exist_ok=True)
    with open(session_path(uid), "w") as fh:
        fh.write('{"city": "Irvine", "field_from_an_older_version": 1}')
    load_session(uid)
    assert get_session(uid).city == "Irvine"


def test_session_file_names_stay_inside_the_folder():
    assert os.path.dirname(session_path("../../etc/passwd")) == bridge.SESSION_DIR
    assert os.path.basename(session_path("+1 (206) 555")) == "_1__206__555.json"


def test_reply_remembers_between_messages():
    uid = fresh("s4")

    def first(message, user_id):
        get_session(user_id).city = "Pasadena"
        return result({"agent": "email", "text": "ok"})
    reply_to("homes in Pasadena", uid, orchestrate=first)
    sessions.clear()                          # next message = new process

    seen = []

    def second(message, user_id):
        seen.append(get_session(user_id).city)
        return result({"agent": "email", "text": "ok"})
    reply_to("are prices rising?", uid, orchestrate=second)
    assert seen == ["Pasadena"]


# ---- failure paths and command line ---------------------------------------
def test_any_failure_becomes_an_apology():
    def broken(message, user_id):
        raise RuntimeError("database down")
    with contextlib.redirect_stderr(io.StringIO()):
        assert reply_to("homes in Irvine", fresh("e1"), orchestrate=broken) == APOLOGY


def test_empty_message_gets_a_greeting():
    assert reply_to("   ", "e2", orchestrate=lambda m, u: 1 / 0) == GREETING


def test_message_from_environment_wins_over_arguments():
    captured = []
    original = bridge.reply_to
    bridge.reply_to = lambda message, user_id: captured.append((message, user_id)) or "reply"
    os.environ["IDX_MESSAGE"] = 'what does DOM mean"; rm -rf ~'
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            main(["--user", "u9", "ignored"])
    finally:
        bridge.reply_to = original
        del os.environ["IDX_MESSAGE"]
    assert captured == [('what does DOM mean"; rm -rf ~', "u9")]
    assert out.getvalue() == "reply\n"


def test_diagnostics_go_to_the_log_not_the_chat():
    # OpenClaw forwards stdout and stderr together, so only the reply may reach either.
    original = bridge.reply_to

    def noisy(message, user_id):
        print("email_agent: listing details unavailable (ProgrammingError)", file=sys.stderr)
        return "reply"
    bridge.reply_to = noisy
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out, \
             contextlib.redirect_stderr(io.StringIO()) as err:
            main(["--user", "u10", "hello"])
    finally:
        bridge.reply_to = original
    assert out.getvalue() == "reply\n" and err.getvalue() == ""
    with open(bridge.LOG_PATH) as fh:
        assert "listing details unavailable" in fh.read()
    assert os.stat(bridge.LOG_PATH).st_mode & 0o777 == 0o600


TESTS = [test_search_results_become_whatsapp_cards, test_search_hint_is_kept_in_italics,
         test_follow_up_question_passes_through, test_market_answers_the_trend_first,
         test_market_without_enough_months_says_so,
         test_market_without_data_passes_through, test_recommendations_show_scores_and_price_check,
         test_recommend_before_search_passes_through, test_knowledge_sources_move_to_an_italic_line,
         test_email_error_and_unknown_keep_their_text, test_mixed_reply_contains_both_parts,
         test_session_survives_a_new_process, test_session_file_is_private,
         test_missing_or_corrupt_session_file_starts_fresh,
         test_unknown_saved_fields_are_ignored, test_session_file_names_stay_inside_the_folder,
         test_reply_remembers_between_messages, test_any_failure_becomes_an_apology,
         test_empty_message_gets_a_greeting, test_message_from_environment_wins_over_arguments,
         test_diagnostics_go_to_the_log_not_the_chat]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
