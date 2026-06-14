"""Reference (correct) implementation — never shown to LLM mutator."""


def ingest(records: list) -> list:
    """Ingest raw records and standardize numeric fields."""
    cleaned = []
    for record in records:
        qty = record.get("qty")
        cleaned.append({
            "id": record.get("id"),
            "qty": float(qty) if qty is not None else 0.0,
            "price": float(record.get("price", 0)),
            "date": record.get("date", ""),
            "category": record.get("category", ""),
        })
    return cleaned
