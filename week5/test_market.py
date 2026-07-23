"""Tests for the Week 5 market-analytics query builders (no database needed)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from market import build_market_summary_query, build_price_trend_query


def ph(sql): return sql.count("%s")


def test_summary_placeholders_match_params():
    sql, params = build_market_summary_query("Pasadena")
    assert ph(sql) == len(params) == 1


def test_summary_params_is_city():
    _, params = build_market_summary_query("San Diego")
    assert params == ["San Diego"]


def test_summary_has_key_metrics():
    sql, _ = build_market_summary_query("Irvine")
    assert "COUNT(*)" in sql
    assert "AVG(ClosePrice)" in sql
    assert "list_to_close_pct" in sql
    assert "NULLIF(LivingArea, 0)" in sql          # divide-by-zero guard present


def test_trend_placeholders_match_params():
    sql, params = build_price_trend_query("Long Beach")
    assert ph(sql) == len(params) == 1


def test_trend_groups_by_month():
    sql, _ = build_price_trend_query("Fresno")
    assert "LEFT(CloseDate, 7)" in sql             # month bucket
    assert "GROUP BY LEFT(CloseDate, 7)" in sql
    assert "ORDER BY month" in sql


def test_injection_safe():
    payload = "LA'; DROP TABLE california_sold;--"
    sql, params = build_market_summary_query(payload)
    assert "DROP TABLE" not in sql                 # stays in params, never in SQL
    assert params == [payload]


TESTS = [test_summary_placeholders_match_params, test_summary_params_is_city,
         test_summary_has_key_metrics, test_trend_placeholders_match_params,
         test_trend_groups_by_month, test_injection_safe]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
