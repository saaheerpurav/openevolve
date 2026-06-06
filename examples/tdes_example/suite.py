"""
Hierarchical TDES test suite for the orders-pipeline example.

Defines unit, integration, and system tests over three modules (``stats``,
``pricing``, ``pipeline``) and an offline ``get_scripted_mutator()`` so the demo
runs without an LLM (``--scripted``).

Run it:
    python tdes-run.py examples/tdes_example/seed examples/tdes_example/suite.py \
        --scripted --gens 5 --no-sandbox
"""

from openevolve.tdes import ScriptedMutator, TDESTestSuite

suite = TDESTestSuite(modules=["stats", "pricing", "pipeline"])


# --- Unit tests -----------------------------------------------------------
@suite.unit("stats", description="mean of a list of numbers")
def test_mean(env):
    env.check_equal(env.stats.mean(env.case([1, 2, 3, 4])), 2.5)


@suite.unit("stats", description="median of an odd-length, unsorted list")
def test_median_odd(env):
    env.check_equal(env.stats.median(env.case([3, 1, 2])), 2)


@suite.unit("stats", description="median of an even-length, unsorted list")
def test_median_even(env):
    env.check_equal(env.stats.median(env.case([3, 1, 2, 4])), 2.5)


@suite.unit("pricing", description="apply a percentage discount to a price")
def test_apply_discount(env):
    env.check_equal(env.pricing.apply_discount(*env.case((200, 10))), 180.0)


@suite.unit("pricing", description="line total is price times quantity")
def test_line_total(env):
    env.check_equal(env.pricing.line_total(*env.case((5, 3))), 15)


# --- Integration tests ----------------------------------------------------
_ORDERS = [
    {"price": 200, "qty": 2, "discount_pct": 10},  # -> line 360
    {"price": 100, "qty": 1, "discount_pct": 0},  # -> line 100
    {"price": 100, "qty": 2, "discount_pct": 0},  # -> line 200
]


@suite.integration(
    "pipeline",
    modules=["pipeline", "pricing"],
    description="pipeline order total reflects discounts (depends on pricing)",
)
def test_pipeline_total(env):
    env.check_equal(env.pipeline.summarize(env.case(_ORDERS))["total"], 660)


# --- System tests ---------------------------------------------------------
@suite.system(
    "pipeline",
    modules=["pipeline", "pricing", "stats"],
    description="end-to-end summary: correct mean and median of line totals",
)
def test_pipeline_summary(env):
    result = env.pipeline.summarize(env.case(_ORDERS))
    env.check_equal(result["mean_line"], 220)
    env.check_equal(result["median_line"], 200)


# --- Offline scripted mutator --------------------------------------------
# Canonical fixes. The `stats` fix deliberately models a two-step search: the
# first attempt fixes `median` but regresses `mean` (rejected by the
# no-regression rule and recorded in negative memory); once the failure is in
# memory, the correct fix is proposed — demonstrating the semantic tabu list.

_STATS_CORRECT = """\
def mean(xs):
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def median(xs):
    n = len(xs)
    if n == 0:
        return 0.0
    s = sorted(xs)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2
"""

_STATS_WRONG = """\
def mean(xs):
    if not xs:
        return 0.0
    return sum(xs) / (len(xs) + 1)  # regression: off-by-one denominator


def median(xs):
    n = len(xs)
    if n == 0:
        return 0.0
    s = sorted(xs)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2
"""

_PRICING_CORRECT = """\
def apply_discount(price, pct):
    return price * (1 - pct / 100)


def line_total(price, qty):
    return price * qty
"""


def _fix(module, source, feedback, memory_text):
    if module == "stats":
        if memory_text:
            # We have already learned the naive fix regresses mean; fix both.
            return _STATS_CORRECT, "sort input in median, keep mean denominator correct"
        # First attempt: fix median but naively touch mean (will regress).
        return _STATS_WRONG, "sort input in median (also rewrote mean denominator)"
    if module == "pricing":
        return _PRICING_CORRECT, "scale price by (1 - pct/100) instead of subtracting pct"
    # pipeline logic is already correct; nothing to change.
    return None


def get_scripted_mutator():
    return ScriptedMutator(_fix)
