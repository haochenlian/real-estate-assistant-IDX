[README.md](https://github.com/user-attachments/files/30291834/README.md)
# Week 5 — Market Analytics

## In one sentence

This is the part of the assistant that reads the ~87K **sold** transactions and turns
them into **market statistics** for a city — so it can answer questions like
*"What's the average price per sqft in Pasadena?"* or *"Is now a good time to buy in San Diego?"*.

## What problem it solves

Weeks 2–4 find *active* listings (`rets_property`). But to judge a market you need
**history** — what actually sold, for how much, and how fast. That lives in
`california_sold`. Week 5 summarizes that history into a few meaningful numbers.

## The five metrics (and what each tells you)

| Metric | Meaning | What it answers |
|--------|---------|-----------------|
| Sales count | how many sold in the period | is the market active? |
| Avg close price | what homes actually sold for | how expensive is here? |
| Price per sqft | close price ÷ living area | fair "unit price" across sizes |
| Avg days on market | listing → sale time | how fast homes sell |
| List-to-close ratio | close price ÷ list price × 100 | negotiation room (<100% = below asking) |

## How it works (no code needed)

Unlike earlier weeks (which return one row per house), this **aggregates** many sold
records into a summary using SQL `COUNT()` and `AVG()`. A couple of data-hygiene guards
matter with real data:

- `NULLIF(LivingArea, 0)` — never divide by a zero square-footage (avoids a crash / junk).
- `AND LivingArea > 0` — ignore records with no size.

There are two queries: a **city summary** (the five metrics above) and a **monthly trend**
(average price per month, oldest first).

## The files in this folder

| File | What it is |
|------|------------|
| `market.py` | The analytics layer — summary + trend queries, execution, and formatting. |
| `test_market.py` | 6 tests for the query builders (safety + structure). |
| `README.md` | This explanation. |

## How to run it

```bash
# Print the SQL the builders produce (no database needed)
python3 market.py

# Run the tests (should print 6/6 passed)
python3 test_market.py
```

To see real numbers, make sure MySQL is running and uncomment the last line of
`market.py` (it calls `market_summary("Los Angeles")` and prints a formatted report).

## Where this fits

```
Weeks 2–4: find active listings  →  Week 5: analyze the sold-market  →  (next) embeddings & recommendations use both
```
Week 5 gives the assistant a sense of *the market*, not just individual homes — the
foundation for comp-validated recommendations in Week 7.
