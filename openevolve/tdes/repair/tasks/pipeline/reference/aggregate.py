"""Reference (correct) implementation — never shown to LLM mutator."""


def group_by(records: list, key: str) -> dict:
    groups = {}
    for r in records:
        k = r.get(key)
        groups.setdefault(k, []).append(r)
    return groups


def aggregate(records: list, group_key: str = "category") -> list:
    groups = group_by(records, group_key)
    result = []
    for k, items in sorted(groups.items(), key=lambda x: str(x[0])):
        total = sum(item.get("quantity", 0) for item in items)
        result.append({"group": k, "total_quantity": total})
    return result
