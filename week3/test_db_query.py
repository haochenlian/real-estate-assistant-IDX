"""Test suite for the Week 3 database query builder.

These tests cover the PURE query-building functions (no live database needed),
so they run anywhere. They check that:
  - only the filters that are set produce WHERE clauses,
  - every value is passed as a %s parameter (SQL-injection safe),
  - the number of %s placeholders always equals the number of params,
  - pagination (LIMIT / OFFSET) is computed correctly.

Run with:  python test_db_query.py   (or)   python -m pytest -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from db_query import build_active_listings_query, build_sold_comps_query  # noqa: E402


def _placeholders(sql: str) -> int:
    return sql.count("%s")


def test_placeholders_match_params():
    """The #1 safety rule: one %s per value, always in sync."""
    filters = {"city": "Irvine", "max_price": 1_500_000, "beds": 3,
               "type": "Condominium", "pool": "True"}
    sql, params = build_active_listings_query(filters)
    assert _placeholders(sql) == len(params)


def test_only_set_filters_appear():
    """Filters that are None must NOT add a clause."""
    filters = {"city": "Irvine"}          # everything else missing
    sql, params = build_active_listings_query(filters)
    assert "L_City = %s" in sql
    assert "L_SystemPrice <= %s" not in sql   # max_price clause not added
    assert "L_Keyword2 >= %s" not in sql      # beds clause not added
    # params = [city, limit, offset]
    assert params[0] == "Irvine"


def test_empty_filters():
    """No filters -> just the base query + pagination."""
    sql, params = build_active_listings_query({})
    assert "WHERE L_Status = 'Active'" in sql
    assert "AND" not in sql
    assert params == [10, 0]              # default limit 10, page 1 -> offset 0


def test_pagination_offset():
    """page 3 with limit 10 -> offset 20."""
    sql, params = build_active_listings_query({}, page=3, limit=10)
    assert params[-2:] == [10, 20]


def test_operators_are_correct():
    """max_price uses <=, beds uses >=, city uses =."""
    filters = {"city": "Irvine", "max_price": 900_000, "beds": 2}
    sql, _ = build_active_listings_query(filters)
    assert "L_City = %s" in sql
    assert "L_SystemPrice <= %s" in sql
    assert "L_Keyword2 >= %s" in sql


def test_values_never_inlined():
    """Injection safety: the raw value must never appear in the SQL string."""
    filters = {"city": "Irvine'; DROP TABLE rets_property;--"}
    sql, params = build_active_listings_query(filters)
    assert "DROP TABLE" not in sql            # the payload stays in params, not SQL
    assert params[0] == "Irvine'; DROP TABLE rets_property;--"


def test_param_order():
    """Params must be in the same order the %s placeholders appear."""
    filters = {"city": "Irvine", "max_price": 1_000_000, "beds": 3,
               "type": "Condominium", "pool": "True"}
    _, params = build_active_listings_query(filters, page=1, limit=5)
    assert params == ["Irvine", 1_000_000, 3, "Condominium", "True", 5, 0]


def test_sold_comps_query():
    sql, params = build_sold_comps_query("Pasadena", months=6)
    assert _placeholders(sql) == len(params) == 2
    assert params == ["Pasadena", 6]


TESTS = [
    test_placeholders_match_params,
    test_only_set_filters_appear,
    test_empty_filters,
    test_pagination_offset,
    test_operators_are_correct,
    test_values_never_inlined,
    test_param_order,
    test_sold_comps_query,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
