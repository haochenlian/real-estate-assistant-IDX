"""
Hybrid recommendation engine (Week 7).

Given a listing the user likes, find comparable active listings and check
whether their asking price is supported by recent sold comps.

Scoring is a blend of two signals:
  * Structured similarity (60 points) - price, beds, city, square footage
  * Semantic similarity   (40 points) - embedding cosine similarity of the
                                        listing descriptions (Week 6)

Total score is 0-100. Structured scoring is pure math and runs without any
API key; the semantic part reuses Week 6's embeddings when vectors are supplied.

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "week6"))
from semantic_search import cosine_similarity  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------- scoring ---

def structured_score(target: dict, candidate: dict) -> float:
    """Score how alike two listings are on hard facts. Max 60 points.

    price closeness  -> up to 20
    same bedrooms    -> 15
    same city        -> 15
    size closeness   -> up to 10
    """
    score = 0.0

    # Price: the closer the asking prices, the better the match.
    t_price = target.get("L_SystemPrice") or 0
    c_price = candidate.get("L_SystemPrice") or 0
    price_diff = abs(t_price - c_price)
    if price_diff < 50_000:
        score += 20
    elif price_diff < 150_000:
        score += 12
    elif price_diff < 300_000:
        score += 5

    # Bedrooms: exact match only.
    if target.get("L_Keyword2") is not None and \
       target.get("L_Keyword2") == candidate.get("L_Keyword2"):
        score += 15

    # City: same market matters a lot.
    if target.get("L_City") and target.get("L_City") == candidate.get("L_City"):
        score += 15

    # Square footage: closer size = more comparable.
    t_sqft = target.get("LM_Int2_3") or 0
    c_sqft = candidate.get("LM_Int2_3") or 0
    sqft_diff = abs(t_sqft - c_sqft)
    if sqft_diff < 300:
        score += 10
    elif sqft_diff < 700:
        score += 5

    return score


def semantic_score(target_emb: list[float] | None,
                   candidate_emb: list[float] | None) -> float:
    """Convert embedding cosine similarity into 0-40 points.

    Cosine runs -1..1; we clamp negatives to 0 so opposite meanings score zero.
    Returns 0 when embeddings aren't available (no API key yet).
    """
    if not target_emb or not candidate_emb:
        return 0.0
    sim = cosine_similarity(target_emb, candidate_emb)
    return max(0.0, sim) * 40


def hybrid_score(target: dict, candidate: dict,
                 target_emb: list[float] | None = None,
                 candidate_emb: list[float] | None = None) -> float:
    """Combined 0-100 recommendation score for one candidate listing."""
    return round(structured_score(target, candidate)
                 + semantic_score(target_emb, candidate_emb), 2)


def recommend(target: dict, candidates: list[dict],
              embeddings: dict | None = None, top_k: int = 5) -> list[tuple]:
    """Rank candidate listings against the target. Returns (listing, score).

    `embeddings` maps listing id -> vector; omit it to score structure only.
    The target listing itself is skipped if it appears among the candidates.
    """
    embeddings = embeddings or {}
    t_id = target.get("L_ListingID")
    t_emb = embeddings.get(t_id)

    scored = []
    for cand in candidates:
        c_id = cand.get("L_ListingID")
        if c_id == t_id:
            continue                              # never recommend the same home
        score = hybrid_score(target, cand, t_emb, embeddings.get(c_id))
        scored.append((cand, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]


# ------------------------------------------------- comp price validation ---

def build_comp_validation_query(city: str, sqft: int):
    """SQL for average sold price-per-sqft of similar-sized homes in a city.

    Looks at homes within +/-20% of the target size so the comparison is fair.
    """
    sql = """
        SELECT ROUND(AVG(ClosePrice / NULLIF(LivingArea, 0)), 0) AS avg_ppsf,
               COUNT(*)                                          AS comp_count
        FROM california_sold
        WHERE City = %s
          AND PropertyType = 'Residential'
          AND LivingArea BETWEEN %s AND %s
    """
    return sql, [city, sqft * 0.8, sqft * 1.2]


def assess_price(list_price: int, sqft: int, avg_ppsf: float,
                 comp_count: int = 0) -> dict:
    """Compare a listing's asking price against what comps suggest it's worth."""
    if not avg_ppsf or not sqft:
        return {"comp_price": None, "delta_pct": None,
                "verdict": "not enough comparable sales", "comp_count": comp_count}

    comp_price = avg_ppsf * sqft
    delta_pct = round((list_price - comp_price) / comp_price * 100, 1)
    if delta_pct <= -5:
        verdict = "priced below comparable sales"
    elif delta_pct >= 5:
        verdict = "priced above comparable sales"
    else:
        verdict = "in line with comparable sales"
    return {"comp_price": round(comp_price), "delta_pct": delta_pct,
            "verdict": verdict, "comp_count": comp_count}


if __name__ == "__main__":
    target = {"L_ListingID": "T1", "L_City": "Irvine", "L_SystemPrice": 1_200_000,
              "L_Keyword2": 3, "LM_Int2_3": 1500}
    candidates = [
        {"L_ListingID": "A", "L_City": "Irvine",   "L_SystemPrice": 1_230_000, "L_Keyword2": 3, "LM_Int2_3": 1550},
        {"L_ListingID": "B", "L_City": "Irvine",   "L_SystemPrice": 1_800_000, "L_Keyword2": 5, "LM_Int2_3": 3000},
        {"L_ListingID": "C", "L_City": "San Jose", "L_SystemPrice": 1_210_000, "L_Keyword2": 3, "LM_Int2_3": 1490},
    ]

    print("Target:", target, "\n")
    print("Recommendations (structured only, no API key needed):")
    for cand, score in recommend(target, candidates):
        print(f"  {cand['L_ListingID']}: {score:5.1f}  "
              f"{cand['L_City']}, ${cand['L_SystemPrice']:,}, "
              f"{cand['L_Keyword2']}bd, {cand['LM_Int2_3']}sqft")

    print("\nPrice assessment vs comps (example: comps avg $800/sqft):")
    print(" ", assess_price(list_price=1_200_000, sqft=1500, avg_ppsf=800, comp_count=42))
