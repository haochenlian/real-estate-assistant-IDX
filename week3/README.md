# Week 3 — Property Database Query Layer

## In one sentence

This is the part of the assistant that takes a person's request and actually
**finds matching homes in the database**.

## What problem it solves

Week 2 turned a sentence like *"3-bedroom condos in Irvine under $1.5M with a pool"*
into a tidy list of conditions (city = Irvine, beds = 3, max price = 1.5M, …).

But a list of conditions doesn't find any houses on its own. **Week 3 takes those
conditions, looks inside the property database, and returns the real listings that
match** — sorted and formatted so a person can actually read them.

## How it works (no code needed)

1. **Receives the conditions** from Week 2 (city, price, beds, type, pool, etc.).
2. **Builds a safe database request** using only the conditions that were actually given.
3. **Asks the database** for matching homes — cheapest first, a handful at a time.
4. **Formats each result** into a clean card: address, price, beds/baths, size, days on market.

## Example

**Input:** "2-bedroom condos in Los Angeles under $1.5M"

**Output:** the 5 cheapest matching listings, e.g.

```
🏠 12287 Osborne Street, Los Angeles
   $299,000 | 2bd/2.0ba | 952 sqft
   1 day on market
```

## The files in this folder

| File | What it is |
|------|------------|
| `db_query.py` | The query layer — connects to the database, builds the request, formats results. |
| `test_db_query.py` | Automated checks that the request is built correctly and safely (8 tests). |
| `README.md` | This explanation. |

## Two ideas worth knowing

- **Safety first.** The user's words are never pasted directly into the database
  request. They are sent separately as "parameters," so nobody can break or abuse
  the database by typing something malicious. (This is called SQL-injection protection.)
- **Only what's asked.** If the user never mentions bathrooms, the search doesn't
  filter by bathrooms. The request adapts to whatever the person actually said.

## How to run it

```bash
# See the pipeline in action (text -> conditions -> database request)
python3 db_query.py

# Run the automated tests (should print 8/8 passed)
python3 test_db_query.py
```

## Where this fits in the whole project

```
User speaks  →  Week 2 understands the request  →  Week 3 fetches real homes  →  Week 4 turns it into a conversation
```

Week 3 is the bridge between "understanding what the user wants" and "showing them
actual homes." Once it works, the assistant goes from *talking about* homes to
*actually finding* them.
