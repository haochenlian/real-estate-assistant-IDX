"""Safety guardrail tests for the Week 11 email agent.

The most important property: no email is ever sent without an explicit "send"
from the user. These tests replace the SMTP sender with an outbox that only
records, and the database with fixed rows, so they need no network, database,
credentials, or API key.
"""

import contextlib
import io
import json
import os
import smtplib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

import email_agent as ea
from email_agent import (email_agent, is_reply, send_email, listings_email, market_report_email,
                         recommendations_email, build_message, draft_path, has_pending_draft,
                         load_draft, find_note, email_kind, home_facts, build_details_query,
                         MAX_ROWS)
import orchestrator as orch                                  # Week 9
from conversation import get_session, clear_session          # Week 4

ea.DRAFT_DIR = tempfile.mkdtemp(prefix="idx-drafts-")          # never touch real drafts
os.environ.pop("EMAIL_SENDER_NAME", None)                      # use the default name, "Howard"


class Outbox:
    """Stands in for SMTP: records drafts instead of sending them."""
    def __init__(self):
        self.sent = []

    def __call__(self, draft):
        self.sent.append(draft)


OUTBOX = Outbox()
REAL_SMTP_SEND = ea.smtp_send
ea.smtp_send = OUTBOX                                         # nothing in this file can reach the network

ROW = {"L_ListingID": "L1", "L_Address": "12 Oak St", "L_City": "Irvine", "price": 1_200_000,
       "beds": 3, "baths": Decimal("2.0"), "sqft": 1500, "DaysOnMarket": 10}
DETAILS = {"L1": {"L_ListingID": "L1", "L_Zip": "92618",
                  "L_Photos": '["https://media.example.com/l1-front.jpg", "https://media.example.com/l1-2.jpg"]',
                  "L_Remarks": "Sunny corner home with a remodeled kitchen, " * 6,
                  "ListAgentFullName": "Ann Lee", "ListAgentEmail": "ann@acme.example",
                  "ListAgentDirectPhone": "949-555-0100", "LO1_OrganizationName": "Acme Realty"}}
AS_OF = datetime(2026, 6, 16, 12, 19)


def fake_sql(sql, params):
    """Stands in for MySQL: listing details and the data date."""
    if "MAX(ModificationTimestamp)" in sql:
        return [{"as_of": AS_OF}]
    if "L_ListingID IN" in sql:
        return [DETAILS[i] for i in params[:-1] if i in DETAILS]
    return []


orch.run_sql = fake_sql                                       # no test in this file touches the database

SUMMARY = {"sold_count": 498, "avg_close_price": 1539977.0, "avg_price_per_sqft": 823.0,
           "avg_dom": Decimal("39.6"), "list_to_close_pct": 103.0}
TREND = {"direction": "flat", "change_pct": 0.8, "recent_ppsf": 839, "prior_ppsf": 832,
         "recent_months": "2026-04 to 2026-05", "prior_months": "2026-02 to 2026-03",
         "months": [{"month": "2026-01", "avg_ppsf": 737}, {"month": "2026-05", "avg_ppsf": 828}],
         "data_through": "2026-06-15"}
ASK = "email these listings to amy@example.com"


def fresh(uid, searched=True):
    """A user with no draft; optionally with one saved search result."""
    clear_session(uid)
    ea.clear_draft(uid)
    OUTBOX.sent.clear()
    if searched:
        get_session(uid).last_results = [ROW]
        get_session(uid).city = "Irvine"
    return uid


class patched:
    def __init__(self, module, **replacements):
        self.module, self.replacements, self.saved = module, replacements, {}

    def __enter__(self):
        for name, value in self.replacements.items():
            self.saved[name] = getattr(self.module, name)
            setattr(self.module, name, value)

    def __exit__(self, *exc):
        for name, value in self.saved.items():
            setattr(self.module, name, value)


# ---- the approval gate -----------------------------------------------------
def test_drafting_never_sends():
    uid = fresh("g1")
    reply = email_agent(ASK, uid)
    assert "not sent yet" in reply["text"] and "*To:* amy@example.com" in reply["text"]
    assert OUTBOX.sent == [] and has_pending_draft(uid)


def test_send_happens_only_after_approval():
    uid = fresh("g2")
    email_agent(ASK, uid)
    reply = email_agent("send", uid)
    assert reply["text"].startswith("✅ Sent")
    assert [d["to"] for d in OUTBOX.sent] == ["amy@example.com"]
    assert not has_pending_draft(uid)


def test_only_whole_message_replies_count():
    for text in ("send", "Send!", "Yes, send it.", "approve", "cancel", "Don't send"):
        assert is_reply(text), text
    for text in ("please send me homes in Irvine", "send it to bob@example.com",
                 "can you send the report", "I'll send it later"):
        assert not is_reply(text), text


def test_dont_send_cancels_instead_of_sending():
    uid = fresh("g3")
    email_agent(ASK, uid)
    reply = email_agent("Don't send", uid)
    assert "Nothing was sent" in reply["text"]
    assert OUTBOX.sent == [] and not has_pending_draft(uid)


def test_send_after_cancel_finds_nothing():
    uid = fresh("g4")
    email_agent(ASK, uid)
    email_agent("cancel", uid)
    assert "no email draft waiting" in email_agent("send", uid)["text"]
    assert OUTBOX.sent == []


def test_expired_draft_cannot_be_sent():
    uid = fresh("g5")
    email_agent(ASK, uid)
    with open(draft_path(uid)) as fh:
        draft = json.load(fh)
    draft["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    ea.save_draft(uid, draft)
    assert "no email draft waiting" in email_agent("send", uid)["text"]
    assert OUTBOX.sent == []


def test_send_email_refuses_an_unapproved_draft():
    for status in ("pending_approval", None, "APPROVED "):
        try:
            send_email({"status": status, "to": "a@b.co"}, OUTBOX)
            raise AssertionError(f"sent a draft with status {status!r}")
        except PermissionError:
            pass
    assert OUTBOX.sent == []


def test_exactly_one_recipient():
    uid = fresh("g6")
    assert "Who should I send it to" in email_agent("email these listings to my wife", uid)["text"]
    assert "one person at a time" in email_agent("email these to a@x.com and b@y.com", uid)["text"]
    assert not has_pending_draft(uid) and OUTBOX.sent == []


def test_listings_need_a_search_first():
    uid = fresh("g7", searched=False)
    assert "Search for homes first" in email_agent(ASK, uid)["text"]
    assert not has_pending_draft(uid)


# ---- credentials and failures ----------------------------------------------
def test_missing_credentials_keep_the_draft():
    uid = fresh("c1")
    email_agent(ASK, uid)
    saved_env = {k: os.environ.pop(k, None) for k in ("EMAIL_USER", "EMAIL_PASSWORD")}
    try:
        with patched(ea, smtp_send=REAL_SMTP_SEND):           # real sender stops before the network
            reply = email_agent("send", uid)
    finally:
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
    assert "isn't set up yet" in reply["text"] and has_pending_draft(uid)


def test_send_failure_keeps_the_draft_and_hides_the_password():
    uid = fresh("c2")
    email_agent(ASK, uid)

    def failing(draft):
        raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
    os.environ["EMAIL_PASSWORD"] = "hunter2-secret"
    try:
        with patched(ea, smtp_send=failing), contextlib.redirect_stderr(io.StringIO()) as err:
            reply = email_agent("send", uid)
    finally:
        del os.environ["EMAIL_PASSWORD"]
    assert "Couldn't send" in reply["text"] and has_pending_draft(uid)
    assert "hunter2" not in reply["text"] and "hunter2" not in err.getvalue()


def test_draft_files_are_private_and_stay_in_their_folder():
    uid = fresh("c3")
    email_agent(ASK, uid)
    assert os.stat(draft_path(uid)).st_mode & 0o777 == 0o600
    assert os.path.dirname(draft_path("../../etc/passwd")) == ea.DRAFT_DIR


def test_corrupt_draft_file_counts_as_no_draft():
    uid = fresh("c4")
    os.makedirs(ea.DRAFT_DIR, exist_ok=True)
    with open(draft_path(uid), "w") as fh:
        fh.write("{not json")
    assert load_draft(uid) is None


# ---- written for the person receiving it -----------------------------------
def test_listings_email_reads_like_a_letter():
    email = listings_email([dict(ROW, **DETAILS["L1"])], note="I like this one", as_of="June 16, 2026")
    assert email["subject"] == "Howard shared 1 home in Irvine with you"
    text = email["text"]
    assert text.startswith("Hi,\n\nHoward asked me to send you these homes for sale in Irvine.")
    assert 'Howard\'s note: "I like this one"' in text
    assert "1. 12 Oak St, Irvine — $1,200,000" in text
    assert "3 beds · 2 baths · 1,500 sq ft · on the market 10 days" in text
    assert "Listing details are as of June 16, 2026 and may have changed." in text
    assert "Sent by Howard's real estate assistant after Howard approved this email." in text


def test_plain_words_instead_of_data_jargon():
    assert home_facts(dict(ROW, beds=0, baths=1, DaysOnMarket=1)) == "Studio · 1 bath · 1,500 sq ft · on the market 1 day"
    email = recommendations_email(ROW, [(dict(ROW, L_Address="14 Oak St"), 60.0)], None)
    assert "match" not in email["text"] and "60/60" not in email["text"]


def test_each_home_has_photo_description_agent_and_map():
    email = listings_email([dict(ROW, **DETAILS["L1"])])
    assert '<img src="https://media.example.com/l1-front.jpg"' in email["html"]
    assert "Listing agent: Ann Lee (Acme Realty) · ann@acme.example · 949-555-0100" in email["text"]
    assert "https://www.google.com/maps/search/?api=1&query=12+Oak+St%2C+Irvine%2C+CA+92618" in email["text"]
    description = email["text"].split('"')[1]
    assert description.startswith("Sunny corner home") and description.endswith("…") and len(description) <= 161


def test_only_https_photos_are_used():
    for photos in ('["http://media.example.com/a.jpg"]', '["javascript:alert(1)"]', "[]", "not json"):
        assert "<img" not in listings_email([dict(ROW, L_Photos=photos)])["html"], photos


def test_note_and_listing_text_are_escaped_in_html():
    email = listings_email([dict(ROW, L_Address="12 Oak & Elm <St>")], note="<script>alert(1)</script>")
    assert "&lt;script&gt;" in email["html"] and "<script>" not in email["html"]
    assert "12 Oak &amp; Elm &lt;St&gt;" in email["html"]


def test_note_is_found_after_a_colon_or_in_quotes():
    assert find_note("Email these to amy@example.com: I like the second one", "amy@example.com") == "I like the second one"
    assert find_note('Email "take a look at #2" to amy@example.com', "amy@example.com") == "take a look at #2"
    assert find_note("Email these listings to amy@example.com", "amy@example.com") is None


def test_note_does_not_change_the_kind_of_email():
    uid = fresh("n1")
    reply = email_agent("email these listings to amy@example.com: the market here is hot", uid)
    assert reply["draft"]["kind"] == "listings"
    assert 'Howard\'s note: "the market here is hot"' in reply["draft"]["text"]
    assert email_kind("email the market report to amy@example.com") == "market"


def test_draft_uses_listing_details_and_data_date():
    uid = fresh("n2")
    text = email_agent(ASK, uid)["draft"]["text"]
    assert "Listing agent: Ann Lee" in text and "as of June 16, 2026" in text


def test_email_still_drafts_when_details_are_unavailable():
    uid = fresh("n3")

    def broken(sql, params):
        raise ConnectionError("database down")
    with patched(orch, run_sql=broken), contextlib.redirect_stderr(io.StringIO()):
        reply = email_agent(ASK, uid)
    assert "12 Oak St" in reply["draft"]["text"] and "Listing agent" not in reply["draft"]["text"]
    assert "from the listing database and may have changed" in reply["draft"]["text"]


def test_sender_name_comes_from_settings():
    os.environ["EMAIL_SENDER_NAME"] = "Ann"
    try:
        assert listings_email([ROW])["subject"] == "Ann shared 1 home in Irvine with you"
    finally:
        del os.environ["EMAIL_SENDER_NAME"]


def test_no_email_lists_more_than_50_rows():
    email = listings_email([dict(ROW, L_ListingID=str(i)) for i in range(60)])
    assert email["subject"] == f"Howard shared {MAX_ROWS} homes in Irvine with you"
    assert email["html"].count('<div style="margin: 0 0 28px;">') == MAX_ROWS


def test_details_query_is_parameterized_and_capped():
    evil = "L1'); DROP TABLE rets_property; --"
    sql, params = build_details_query([evil] + [str(i) for i in range(60)])
    assert evil not in sql and params[0] == evil
    assert sql.count("%s") == len(params) == MAX_ROWS + 1 and params[-1] == MAX_ROWS


def test_market_report_in_plain_words():
    email = market_report_email("Pasadena", SUMMARY, TREND)
    assert email["subject"] == "Pasadena housing market report (data through June 15, 2026)"
    text = email["text"]
    assert ("Prices are roughly flat: homes sold for about $839 per sq ft in April–May 2026, "
            "compared with $832 in February–March 2026 (+0.8%).") in text
    assert "Homes sold for about 3% above asking price, so expect competition." in text
    assert "A typical home sold in about 40 days." in text
    assert "  January 2026: $737" in text
    assert "list-to-close" not in text.lower()


def test_recommendations_explain_the_price_check():
    similar = dict(ROW, L_Address="14 Oak St")
    check = {"comp_price": 1_200_000, "delta_pct": 0.0, "comp_count": 12,
             "verdict": "in line with comparable sales"}
    email = recommendations_email(ROW, [(similar, 60.0)], check)
    assert email["subject"] == "Howard found 1 home similar to 12 Oak St"
    assert ("Is it fairly priced? 12 similar-sized homes that sold in Irvine suggest it's worth "
            "about $1,200,000, so its $1,200,000 asking price is in line with the market.") in email["text"]
    below = recommendations_email(ROW, [], dict(check, comp_price=1_500_000, delta_pct=-20.0))
    assert "it's 20% below that" in below["text"]


def test_market_request_drafts_a_market_report():
    uid = fresh("t1")
    market = {"agent": "market", "text": "...", "summary": SUMMARY, "trend": TREND}
    with patched(orch, market_stats_agent=lambda q, u: market):
        reply = email_agent("email the market report in Pasadena to amy@example.com", uid)
    assert reply["draft"]["kind"] == "market"
    assert reply["draft"]["subject"].startswith("Pasadena housing market report")
    assert OUTBOX.sent == []


def test_message_has_plain_text_and_html():
    draft = dict(listings_email([ROW]), to="amy@example.com")
    message = build_message(draft, "me@gmail.com")
    assert message["To"] == "amy@example.com" and message["From"] == "Howard <me@gmail.com>"
    assert [part.get_content_type() for part in message.iter_parts()] == ["text/plain", "text/html"]


# ---- editing a waiting draft -----------------------------------------------
THREE = [dict(ROW, L_ListingID=f"H{i}", L_Address=f"{i} Pine St", price=1_000_000 + i) for i in (1, 2, 3)]


def draft_of_three(uid):
    fresh(uid)
    get_session(uid).last_results = THREE
    return email_agent(ASK, uid)["draft"]


def test_edit_commands_are_recognized_strictly():
    assert ea.parse_selection("only 2 and 4") == [2, 4]
    assert ea.parse_selection("Just #2, #4, #2") == [2, 4]
    assert ea.parse_selection("keep 1") == [1]
    for text in ("only homes in Irvine", "just 2 bedrooms please", "only", "keep it simple"):
        assert ea.parse_selection(text) is None, text
    assert ea.parse_note_edit("Note: take a look at #2") == (True, "take a look at #2")
    assert ea.parse_note_edit("note: none") == (True, None)
    assert ea.parse_note_edit("notes about the market")[0] is False


def test_only_keeps_the_chosen_homes_and_renumbers():
    uid = "e1"
    draft_of_three(uid)
    reply = email_agent("only 1 and 3", uid)
    draft = load_draft(uid)
    assert reply["text"].startswith("✏️ *Draft updated.*")
    assert draft["subject"] == "Howard shared 2 homes in Irvine with you"
    assert "1. 1 Pine St" in draft["text"] and "2. 3 Pine St" in draft["text"]
    assert "2 Pine St" not in draft["text"] and OUTBOX.sent == []


def test_preview_lists_every_home_by_number():
    uid = fresh("e0")
    get_session(uid).last_results = [dict(ROW, L_ListingID=f"P{i}", L_Address=f"{i} Elm St") for i in range(1, 13)]
    text = email_agent(ASK, uid)["text"]
    assert "1. 1 Elm St, Irvine — $1,200,000 · 3 beds" in text
    assert "12. 12 Elm St, Irvine" in text and "each home also has a photo" in text


def test_out_of_range_selection_leaves_the_draft_unchanged():
    uid = "e2"
    before = draft_of_three(uid)
    reply = email_agent("only 5", uid)
    assert "numbered 1 to 3" in reply["text"] and "unchanged" in reply["text"]
    assert load_draft(uid)["subject"] == before["subject"]


def test_note_can_be_replaced_and_removed():
    uid = "e3"
    draft_of_three(uid)
    email_agent("note: take a look at the second one", uid)
    assert 'Howard\'s note: "take a look at the second one"' in load_draft(uid)["text"]
    email_agent("note: none", uid)
    assert "Howard's note" not in load_draft(uid)["text"]


def test_market_report_has_no_homes_to_pick():
    uid = fresh("e4")
    market = {"agent": "market", "text": "...", "summary": SUMMARY, "trend": TREND}
    with patched(orch, market_stats_agent=lambda q, u: market):
        email_agent("email the market report in Pasadena to amy@example.com", uid)
    assert "no homes to pick" in email_agent("only 2", uid)["text"]
    email_agent("note: prices look steady", uid)
    assert 'Howard\'s note: "prices look steady"' in load_draft(uid)["text"]


def test_edited_draft_is_what_gets_sent():
    uid = "e5"
    draft_of_three(uid)
    email_agent("only 2", uid)
    email_agent("send", uid)
    assert [d["subject"] for d in OUTBOX.sent] == ["Howard shared 1 home in Irvine with you"]


def test_editing_restarts_the_one_hour_clock():
    uid = "e6"
    draft = draft_of_three(uid)
    draft["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=50)).isoformat()
    ea.save_draft(uid, draft)
    email_agent("note: hi", uid)
    later = datetime.now(timezone.utc) + timedelta(minutes=30)
    assert load_draft(uid, now=later) is not None


def test_edits_go_through_the_orchestrator_without_the_model():
    uid = "e7"
    draft_of_three(uid)

    def model(prompt):
        raise AssertionError("the model must not handle edits to a waiting draft")
    result = orch.orchestrate("only 3", uid, llm=model)
    assert result["intent"] == "email" and "3 Pine St" in load_draft(uid)["text"]


def test_edit_words_without_a_draft_go_to_the_model():
    uid = fresh("e8")
    asked = []
    orch.orchestrate("note: hello", uid, llm=lambda prompt: asked.append(prompt) or "unknown")
    assert asked and not has_pending_draft(uid)


# ---- wiring into the Week 9 orchestrator -----------------------------------
def test_orchestrator_handles_send_without_asking_the_model():
    uid = fresh("o1")
    email_agent(ASK, uid)

    def model(prompt):
        raise AssertionError("the model must not decide whether an email is sent")
    result = orch.orchestrate("send", uid, llm=model)
    assert result["intent"] == "email" and result["text"].startswith("✅ Sent")
    assert len(OUTBOX.sent) == 1


def test_reply_words_without_a_draft_go_to_the_model():
    uid = fresh("o2")
    asked = []
    result = orch.orchestrate("no", uid, llm=lambda prompt: asked.append(prompt) or "unknown")
    assert asked and result["intent"] == "unknown" and OUTBOX.sent == []


def test_email_intent_drafts_through_the_orchestrator():
    uid = fresh("o3")
    result = orch.orchestrate(ASK, uid, llm=lambda prompt: "email")
    assert "not sent yet" in result["text"] and OUTBOX.sent == []


def test_recommendation_candidates_stay_within_50_rows():
    sql, params = orch.build_candidates_query("Irvine", 1_000_000, "L1")
    assert params[-1] <= MAX_ROWS and "LIMIT %s" in sql


TESTS = [test_drafting_never_sends, test_send_happens_only_after_approval,
         test_only_whole_message_replies_count, test_dont_send_cancels_instead_of_sending,
         test_send_after_cancel_finds_nothing, test_expired_draft_cannot_be_sent,
         test_send_email_refuses_an_unapproved_draft, test_exactly_one_recipient,
         test_listings_need_a_search_first, test_missing_credentials_keep_the_draft,
         test_send_failure_keeps_the_draft_and_hides_the_password,
         test_draft_files_are_private_and_stay_in_their_folder,
         test_corrupt_draft_file_counts_as_no_draft,
         test_listings_email_reads_like_a_letter, test_plain_words_instead_of_data_jargon,
         test_each_home_has_photo_description_agent_and_map, test_only_https_photos_are_used,
         test_note_and_listing_text_are_escaped_in_html, test_note_is_found_after_a_colon_or_in_quotes,
         test_note_does_not_change_the_kind_of_email, test_draft_uses_listing_details_and_data_date,
         test_email_still_drafts_when_details_are_unavailable, test_sender_name_comes_from_settings,
         test_no_email_lists_more_than_50_rows, test_details_query_is_parameterized_and_capped,
         test_market_report_in_plain_words, test_recommendations_explain_the_price_check,
         test_market_request_drafts_a_market_report, test_message_has_plain_text_and_html,
         test_edit_commands_are_recognized_strictly, test_only_keeps_the_chosen_homes_and_renumbers,
         test_preview_lists_every_home_by_number,
         test_out_of_range_selection_leaves_the_draft_unchanged, test_note_can_be_replaced_and_removed,
         test_market_report_has_no_homes_to_pick, test_edited_draft_is_what_gets_sent,
         test_editing_restarts_the_one_hour_clock, test_edits_go_through_the_orchestrator_without_the_model,
         test_edit_words_without_a_draft_go_to_the_model,
         test_orchestrator_handles_send_without_asking_the_model,
         test_reply_words_without_a_draft_go_to_the_model, test_email_intent_drafts_through_the_orchestrator,
         test_recommendation_candidates_stay_within_50_rows]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
