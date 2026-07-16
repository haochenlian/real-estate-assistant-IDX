"""Tests for the Week 4 conversational agent (session / multi-turn logic)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from conversation import (handle_message, get_session, clear_session, sessions)


def fresh(uid):
    clear_session(uid)


def test_asks_for_missing_budget_first():
    uid = "u1"; fresh(uid)
    r = handle_message(uid, "Find me a home in Irvine")
    assert r["action"] == "ask" and r["slot"] == "max_price"   # city known, budget missing


def test_asks_for_city_when_nothing_given():
    uid = "u2"; fresh(uid)
    r = handle_message(uid, "I want to buy something")
    assert r["action"] == "ask" and r["slot"] == "city"


def test_state_accumulates_across_turns():
    uid = "u3"; fresh(uid)
    handle_message(uid, "homes in Irvine")
    handle_message(uid, "under $1.2M")
    s = get_session(uid)
    assert s.city == "Irvine" and s.max_price == 1_200_000     # remembered both turns


def test_reaches_search_when_complete():
    uid = "u4"; fresh(uid)
    handle_message(uid, "homes in Irvine")
    handle_message(uid, "under $1.2M")
    r = handle_message(uid, "a condo with at least 2 beds")
    assert r["action"] == "search"
    assert r["filters"]["city"] == "Irvine"
    assert r["filters"]["max_price"] == 1_200_000
    assert r["filters"]["beds"] == 2
    assert r["filters"]["type"] == "Condominium"


def test_clear_session_starts_over():
    uid = "u5"; fresh(uid)
    handle_message(uid, "homes in Irvine")
    clear_session(uid)
    assert uid not in sessions


def test_two_users_are_independent():
    fresh("a"); fresh("b")
    handle_message("a", "homes in Irvine")
    handle_message("b", "homes in San Diego")
    assert get_session("a").city == "Irvine"
    assert get_session("b").city == "San Diego"


def test_step_counter_increments():
    uid = "u6"; fresh(uid)
    handle_message(uid, "homes in Irvine")
    handle_message(uid, "under $1M")
    assert get_session(uid).step == 2


def test_all_info_in_one_message():
    """If the user says everything at once, search immediately -- no follow-ups."""
    uid = "u7"; fresh(uid)
    r = handle_message(uid, "3-bed condos in Irvine under $1.5M")
    assert r["action"] == "search"
    assert r["filters"]["city"] == "Irvine"
    assert r["filters"]["beds"] == 3
    assert r["filters"]["type"] == "Condominium"


def test_user_changes_their_mind():
    """A later value overwrites an earlier one for the same slot."""
    uid = "u8"; fresh(uid)
    handle_message(uid, "homes in Irvine under $1M")
    handle_message(uid, "actually under $1.2M")
    assert get_session(uid).max_price == 1_200_000     # updated, not stuck at 1M


def test_out_of_order_information():
    """User gives type, then city, then budget -- still reaches a search."""
    uid = "u9"; fresh(uid)
    handle_message(uid, "I want a condo")       # type first
    handle_message(uid, "in San Diego")         # city second
    r = handle_message(uid, "under 800k")       # budget last
    assert r["action"] == "search"
    assert r["filters"]["type"] == "Condominium"
    assert r["filters"]["city"] == "San Diego"
    assert r["filters"]["max_price"] == 800_000


def test_optional_details_are_captured():
    """Extras like pool are remembered even though they aren't required to search."""
    uid = "u10"; fresh(uid)
    r = handle_message(uid, "condo in Irvine under $1M with a pool")
    assert r["action"] == "search"
    assert r["filters"]["pool"] == "True"


def test_unrecognized_input_keeps_asking():
    """Vague text the parser can't read must not crash or fill slots falsely."""
    uid = "u11"; fresh(uid)
    r = handle_message(uid, "somewhere nice and cozy")
    assert r["action"] == "ask" and r["slot"] == "city"   # still needs a city
    assert get_session(uid).city is None                  # nothing wrongly captured


TESTS = [test_asks_for_missing_budget_first, test_asks_for_city_when_nothing_given,
         test_state_accumulates_across_turns, test_reaches_search_when_complete,
         test_clear_session_starts_over, test_two_users_are_independent,
         test_step_counter_increments,
         test_all_info_in_one_message, test_user_changes_their_mind,
         test_out_of_order_information, test_optional_details_are_captured,
         test_unrecognized_input_keeps_asking]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
