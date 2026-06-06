"""Pricing helpers (seed version with one deliberate bug)."""


def apply_discount(price, pct):
    # BUG: treats `pct` as an absolute amount to subtract rather than a
    # percentage. apply_discount(100, 10) should be 90.0, not 90 by coincidence
    # — apply_discount(200, 10) returns 190 instead of the correct 180.0.
    return price - pct


def line_total(price, qty):
    return price * qty
