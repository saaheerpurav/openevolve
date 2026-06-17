"""Transform stage: order-preserving cleanup passes over lists of row dicts.

Every pass returns a new list; input rows are never mutated. Rows are plain
dicts and may carry None for missing values.
"""


def window_dedup(rows, key, window=None):
    """Suppress rows whose ``row[key]`` repeated too recently; ``window``
    controls how recent still counts as a repeat. ``window=None``
    deduplicates over the whole stream."""
    out = []
    recent = {}
    for i, row in enumerate(rows):
        k = row.get(key)
        prev = recent.get(k)
        if prev is not None and (window is None or i - prev <= window):
            continue
        recent[k] = i
        out.append(row)
    return out


def filter_ranges(rows, conditions):
    """Keep rows that satisfy every ``(field, lo, hi)`` condition; a None
    bound leaves that side open."""
    out = []
    for row in rows:
        ok = True
        for field, lo, hi in conditions:
            v = row.get(field)
            if v is None:
                ok = False
                break
            if lo is not None and v < lo:
                ok = False
                break
            if hi is not None and v > hi:
                ok = False
                break
        if ok:
            out.append(row)
    return out


def enrich(rows, lookup, key, fields):
    """Fill in ``fields`` on each row from the lookup entry whose ``key``
    matches the row's."""
    index = {}
    for entry in lookup:
        index[entry.get(key)] = entry
    out = []
    for row in rows:
        new = dict(row)
        match = index.get(new.get(key))
        if match is not None:
            for f in fields:
                if new.get(f) is None:
                    new[f] = match.get(f)
        out.append(new)
    return out


def coalesce(rows, target, sources):
    """Fill a missing ``target`` field from the first usable ``sources``
    field."""
    out = []
    for row in rows:
        new = dict(row)
        value = new.get(target)
        if value is None:
            for s in sources:
                if new.get(s) is not None:
                    value = new.get(s)
                    break
        new[target] = value
        out.append(new)
    return out


def project(rows, fields):
    """Restrict each row to ``fields``, in the given order."""
    return [{f: row.get(f) for f in fields} for row in rows]
