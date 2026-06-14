"""
Aggregation module — group records and sum quantities.

BUG A: group_by uses hardcoded r.get("id") instead of r.get(key).
BUG B: aggregate() sums quantity + price instead of quantity alone.
Both bugs are independent.
"""


def group_by(records: list, key: str) -> dict:
    groups = {}
    for r in records:
        k = r.get("id")    # BUG: ignores the key parameter, always groups by "id"
        groups.setdefault(k, []).append(r)
    return groups


def aggregate(records: list, group_key: str = "category") -> list:
    groups = group_by(records, group_key)
    result = []
    for k, items in sorted(groups.items(), key=lambda x: str(x[0])):
        total = sum(
            item.get("quantity", 0) + item.get("price", 0)   # BUG: adds price too
            for item in items
        )
        result.append({"group": k, "total_quantity": total})
    return result
