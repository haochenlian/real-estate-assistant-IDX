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


TESTS = [test_asks_for_missing_budget_first, test_asks_for_city_when_nothing_given,
         test_state_accumulates_across_turns, test_reaches_search_when_complete,
         test_clear_session_starts_over, test_two_users_are_independent,
         test_step_counter_increments]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
