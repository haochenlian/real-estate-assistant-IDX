#!/opt/anaconda3/bin/python3
"""
WhatsApp bridge (Week 10).

OpenClaw receives the WhatsApp message, and its `idx-real-estate` skill runs
this script once per message. The script hands the message to the Week 9
orchestrator and prints a reply formatted for WhatsApp. The agent sends that
reply back unchanged.

    WhatsApp -> OpenClaw -> whatsapp_bridge.py -> orchestrate() -> agents -> MySQL
                                  |
                          stdout = the WhatsApp reply

Every message starts a new Python process, so the Week 4 session (city,
budget, last search results) would be forgotten between messages. This script
saves each user's session to a JSON file after every reply and loads it before
the next one, so "show me similar homes" still knows what was searched.

Usage:
    whatsapp_bridge.py --user <id> "<message>"
    IDX_MESSAGE="<message>" whatsapp_bridge.py --user <id>

Passing the message in IDX_MESSAGE keeps it out of the shell command, so text
like `"; rm -rf ~` stays a message instead of becoming a command.

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
from dataclasses import asdict, fields
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "week9"))
import orchestrator                                      # noqa: E402  Week 9 (puts weeks 2-8 on the path)
from conversation import UserSession, sessions           # noqa: E402  Week 4

# Outside the repo on purpose: session files hold the sender's id and search history.
SESSION_DIR = os.path.expanduser(os.getenv("IDX_SESSION_DIR", "~/.idx-assistant/sessions"))

GREETING = ("Hi! Ask me about homes for sale, market trends, similar listings, "
            "or what a real estate term means.")
APOLOGY = "Sorry, I hit an issue. Please try again."

# Week 9 adds this sentence when a mixed request searched without a budget or type.
NARROW_HINT = "Tell me a budget and property type"


# ---------------------------------------------------------- session storage ---

def session_path(user_id: str) -> str:
    """One file per user. Anything but letters, digits, _ and - becomes _, so an
    id can never point outside the session folder."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id) or "anonymous"
    return os.path.join(SESSION_DIR, f"{safe}.json")


def _to_json(value):
    """MySQL returns Decimal for some numbers (e.g. baths); JSON has no Decimal."""
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def load_session(user_id: str) -> None:
    """Put the user's saved session back into Week 4's in-memory store."""
    try:
        with open(session_path(user_id), encoding="utf-8") as fh:
            saved = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    known = {f.name for f in fields(UserSession)}
    sessions[user_id] = UserSession(**{k: v for k, v in saved.items() if k in known})


def save_session(user_id: str) -> None:
    """Write the user's session to disk, readable only by this Mac user, replacing
    the old file in one step so a crash mid-write can't leave a half-written file."""
    session = sessions.get(user_id)
    if session is None:
        return
    os.makedirs(SESSION_DIR, mode=0o700, exist_ok=True)
    path = session_path(user_id)
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
        json.dump(asdict(session), fh, default=_to_json)
    os.replace(tmp, path)


# --------------------------------------------------------- WhatsApp formatting ---
# WhatsApp renders *bold* and _italic_. Each formatter takes (part, message, user_id)
# and turns one agent's output from Week 9 into chat-friendly text.

def money(value) -> str:
    return f"${float(value):,.0f}" if value not in (None, "") else "?"


def format_listing(row: dict, score: float | None = None) -> str:
    baths = row.get("baths")
    baths = f"{float(baths):g}" if baths not in (None, "") else "?"
    card = (f"🏠 *{row.get('L_Address') or 'Address unavailable'}, {row.get('L_City') or ''}*\n"
            f"💰 {money(row.get('price'))} | 🛏 {row.get('beds', '?')}bd/{baths}ba | "
            f"📐 {row.get('sqft', '?')} sqft\n"
            f"📅 {row.get('DaysOnMarket', '?')} days on market")
    if score is not None:
        card += f" | ⭐ match {score:.0f}/60"
    return card


def format_search(part: dict, message: str, user_id: str) -> str:
    listings = part.get("listings")
    if not listings:
        return part["text"]                    # a follow-up question or "no matches"
    city = listings[0].get("L_City", "")
    lines = [f"*Homes for sale in {city}* (lowest price first)"]
    lines += [format_listing(row) for row in listings]
    if NARROW_HINT in part["text"]:
        lines.append(f"_{NARROW_HINT} to narrow these down._")
    return "\n\n".join(lines)


TREND_HEADLINES = {
    "rising": "📈 *{city} prices are rising*",
    "falling": "📉 *{city} prices are falling*",
    "flat": "➖ *{city} prices are roughly flat*",
}


def month_label(month: str, with_year: bool) -> str:
    name = calendar.month_abbr[int(month[5:7])]
    return f"{name} {month[:4]}" if with_year else name


def format_trend(city: str, trend: dict) -> list[str]:
    """Answer "are prices rising?" first, then show the monthly numbers behind it."""
    through = trend.get("data_through")
    if trend.get("change_pct") is None:
        note = f" Data through {through}." if through else ""
        return [f"_Not enough complete months to tell a price trend.{note}_"]
    months = trend.get("months") or []
    one_year = len({m["month"][:4] for m in months}) == 1
    year = f" ({months[0]['month'][:4]})" if one_year else ""
    series = " · ".join(f"{month_label(m['month'], not one_year)} {money(m['avg_ppsf'])}"
                        for m in months)
    return [
        f"{TREND_HEADLINES[trend['direction']].format(city=city)} "
        f"({trend['change_pct']:+.1f}% per sqft)",
        f"{money(trend['recent_ppsf'])}/sqft in {trend['recent_months']} vs "
        f"{money(trend['prior_ppsf'])}/sqft in {trend['prior_months']}",
        f"Monthly $/sqft{year}: {series}",
        f"_Complete months only; data through {through}._",
    ]


def format_market(part: dict, message: str, user_id: str) -> str:
    summary, trend = part.get("summary"), part.get("trend") or {}
    if not summary or not summary.get("sold_count"):
        return part["text"]                    # "which city?" or "no sold data"
    city = orchestrator.extract_city(message, user_id)
    ratio = float(summary["list_to_close_pct"])
    ratio_note = "below asking, room to negotiate" if ratio < 100 else "at or above asking, competitive"
    lines = format_trend(city, trend) + [
        "",
        f"📊 *{city} market* (residential sales)",
        f"• Sales analyzed: {summary['sold_count']:,}",
        f"• Avg close price: {money(summary['avg_close_price'])}",
        f"• Price per sqft: {money(summary['avg_price_per_sqft'])}",
        f"• Avg days on market: {float(summary['avg_dom']):g}",
        f"• List-to-close: {ratio:g}% ({ratio_note})",
    ]
    return "\n".join(lines)


def format_recommend(part: dict, message: str, user_id: str) -> str:
    picks, check = part.get("recommendations"), part.get("price_check")
    if picks is None:
        return part["text"]                    # "search for homes first"
    target = sessions[user_id].last_results[0]
    lines = [f"✨ *Homes similar to {target.get('L_Address')}* ({money(target.get('price'))})"]
    lines += [format_listing(home, score) for home, score in picks] or \
             ["No similar active listings nearby in price."]
    if check and check.get("comp_price"):
        lines.append(f"💡 *Price check:* {check['verdict']}. {check['comp_count']} similar-sized "
                     f"sales suggest about {money(check['comp_price'])} ({check['delta_pct']:+.1f}%).")
    elif check:
        lines.append(f"💡 *Price check:* {check['verdict']}.")
    return "\n\n".join(lines)


def format_knowledge(part: dict, message: str, user_id: str) -> str:
    answer = part["text"].split("\n(Sources:")[0]
    sources = part.get("sources") or []
    return f"{answer}\n\n_Sources: {', '.join(sources)}_" if sources else answer


FORMATTERS = {
    "search": format_search,
    "market": format_market,
    "recommend": format_recommend,
    "knowledge": format_knowledge,
}


def format_for_whatsapp(result: dict, message: str, user_id: str) -> str:
    """Format each agent's part; parts without a formatter (email, errors) keep their text."""
    if not result["parts"]:
        return result["text"]                  # unknown intent -> fallback message
    replies = []
    for part in result["parts"]:
        formatter = FORMATTERS.get(part.get("agent"))
        if part.get("error") or formatter is None:
            replies.append(part["text"])
        else:
            replies.append(formatter(part, message, user_id))
    return "\n\n".join(replies)


# ------------------------------------------------------------------ entry ---

def reply_to(message: str, user_id: str, orchestrate=None) -> str:
    """Answer one WhatsApp message. Never raises: any failure becomes an apology."""
    orchestrate = orchestrate or orchestrator.orchestrate
    message = (message or "").strip()
    if not message:
        return GREETING
    try:
        load_session(user_id)
        result = orchestrate(message, user_id)
        reply = format_for_whatsapp(result, message, user_id)
    except Exception as exc:
        print(f"whatsapp_bridge: {exc!r}", file=sys.stderr)
        return APOLOGY
    try:
        save_session(user_id)
    except OSError as exc:                     # the answer is still good; memory just didn't save
        print(f"whatsapp_bridge: could not save session: {exc!r}", file=sys.stderr)
    return reply


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Answer one WhatsApp message.")
    parser.add_argument("--user", default="whatsapp",
                        help="stable id for the sender; each id gets its own saved session")
    parser.add_argument("message", nargs="*", help="the message (or set IDX_MESSAGE)")
    args = parser.parse_args(argv)
    message = os.getenv("IDX_MESSAGE") or " ".join(args.message)
    print(reply_to(message, args.user))


if __name__ == "__main__":
    main()
