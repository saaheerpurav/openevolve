"""
Data ingestion module — raw records to standardized dicts.

BUG: float(record["qty"]) crashes with TypeError when qty is None.
Fix: replace None with 0.0 before casting.
"""


def ingest(records: list) -> list:
    """Ingest raw records and standardize numeric fields."""
    cleaned = []
    for record in records:
        cleaned.append({
            "id": record.get("id"),
            "qty": float(record["qty"]),   # BUG: crashes on None
            "price": float(record.get("price", 0)),
            "date": record.get("date", ""),
            "category": record.get("category", ""),
        })
    return cleaned
