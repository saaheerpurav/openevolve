"""Basic statistics helpers (seed version with one deliberate bug)."""


def mean(xs):
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def median(xs):
    # BUG: the input is not sorted before indexing, so the median is wrong
    # for any unsorted sequence.
    n = len(xs)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2
