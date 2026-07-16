"""
Conversational property-search agent (Week 4).

Turns the single-shot search from Week 3 into a multi-turn conversation.
The agent remembers what the user has said so far, asks follow-up questions
for whatever is still missing, and runs the search once it has enough info.

Design (per program guidance):
  UserSession is NOT the LLM's chat memory. It is *structured application
  state* -- a set of explicit, typed slots our own code can check directly,
  e.g. `if session.max_price is None: ask_for_budget()`. This is deterministic
  (we know exactly what's captured), fast (plain object lookup), and scoped to
  the property-search task only.

Pipeline reused from earlier weeks:
  each message --(Week 2 parser)--> new filters --> merged into the session
  session complete --(Week 3 query builder)--> real listings

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

# Reuse the Week 2 parser and the Week 3 query builder.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "week2"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "week3"))
from query_parser import parse_property_query          # noqa: E402
from db_query import build_active_listings_query        # noqa: E402


@dataclass
class UserSession:
    """Structured state for one user's property search (typed slots)."""
    city: str | None = None
    max_price: int | None = None
    beds: int | None = None
    baths: float | None = None
    sqft: int | None = None
    type: str | None = None
    pool: str | None = None
    has_view: str | None = None
    max_hoa: int | None = None
    last_results: list | None = None
    step: int = 0            # how many turns this conversation has had


# All active conversations, keyed by user id (e.g. a WhatsApp number).
sessions: dict[str, UserSession] = {}


def get_session(user_id: str) -> UserSession:
    """Return the user's session, creating a fresh one on first contact."""
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    return sessions[user_id]


def update_session(user_id: str, updates: dict) -> UserSession:
    """Merge new filter values into the user's session (ignore None)."""
    session = get_session(user_id)
    for key, value in updates.items():
        if value is not None and hasattr(session, key):
            setattr(session, key, value)
    return session


def clear_session(user_id: str) -> None:
    """Forget a user's search (e.g. when they start over)."""
    sessions.pop(user_id, None)


# The minimum slots we collect before searching, and the question to ask
# for each one. Asked in this order; the first missing one is requested.
ASK_ORDER = [
    ("city",      "Which city are you looking in?"),
    ("max_price", "What's your budget (maximum price)?"),
    ("type",      "Any preference - condo, single family, or townhouse?"),
]

# Slots that map to database columns (what we hand to the Week 3 query builder).
_FILTER_KEYS = ["city", "max_price", "beds", "baths", "sqft",
                "type", "pool", "has_view", "max_hoa"]


def handle_message(user_id: str, text: str) -> dict:
    """Handle one incoming message and decide what to do next.

    Returns a dict describing the action:
      {"action": "ask",    "slot": <name>, "message": <follow-up question>}
      {"action": "search", "filters": {...}, "sql": ..., "params": [...],
                           "message": <confirmation>}
    """
    session = get_session(user_id)
    session.step += 1

    # 1. Parse this message and merge anything new into the session.
    new_filters = parse_property_query(text)
    update_session(user_id, new_filters)
    session = get_session(user_id)

    # 2. Ask for the first required slot that is still empty.
    for slot, question in ASK_ORDER:
        if getattr(session, slot) is None:
            return {"action": "ask", "slot": slot, "message": question}

    # 3. We have enough -- build the search from the collected slots.
    filters = {k: getattr(session, k) for k in _FILTER_KEYS}
    sql, params = build_active_listings_query(filters, page=1, limit=5)
    summary = _summary(session)
    return {
        "action": "search",
        "filters": filters,
        "sql": sql,
        "params": params,
        "message": f"Great - searching for {summary}. Here are the top matches:",
    }


def _summary(s: UserSession) -> str:
    """A short human-readable summary of what the user asked for."""
    bits = []
    if s.beds:
        bits.append(f"{s.beds}-bed")
    if s.type:
        bits.append(s.type)
    else:
        bits.append("homes")
    if s.city:
        bits.append(f"in {s.city}")
    if s.max_price:
        bits.append(f"under ${s.max_price:,.0f}")
    if s.pool:
        bits.append("with a pool")
    return " ".join(bits)


if __name__ == "__main__":
    # Simulate a multi-turn conversation for one user.
    uid = "whatsapp:+15551234567"
    clear_session(uid)
    conversation = [
        "Find me a home in Irvine",
        "under $1.2M",
        "a condo with at least 2 beds",
    ]
    for msg in conversation:
        print(f"\nUSER : {msg}")
        result = handle_message(uid, msg)
        print(f"AGENT: {result['message']}")
        if result["action"] == "search":
            print("       filters:", {k: v for k, v in result["filters"].items() if v})
