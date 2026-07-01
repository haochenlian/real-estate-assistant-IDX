"""
Natural-language property query parser (Week 2).

Converts a free-text real-estate request such as
    "Show me 3-bedroom condos in Irvine under $1.5M with a pool"
into a structured filter object that maps to `rets_property` columns.

This is the natural-language front end for the database layer built in Week 3.

Field mapping (rets_property):
    city        -> L_City
    max_price   -> L_SystemPrice
    beds (min)  -> L_Keyword2
    baths (min) -> LM_Dec_3
    sqft (min)  -> LM_Int2_3
    type        -> L_Type_
    pool        -> PoolPrivateYN
    has_view    -> ViewYN
    max_hoa     -> AssociationFee

Author: Howard (Haochen) Lian — IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import re
from typing import Optional


# Free-text keyword -> canonical rets_property L_Type_ value
TYPE_MAP = {
    "condo": "Condominium",
    "condominium": "Condominium",
    "townhome": "Townhouse",
    "townhouse": "Townhouse",
    "single family": "SingleFamilyResidence",
    "single-family": "SingleFamilyResidence",
    "house": "SingleFamilyResidence",
    "land": "UnimprovedLand",
}

# Word tokens that mark the end of a city name in "... in <City> ..."
_CITY_WORDS = r"under|below|less|with|without|that|for|priced|around|near|and|at|up|to"


def _parse_price(raw: str, suffix: Optional[str]) -> int:
    """Turn a matched price string like '1.5' + 'm' into an integer dollar amount."""
    value = float(raw.replace(",", ""))
    if suffix:
        s = suffix.lower()
        if s == "k":
            value *= 1_000
        elif s == "m":
            value *= 1_000_000
    return int(value)


def parse_property_query(query: str) -> dict:
    """Parse a free-text property query into a structured filter dict.

    Returns a dict with keys: city, max_price, beds, baths, sqft, type,
    pool, has_view, max_hoa. Missing values are None.
    """
    q = query.strip()
    ql = q.lower()

    filters: dict = {
        "city": None,
        "max_price": None,
        "beds": None,
        "baths": None,
        "sqft": None,
        "type": None,
        "pool": None,
        "has_view": None,
        "max_hoa": None,
    }

    # --- City: "in <City>" up to a stop word / symbol / number ---
    city_match = re.search(
        rf"\bin\s+([a-z][a-z\s]+?)(?=\s+(?:{_CITY_WORDS})\b|\s+\$|\s+\d|[,\.]|$)",
        ql,
    )
    if city_match:
        # Recover original casing from the source query span
        start, end = city_match.start(1), city_match.end(1)
        filters["city"] = q[start:end].strip().title()

    # --- Max HOA: must be checked before generic price ---
    hoa_match = re.search(r"hoa[^0-9$]*\$?([\d,]+)", ql)
    if hoa_match:
        filters["max_hoa"] = _parse_price(hoa_match.group(1), None)

    # --- Max price: "under/below/less than $1.5m" ---
    price_match = re.search(
        r"(?:under|below|less than|max(?:imum)?|up to)\s*\$?([\d,.]+)\s*(k|m)?",
        ql,
    )
    if price_match:
        filters["max_price"] = _parse_price(price_match.group(1), price_match.group(2))

    # --- Bedrooms (minimum) ---
    beds_match = re.search(r"(\d+)\s*[-]?\s*(?:bed|beds|bedroom|bedrooms|br|bd)\b", ql)
    if beds_match:
        filters["beds"] = int(beds_match.group(1))

    # --- Bathrooms (minimum, supports half-baths e.g. 2.5) ---
    baths_match = re.search(r"(\d+(?:\.5)?)\s*[-]?\s*(?:bath|baths|bathroom|bathrooms|ba)\b", ql)
    if baths_match:
        filters["baths"] = float(baths_match.group(1))

    # --- Square footage (minimum) ---
    sqft_match = re.search(r"([\d,]+)\+?\s*(?:sqft|sq\s*ft|square\s*feet|sf)\b", ql)
    if sqft_match:
        filters["sqft"] = int(sqft_match.group(1).replace(",", ""))

    # --- Property type ---
    for key in sorted(TYPE_MAP, key=len, reverse=True):
        if key in ql:
            filters["type"] = TYPE_MAP[key]
            break

    # --- Pool / View flags ---
    if "pool" in ql:
        filters["pool"] = "True"
    if "view" in ql or "ocean" in ql or "mountain" in ql:
        filters["has_view"] = "True"

    return filters


if __name__ == "__main__":
    import json

    demo = "Show me 3-bedroom condos in Irvine under $1.5M with a pool"
    print("Query :", demo)
    print("Filter:", json.dumps(parse_property_query(demo), indent=2))
