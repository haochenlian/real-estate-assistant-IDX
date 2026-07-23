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


def test_summary_filters_residential():
    sql, _ = build_market_summary_query("Irvine")
    assert "PropertyType = 'Residential'" in sql        # only residential sales


def test_summary_excludes_zero_area():
    sql, _ = build_market_summary_query("Irvine")
    assert "LivingArea > 0" in sql                       # skip rows with no size


def test_price_per_sqft_formula():
    sql, _ = build_market_summary_query("Irvine")
    assert "ClosePrice / NULLIF(LivingArea, 0)" in sql   # price divided by size


def test_list_to_close_multiplies_by_100():
    sql, _ = build_market_summary_query("Irvine")
    assert "* 100" in sql                                # ratio turned into a percentage


def test_trend_selects_avg_price():
    sql, _ = build_price_trend_query("Irvine")
    assert "AVG(ClosePrice)" in sql
    assert "AS sales" in sql                             # monthly volume column


def test_trend_injection_safe():
    payload = "X'; DROP TABLE california_sold;--"
    sql, params = build_price_trend_query(payload)
    assert "DROP TABLE" not in sql
    assert params == [payload]


def test_city_flows_into_params():
    for city in ["San Diego", "Fresno", "Oakland"]:
        _, params = build_market_summary_query(city)
        assert params == [city]                          # exactly what we passed


TESTS = [test_summary_placeholders_match_params, test_summary_params_is_city,
         test_summary_has_key_metrics, test_trend_placeholders_match_params,
         test_trend_groups_by_month, test_injection_safe,
         test_summary_filters_residential, test_summary_excludes_zero_area,
         test_price_per_sqft_formula, test_list_to_close_multiplies_by_100,
         test_trend_selects_avg_price, test_trend_injection_safe,
         test_city_flows_into_params]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
