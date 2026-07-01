"""Test suite for the natural-language property query parser (Week 2).

Validates parse_property_query against 12 free-text queries.
Run with:  python test_query_parser.py   (or)   python -m pytest -v
"""

import os
import sys

# Import query_parser.py from the same folder
sys.path.insert(0, os.path.dirname(__file__))

from query_parser import parse_property_query  # noqa: E402


CASES = [
    (
        "Show me 3-bedroom condos in Irvine under $1.5M with a pool",
        {"city": "Irvine", "max_price": 1_500_000, "beds": 3,
         "type": "Condominium", "pool": "True"},
    ),
    (
        "4 bed single family homes in San Diego below $900k",
        {"city": "San Diego", "max_price": 900_000, "beds": 4,
         "type": "SingleFamilyResidence"},
    ),
    (
        "townhouse in Pasadena with 2.5 baths and a view",
        {"city": "Pasadena", "baths": 2.5, "type": "Townhouse", "has_view": "True"},
    ),
    (
        "condos in Newport Beach under 2m with at least 1800 sqft",
        {"city": "Newport Beach", "max_price": 2_000_000,
         "sqft": 1800, "type": "Condominium"},
    ),
    (
        "homes in Riverside with max HOA $300",
        {"city": "Riverside", "max_hoa": 300},
    ),
    (
        "5 bedroom house in Los Angeles under $3,000,000",
        {"city": "Los Angeles", "max_price": 3_000_000, "beds": 5,
         "type": "SingleFamilyResidence"},
    ),
    (
        "land in Temecula under 500k",
        {"city": "Temecula", "max_price": 500_000, "type": "UnimprovedLand"},
    ),
    (
        "2 bed 2 bath condo in Long Beach with ocean view",
        {"city": "Long Beach", "beds": 2, "baths": 2.0,
         "type": "Condominium", "has_view": "True"},
    ),
    (
        "houses in Anaheim below $750k with a pool",
        {"city": "Anaheim", "max_price": 750_000,
         "type": "SingleFamilyResidence", "pool": "True"},
    ),
    (
        "3 bed homes in Fresno up to 600k",
        {"city": "Fresno", "max_price": 600_000, "beds": 3},
    ),
    (
        "condo in Santa Monica with mountain view under 1.2m",
        {"city": "Santa Monica", "max_price": 1_200_000,
         "type": "Condominium", "has_view": "True"},
    ),
    (
        "4 bedroom 3 bath house in Sacramento with at least 2500 square feet",
        {"city": "Sacramento", "beds": 4, "baths": 3.0, "sqft": 2500,
         "type": "SingleFamilyResidence"},
    ),
]


def check(query, expected):
    result = parse_property_query(query)
    for key, want in expected.items():
        got = result.get(key)
        assert got == want, f"[{query}]\n  {key}: expected {want!r}, got {got!r}"
    return result


def test_all_cases():
    for query, expected in CASES:
        check(query, expected)


if __name__ == "__main__":
    passed = 0
    for query, expected in CASES:
        try:
            check(query, expected)
            passed += 1
            print(f"PASS | {query}")
        except AssertionError as e:
            print(f"FAIL | {e}")
    print(f"\n{passed}/{len(CASES)} test queries passed.")
