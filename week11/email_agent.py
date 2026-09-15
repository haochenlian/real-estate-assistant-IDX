"""
Email agent with a human-approval gate (Week 11).

The assistant drafts emails, but it never sends one on its own. Every email is a
two-step exchange:

    user:  "Email these listings to amy@example.com: I like the second one"
    agent: 📧 Email draft (not sent yet) ... Reply *send* to send it, or *cancel* to discard it.
    user:  "send"
    agent: ✅ Sent "Howard shared 5 homes in Pasadena with you" to amy@example.com.

Drafting and sending are separate functions. `send_email()` refuses any draft
that isn't marked approved, and a draft is only marked approved when the user's
whole reply is one of a few exact phrases ("send", "send it", "yes send", ...).
"Please don't send" is a cancellation, not an approval. Drafts expire after an
hour, so an old "send" can't fire a stale email.

The emails are written for the person receiving them, who has never used the
assistant: they say who sent them and why, carry the sender's own note, use plain
words instead of data jargon, show a photo, description, listing agent and map
link for each home, and say how old the data is.

Email kinds:
    listings         the homes from the user's last search            (rets_property)
    market report    city summary and price trend                      (california_sold)
    recommendations  homes similar to the first search result + comps  (both tables)

Only the SMTP send needs credentials: EMAIL_USER and EMAIL_PASSWORD (a Gmail app
password) in .env. They're read at send time and never printed or logged.
EMAIL_SENDER_NAME (optional, default "Howard") is the name the emails use.

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import calendar
import contextlib
import html
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
from urllib.parse import quote_plus

HERE = os.path.dirname(os.path.abspath(__file__))
# The Week 9 orchestrator is imported inside the functions that need it, because it
# imports this module too.
sys.path.insert(0, os.path.join(HERE, "..", "week9"))

# Outside the repo on purpose: drafts hold recipients' addresses.
DRAFT_DIR = os.path.expanduser(os.getenv("IDX_DRAFT_DIR", "~/.idx-assistant/drafts"))
DRAFT_TTL = timedelta(hours=1)
MAX_ROWS = 50                   # handbook rule: never return more than 50 rows at once

APPROVE = {"send", "send it", "yes send", "yes send it", "approve", "approved", "confirm"}
CANCEL = {"cancel", "cancel it", "discard", "discard it", "dont send", "do not send", "stop"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NOTE_LIMIT = 500


class MissingCredentials(RuntimeError):
    """EMAIL_USER or EMAIL_PASSWORD isn't set."""


def sender_name() -> str:
    return os.getenv("EMAIL_SENDER_NAME") or "Howard"


# ------------------------------------------------------------ reply words ---

def normalize_reply(text: str) -> str:
    """'Yes, send it!' -> 'yes send it'; "Don't send." -> 'dont send'."""
    return " ".join(re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).split())


def is_reply(text: str) -> bool:
    """True only if the whole message is an approval or a cancellation."""
    return normalize_reply(text) in APPROVE | CANCEL


SELECT_WORDS = {"only", "just", "keep"}
SELECT_FILLER = {"send", "the", "home", "homes", "listing", "listings", "number", "numbers",
                 "and", "one", "ones"}


def parse_selection(text: str) -> list[int] | None:
    """'only 2 and 4' / 'just #2, #4' / 'keep 1' -> [2, 4] / [2, 4] / [1]. Anything with
    other words ('only homes in Irvine', 'just 2 bedrooms') is not a selection -> None."""
    tokens = re.findall(r"[a-z]+|\d+", (text or "").lower())
    if len(tokens) < 2 or tokens[0] not in SELECT_WORDS:
        return None
    numbers = [int(t) for t in tokens[1:] if t.isdigit()]
    if not numbers or any(t not in SELECT_FILLER for t in tokens[1:] if not t.isdigit()):
        return None
    return list(dict.fromkeys(numbers))          # keep the order given, drop repeats


NOTE_RE = re.compile(r"^\s*note\s*[:：]\s*(.*)$", re.I | re.S)
NO_NOTE = {"", "none", "remove", "delete", "no note"}


def parse_note_edit(text: str) -> tuple[bool, str | None]:
    """'note: take a look at #2' -> (True, 'take a look at #2'); 'note: none' -> (True, None),
    which removes the note; anything else -> (False, None)."""
    match = NOTE_RE.match(text or "")
    if not match:
        return False, None
    note = " ".join(match.group(1).split())[:NOTE_LIMIT]
    return True, (None if note.lower() in NO_NOTE else note)


def is_draft_command(text: str) -> bool:
    """send / cancel, or an edit to the waiting draft. Week 9 handles these without the model."""
    return is_reply(text) or parse_selection(text) is not None or parse_note_edit(text)[0]


# ----------------------------------------------------------- draft storage ---

def draft_path(user_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id) or "anonymous"
    return os.path.join(DRAFT_DIR, f"{safe}.json")


def _json_value(value):
    """MySQL hands back Decimal and datetime values; store them as plain JSON."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def save_draft(user_id: str, draft: dict) -> None:
    """One pending draft per user, readable only by this Mac user, written in one step."""
    os.makedirs(DRAFT_DIR, mode=0o700, exist_ok=True)
    path = draft_path(user_id)
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
        json.dump(draft, fh, default=_json_value)
    os.replace(tmp, path)


def clear_draft(user_id: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.remove(draft_path(user_id))


def load_draft(user_id: str, now: datetime | None = None) -> dict | None:
    """The user's pending draft, or None if there isn't one or it has expired."""
    try:
        with open(draft_path(user_id), encoding="utf-8") as fh:
            draft = json.load(fh)
        created = datetime.fromisoformat(draft["created_at"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        return None
    if (now or datetime.now(timezone.utc)) - created > DRAFT_TTL:
        clear_draft(user_id)
        return None
    return draft


def has_pending_draft(user_id: str) -> bool:
    return load_draft(user_id) is not None


# ------------------------------------------------------ plain-English pieces ---

def _money(value) -> str:
    return f"${float(value):,.0f}" if value not in (None, "") else "price not listed"


def _plural(n, word: str) -> str:
    return f"{n:g} {word}" + ("" if float(n) == 1 else "s")


def long_date(value) -> str | None:
    """'2026-06-15' or a datetime -> 'June 15, 2026'."""
    if not value:
        return None
    day = value if isinstance(value, (date, datetime)) else date.fromisoformat(str(value)[:10])
    return f"{calendar.month_name[day.month]} {day.day}, {day.year}"


def month_span(label: str) -> str:
    """'2026-04 to 2026-05' -> 'April–May 2026'; '2025-12 to 2026-01' -> 'December 2025–January 2026'."""
    parts = [p.strip() for p in label.split(" to ")]
    (y1, m1), (y2, m2) = [(int(p[:4]), int(p[5:7])) for p in (parts[0], parts[-1])]
    if (y1, m1) == (y2, m2):
        return f"{calendar.month_name[m1]} {y1}"
    if y1 == y2:
        return f"{calendar.month_name[m1]}–{calendar.month_name[m2]} {y1}"
    return f"{calendar.month_name[m1]} {y1}–{calendar.month_name[m2]} {y2}"


def home_facts(row: dict) -> str:
    """'Studio · 1 bath · 450 sq ft · on the market 29 days' — no MLS jargon."""
    bits = []
    beds, baths, sqft, dom = (row.get(k) for k in ("beds", "baths", "sqft", "DaysOnMarket"))
    if beds not in (None, ""):
        bits.append("Studio" if float(beds) == 0 else _plural(float(beds), "bed"))
    if baths not in (None, ""):
        bits.append(_plural(float(baths), "bath"))
    if sqft not in (None, "", 0):
        bits.append(f"{int(sqft):,} sq ft")
    if dom not in (None, ""):
        bits.append(f"on the market {_plural(int(dom), 'day')}")
    return " · ".join(bits)


def first_photo(row: dict) -> str | None:
    """The first listing photo, only if it's an https link."""
    photos = row.get("L_Photos")
    if isinstance(photos, str):
        try:
            photos = json.loads(photos)
        except json.JSONDecodeError:
            return None
    if isinstance(photos, list) and photos and str(photos[0]).startswith("https://"):
        return str(photos[0])
    return None


def short_description(text, limit: int = 160) -> str | None:
    text = " ".join(str(text or "").split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def agent_line(row: dict) -> str | None:
    name = row.get("ListAgentFullName") or \
        f"{row.get('LA1_UserFirstName') or ''} {row.get('LA1_UserLastName') or ''}".strip()
    if not name:
        return None
    office = row.get("LO1_OrganizationName")
    contact = [c for c in (row.get("ListAgentEmail"),
                           row.get("ListAgentDirectPhone") or row.get("ListAgentOfficePhone")) if c]
    line = f"Listing agent: {name}" + (f" ({office})" if office else "")
    return line + (" · " + " · ".join(contact) if contact else "")


def maps_link(row: dict) -> str:
    place = ", ".join(str(p) for p in (row.get("L_Address"), row.get("L_City"),
                                        f"CA {row.get('L_Zip') or ''}".strip()) if p)
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(place)


def _address(row: dict) -> str:
    return f"{row.get('L_Address') or 'Address unavailable'}, {row.get('L_City') or ''}".rstrip(", ")


# --------------------------------------------------------------- templates ---
# Each returns {"subject", "text", "html"}: a plain-text part for any mail client and
# an HTML part for ones that render it. Every value placed in the HTML is escaped.

def _home_card(number: int, row: dict) -> tuple[str, str]:
    headline = f"{number}. {_address(row)} — {_money(row.get('price'))}"
    facts, desc, agent, link = home_facts(row), short_description(row.get("L_Remarks")), \
        agent_line(row), maps_link(row)
    text = [headline, f"   {facts}"] + ([f'   "{desc}"'] if desc else []) + \
           ([f"   {agent}"] if agent else []) + [f"   Map: {link}"]
    markup = ['<div style="margin: 0 0 28px;">']
    photo = first_photo(row)
    if photo:
        markup.append(f'<img src="{html.escape(photo, quote=True)}" alt="{html.escape(_address(row))}" '
                      'width="480" style="max-width: 100%; border-radius: 6px; display: block;">')
    markup.append(f'<p style="margin: 8px 0 4px;"><strong>{html.escape(headline)}</strong><br>'
                  f"{html.escape(facts)}</p>")
    if desc:
        markup.append(f'<p style="margin: 4px 0; color: #555;"><em>{html.escape(desc)}</em></p>')
    if agent:
        markup.append(f'<p style="margin: 4px 0;">{html.escape(agent)}</p>')
    markup.append(f'<p style="margin: 4px 0;"><a href="{html.escape(link, quote=True)}">'
                  "📍 View on Google Maps</a></p></div>")
    return "\n".join(text), "".join(markup)


def _letter(subject: str, opening: str, note: str | None, body_text: str, body_html: str,
            closing: list[str]) -> dict:
    """Wrap the body in a short letter: who is writing and why, their note, then the fine print."""
    name = sender_name()
    signoff = f"Sent by {name}'s real estate assistant after {name} approved this email."
    note_line = f"{name}'s note: \"{note}\"" if note else None
    text = ["Hi,", "", opening] + ([note_line] if note_line else []) + ["", body_text, ""] + \
           closing + ["", signoff]
    small = 'style="color: #777; font-size: 12px;"'
    markup = ('<html><body style="font-family: Arial, sans-serif; color: #222; max-width: 560px;">'
              f"<p>Hi,</p><p>{html.escape(opening)}</p>"
              + (f'<p style="background: #f4f4f4; padding: 10px; border-radius: 6px;">'
                 f"{html.escape(note_line)}</p>" if note_line else "")
              + body_html
              + "".join(f"<p {small}>{html.escape(line)}</p>" for line in closing + [signoff])
              + "</body></html>")
    return {"subject": subject, "text": "\n".join(text), "html": markup}


def _freshness(as_of: str | None) -> str:
    when = f"as of {as_of}" if as_of else "from the listing database"
    return (f"Listing details are {when} and may have changed. "
            "Contact the listing agent to confirm a home is still available.")


def listings_email(homes: list[dict], note: str | None = None, as_of: str | None = None) -> dict:
    homes = homes[:MAX_ROWS]
    city = homes[0].get("L_City", "") if homes else ""
    count = f"{len(homes)} home{'s' if len(homes) != 1 else ''}"
    cards = [_home_card(i, h) for i, h in enumerate(homes, 1)]
    return _letter(f"{sender_name()} shared {count} in {city} with you",
                   f"{sender_name()} asked me to send you these homes for sale in {city}.",
                   note, "\n\n".join(t for t, _ in cards), "".join(m for _, m in cards),
                   [_freshness(as_of)])


def price_check_sentence(target: dict, check: dict | None) -> str:
    """Week 7's comp check in plain words."""
    if not check or not check.get("comp_price"):
        return "There weren't enough similar sales nearby to check whether it's fairly priced."
    delta = float(check["delta_pct"])
    worth = (f"{check['comp_count']} similar-sized homes that sold in {target.get('L_City')} "
             f"suggest it's worth about {_money(check['comp_price'])}")
    if abs(delta) < 5:
        return f"Is it fairly priced? {worth}, so its {_money(target.get('price'))} asking price is in line with the market."
    side = "below" if delta < 0 else "above"
    return f"Is it fairly priced? {worth}. At {_money(target.get('price'))}, it's {abs(delta):.0f}% {side} that."


def recommendations_email(target: dict, picks: list[tuple], check: dict | None,
                          note: str | None = None, as_of: str | None = None) -> dict:
    homes = [home for home, _score in picks[:MAX_ROWS]]
    cards = [_home_card(i, h) for i, h in enumerate(homes, 1)]
    price_line = price_check_sentence(target, check)
    body_text = "\n\n".join(t for t, _ in cards) or "No similar homes are for sale nearby at a similar price."
    body_html = "".join(m for _, m in cards) or f"<p>{html.escape(body_text)}</p>"
    count = f"{len(homes)} home{'s' if len(homes) != 1 else ''}"
    return _letter(f"{sender_name()} found {count} similar to {target.get('L_Address')}",
                   f"{sender_name()} liked {_address(target)} ({_money(target.get('price'))}) "
                   "and asked me to send you similar homes for sale.",
                   note, f"{price_line}\n\n{body_text}",
                   f"<p>{html.escape(price_line)}</p>{body_html}", [_freshness(as_of)])


def market_report_email(city: str, summary: dict, trend: dict, note: str | None = None) -> dict:
    """The weekly market report template, filled from california_sold (via Week 5 and Week 9)."""
    through = long_date(trend.get("data_through"))
    subject = f"{city} housing market report" + (f" (data through {through})" if through else "")
    if trend.get("change_pct") is not None:
        direction = {"rising": "rising", "falling": "falling"}.get(trend["direction"], "roughly flat")
        headline = (f"Prices are {direction}: homes sold for about {_money(trend['recent_ppsf'])} per sq ft "
                    f"in {month_span(trend['recent_months'])}, compared with {_money(trend['prior_ppsf'])} "
                    f"in {month_span(trend['prior_months'])} ({trend['change_pct']:+.1f}%).")
    else:
        headline = "There isn't enough recent data yet to say whether prices are rising or falling."
    ratio = float(summary["list_to_close_pct"])
    if ratio >= 100.5:
        asking = f"Homes sold for about {ratio - 100:.0f}% above asking price, so expect competition."
    elif ratio <= 99.5:
        asking = f"Homes sold for about {100 - ratio:.0f}% below asking price, so buyers have room to negotiate."
    else:
        asking = "Homes sold at about their asking price."
    facts = [
        f"{summary['sold_count']:,} homes sold in the period covered.",
        f"The average sale price was {_money(summary['avg_close_price'])}.",
        f"Homes sold for about {_money(summary['avg_price_per_sqft'])} per sq ft.",
        f"A typical home sold in about {_plural(round(float(summary['avg_dom'])), 'day')}.",
        asking,
    ]
    monthly = [(f"{calendar.month_name[int(m['month'][5:7])]} {m['month'][:4]}", _money(m["avg_ppsf"]))
               for m in trend.get("months") or []]
    closing = [f"Based on residential home sales recorded through {through or 'the latest data'}. "
               "The trend compares full calendar months only."]

    body_text = "\n".join([headline, ""] + [f"- {f}" for f in facts] +
                          (["", "Price per sq ft by month:"] + [f"  {m}: {v}" for m, v in monthly]
                           if monthly else []))
    cell = 'style="padding: 4px 12px; border-bottom: 1px solid #eee;"'
    body_html = (f"<p><strong>{html.escape(headline)}</strong></p>"
                 "<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>"
                 + ("<p><strong>Price per sq ft by month</strong></p><table>" +
                    "".join(f"<tr><td {cell}>{html.escape(m)}</td><td {cell}>{html.escape(v)}</td></tr>"
                            for m, v in monthly) + "</table>" if monthly else ""))
    return _letter(subject, f"{sender_name()} asked me to send you this snapshot of the {city} housing market.",
                   note, body_text, body_html, closing)


# ------------------------------------------------------------------ drafting ---

def find_recipient(text: str) -> tuple[str | None, str | None]:
    """(address, None) for exactly one address in the message, else (None, what to ask)."""
    found = sorted(set(EMAIL_RE.findall(text or "")))
    if not found:
        return None, ("Who should I send it to? Ask again with their email address, "
                      "e.g. *email these listings to amy@example.com*.")
    if len(found) > 1:
        return None, "I can only email one person at a time. Ask again with a single address."
    return found[0], None


def find_note(text: str, address: str | None) -> str | None:
    """The sender's own words: anything in quotes, or anything after a colon or dash that
    follows the address. 'Email these to amy@x.com: I like the second one' -> 'I like the second one'."""
    quoted = re.search(r'["“](.+?)["”]', text or "")
    if quoted:
        note = quoted.group(1)
    elif address and address in text:
        after = re.match(r"\s*[:—–-]\s*(.+)", text.split(address, 1)[1], re.S)
        note = after.group(1) if after else None
    else:
        note = None
    note = " ".join((note or "").split())
    return note[:NOTE_LIMIT] or None


def email_kind(request: str) -> str:
    lower = request.lower()
    if any(word in lower for word in ("report", "market", "trend")):
        return "market"
    if "similar" in lower or "recommend" in lower:
        return "recommendations"
    return "listings"


DETAIL_COLUMNS = ("L_ListingID, L_Zip, L_Photos, L_Remarks, ListAgentFullName, ListAgentEmail, "
                  "ListAgentDirectPhone, ListAgentOfficePhone, LO1_OrganizationName")


def build_details_query(listing_ids: list[str]):
    """Photos, description and agent contact for up to 50 listings (Week 3 rows don't carry them)."""
    ids = list(listing_ids)[:MAX_ROWS]
    marks = ", ".join(["%s"] * len(ids))
    sql = f"SELECT {DETAIL_COLUMNS} FROM rets_property WHERE L_ListingID IN ({marks}) LIMIT %s"
    return sql, ids + [MAX_ROWS]


def build_as_of_query(today: str):
    """When the listing data was last updated. Future timestamps are ignored."""
    return ("SELECT MAX(ModificationTimestamp) AS as_of FROM rets_property "
            "WHERE ModificationTimestamp <= %s"), [today]


def with_details(run_sql, homes: list[dict]) -> list[dict]:
    """Add photos, description and agent contact to each home. Without them the email still works."""
    ids = [h.get("L_ListingID") for h in homes if h.get("L_ListingID")]
    if not ids:
        return homes
    try:
        extra = {row["L_ListingID"]: row for row in run_sql(*build_details_query(ids))}
    except Exception as exc:
        print(f"email_agent: listing details unavailable ({exc.__class__.__name__})", file=sys.stderr)
        return homes
    return [dict(extra.get(h.get("L_ListingID"), {}), **h) for h in homes]


def listing_as_of(run_sql) -> str | None:
    try:
        rows = run_sql(*build_as_of_query(date.today().isoformat()))
    except Exception:
        return None
    return long_date(rows[0]["as_of"]) if rows and rows[0].get("as_of") else None


def build_draft(query: str, user_id: str) -> tuple[dict | None, str | None]:
    """(draft, None) or (None, a message explaining what's missing). Never sends."""
    import orchestrator                        # noqa: E402  Week 9 (imports this module too)

    to, problem = find_recipient(query)
    if problem:
        return None, problem
    note = find_note(query, to)
    request = query.replace(note, " ") if note else query    # the note mustn't change the email kind
    kind = email_kind(request)

    if kind == "market":
        market = orchestrator.market_stats_agent(request, user_id)
        if not (market.get("summary") or {}).get("sold_count"):
            return None, market["text"]                  # "which city?" or "no sold data"
        source = {"city": orchestrator.extract_city(request, user_id),
                  "summary": market["summary"], "trend": market["trend"]}
    elif kind == "recommendations":
        rec = orchestrator.recommendation_agent(request, user_id)
        if rec.get("recommendations") is None:
            return None, rec["text"]                     # "search for homes first"
        target = orchestrator.get_session(user_id).last_results[0]
        homes = with_details(orchestrator.run_sql, [target] + [h for h, _ in rec["recommendations"]])
        source = {"target": homes[0], "check": rec.get("price_check"),
                  "picks": [[home, score] for home, (_, score) in zip(homes[1:], rec["recommendations"])],
                  "as_of": listing_as_of(orchestrator.run_sql)}
    else:
        homes = orchestrator.get_session(user_id).last_results
        if not homes:
            return None, "Search for homes first, then ask me to email them."
        source = {"homes": with_details(orchestrator.run_sql, homes[:MAX_ROWS]),
                  "as_of": listing_as_of(orchestrator.run_sql)}
    source["note"] = note
    return new_draft(to, kind, source), None


def render(kind: str, source: dict) -> dict:
    """Turn a draft's saved data into subject, text and HTML. Edits change the data, then re-render."""
    if kind == "market":
        return market_report_email(source["city"], source["summary"], source["trend"], source.get("note"))
    if kind == "recommendations":
        return recommendations_email(source["target"], [tuple(p) for p in source["picks"]],
                                     source.get("check"), source.get("note"), source.get("as_of"))
    return listings_email(source["homes"], source.get("note"), source.get("as_of"))


def new_draft(to: str, kind: str, source: dict) -> dict:
    """A draft waiting for approval. The source data is kept so the user can edit it."""
    return dict(render(kind, source), to=to, kind=kind, source=source,
                status="pending_approval", created_at=datetime.now(timezone.utc).isoformat())


def preview(draft: dict, updated: bool = False) -> str:
    """What the user sees in chat before anything is sent. Every home is listed on one line
    by number, however many there are, so the user can pick with "only 2 and 4"."""
    source = draft.get("source") or {}
    if draft.get("kind") in ("listings", "recommendations"):
        homes = source.get("homes") if draft["kind"] == "listings" else \
            [home for home, _score in source.get("picks", [])]
        sections = []
        if source.get("note"):
            sections.append(f"{sender_name()}'s note: \"{source['note']}\"")
        if draft["kind"] == "recommendations":
            sections.append(price_check_sentence(source["target"], source.get("check")))
        sections.append("\n".join(f"{i}. {_address(h)} — {_money(h.get('price'))} · {home_facts(h)}"
                                  for i, h in enumerate(homes or [], 1)))
        sections.append("_In the email, each home also has a photo, description, listing agent and map link._")
        body = "\n\n".join(s for s in sections if s)
    else:
        body = draft["text"]
        if len(body) > 900:
            body = body[:900].rstrip() + "\n…"
    if draft.get("kind") in ("listings", "recommendations"):
        tips = ("Reply *send* to send it, *cancel* to discard it, *only 1 and 3* to keep just "
                "those homes, or *note: …* to change your note.")
    else:
        tips = "Reply *send* to send it, *cancel* to discard it, or *note: …* to change your note."
    return (("✏️ *Draft updated.*\n" if updated else "") + "📧 *Email draft (not sent yet)*\n"
            f"*To:* {draft['to']}\n*Subject:* {draft['subject']}\n\n{body}\n\n"
            f"{tips} The draft expires in 1 hour.")


def edit_draft(query: str, user_id: str, draft: dict) -> dict:
    """Apply 'only 2 and 4' or 'note: …' to the waiting draft and show the new preview."""
    source = draft.get("source")
    picked = parse_selection(query)
    is_note, note = parse_note_edit(query)
    if source is None or (picked is None and not is_note):
        return {"agent": "email", "text": "Reply *send* to send the draft, or *cancel* to discard it."}
    if picked is not None:
        key = {"listings": "homes", "recommendations": "picks"}.get(draft["kind"])
        if key is None:
            return {"agent": "email", "text": "This draft is a market report, so there are no homes to "
                                              "pick. Reply *send*, *cancel*, or *note: …*."}
        items = source[key]
        if any(n < 1 or n > len(items) for n in picked):
            return {"agent": "email", "text": f"This draft has {len(items)} homes, numbered 1 to "
                                              f"{len(items)}. Reply e.g. *only 1*. The draft is unchanged."}
        source[key] = [items[n - 1] for n in picked]
    else:
        source["note"] = note
    edited = new_draft(draft["to"], draft["kind"], source)
    save_draft(user_id, edited)
    return {"agent": "email", "text": preview(edited, updated=True), "draft": edited}


# ------------------------------------------------------------------- sending ---

def build_message(draft: dict, from_address: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = f"{sender_name()} <{from_address}>"
    message["To"] = draft["to"]
    message["Subject"] = draft["subject"]
    message.set_content(draft["text"])
    message.add_alternative(draft["html"], subtype="html")
    return message


def smtp_send(draft: dict) -> None:
    """Send through Gmail. Credentials come from the environment and are never printed."""
    user = os.getenv("EMAIL_USER")
    password = (os.getenv("EMAIL_PASSWORD") or "").replace(" ", "")   # Google shows it in groups of 4
    if not user or not password:
        raise MissingCredentials()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(),
                          timeout=20) as smtp:
        smtp.login(user, password)
        smtp.send_message(build_message(draft, user))


def send_email(draft: dict, sender=None) -> None:
    """The only function that sends. It refuses anything the user hasn't approved."""
    if draft.get("status") != "approved":
        raise PermissionError("an email draft must be approved before it can be sent")
    (sender or smtp_send)(draft)


def handle_reply(query: str, user_id: str) -> dict:
    """Act on "send", "cancel", or an edit ("only 2 and 4", "note: …") for the user's pending draft."""
    word = normalize_reply(query)
    draft = load_draft(user_id)
    if draft is None:
        return {"agent": "email", "text": "There's no email draft waiting. Ask me to email "
                                          "something first, e.g. *email these listings to amy@example.com*."}
    if word in CANCEL:
        clear_draft(user_id)
        return {"agent": "email", "text": f"🗑 Discarded the draft to {draft['to']}. Nothing was sent."}
    if word not in APPROVE:
        return edit_draft(query, user_id, draft)

    draft["status"] = "approved"
    try:
        send_email(draft)
    except MissingCredentials:
        return {"agent": "email", "text": "Email isn't set up yet: EMAIL_USER and EMAIL_PASSWORD "
                                          "are missing from .env. The draft is still waiting."}
    except (smtplib.SMTPException, OSError) as exc:
        # Only the error type: server messages can echo account details.
        print(f"email_agent: send failed ({exc.__class__.__name__})", file=sys.stderr)
        return {"agent": "email", "text": "Couldn't send the email. The draft is still waiting; "
                                          "reply *send* to try again."}
    clear_draft(user_id)
    return {"agent": "email", "text": f"✅ Sent \"{draft['subject']}\" to {draft['to']}."}


# ----------------------------------------------------------------- the agent ---

def email_agent(query: str, user_id: str) -> dict:
    """Week 9 routes "email" requests here: draft and preview, or act on send/cancel/edits."""
    if is_draft_command(query):
        return handle_reply(query, user_id)
    draft, problem = build_draft(query, user_id)
    if problem:
        return {"agent": "email", "text": problem}
    save_draft(user_id, draft)
    return {"agent": "email", "text": preview(draft), "draft": draft}


if __name__ == "__main__":
    # Preview a market report draft from the real database. Nothing is saved or sent.
    import orchestrator
    city = "Pasadena"
    market = orchestrator.market_stats_agent(f"prices in {city}", "email-self-check")
    report = market_report_email(city, market["summary"], market["trend"])
    print(preview(dict(report, to="amy@example.com")))
