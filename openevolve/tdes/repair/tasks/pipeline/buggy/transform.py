"""
Field transformation module — rename fields, parse dates.

BUG A: parse_date uses parts[0] (the year) instead of parts[1] (the month).
BUG B: transform() maps qty to "count" instead of "quantity".
Both bugs are independent — fixing one does not fix the other.
"""


def parse_date(date_str: str) -> str:
    """Parse 'YYYY-MM-DD' and return 'MM-DD'."""
    parts = date_str.split("-")
    month = int(parts[0])   # BUG: index 0 is the year; should be parts[1]
    day = int(parts[2])
    return f"{month:02d}-{day:02d}"


def transform(records: list) -> list:
    """Rename raw fields to the canonical schema and parse dates."""
    result = []
    for r in records:
        result.append({
            "id": r.get("id"),
            "count": r.get("qty"),          # BUG: should be "quantity"
            "price": r.get("price"),
            "date": parse_date(r.get("date", "2024-01-01")),
            "category": r.get("category"),
        })
    return result
