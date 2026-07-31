"""Tests for the Week 6 semantic-search math (no OpenAI API needed)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from semantic_search import build_listing_text, cosine_similarity, find_similar


# --- cosine_similarity ---------------------------------------------------
def test_identical_vectors_score_1():
    assert abs(cosine_similarity([1, 2, 3], [1, 2, 3]) - 1.0) < 1e-9

def test_orthogonal_vectors_score_0():
    assert abs(cosine_similarity([1, 0], [0, 1]) - 0.0) < 1e-9

def test_opposite_vectors_score_minus_1():
    assert abs(cosine_similarity([1, 0], [-1, 0]) + 1.0) < 1e-9

def test_scaled_vectors_still_score_1():
    # direction matters, not magnitude
    assert abs(cosine_similarity([1, 1], [10, 10]) - 1.0) < 1e-9

def test_zero_vector_scores_0():
    assert cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0

def test_mismatched_lengths_score_0():
    assert cosine_similarity([1, 2], [1, 2, 3]) == 0.0


# --- find_similar --------------------------------------------------------
def test_ranks_most_similar_first():
    query = [1.0, 0.0]
    listings = [("A", [0.0, 1.0]), ("B", [0.9, 0.1]), ("C", [-1.0, 0.0])]
    ranked = find_similar(query, listings, top_k=3)
    assert ranked[0][0] == "B"        # closest in direction
    assert ranked[-1][0] == "C"       # opposite direction, last

def test_respects_top_k():
    query = [1.0, 0.0]
    listings = [("A", [1, 0]), ("B", [0.9, 0.1]), ("C", [0.8, 0.2]), ("D", [0.7, 0.3])]
    assert len(find_similar(query, listings, top_k=2)) == 2

def test_returns_id_and_score():
    ranked = find_similar([1, 0], [("A", [1, 0])], top_k=1)
    lid, score = ranked[0]
    assert lid == "A" and abs(score - 1.0) < 1e-9


# --- build_listing_text --------------------------------------------------
def test_listing_text_includes_key_fields():
    row = {"L_Type_": "Condominium", "L_City": "Irvine", "L_Keyword2": 3,
           "LM_Dec_3": 2.0, "LM_Int2_3": 1500, "YearBuilt": 2005,
           "L_SystemPrice": 1200000, "L_Remarks": "Bright corner unit."}
    text = build_listing_text(row)
    assert "Condominium" in text
    assert "Irvine" in text
    assert "$1,200,000" in text
    assert "Bright corner unit." in text

def test_listing_text_handles_missing_price():
    text = build_listing_text({"L_City": "Irvine"})   # no price key
    assert "$0" in text                                # defaults safely, no crash


TESTS = [test_identical_vectors_score_1, test_orthogonal_vectors_score_0,
         test_opposite_vectors_score_minus_1, test_scaled_vectors_still_score_1,
         test_zero_vector_scores_0, test_mismatched_lengths_score_0,
         test_ranks_most_similar_first, test_respects_top_k,
         test_returns_id_and_score, test_listing_text_includes_key_fields,
         test_listing_text_handles_missing_price]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
