"""
Multi-agent orchestrator (Week 9).

One entry point for the whole assistant. Every message goes to `orchestrate()`,
which asks the model what kind of request it is, then hands it to the right
specialist agent -- or, for a mixed request, to two agents at once.

    "Find me affordable homes in Pasadena and tell me whether prices are rising."
        -> intent: mixed
        -> propertySearchAgent + marketStatsAgent run in parallel
        -> one combined answer

Agent registry (each wraps code from an earlier week):
    search     propertySearchAgent   Week 2 parser + Week 3 query + Week 4 session
    market     marketStatsAgent      Week 5 market summary + monthly trend
    recommend  recommendationAgent   Week 7 hybrid scoring + comp price check
    knowledge  ragAgent              Week 8 RAG knowledge assistant
    email      emailDraftAgent       placeholder until Week 11

Only `call_llm()` (intent classification) and the RAG agent call OpenAI. Agents
and the model call are passed in as arguments, so the routing logic is tested
without an API key or a database.

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import calendar
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
for _week in ("week2", "week3", "week4", "week5", "week6", "week7", "week8"):
    sys.path.insert(0, os.path.join(ROOT, _week))

try:
    from dotenv import load_dotenv
    # load_dotenv() never overrides a value that is already set, so the first
    # file that defines a variable wins.
    for _candidate in (".env", os.path.join("idx", ".env"), os.path.join("week6", ".env")):
        load_dotenv(os.path.join(ROOT, _candidate))
except ImportError:
    pass

from query_parser import parse_property_query                           # noqa: E402  Week 2
from db_query import (search_active_listings, format_listing_card,      # noqa: E402  Week 3
                      get_connection, _run as run_sql, _SELECT as LISTING_COLUMNS)
from conversation import get_session, handle_message                    # noqa: E402  Week 4
from market import market_summary, format_market_summary                # noqa: E402  Week 5
from recommender import recommend, build_comp_validation_query, assess_price  # noqa: E402  Week 7
from rag import load_documents, build_index, answer_question            # noqa: E402  Week 8
from rag import get_embedding as rag_embedding                          # noqa: E402


# -------------------------------------------------------- intent routing ---

INTENTS = ("search", "market", "recommend", "knowledge", "email", "mixed")

CLASSIFIER_PROMPT = """You route messages for a California real estate assistant.
Reply with exactly one word from this list:

search    - wants to find or filter homes for sale
market    - asks about prices, trends, days on market, or whether it is a good time to buy in an area
recommend - wants homes similar to one they already saw, or asks if a listing is fairly priced
knowledge - asks what a real estate term or a data field means
email     - wants something drafted or sent by email
mixed     - asks to find homes AND about market conditions in the same message
unknown   - none of the above

Message: {query}
Intent:"""


def call_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """Send one prompt to OpenAI and return the reply text (needs an API key)."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        temperature=0,          # same message -> same label, as far as the model allows
        max_tokens=5,           # the reply is a single word
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def classify_intent(query: str, llm=None) -> str:
    """Ask the model which kind of request this is.

    `llm` is injected so tests can use a stand-in. Anything other than one of
    the known labels becomes "unknown" -- the model's reply is never trusted
    as-is.
    """
    llm = llm or call_llm
    reply = (llm(CLASSIFIER_PROMPT.format(query=query)) or "").strip().lower()
    if not reply:
        return "unknown"
    label = reply.split()[0].strip(".,:;!?\"'")
    return label if label in INTENTS else "unknown"


# ---------------------------------------------------------------- helpers ---

# Slots in the Week 4 session that map to Week 3 search filters.
SEARCH_FILTER_KEYS = ["city", "max_price", "beds", "baths", "sqft",
                      "type", "pool", "has_view", "max_hoa"]


def normalize_query(query: str) -> str:
    """The Week 2 parser only ends a city name at '.', ',' or a stop word, so
    'in Pasadena?' would miss the city. Treat ? and ! like a period."""
    return query.replace("?", ".").replace("!", ".")


def extract_city(query: str, user_id: str) -> str | None:
    """City named in this message, or the one already in the user's session."""
    city = parse_property_query(normalize_query(query))["city"]
    return city or get_session(user_id).city


def to_listing_fields(row: dict) -> dict:
    """Week 3 renames columns (price, beds, sqft); Week 7 scores on the raw
    rets_property names. Add the raw names so a Week 3 row works in Week 7."""
    return dict(row,
                L_SystemPrice=row.get("price"),
                L_Keyword2=row.get("beds"),
                LM_Int2_3=row.get("sqft"))


# Week 7 awards no price points beyond a $300K gap, so homes further away than
# that aren't realistic alternatives for this buyer.
PRICE_BAND = 300_000


def build_candidates_query(city: str, price: int, exclude_id: str, limit: int = 100):
    """Active listings in the same city near the target's price, closest first."""
    sql = f"""
        SELECT {LISTING_COLUMNS}
        FROM rets_property
        WHERE L_Status = 'Active'
          AND L_City = %s
          AND L_ListingID <> %s
          AND L_SystemPrice BETWEEN %s AND %s
        ORDER BY ABS(L_SystemPrice - %s)
        LIMIT %s
    """
    return sql, [city, exclude_id, price - PRICE_BAND, price + PRICE_BAND, price, limit]


def build_data_range_query(today: str):
    """First and last close date in the sold table. Dates after today are ignored:
    the table contains some impossible future close dates (e.g. 2072)."""
    sql = """
        SELECT MIN(CloseDate) AS first_date, MAX(CloseDate) AS last_date
        FROM california_sold
        WHERE CloseDate <> ''
          AND CloseDate <= %s
    """
    return sql, [today]


def build_ppsf_trend_query(city: str, today: str):
    """Monthly average price per sqft for a city's residential sales, oldest first."""
    sql = """
        SELECT LEFT(CloseDate, 7)                                 AS month,
               COUNT(*)                                           AS sales,
               ROUND(AVG(ClosePrice / NULLIF(LivingArea, 0)), 0)  AS avg_ppsf
        FROM california_sold
        WHERE City = %s
          AND PropertyType = 'Residential'
          AND LivingArea > 0
          AND CloseDate <> ''
          AND CloseDate <= %s
        GROUP BY LEFT(CloseDate, 7)
        ORDER BY month
    """
    return sql, [city, today]


def month_is_complete(month: str, first_date: str, last_date: str) -> bool:
    """True if the data runs from the 1st to the last day of this month ('YYYY-MM')."""
    last_day = calendar.monthrange(int(month[:4]), int(month[5:7]))[1]
    return first_date <= f"{month}-01" and last_date >= f"{month}-{last_day:02d}"


def _span(months: list[dict]) -> str:
    if len(months) == 1:
        return months[0]["month"]
    return f"{months[0]['month']} to {months[-1]['month']}"


def price_direction(trend: list[dict], first_date: str | None, last_date: str | None,
                    max_window: int = 3) -> dict:
    """Is the price per sqft higher in the latest complete months than in the ones before?

    - Price per sqft, not average price: when bigger homes happen to sell in later
      months, the average price climbs even though homes aren't getting pricier.
    - Complete months only: the data starts and ends partway through a month, and
      a half month has fewer sales and swings more.
    - Up to 3 months on each side; with fewer complete months, both sides shrink
      to the same length.
    """
    if not first_date or not last_date:
        return {"direction": "not enough data", "change_pct": None,
                "months": [], "data_through": None}
    months = [m for m in trend
              if m.get("month") and m.get("avg_ppsf")
              and month_is_complete(m["month"], first_date, last_date)]
    result = {"months": months, "data_through": last_date}
    window = min(max_window, len(months) // 2)
    if window < 1:
        return dict(result, direction="not enough data", change_pct=None)

    recent, prior = months[-window:], months[-2 * window:-window]
    recent_ppsf = sum(float(m["avg_ppsf"]) for m in recent) / window
    prior_ppsf = sum(float(m["avg_ppsf"]) for m in prior) / window
    change = round((recent_ppsf - prior_ppsf) / prior_ppsf * 100, 1)

    if change >= 2:
        direction = "rising"
    elif change <= -2:
        direction = "falling"
    else:
        direction = "flat"
    return dict(result, direction=direction, change_pct=change,
                recent_ppsf=round(recent_ppsf), prior_ppsf=round(prior_ppsf),
                recent_months=_span(recent), prior_months=_span(prior))


# ------------------------------------------------------------------ agents ---
# Every agent takes (query, user_id) and returns {"agent": ..., "text": ...}.

def property_search_agent(query: str, user_id: str, follow_up: bool = True) -> dict:
    """Search active listings (Weeks 2-4). Remembers results for recommendations.

    follow_up=True  : behave like Week 4 -- ask for the next missing detail.
    follow_up=False : used in mixed requests -- search with whatever is known,
                      since the other half of the answer is already coming.
    """
    step = handle_message(user_id, normalize_query(query))
    session = get_session(user_id)

    if step["action"] == "ask" and (follow_up or not session.city):
        return {"agent": "search", "text": step["message"], "listings": []}

    filters = {k: getattr(session, k) for k in SEARCH_FILTER_KEYS}
    listings = search_active_listings(filters, limit=5)
    session.last_results = listings

    if not listings:
        return {"agent": "search", "listings": [],
                "text": f"No active listings matched in {session.city}. Try a higher budget or fewer filters."}

    cards = "\n".join(format_listing_card(row) for row in listings)
    note = "" if step["action"] == "search" else \
        "\n(Tell me a budget and property type to narrow these down.)"
    return {"agent": "search", "listings": listings,
            "text": f"Homes for sale in {session.city}, lowest price first:\n{cards}{note}"}


def market_stats_agent(query: str, user_id: str) -> dict:
    """City market summary plus whether prices are rising (Week 5)."""
    city = extract_city(query, user_id)
    if not city:
        return {"agent": "market", "text": "Which city's market would you like to know about?"}

    summary = market_summary(city)
    today = date.today().isoformat()
    data_range = (run_sql(*build_data_range_query(today)) or [{}])[0]
    trend = price_direction(run_sql(*build_ppsf_trend_query(city, today)),
                            data_range.get("first_date"), data_range.get("last_date"))
    text = format_market_summary(city, summary)
    if trend["change_pct"] is not None:
        text += (f"\n  Price trend     : {trend['direction']} ({trend['change_pct']:+.1f}% per sqft) -- "
                 f"${trend['recent_ppsf']:,}/sqft in {trend['recent_months']} vs "
                 f"${trend['prior_ppsf']:,}/sqft in {trend['prior_months']} "
                 f"(complete months; data through {trend['data_through']})")
    return {"agent": "market", "text": text, "summary": summary, "trend": trend}


def recommendation_agent(query: str, user_id: str) -> dict:
    """Similar homes to the first result of the last search, plus a price check (Week 7).

    Uses Week 7's structured score only (max 60). The semantic 40 points would
    need an embedding call per candidate listing on every request.
    """
    session = get_session(user_id)
    if not session.last_results:
        return {"agent": "recommend",
                "text": "Search for homes first, then ask me for similar ones."}

    target = to_listing_fields(session.last_results[0])
    price = int(target["L_SystemPrice"] or 0)
    sqft = int(target["LM_Int2_3"] or 0)

    rows = run_sql(*build_candidates_query(target["L_City"], price, target["L_ListingID"]))
    picks = recommend(target, [to_listing_fields(r) for r in rows], top_k=3)

    comp = (run_sql(*build_comp_validation_query(target["L_City"], sqft)) or [{}])[0]
    check = assess_price(price, sqft, comp.get("avg_ppsf"), comp.get("comp_count") or 0)

    lines = [f"Homes similar to {target.get('L_Address')}, {target.get('L_City')} (${price:,}):"]
    if picks:
        lines += [f"{format_listing_card(home)}\n   match score {score:.0f}/60"
                  for home, score in picks]
    else:
        lines.append("  No similar active listings nearby in price.")
    if check["comp_price"]:
        lines.append(f"Price check: {check['verdict']} -- {check['comp_count']} similar-sized "
                     f"sales suggest about ${check['comp_price']:,} ({check['delta_pct']:+.1f}%).")
    else:
        lines.append(f"Price check: {check['verdict']}.")
    return {"agent": "recommend", "text": "\n".join(lines),
            "recommendations": picks, "price_check": check}


_rag_index = None


def get_rag_index() -> list[dict]:
    """Build the Week 8 knowledge index once, on first use (15 embedding calls)."""
    global _rag_index
    if _rag_index is None:
        _rag_index = build_index(load_documents(), rag_embedding)
    return _rag_index


def rag_agent(query: str, user_id: str) -> dict:
    """Answer a definitional question from the knowledge documents (Week 8)."""
    result = answer_question(query, get_rag_index())
    sources = ", ".join(result["sources"])
    return {"agent": "knowledge", "text": f"{result['answer']}\n(Sources: {sources})",
            "sources": result["sources"]}


def email_draft_agent(query: str, user_id: str) -> dict:
    """Registered now so routing is complete; drafting with approval is Week 11."""
    return {"agent": "email",
            "text": "Email drafting isn't available yet. I can search homes, "
                    "show market stats, recommend similar listings, or explain terms."}


AGENTS = {
    "search": property_search_agent,
    "market": market_stats_agent,
    "recommend": recommendation_agent,
    "knowledge": rag_agent,
    "email": email_draft_agent,
}

FALLBACK = ("I'm not sure how to help with that. Try asking about homes for sale, "
            "market trends, similar listings, or what a real estate term means.")


# ------------------------------------------------------------ entry point ---

_database_ready = False
_database_ready_lock = threading.Lock()


def prepare_database() -> None:
    """Connect to MySQL once from the calling thread, before any worker threads start.

    The MySQL C client sets up global library state during the first connection
    in a process, and that setup is not thread-safe. If two threads make their
    first connection at the same moment, one can use the half-initialized state
    and crash the whole Python process. One connection up front does the setup
    safely; afterwards threads can connect freely.
    """
    global _database_ready
    with _database_ready_lock:
        if _database_ready:
            return
        try:
            get_connection().close()
        except Exception:
            pass            # the library is initialized even if the connect fails;
                            # the agents report connection problems themselves
        _database_ready = True


def run_agent(name: str, agent, query: str, user_id: str, **kwargs) -> dict:
    """Run one agent; if it fails, return an apology instead of crashing the chat."""
    try:
        return agent(query, user_id, **kwargs)
    except Exception as exc:
        return {"agent": name, "error": repr(exc),
                "text": f"Sorry, the {name} agent ran into a problem. Please try again."}


def orchestrate(query: str, user_id: str, llm=None, agents: dict | None = None) -> dict:
    """The single entry point: classify the message, route it, return one answer.

    Returns {"intent", "agents" (which ran), "text" (the reply), "parts" (each agent's output)}.
    """
    using_real_agents = agents is None
    agents = agents or AGENTS
    intent = classify_intent(query, llm)

    if intent == "mixed":
        # Two setup steps aren't safe to run from both threads at once, so do them first:
        # - the session: a new user could otherwise get two, and the search
        #   results would be saved on the one that gets thrown away
        # - the MySQL client library (see prepare_database)
        get_session(user_id)
        if using_real_agents:
            prepare_database()
        # Search and market stats don't depend on each other, so run them at the same time.
        with ThreadPoolExecutor(max_workers=2) as pool:
            search = pool.submit(run_agent, "search", agents["search"], query, user_id,
                                 follow_up=False)
            market = pool.submit(run_agent, "market", agents["market"], query, user_id)
            parts = [search.result(), market.result()]
        return {"intent": "mixed", "agents": ["search", "market"],
                "text": "\n\n".join(p["text"] for p in parts), "parts": parts}

    if intent in agents:
        part = run_agent(intent, agents[intent], query, user_id)
        return {"intent": intent, "agents": [intent], "text": part["text"], "parts": [part]}

    return {"intent": "unknown", "agents": [], "text": FALLBACK, "parts": []}


if __name__ == "__main__":
    example = "Find me affordable homes in Pasadena and tell me whether prices are rising."
    print("Agent registry:")
    for name, agent in AGENTS.items():
        print(f"  {name:10s} -> {agent.__name__}")
    print(f"\nCity found in {example!r}: {extract_city(example, 'self-check')}")
    print("\nClassifier prompt sent to the model (no API call made):\n")
    print(CLASSIFIER_PROMPT.format(query=example))
