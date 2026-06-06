"""End-to-end order summary pipeline.

This module's own logic is correct; its integration/system tests only pass once
the `pricing` and `stats` modules it depends on are fixed. This is what gives
the example its test hierarchy: unit-level fixes cascade up to integration and
system correctness.
"""

import pricing
import stats


def summarize(orders):
    """Summarize a list of orders.

    Each order is a dict with keys: price, qty, discount_pct.
    """
    totals = []
    for o in orders:
        unit = pricing.apply_discount(o["price"], o["discount_pct"])
        totals.append(pricing.line_total(unit, o["qty"]))
    return {
        "total": sum(totals),
        "mean_line": stats.mean(totals),
        "median_line": stats.median(totals),
    }
