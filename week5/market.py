"""
Market analytics over california_sold (Week 5).

Given a city, compute market statistics from the ~87K sold transactions so the
agent can answer questions like "What's the average price per sqft in Pasadena?"
or "Is now a good time to buy in San Diego?".

Two views:
  1. A single-number *summary* for a city (avg price, price/sqft, days on market,
     list-to-close ratio).
  2. A month-by-month *trend* to see how prices have moved over time.

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:      # only needed to actually connect; builders work without it
    pass


# --- Pure query builders (no database needed -> easy to test) ----------------

def build_market_summary_query(city: str):
    """One row of headline market stats for a city's residential sales."""
    sql = """
        SELECT
          COUNT(*)                                                 AS sold_count,
          ROUND(AVG(ClosePrice), 0)                                AS avg_close_price,
          ROUND(AVG(ClosePrice / NULLIF(LivingArea, 0)), 0)        AS avg_price_per_sqft,
          ROUND(AVG(DaysOnMarket), 1)                              AS avg_dom,
          ROUND(AVG(ClosePrice / NULLIF(ListPrice, 0)) * 100, 1)   AS list_to_close_pct
        FROM california_sold
        WHERE City = %s
          AND PropertyType = 'Residential'
          AND LivingArea > 0
    """
    return sql, [city]


def build_price_trend_query(city: str):
    """Monthly average price and volume for a city (oldest month first)."""
    # CloseDate is stored as a 'YYYY-MM-DD' string, so LEFT(...,7) = 'YYYY-MM'.
    sql = """
        SELECT
          LEFT(CloseDate, 7)          AS month,
          COUNT(*)                    AS sales,
          ROUND(AVG(ClosePrice), 0)   AS avg_price,
          ROUND(AVG(DaysOnMarket), 1) AS avg_dom
        FROM california_sold
        WHERE City = %s
          AND PropertyType = 'Residential'
          AND CloseDate <> ''
        GROUP BY LEFT(CloseDate, 7)
        ORDER BY month
    """
    return sql, [city]


# --- Database execution ------------------------------------------------------

def get_connection():
    import mysql.connector
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "idx_exchange"),
    )


def _run(sql: str, params: list) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def market_summary(city: str) -> dict | None:
    rows = _run(*build_market_summary_query(city))
    return rows[0] if rows else None


def price_trend(city: str) -> list[dict]:
    return _run(*build_price_trend_query(city))


# --- Turn the numbers into a plain-English answer ----------------------------

def format_market_summary(city: str, s: dict | None) -> str:
    if not s or not s.get("sold_count"):
        return f"No sold data found for {city}."
    return (
        f"Market summary for {city} (residential sales):\n"
        f"  Sales analyzed  : {s['sold_count']}\n"
        f"  Avg close price : ${s['avg_close_price']:,.0f}\n"
        f"  Price per sqft  : ${s['avg_price_per_sqft']:,.0f}\n"
        f"  Avg days on mkt : {s['avg_dom']}\n"
        f"  List-to-close   : {s['list_to_close_pct']}%  "
        f"({'below asking - room to negotiate' if s['list_to_close_pct'] < 100 else 'at/above asking - competitive'})"
    )


if __name__ == "__main__":
    city = "Los Angeles"
    sql, params = build_market_summary_query(city)
    print("SUMMARY SQL:", " ".join(sql.split()))
    print("PARAMS     :", params)

    tsql, tparams = build_price_trend_query(city)
    print("\nTREND SQL  :", " ".join(tsql.split()))
    print("PARAMS     :", tparams)

    # Uncomment once MySQL is running to see real numbers:
    # print("\n" + format_market_summary(city, market_summary(city)))
