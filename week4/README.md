[README.md](https://github.com/user-attachments/files/30101601/README.md)
# Week 4 — Conversational Property-Search Agent

## In one sentence

This turns the one-shot search into a **back-and-forth conversation**: the agent
remembers what you've said, asks for whatever is still missing, and searches once
it has enough.

## What problem it solves

Week 3 could search, but only if the user handed over everything in a single
sentence. Real people don't talk like that — they say *"Find me a home in Irvine,"*
then figure out the budget, then the type. **Week 4 lets the agent hold a
conversation**: it fills in details across several messages and only searches when
it has enough to be useful.

## How it works (no code needed)

1. **Every message is parsed** (reusing the Week 2 parser) for any new details.
2. **New details are merged into a "session"** — a small record of what this user
   has told us so far (city, budget, beds, type, …).
3. **The agent asks for the first thing still missing** (city → budget → type).
4. **Once the session is complete, it runs the Week 3 search** and returns listings.

Each user has their own separate session, so two people can search at the same time
without mixing up their answers.

## Example conversation

```
USER : Find me a home in Irvine
AGENT: What's your budget (maximum price)?
USER : under $1.2M
AGENT: Any preference - condo, single family, or townhouse?
USER : a condo with at least 2 beds
AGENT: Great - searching for 2-bed Condominium in Irvine under $1,200,000. Here are the top matches:
```

## The files in this folder

| File | What it is |
|------|------------|
| `conversation.py` | The conversational agent — session state + follow-up logic. |
| `test_conversation.py` | 7 automated tests for the multi-turn logic. |
| `README.md` | This explanation. |

## One idea worth knowing (why a "session" instead of asking the AI to remember)

The session is **our own structured tracker**, not the AI's chat memory. It's a set
of clearly-named slots (`city`, `max_price`, `type`, …) our code can check directly —
`if session.max_price is None: ask for the budget`.

**Why store it in a dedicated object instead of letting the AI recall the chat?**
Because making the AI re-read the whole conversation every turn is (1) **slow**, and
(2) **error-prone** — it can misremember or drop a detail the user gave earlier. A
plain, explicit slot table lets us check "has the budget been filled yet?" instantly
and reliably — it's **deterministic and fast**.

For this project the session lives in memory, which is fine for a local demo; a
production system would store it somewhere shared and persistent (like Redis) so it
survives restarts and works across servers.

## Why one session per user

Two people might talk to the agent at the same time — person A is searching in Irvine,
person B in San Diego. With a single shared notepad their answers would get mixed up:
B says "$1.2M" and it lands on A's search. So each user gets **their own notepad**,
stored in a dictionary keyed by *who they are* (`user_id`, e.g. a WhatsApp number):

```python
sessions: dict[str, UserSession] = {}   # user_id -> that person's notepad
```

Three small helpers operate on one person's notepad:

- `get_session(user_id)` — fetch their notepad (create a fresh one on first contact).
- `update_session(user_id, updates)` — write in only the details they actually gave
  this turn (skip empty ones, so we never wipe a value captured earlier).
- `clear_session(user_id)` — throw the notepad away (when they start over).

Core idea: **isolate by `user_id` — one notepad per person, so nobody's answers bleed
into anyone else's.**

## Saying it back in plain words (the confirmation)

Before searching, the agent says something like *"Great — searching for 2-bed
Condominium in Irvine under $1,200,000…"*. That sentence is built by a small helper
that turns the filled-in slots of the notepad into one readable line:

```python
def _summary(s):
    bits = []
    if s.beds: bits.append(f"{s.beds}-bed")     # only add if it was filled
    bits.append(s.type if s.type else "homes")
    if s.city: bits.append(f"in {s.city}")
    if s.max_price: bits.append(f"under ${s.max_price:,.0f}")
    return " ".join(bits)
```

**Why a separate function?** The sentence-building details have nothing to do with the
main flow, so pulling them out keeps `handle_message` clean. The `if s.beds:` checks
mean we only mention what was actually given — no ugly "None-bed" text. This step is
purely about making the agent **sound like a person**, confirming what it understood
before it acts.

## The heart: how the agent decides each turn (`handle_message`)

Every incoming message runs through one function that does three things:

**A. Understand and remember.** Parse the message (reusing the Week 2 parser) for any
new details, and merge them into this user's notepad. We don't rebuild "understanding"
— we reuse Week 2 and only add what's new this turn.

```python
new_filters = parse_property_query(text)   # reuse Week 2
update_session(user_id, new_filters)       # write new details into the notepad
```

**B. Ask for the first thing still missing.** We keep an ordered list of the slots we
need (city -> budget -> type) and scan for the first empty one; if found, we ask that
question and stop for this turn.

```python
for slot, question in ASK_ORDER:
    if getattr(session, slot) is None:     # still empty
        return {"action": "ask", "message": question}
```

Using a list + loop keeps the logic in one place — to ask for one more thing, just add
a row to `ASK_ORDER`, no other change.

**C. Search once we have enough.** If nothing is missing, hand the collected slots to
the Week 3 query builder and return listings.

```python
filters = {k: getattr(session, k) for k in _FILTER_KEYS}
sql, params = build_active_listings_query(filters)   # reuse Week 3
return {"action": "search", "filters": filters, ...}
```

So `handle_message` barely does new work of its own — it **wires Weeks 2 and 3 together
into a "conversation with memory"**: understand -> ask if incomplete -> search when ready.

## How to run it

```bash
# Watch a simulated 3-turn conversation
python3 conversation.py

# Run the automated tests (should print 7/7 passed)
python3 test_conversation.py
```

## Where this fits

```
Week 2 understands one sentence  →  Week 3 searches the database  →  Week 4 holds a conversation  →  (next) semantic search & recommendations
```
