"""Reference (correct) implementation — never shown to LLM mutator."""


def parse_date(date_str: str) -> str:
    """Parse 'YYYY-MM-DD' and return 'MM-DD'."""
    parts = date_str.split("-")
    month = int(parts[1])
    day = int(parts[2])
    return f"{month:02d}-{day:02d}"


def transform(records: list) -> list:
    """Rename raw fields to the canonical schema and parse dates."""
    result = []
    for r in records:
        result.append({
            "id": r.get("id"),
            "quantity": r.get("qty"),
            "price": r.get("price"),
            "date": parse_date(r.get("date", "2024-01-01")),
            "category": r.get("category"),
        })
    return result
