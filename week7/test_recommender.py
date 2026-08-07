"""Tests for the Week 7 hybrid recommendation engine.

Covers the scoring bands, ranking behaviour, comp-query construction, and the
price verdict thresholds. Runs without a database or an API key.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from recommender import (structured_score, semantic_score, hybrid_score,
                         recommend, build_comp_validation_query, assess_price)


TARGET = {"L_ListingID": "T1", "L_City": "Irvine", "L_SystemPrice": 1_200_000,
          "L_Keyword2": 3, "LM_Int2_3": 1500}


# ---- structured scoring (60 points max) --------------------------------
def test_perfect_structured_match_scores_60():
    twin = dict(TARGET, L_ListingID="X")          # identical on every signal
    assert structured_score(TARGET, twin) == 60


def test_price_bands():
    near = dict(TARGET, L_ListingID="X", L_SystemPrice=1_230_000)   # <50K  -> 20
    mid  = dict(TARGET, L_ListingID="X", L_SystemPrice=1_320_000)   # <150K -> 12
    far  = dict(TARGET, L_ListingID="X", L_SystemPrice=1_450_000)   # <300K -> 5
    way  = dict(TARGET, L_ListingID="X", L_SystemPrice=2_000_000)   # beyond -> 0
    assert structured_score(TARGET, near) == 60      # 20+15+15+10
    assert structured_score(TARGET, mid)  == 52      # 12+15+15+10
    assert structured_score(TARGET, far)  == 45      #  5+15+15+10
    assert structured_score(TARGET, way)  == 40      #  0+15+15+10


def test_different_city_loses_15():
    other = dict(TARGET, L_ListingID="X", L_City="San Jose")
    assert structured_score(TARGET, other) == 45     # 60 - 15


def test_different_bedrooms_loses_15():
    other = dict(TARGET, L_ListingID="X", L_Keyword2=4)
    assert structured_score(TARGET, other) == 45


def test_sqft_bands():
    close = dict(TARGET, L_ListingID="X", LM_Int2_3=1600)   # <300 -> 10
    mid   = dict(TARGET, L_ListingID="X", LM_Int2_3=2000)   # <700 -> 5
    far   = dict(TARGET, L_ListingID="X", LM_Int2_3=3000)   # beyond -> 0
    assert structured_score(TARGET, close) == 60
    assert structured_score(TARGET, mid)   == 55
    assert structured_score(TARGET, far)   == 50


def test_missing_fields_do_not_crash():
    sparse = {"L_ListingID": "X"}                    # no price, beds, city, sqft
    assert structured_score(TARGET, sparse) >= 0     # returns a number, no error


# ---- semantic scoring (40 points max) ----------------------------------
def test_identical_embeddings_score_40():
    assert abs(semantic_score([1, 0], [1, 0]) - 40) < 1e-9


def test_opposite_embeddings_clamp_to_0():
    assert semantic_score([1, 0], [-1, 0]) == 0.0    # negatives clamped


def test_missing_embeddings_score_0():
    assert semantic_score(None, [1, 0]) == 0.0       # works before API key is wired


# ---- hybrid + ranking ---------------------------------------------------
def test_hybrid_caps_at_100():
    twin = dict(TARGET, L_ListingID="X")
    assert hybrid_score(TARGET, twin, [1, 0], [1, 0]) == 100


def test_recommend_orders_by_score():
    candidates = [
        {"L_ListingID": "A", "L_City": "Irvine",   "L_SystemPrice": 1_230_000, "L_Keyword2": 3, "LM_Int2_3": 1550},
        {"L_ListingID": "B", "L_City": "Irvine",   "L_SystemPrice": 1_800_000, "L_Keyword2": 5, "LM_Int2_3": 3000},
        {"L_ListingID": "C", "L_City": "San Jose", "L_SystemPrice": 1_210_000, "L_Keyword2": 3, "LM_Int2_3": 1490},
    ]
    ranked = recommend(TARGET, candidates)
    assert [c["L_ListingID"] for c, _ in ranked] == ["A", "C", "B"]


def test_recommend_excludes_the_target_itself():
    candidates = [dict(TARGET), {"L_ListingID": "A", "L_City": "Irvine",
                                 "L_SystemPrice": 1_230_000, "L_Keyword2": 3, "LM_Int2_3": 1550}]
    ranked = recommend(TARGET, candidates)
    assert all(c["L_ListingID"] != "T1" for c, _ in ranked)


def test_recommend_respects_top_k():
    candidates = [dict(TARGET, L_ListingID=str(i)) for i in range(10)]
    assert len(recommend(TARGET, candidates, top_k=3)) == 3


# ---- comp query ---------------------------------------------------------
def test_comp_query_uses_20_percent_band():
    sql, params = build_comp_validation_query("Irvine", 1500)
    assert params[0] == "Irvine"
    assert params[1] == 1200 and params[2] == 1800      # +/-20% of 1500
    assert sql.count("%s") == len(params) == 3


def test_comp_query_injection_safe():
    payload = "X'; DROP TABLE california_sold;--"
    sql, params = build_comp_validation_query(payload, 1500)
    assert "DROP TABLE" not in sql
    assert params[0] == payload


# ---- price verdicts -----------------------------------------------------
def test_price_in_line():
    r = assess_price(list_price=1_200_000, sqft=1500, avg_ppsf=800)
    assert r["delta_pct"] == 0.0
    assert r["verdict"] == "in line with comparable sales"


def test_price_above_market():
    r = assess_price(list_price=1_400_000, sqft=1500, avg_ppsf=800)   # +16.7%
    assert r["verdict"] == "priced above comparable sales"


def test_price_below_market():
    r = assess_price(list_price=1_000_000, sqft=1500, avg_ppsf=800)   # -16.7%
    assert r["verdict"] == "priced below comparable sales"


def test_no_comps_available():
    r = assess_price(list_price=1_200_000, sqft=1500, avg_ppsf=0)
    assert r["verdict"] == "not enough comparable sales"
    assert r["comp_price"] is None


TESTS = [test_perfect_structured_match_scores_60, test_price_bands,
         test_different_city_loses_15, test_different_bedrooms_loses_15,
         test_sqft_bands, test_missing_fields_do_not_crash,
         test_identical_embeddings_score_40, test_opposite_embeddings_clamp_to_0,
         test_missing_embeddings_score_0, test_hybrid_caps_at_100,
         test_recommend_orders_by_score, test_recommend_excludes_the_target_itself,
         test_recommend_respects_top_k, test_comp_query_uses_20_percent_band,
         test_comp_query_injection_safe, test_price_in_line,
         test_price_above_market, test_price_below_market, test_no_comps_available]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
