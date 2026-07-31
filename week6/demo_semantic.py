"""
Live semantic-search demo (Week 6).

Pulls a handful of real active listings from MySQL, embeds each one plus a
fuzzy natural-language query via OpenAI, and prints the closest matches by
meaning. Needs a working OpenAI API key in .env and MySQL running.

Usage:
    python3 demo_semantic.py                      # default city + query
    python3 demo_semantic.py "Santa Monica" "a cozy beachy condo with charm"
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from semantic_search import build_listing_text, get_embedding, find_similar  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import mysql.connector


def fetch_listings(city: str, limit: int = 20) -> list[dict]:
    """Grab active listings in a city that actually have a description."""
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "idx_exchange"),
    )
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT L_ListingID, L_Address, L_City, L_Type_, L_Keyword2,
                   LM_Dec_3, LM_Int2_3, YearBuilt, L_SystemPrice, L_Remarks
            FROM rets_property
            WHERE L_Status = 'Active' AND L_City = %s
              AND L_Remarks IS NOT NULL AND L_Remarks <> ''
            LIMIT %s
            """,
            [city, limit],
        )
        return cur.fetchall()
    finally:
        conn.close()


def main():
    city = sys.argv[1] if len(sys.argv) > 1 else "Irvine"
    query = sys.argv[2] if len(sys.argv) > 2 else \
        "a bright modern home with a pool and nice views, great for entertaining"

    print(f"City : {city}")
    print(f"Query: \"{query}\"\n")

    listings = fetch_listings(city)
    if not listings:
        print("No listings with descriptions found for that city.")
        return
    print(f"Embedding {len(listings)} listings + the query via OpenAI...\n")

    # Embed the query and every listing, then rank by meaning.
    query_vec = get_embedding(query)
    by_id = {row["L_ListingID"]: row for row in listings}
    embeddings = [(row["L_ListingID"], get_embedding(build_listing_text(row)))
                  for row in listings]

    print("Top 5 matches by meaning:\n")
    for rank, (lid, score) in enumerate(find_similar(query_vec, embeddings, top_k=5), 1):
        row = by_id[lid]
        remarks = (row.get("L_Remarks") or "")[:110].replace("\n", " ")
        price = row.get("L_SystemPrice") or 0
        print(f"{rank}. [{score:.3f}] {row['L_Address']} — ${price:,} "
              f"({row.get('L_Keyword2','?')}bd)")
        print(f"     {remarks}...\n")


if __name__ == "__main__":
    main()
