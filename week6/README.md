# Week 6 — Semantic (Embedding) Search

## In one sentence

This lets the assistant find listings by **meaning**, not just exact keywords — so
*"a charming craftsman with character and mountain views"* can match the right homes
even if those exact words never appear in the data.

## What problem it solves

Weeks 2–3 filter on exact fields (city, price, beds). But people describe homes in
fuzzy, human language that keyword filters can't handle. **Week 6 uses AI embeddings**
to compare *meaning*: it turns text into a list of numbers (a "vector") where similar
meanings sit close together, then finds the listings closest to what the user described.

This is the first genuinely **AI** part of the project — earlier weeks were exact SQL.

## How it works (no code needed)

1. **Describe each listing as text** — combine its type, city, beds/baths, size, price,
   and the listing remarks into one sentence.
2. **Embed it** — send that text to OpenAI, which returns a vector (a list of numbers)
   that captures its meaning.
3. **Embed the user's query** the same way.
4. **Rank by cosine similarity** — a math measure of how close two vectors point in the
   same direction (1 = same meaning, 0 = unrelated). The closest listings win.

Think of embeddings as giving every listing and every query a position on a huge "map
of meaning." Similar things land near each other, so we just return the nearest ones.

## The files in this folder

| File | What it is |
|------|------------|
| `semantic_search.py` | Build listing text, embed via OpenAI, and rank by cosine similarity. |
| `test_semantic_search.py` | 11 tests for the math (similarity, ranking, text-building). |
| `README.md` | This explanation. |

## Two ideas worth knowing

- **Cosine similarity measures direction, not size.** Two vectors pointing the same way
  score 1 even if one is "longer" — so it compares *meaning*, not text length.
- **The math is separated from the API.** Similarity, ranking, and text-building are
  pure functions (fast, fully tested with no API). Only `get_embedding()` calls OpenAI,
  which needs an API key and costs a tiny amount per call.

## How to run it

```bash
# Demo: shows a listing turned into text, and ranks tiny sample vectors (no API needed)
python3 semantic_search.py

# Tests (should print 11/11 passed) — no API key required
python3 test_semantic_search.py
```

To run real semantic search over listings you need an OpenAI API key in `.env`; then
`semantic_search(query, listings)` embeds the query and each listing and returns the
top matches.

## Where this fits

```
Weeks 2–3: exact keyword search  →  Week 6: search by meaning (embeddings)  →  Week 7: recommendations blend both
```
Week 6 adds "understanding" — the foundation for the hybrid recommendation engine in
Week 7, which combines structured similarity with this semantic similarity.
