"""Aggregate stage: grouped statistics and rankings over lists of row dicts.

Values may be None for missing data; the statistics here are defined over
the usable portion of their input.
"""


def group_rows(rows, key):
    """Group rows by ``row[key]``, preserving first-seen group order and
    within-group input order."""
    groups = {}
    for row in rows:
        groups.setdefault(row.get(key), []).append(row)
    return groups


def weighted_mean(rows, value_field, weight_field):
    """Weighted average of ``value_field`` under ``weight_field``; None when
    there is nothing to average."""
    num = 0.0
    den = 0.0
    for row in rows:
        v = row.get(value_field)
        w = row.get(weight_field)
        if v is None or w is None:
            continue
        num += v * w
        den += w
    if den == 0:
        return None
    return num / den


def group_weighted_means(rows, key, value_field, weight_field):
    """Per-group weighted mean of ``value_field``, keyed by group."""
    return {
        k: weighted_mean(group, value_field, weight_field)
        for k, group in group_rows(rows, key).items()
    }


def top_k(rows, field, k, tie_field=None):
    """The ``k`` best rows by ``field``, highest first. ``tie_field``
    settles equal values; rows missing ``field`` are not ranked."""
    eligible = [row for row in rows if row.get(field) is not None]
    if tie_field is None:
        ranked = sorted(eligible, key=lambda r: r[field], reverse=True)
    else:
        ranked = sorted(eligible, key=lambda r: (r[field], r[tie_field]), reverse=True)
    return ranked[:k]


def percentile(values, p):
    """The ``p``-th percentile (0..100) of the usable values, interpolating
    between the two nearest data points."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    rank = (p / 100.0) * (len(vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(vals) - 1)
    frac = rank - lo
    return vals[lo] * (1.0 - frac) + vals[hi] * frac
