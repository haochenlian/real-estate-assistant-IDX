# Week 8 — RAG Knowledge Assistant

## In one sentence

This lets the assistant answer **conceptual questions** — *"What does DOM mean?"*,
*"What columns are in california_sold?"*, *"How is the list-to-close ratio calculated?"* —
by first **looking up the answer in source documents**, then answering only from what it found.

## What problem it solves

Weeks 2–7 answer questions about *data*: which homes match, what the market looks like,
what's similar. But users also ask about *meaning*: what a term stands for, what a field
contains. A plain LLM will answer those confidently even when it doesn't know — and IDX's
legacy field names (`L_Keyword2`, `LM_Dec_3`, `L_SystemPrice`) appear nowhere on the
internet, so it *can't* know. Ask it what `L_Keyword2` means and it will guess
"a search keyword." It's actually the bedroom count.

**RAG (Retrieval-Augmented Generation)** fixes this: retrieve the relevant passages first,
hand them to the model, and instruct it to answer **only** from those passages. It's the
difference between a closed-book exam (answer from memory, guess when unsure) and an
open-book exam (find the right page, then answer).

## RAG in two halves

RAG splits the work between math and the model:

| Half | Who does it | What happens |
|------|-------------|--------------|
| **1. Find the relevant passages** | Math — `retrieve()` in this module, *not* the LLM | Compares the question against every passage and picks the 4 closest in meaning. |
| **2. Answer from them** | The LLM (`gpt-4o-mini`) | Receives only those 4 passages, with a rule: use only this context, and say "I don't know" if the answer isn't there. |

The model never searches anything itself. It only reads what the math selected.

### Vectors and dimensions: how the math compares meaning

- A **vector** is just a list of numbers that represents a piece of text.
- A **dimension** is one position in that list, so the vector's length is its number of dimensions.

The stand-in embedder in `test_rag.py` makes this concrete. It counts 7 keywords, so every
text becomes a **7-dimensional** vector:

```
[dom, market, price, ratio, column, table, bedroom]
```

| Text | Vector (illustrative) |
|------|-----------------------|
| Question: *"What does DOM mean?"* | `[1, 0, 0, 0, 0, 0, 0]` |
| Glossary passage about DOM | `[4, 3, 0, 0, 0, 0, 0]` |
| Schema passage about table columns | `[0, 0, 0, 0, 3, 4, 1]` |

Cosine similarity measures how closely two vectors point in the same direction. The question
and the DOM passage both point toward `dom`, so they score high and that passage is retrieved.
The schema passage shares nothing with the question and scores 0.

Real OpenAI embeddings work the same way at a larger scale. `text-embedding-3-small` returns
**1536 dimensions**. Its dimensions aren't tied to specific words; the model learns them, so
texts with similar meaning get similar vectors even when they share no words. For example,
*"how long was the house listed before it sold?"* still lands next to the DOM definition.

## How it works (no code needed)

1. **Chunk** — split each knowledge document into ~600-character passages. Consecutive
   passages overlap by 100 characters, so a definition that straddles a boundary still
   appears whole in at least one chunk.
2. **Embed** — turn every passage into a vector with OpenAI embeddings (the same technique
   as Week 6). Passages with similar meaning end up with similar vectors.
3. **Retrieve** — embed the user's question the same way, rank all passages by cosine
   similarity, and keep the top 4.
4. **Generate** — send those 4 passages plus the question to the model, with one rule:

   > Answer the question using ONLY the context below. If the context does not contain
   > the answer, say you don't have that information rather than guessing.

The response includes the answer **and which source files it came from**, so every answer
is traceable.

## The knowledge sources

| File | What it covers |
|------|----------------|
| `knowledge/glossary.md` | Real estate terms: DOM, list vs. close price, list-to-close ratio, price per sqft, comps, HOA, MLS, RESO, buyer's vs. seller's market. |
| `knowledge/schema_fields.md` | Every column in both tables, including `rets_property`'s legacy IDX field names, plus how the two tables join. |

Together: 2 documents → 15 indexed passages.

## The files in this folder

| File | What it is |
|------|------------|
| `rag.py` | The pipeline: chunking, document loading, indexing, retrieval, grounded prompt, and the full `answer_question()` round trip. |
| `demo_rag.py` | Live demo — indexes the knowledge docs with real embeddings and answers the three handbook questions. |
| `test_rag.py` | 15 tests for chunking, loading, indexing, retrieval, and prompt grounding. |
| `knowledge/` | The source documents the assistant answers from. |
| `README.md` | This explanation. |

## Two ideas worth knowing

- **The grounding instruction is the whole point.** Retrieval finds the right passages,
  but the "ONLY the context… don't guess" rule is what stops the model from filling gaps
  with plausible-sounding inventions. Saying "I don't have that information" is a correct
  answer.
- **The logic is separated from the API.** Chunking, retrieval, and prompt-building are
  pure functions. The embedding function is *injected* into `build_index()`, so the tests
  use a keyword-counting stand-in instead of OpenAI — the whole pipeline is verified with
  no API key and no cost. Only `get_embedding()` and `generate_answer()` call OpenAI.

## How to run it

```bash
# Show how the documents are chunked and what a grounded prompt looks like (no API needed)
python3 rag.py

# Tests (should print 15/15 passed) — no API key required
python3 test_rag.py

# Live demo: answers the three handbook questions (needs OPENAI_API_KEY in .env)
python3 demo_rag.py

# Ask your own question
python3 demo_rag.py "What is a comp?"
```

`demo_rag.py` makes real OpenAI calls (15 passage embeddings + one per question, plus one
chat completion per question) — a fraction of a cent per run with `text-embedding-3-small`
and `gpt-4o-mini`.

## Known gaps

- The handbook also lists *IDX internal documentation* and *California real estate
  law / disclosure summaries* as knowledge sources. These don't exist as files — the
  program lead confirmed they were illustrative examples, not required inputs — so they
  aren't indexed here.
- Week 5 market summaries aren't indexed yet. Adding them would let the assistant answer
  questions like "What was the average DOM in Pasadena?" from the same pipeline.
- The index is rebuilt in memory on every run. That's fine at 15 passages; a larger
  corpus would need a persistent vector store so documents aren't re-embedded each time.

## Where this fits

```
Weeks 2–7: answer questions about the DATA   →   Week 8: answer questions about MEANING   →   Week 9: orchestrator routes each question to the right agent
```

Week 8 becomes the orchestrator's **knowledge agent**: when a user asks what something
means rather than what's for sale, Week 9 routes the question here.
