"""
MLS database integration layer (Week 3).

Takes the structured filters produced by the Week 2 parser and runs a safe,
parameterized query against the local MySQL `idx_exchange` database, then
formats the rows into readable property cards.

Pipeline:  free text --(Week 2 parser)--> filters --(this module)--> listings

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import os

# python-dotenv reads the .env file so we never hard-code DB credentials.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional for building queries; only needed to connect
    pass


# --- Map each parser filter key -> (SQL column, comparison operator) ---------
# Values are always passed as parameters (never string-concatenated) so the
# query is safe from SQL injection.
FILTER_TO_COLUMN = {
    "city":     ("L_City",        "="),   # exact city match
    "max_price": ("L_SystemPrice", "<="), # price at or below the budget
    "beds":     ("L_Keyword2",    ">="),  # at least N bedrooms
    "baths":    ("LM_Dec_3",      ">="),  # at least N bathrooms
    "sqft":     ("LM_Int2_3",     ">="),  # at least N square feet
    "type":     ("L_Type_",       "="),   # property subtype
    "pool":     ("PoolPrivateYN", "="),   # "True"
    "has_view": ("ViewYN",        "="),   # "True"
    "max_hoa":  ("AssociationFee", "<="), # HOA at or below limit
}

# Columns we return for each listing (aliased to friendly names).
_SELECT = """
    L_ListingID, L_DisplayId, L_Address, L_City, L_Zip,
    L_SystemPrice AS price, L_Keyword2 AS beds, LM_Dec_3 AS baths,
    LM_Int2_3 AS sqft, L_Type_ AS type, L_Status AS status,
    YearBuilt, AssociationFee, DaysOnMarket,
    PoolPrivateYN, ViewYN, PhotoCount,
    LA1_UserFirstName, LA1_UserLastName, LO1_OrganizationName
"""


def build_active_listings_query(filters: dict, page: int = 1, limit: int = 10):
    """Turn a filter dict into a parameterized SQL string + params list.

    This function is PURE (no database needed), which makes it easy to test.
    Returns a tuple: (sql, params).
    """
    offset = (page - 1) * limit

    sql = f"SELECT {_SELECT} FROM rets_property WHERE L_Status = 'Active'"
    params: list = []

    # Add one "AND column <op> ?" clause for every filter that is set.
    for key, (column, op) in FILTER_TO_COLUMN.items():
        value = filters.get(key)
        if value is not None:
            sql += f" AND {column} {op} %s"
            params.append(value)

    # Cheapest first, then page through the results.
    sql += " ORDER BY price ASC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    return sql, params


def build_sold_comps_query(city: str, months: int = 12):
    """Recent sold comparables in a city (from california_sold), last N months."""
    sql = """
        SELECT ListingKey, UnparsedAddress, City, CloseDate, ClosePrice,
               ListPrice, DaysOnMarket, BedroomsTotal, BathroomsTotalInteger,
               LivingArea, PropertyType
        FROM california_sold
        WHERE City = %s
          AND PropertyType = 'Residential'
          AND CloseDate >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
        ORDER BY CloseDate DESC
        LIMIT 50
    """
    return sql, [city, months]


# --- Database execution (needs a live MySQL connection) ---------------------
def get_connection():
    """Open a MySQL connection using credentials from the .env file."""
    import mysql.connector  # imported here so query-building works without the driver
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "idx_exchange"),
    )


def _run(sql: str, params: list) -> list[dict]:
    """Execute a query and return rows as a list of dicts."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)  # dictionary=True -> rows as dicts
        cursor.execute(sql, params)            # driver safely substitutes %s params
        return cursor.fetchall()
    finally:
        conn.close()                           # always close, even on error


def search_active_listings(filters: dict, page: int = 1, limit: int = 10) -> list[dict]:
    sql, params = build_active_listings_query(filters, page, limit)
    return _run(sql, params)


def get_sold_comps(city: str, months: int = 12) -> list[dict]:
    sql, params = build_sold_comps_query(city, months)
    return _run(sql, params)


def format_listing_card(row: dict) -> str:
    """Turn one DB row into a clean, human-readable card (WhatsApp-style)."""
    price = row.get("price") or 0
    beds = row.get("beds")
    baths = row.get("baths")
    sqft = row.get("sqft")
    agent = f"{row.get('LA1_UserFirstName','')} {row.get('LA1_UserLastName','')}".strip()
    return (
        f"🏠 {row.get('L_Address','(no address)')}, {row.get('L_City','')}\n"
        f"   ${price:,.0f} | {beds}bd/{baths}ba | {sqft} sqft\n"
        f"   {row.get('DaysOnMarket','?')} days on market | Agent: {agent or 'N/A'}"
    )


if __name__ == "__main__":
    # Full pipeline demo: free text -> Week 2 parser -> Week 3 query -> cards.
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "week2"))
    from query_parser import parse_property_query

    text = "3 bedroom condos in Irvine under $1.5M with a pool"
    filters = parse_property_query(text)
    print("Query   :", text)
    print("Filters :", filters)

    sql, params = build_active_listings_query(filters, page=1, limit=5)
    print("\nSQL     :", " ".join(sql.split()))
    print("Params  :", params)

    # Uncomment once MySQL is running to see real listings:
    # for row in search_active_listings(filters, limit=5):
    #     print(format_listing_card(row))
