"""
Semantic (embedding-based) property search — Week 6.

Keyword filters (Weeks 2-3) can't handle vague, descriptive language like
"a charming craftsman with character and mountain views". This module turns
text into an OpenAI *embedding* — a list of numbers capturing meaning — and
finds listings whose descriptions are closest in meaning, even with no exact
keyword overlap.

Pipeline:
  listing fields --> descriptive text --> embedding vector
  user query     --> embedding vector
  rank listings by cosine similarity to the query vector --> top matches

The math (cosine similarity, ranking, text-building) is pure Python and fully
testable. Only get_embedding() calls the OpenAI API.

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import math
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:      # only needed for the live API call
    pass


def build_listing_text(row: dict) -> str:
    """Combine a listing's key fields into one descriptive string to embed."""
    price = row.get("L_SystemPrice") or 0
    return (
        f"{row.get('L_Type_', '')} in {row.get('L_City', '')}, CA. "
        f"{row.get('L_Keyword2', '?')} beds, {row.get('LM_Dec_3', '?')} baths. "
        f"{row.get('LM_Int2_3', '?')} sqft. Built {row.get('YearBuilt', '?')}. "
        f"Price: ${price:,}. "
        f"{row.get('L_Remarks', '')}"
    ).strip()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors: 1 = same direction, 0 = unrelated.

    Pure Python (no numpy) so it runs and tests anywhere.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_similar(query_vec: list[float],
                 listing_embeddings: list[tuple],
                 top_k: int = 5) -> list[tuple]:
    """Rank (listing_id, embedding) pairs by similarity to the query vector.

    Returns the top_k as (listing_id, score), most similar first.
    """
    scored = [(lid, cosine_similarity(query_vec, emb))
              for lid, emb in listing_embeddings]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]


def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Turn text into an embedding vector via the OpenAI API (needs an API key)."""
    from openai import OpenAI
    client = OpenAI()
    text = text.replace("\n", " ").strip()[:8000]     # token-safety cap
    resp = client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def semantic_search(query: str, listings: list[dict], top_k: int = 5) -> list[tuple]:
    """End-to-end: embed the query and each listing, return top_k similar ids.

    Requires a working OpenAI API key (each listing + the query is embedded).
    """
    query_vec = get_embedding(query)
    listing_embeddings = [
        (row["L_ListingID"], get_embedding(build_listing_text(row)))
        for row in listings
    ]
    return find_similar(query_vec, listing_embeddings, top_k)


if __name__ == "__main__":
    # 1) Show how a listing becomes descriptive text (no API needed).
    sample = {
        "L_ListingID": "123", "L_Type_": "Condominium", "L_City": "Irvine",
        "L_Keyword2": 3, "LM_Dec_3": 2.0, "LM_Int2_3": 1500, "YearBuilt": 2005,
        "L_SystemPrice": 1200000, "L_Remarks": "Bright corner unit with a pool and city views.",
    }
    print("Listing text to embed:\n ", build_listing_text(sample))

    # 2) Demonstrate ranking with tiny hand-made vectors (no API needed).
    #    Query points 'toward' listing B, so B should rank first.
    query = [1.0, 0.0]
    listings = [("A", [0.0, 1.0]), ("B", [0.9, 0.1]), ("C", [-1.0, 0.0])]
    print("\nRanked by similarity to query", query, ":")
    for lid, score in find_similar(query, listings, top_k=3):
        print(f"  {lid}: {score:.3f}")
