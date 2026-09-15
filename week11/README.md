# Week 11 — Email Agent with a Human-Approval Gate

## In one sentence

The assistant can now **draft emails** about homes and the market, let the user **edit** the
draft, and **send it only after the user replies "send"**. It never sends an email on its own.

## What problem it solves

Weeks 2–10 only answer questions. Email is the first thing the assistant does **outside the
chat**, and an email can't be taken back once it's sent. The handbook's rule is
non-negotiable: *no email is ever sent autonomously without explicit confirmation.* So this
week is as much about the gate in front of the send button as about the emails themselves.

## How it works (no code needed)

```
user:  "Email these listings to amy@example.com: I like the second one"
          ↓  Week 9 classifies it as "email" → email_agent()
          ↓  build the draft from the user's last search, save it as "pending approval"
agent: 📧 Email draft (not sent yet)
       To: amy@example.com
       Subject: Howard shared 5 homes in Pasadena with you
       Howard's note: "I like the second one"
       1. 300 N El Molino #312, Pasadena — $378,000 · Studio · 1 bath · 450 sq ft · …
       2. 972 E California 307, Pasadena — $399,000 · Studio · 1 bath · 555 sq ft · …
       …
       Reply send to send it, cancel to discard it, only 1 and 3 to keep just those
       homes, or note: … to change your note. The draft expires in 1 hour.

user:  "only 2 and 4"            → ✏️ Draft updated (2 homes, renumbered 1–2)
user:  "send"
          ↓  recognized as an approval before the model is asked
          ↓  the draft is marked approved → send_email() → Gmail
agent: ✅ Sent "Howard shared 2 homes in Pasadena with you" to amy@example.com.
```

## The approval gate

| Rule | How it's enforced |
|------|-------------------|
| Drafting never sends | `build_draft()` and `send_email()` are separate functions. Drafting only saves a file. |
| Nothing is sent without approval | `send_email()` raises `PermissionError` for any draft not marked `approved`. |
| Only a clear "yes" counts | A draft is approved only if the **whole message** is one of `send`, `send it`, `yes send`, `yes send it`, `approve`, `approved`, `confirm`. *"Please don't send"* is a cancellation; *"send it to bob@…"* is not a reply at all. |
| The model doesn't decide | When a draft is waiting, Week 9 recognizes approvals, cancellations and edits with exact rules **before** asking GPT to classify the message. Whether an email goes out, and what it says, never depends on how a model reads a short reply. |
| Old approvals can't fire | Drafts expire **1 hour** after they were created or last edited. A "send" after that finds nothing. |
| One recipient per email | A request with no address gets a question back; two or more addresses are refused. |
| Credentials stay secret | `EMAIL_USER` and `EMAIL_PASSWORD` are read from `.env` at send time and never printed. Send errors log only the error type, because server messages can echo account details. |
| Failures don't lose work | Missing credentials or a Gmail error keep the draft pending, so the user can fix it and reply "send" again. |

## Written for the person receiving it

The recipient is usually someone the user is sharing homes with, a partner or a friend, who
has never used the assistant. So the emails are designed around what that person needs, not
around what the database contains:

- **Who sent it and why.** The subject and first line say it comes from the user
  (*"Howard shared 5 homes in Pasadena with you"*), and the user's own note is shown.
- **Plain words.** "Studio · 1 bath · 450 sq ft · on the market 29 days", not
  `0bd/1ba` or DOM. No match scores, no "list-to-close ratio"; the market report says
  *"Homes sold for about 3% above asking price, so expect competition."*
- **What to do next.** Each home has a **photo**, a short **description**, the **listing
  agent's name, office, email and phone**, and a **Google Maps** link.
- **How old the data is.** *"Listing details are as of June 16, 2026 and may have changed.
  Contact the listing agent to confirm a home is still available."*

Photos, descriptions and agent contact aren't in the rows Week 3 returns, so the email agent
fetches them for the chosen listings (at most 50, parameterized). If that lookup fails, the
email is still drafted without them.

## The emails

| Kind | Asked for with | Built from |
|------|----------------|------------|
| **Listings** | *"email these listings to …"* | The homes from the user's last search (`rets_property`), saved in the Week 10 session |
| **Market report** | *"email the market report in Pasadena to …"* | Week 5 summary + Week 9 price-per-sqft trend (`california_sold`) |
| **Recommendations** | *"email similar homes to …"* | Week 7 similar homes and comp price check (both tables) |

The user can add a note after a colon (*"…to amy@example.com: I like the second one"*) or in
quotes. Each email has a plain-text part and an HTML part; every value placed in the HTML is
escaped. The name the emails use comes from `EMAIL_SENDER_NAME` in `.env` (default "Howard").

The market report is the handbook's required template. A real draft from the local data:

```
Prices are roughly flat: homes sold for about $839 per sq ft in April–May 2026, compared
with $832 in February–March 2026 (+0.8%).

- 498 homes sold in the period covered.
- The average sale price was $1,539,977.
- Homes sold for about $823 per sq ft.
- A typical home sold in about 40 days.
- Homes sold for about 3% above asking price, so expect competition.

Price per sq ft by month:
  January 2026: $737
  …
  May 2026: $828
```

## Editing a draft

While a draft is waiting, the user can change it before sending:

| Reply | Effect |
|-------|--------|
| `only 2 and 4` (also `just #2, #4`, `keep 1`) | Keep only those homes, renumbered; the subject's count updates |
| `note: take a look at the second one` | Replace the note |
| `note: none` | Remove the note |

Edits are recognized with strict rules: *"only homes in Irvine"* or *"just 2 bedrooms"* are
not edits. A number that isn't in the draft gets an explanation and leaves the draft
unchanged, and a market report has no homes to pick. The draft keeps the data it was built
from, so each edit changes that data and re-renders the whole email. The preview lists every
home on one line so the user can see all the numbers.

## Handbook safety rules

| Never | Where it's handled |
|-------|--------------------|
| Send emails without explicit user approval | The approval gate above |
| Expose API keys or credentials in logs | Secrets only in `.env`; the agent never prints them (tested) |
| Export or bulk-download full MLS datasets | Emails list at most 50 homes, the details lookup returns at most 50 rows, and the Week 9 recommendation query was capped at 50 rows (it was 100) |
| Operate autonomously without human oversight | The only outbound action, sending email, needs a human "send" every time |

## The files in this folder

| File | What it is |
|------|------------|
| `email_agent.py` | Approval and edit rules, draft storage, the three email templates, the listing-details lookup, and the Gmail sender. |
| `test_email_agent.py` | 43 tests: the approval gate, edits, failures and secrets, the email content, and the wiring into Week 9. The SMTP sender is replaced by an outbox that only records and the database by fixed rows, so no test can send mail. |
| `README.md` | This explanation. |

## How to run it

```bash
# Tests (should print 43/43 passed) — no network, database, credentials, or API key
python3 test_email_agent.py

# Preview a real market report draft from the database. Nothing is saved or sent.
python3 email_agent.py
```

### Setting up Gmail

The sender uses Gmail over SMTP with an **app password**, not the account password:

1. Turn on 2-Step Verification for the Google account that will send.
2. Create an app password at <https://myaccount.google.com/apppasswords>.
3. Add these lines to the project's `.env` (never commit it):

```
EMAIL_USER=the.sending.account@gmail.com
EMAIL_PASSWORD=the 16-character app password
EMAIL_SENDER_NAME=Howard          # optional
```

Then ask over WhatsApp, e.g. *"Email these listings to amy@example.com"*, and reply *send*.

## Known gaps

- **New-listing alerts aren't built.** The handbook lists them as a use case. They'd need a
  scheduled job that re-runs a saved search and drafts an alert; even then, each alert would
  wait for approval rather than send itself.
- **Only two kinds of edits.** The user can pick homes and change the note, but not reword the
  email. Free-form edits would mean letting a model rewrite the body, and then checking it
  didn't change any prices or addresses.
- **One pending draft per user.** Asking for a new email replaces the waiting draft. All
  allowlisted WhatsApp numbers share one user id (see Week 10), so they share one draft.
- **Photo links come from the listing service.** They load without a login today, but they're
  signed links that could stop working; the email still reads fine without them.
- **The OpenClaw agent could read `.env`.** Under the current OpenClaw exec policy it can run any
  shell command, so the Gmail app password is only as safe as that policy. Restricting `exec` to
  the Week 10 bridge would close this.

## Where this fits

```
Week 10: reachable from WhatsApp   →   Week 11: can act outside the chat, only with approval   →   Week 12: capstone demo
```

Week 11 gives the assistant its first outbound action, and puts a human in front of it.
