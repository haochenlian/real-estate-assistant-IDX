# Week 9 — Multi-Agent Orchestrator

## In one sentence

This is the **single front door** of the assistant: every message goes into
`orchestrate()`, which asks the model what kind of request it is and hands it to the
right specialist agent — or to two agents at once when the user asks two things in one message.

## What problem it solves

Weeks 2–8 each built one skill: searching listings, market stats, recommendations,
answering definitions. But a user doesn't know or care which module does what. They just
type things like:

> *"Find me affordable homes in Pasadena and tell me whether prices are rising."*

That one message needs **two** skills. Week 9 adds no new skill of its own. It connects
the existing ones so the assistant behaves like one system instead of a folder of scripts.

## How it works (no code needed)

```
user message
    ↓
orchestrate()
    ↓
GPT classifies the message
    ├─ search    → propertySearchAgent    (Weeks 2–4)
    ├─ market    → marketStatsAgent       (Week 5)
    ├─ recommend → recommendationAgent    (Week 7)
    ├─ knowledge → ragAgent               (Week 8)
    ├─ email     → emailDraftAgent        (placeholder until Week 11)
    ├─ mixed     → search + market at the same time, answers merged
    └─ unknown   → a short message listing what the assistant can do
```

## How the model decides the category

Classification is a **multiple-choice question**. For every message the orchestrator sends
`gpt-4o-mini` a prompt containing:

1. **A role**: "You route messages for a California real estate assistant."
2. **A rule**: reply with exactly one word from the list.
3. **The options**, each with a one-line definition (e.g. *mixed — asks to find homes AND
   about market conditions in the same message*). These definitions are what the model
   judges against, so they are the first thing to adjust if a type of message gets misrouted.
4. **The user's message**, followed by `Intent:` so the model completes it with one word.

Two settings keep it predictable: `temperature=0` (pick the most likely label rather than
varying), and `max_tokens=5` (the reply can only be a word).

**The reply is never trusted as-is.** `classify_intent()` lowercases it, keeps the first
word, strips punctuation, and checks it against the known labels. Anything else — a full
sentence, an invented category, an empty reply — becomes `unknown`.

### Why a model instead of keyword rules

A keyword prototype was tried first and scored against 32 sample messages. It routed
common phrasings correctly but misread messages whose words have two meanings:
*"Send me homes in Irvine under 1M"* went to **email** (because of "send"), and
*"How fast are homes selling in Los Angeles?"* went to **search** (because of "homes").
A keyword router can't tell it's wrong, and every fix invites a new phrasing it misses.
Understanding what the user means is exactly the job an agent should hand to the model.

## The agents

| Intent | Agent | Built from | What it returns |
|--------|-------|-----------|-----------------|
| `search` | `property_search_agent` | Week 2 parser, Week 3 query, Week 4 session | The 5 cheapest matching active listings; asks for missing details (city → budget → type) like Week 4. Saves the results for later recommendations. |
| `market` | `market_stats_agent` | Week 5 | City summary (sales count, avg price, price/sqft, days on market, list-to-close ratio) **plus a price trend**: the last 3 months' average vs. the 3 before. |
| `recommend` | `recommendation_agent` | Week 7 | 3 homes most similar to the first result of the user's last search, and whether that home is priced above, below, or in line with comparable sales. |
| `knowledge` | `rag_agent` | Week 8 | A grounded answer from the knowledge documents, with sources. |
| `email` | `email_draft_agent` | — | A placeholder so routing is complete; drafting with an approval gate is Week 11. |

Example — the market agent on the local dataset:

```
Market summary for Pasadena (residential sales):
  Sales analyzed  : 498
  Avg close price : $1,539,977
  Price per sqft  : $823
  Avg days on mkt : 39.6
  List-to-close   : 103.0%  (at/above asking - competitive)
  Price trend     : rising (+14.6%) -- avg $1,695,678 in 2026-04 to 2026-06 vs $1,480,246 in 2026-01 to 2026-03
```

## Mixed requests

When the message is `mixed`, search and market stats don't depend on each other, so they
run **in parallel** (two threads) and their answers are joined into one reply.

In a mixed request the search agent **doesn't stop to ask follow-up questions**. On its own,
*"affordable homes in Pasadena"* would make the Week 4 flow ask for a budget — but the user
already gets a market answer in the same reply, so it searches with what it knows (the city)
and suggests adding a budget to narrow things down.

Two setup steps run **before** the threads start, because doing them from both threads at
once isn't safe:

- **The user's session.** For a new user, both agents could create a session at the same
  moment, and the search results would be saved on the one that gets discarded.
- **The MySQL client library.** It sets up global state on the first connection in a process,
  and that setup is not thread-safe; two simultaneous first connections can crash Python.
  `prepare_database()` connects once from the main thread so the setup is already done.

## Connecting the earlier weeks

The weeks weren't written to plug into each other, so the orchestrator handles the seams:

- **City names followed by `?`.** The Week 2 parser only ends a city at `.`, `,` or a stop
  word, so *"…in Pasadena?"* found no city. The orchestrator treats `?` and `!` as periods
  before parsing. If the message names no city, it uses the one in the user's session.
- **Different field names.** Week 3 returns `price`, `beds`, `sqft`; Week 7 scores on the raw
  columns `L_SystemPrice`, `L_Keyword2`, `LM_Int2_3`. `to_listing_fields()` adds the raw names.
- **Recommendation candidates.** Week 3's search sorts cheapest-first, which would compare an
  expensive home against the cheapest ones. `build_candidates_query()` instead takes active
  listings in the same city within ±$300K of the target, closest price first. (Week 7 awards
  no price points beyond a $300K gap.)
- **Impossible dates.** The sold table contains close dates as late as 2072.
  `price_direction()` ignores months after the current one, so those can't pose as "the latest month".

## Reliability

- **A failing agent doesn't end the conversation.** Errors are caught per agent and turned
  into an apology. In a mixed request, the other agent's answer still comes through.
- **Unexpected model output** becomes `unknown`, which gets a helpful fallback message.

## The files in this folder

| File | What it is |
|------|------------|
| `orchestrator.py` | Intent classification, the five agents, the helpers above, and `orchestrate()`. |
| `test_orchestrator.py` | 28 tests: classification, routing to every agent, mixed requests running in parallel, failure handling, the helpers, and each agent with the database and model replaced. |
| `demo_orchestrator.py` | Plays a five-message conversation against the real database and OpenAI. |
| `README.md` | This explanation. |

## How to run it

```bash
# Self-check: agent registry, city extraction, and the exact classifier prompt (no API, no database)
python3 orchestrator.py

# Tests (should print 28/28 passed) — no API key or database required
python3 test_orchestrator.py

# Live conversation (needs MySQL running and OPENAI_API_KEY in .env)
python3 demo_orchestrator.py

# Or try your own messages
python3 demo_orchestrator.py "Is now a good time to buy in San Diego?"
```

The tests pass a stand-in model and stand-in agents into `orchestrate()`, the same
injection pattern as Week 8's embedder, so routing is verified with no cost.

The live demo sends one classification call per message. The first `knowledge` question
also embeds the 15 knowledge passages once; after that the index is reused.

## Known gaps

- **Classification accuracy with the live model hasn't been measured systematically.** The tests
  prove the routing logic, not how often GPT picks the right label. In a live run, all five
  demo messages (mixed, recommend, knowledge, market, email) were routed correctly, but five
  messages isn't an evaluation. The next step is a labeled set
  of sample messages, including tricky phrasings like the two above, run through the model
  with the results recorded.
- **Recommendations use only Week 7's structured score (max 60).** The semantic 40 points
  would need an embedding call for every candidate listing on every request.
- **Email is a placeholder** until the Week 11 approval-gated email agent exists.
- **Sessions live in memory** (the Week 4 design), so a restart forgets every conversation.
- **The entry point is Python, not an OpenClaw skill.** Weeks 2–8 are Python, so the
  orchestrator calls them directly; Week 10 connects OpenClaw's WhatsApp channel to it.

## Where this fits

```
Weeks 2–8: one skill each   →   Week 9: one entry point that routes to all of them   →   Week 10: users reach it over WhatsApp
```

Week 9 is where the project stops being separate modules and becomes one assistant.
