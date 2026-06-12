"""Variant manifest for the data-pipeline repair task.

Each variant is a bug-placement configuration over the three modules
(``ingest``/``transform``/``aggregate``): ``overrides`` maps a module to the
pre-written buggy source (relative to ``buggy/``) that replaces the reference
in the seed candidate; ``bugs`` documents every planted defect and the unit
test that catches it. ``kind`` is the experimental stratum:

  * ``split``     — bugs in *different* modules, so two candidates can hold
    complementary fixes (the crossover-favorable stratum).
  * ``colocated`` — comparable bugs concentrated in *one* module (control
    stratum: complementary-coverage crossover should be neutral).

The bugs are calibrated to resist one-look repair: docstrings state what each
function does but not the edge rule the bug violates (unit-test descriptions
and CEGIS counterexamples are the only channel for edge semantics), the
failing inputs are sequences whose generating rule is under-determined by a
single example, and each buggy function sits next to guard-tested behaviors
that a careless full-module rewrite breaks. Three reference behaviors are
deliberately non-canonical and pinned only by always-green guard tests, so
the textbook fix regresses: int fields accept integral-valued decimal text
(``int(text)`` rewrites fail ``u_ingest_numeric_shapes``), ``top_k`` ranks
non-numeric fields (``(-value, tie)`` rewrites fail ``u_agg_top_k_labels``),
and the dedup window boundary is exercised only by ``u_transform_dedup_spread``
(the failing stream is consistent with both strict and inclusive boundaries).
"""

MODULES = ["ingest", "transform", "aggregate"]

BUGS = {
    "I1": {
        "module": "ingest",
        "description": (
            "split_fields treats a doubled quote inside a quoted field as "
            "close-then-reopen instead of an escaped literal quote, silently "
            "dropping the quote character"
        ),
        "caught_by": "u_ingest_quoted",
    },
    "I2": {
        "module": "ingest",
        "description": (
            "int coercion goes through float() and truncates, so records with "
            "fractional values in int fields are kept (with corrupted values) "
            "instead of rejected"
        ),
        "caught_by": "u_ingest_rejects_bad_numerics",
    },
    "T1": {
        "module": "transform",
        "description": (
            "window_dedup refreshes the suppression window on every occurrence "
            "(state carryover from suppressed rows) instead of measuring it "
            "from the last emitted occurrence"
        ),
        "caught_by": "u_transform_window_dedup",
    },
    "T2": {
        "module": "transform",
        "description": (
            "enrich builds its lookup index by overwriting, so the LAST "
            "duplicate lookup entry wins instead of the first"
        ),
        "caught_by": "u_transform_enrich_duplicates",
    },
    "A1": {
        "module": "aggregate",
        "description": (
            "weighted_mean skips None values in the numerator but still adds "
            "their weights to the denominator (wrong denominator)"
        ),
        "caught_by": "u_agg_weighted_mean",
    },
    "A2": {
        "module": "aggregate",
        "description": (
            "top_k sorts (field, tie_field) with reverse=True, so the "
            "secondary tie-break runs descending instead of ascending"
        ),
        "caught_by": "u_agg_top_k_ties",
    },
}

VARIANTS = {
    "v1_split": {
        "kind": "split",
        "bugs": ["I1", "T1"],
        "overrides": {"ingest": "ingest_i1.py", "transform": "transform_t1.py"},
    },
    "v2_split": {
        "kind": "split",
        "bugs": ["T2", "A1"],
        "overrides": {"transform": "transform_t2.py", "aggregate": "aggregate_a1.py"},
    },
    "v3_split": {
        "kind": "split",
        "bugs": ["I2", "A2"],
        "overrides": {"ingest": "ingest_i2.py", "aggregate": "aggregate_a2.py"},
    },
    "v4_split": {
        "kind": "split",
        "bugs": ["I1", "T2", "A2"],
        "overrides": {
            "ingest": "ingest_i1.py",
            "transform": "transform_t2.py",
            "aggregate": "aggregate_a2.py",
        },
    },
    "v5_coloc": {
        "kind": "colocated",
        "bugs": ["T1", "T2"],
        "overrides": {"transform": "transform_t1_t2.py"},
    },
    "v6_coloc": {
        "kind": "colocated",
        "bugs": ["A1", "A2"],
        "overrides": {"aggregate": "aggregate_a1_a2.py"},
    },
}
