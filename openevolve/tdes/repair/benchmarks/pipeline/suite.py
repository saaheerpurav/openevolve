"""Hierarchical TDES test suite for the data-pipeline repair task.

Three modules — ``ingest`` (CSV-dialect parsing with quoting and typed
schemas), ``transform`` (windowed dedup, multi-key range filtering, lookup
enrichment), ``aggregate`` (weighted grouped statistics, tie-broken top-k,
percentiles) — with UNIT tests per module (each catalogued bug in
``manifest.BUGS`` is caught by at least one unit test of its own module,
which is what routes complementary-coverage crossover), always-green guard
unit tests that make rewrite regressions visible, INTEGRATION tests over
stage pairs, and SYSTEM tests over the full feed -> report chain that are
sensitive to every catalogued bug.

All expected values were computed by executing the reference modules.
Loaded via ``TDESTestSuite.load_from_file`` (required for sandboxed runs).
"""

from openevolve.tdes import TDESTestSuite

suite = TDESTestSuite(modules=["ingest", "transform", "aggregate"])

SCHEMA = [("id", "str"), ("region", "str"), ("score", "float"), ("units", "int")]


# --- Unit: ingest -----------------------------------------------------------
@suite.unit(
    "ingest",
    description="plain feed: typed fields, blank/comment/short lines skipped, "
    "empty fields missing",
)
def u_ingest_plain(env):
    lines = env.case(
        ["a-1,west,1.5,3", "  ", "# comment", 'a-2,"south, low",2.0,', "broken,row", "a-3,east,,4"]
    )
    rows = env.ingest.parse_records(lines, SCHEMA)
    env.check_equal(env.ingest.column(rows, "id"), ["a-1", "a-2", "a-3"])
    env.check_equal(rows[0]["score"], 1.5)
    env.check_equal(rows[0]["units"], 3)
    env.check_equal(rows[1]["region"], "south, low")
    env.check(rows[1]["units"] is None, "empty trailing field must be missing")
    env.check(rows[2]["score"] is None, "empty mid-row field must be missing")


@suite.unit(
    "ingest",
    description="quoted fields carrying separators and quote characters parse "
    "back to the exact original text",
)
def u_ingest_quoted(env):
    lines = env.case(
        ['"r-100","west, upper",4.5,2', '"r-101","east ""hub"" annex",3.25,1', "r-102,north,8.0,5"]
    )
    rows = env.ingest.parse_records(lines, SCHEMA)
    env.check_equal(
        env.ingest.column(rows, "region"),
        ["west, upper", 'east "hub" annex', "north"],
    )
    env.check_equal(env.ingest.column(rows, "id"), ["r-100", "r-101", "r-102"])


@suite.unit(
    "ingest",
    description="records whose fields do not conform to the declared schema "
    "kinds are rejected whole",
)
def u_ingest_rejects_bad_numerics(env):
    lines = env.case(
        [
            "b-1,west,3.5,2",
            "b-2,west,oops,3",
            "b-3,east,4.0,2.5",
            "b-4,east,1e2,4",
            "b-5,south,2.25,008",
        ]
    )
    rows = env.ingest.parse_records(lines, SCHEMA)
    env.check_equal(env.ingest.column(rows, "id"), ["b-1", "b-4", "b-5"])
    env.check_equal(env.ingest.column(rows, "units"), [2, 4, 8])
    env.check_equal(env.ingest.column(rows, "score"), [3.5, 100.0, 2.25])


@suite.unit(
    "ingest",
    description="numeric fields tolerate the feed's recurring formatting quirks",
)
def u_ingest_numeric_shapes(env):
    lines = env.case(["n-1,west,2.5,4.0", "n-2,east,3.0,12", "n-3,south,1e1,2e1"])
    rows = env.ingest.parse_records(lines, SCHEMA)
    env.check_equal(env.ingest.column(rows, "id"), ["n-1", "n-2", "n-3"])
    env.check_equal(env.ingest.column(rows, "units"), [4, 12, 20])
    env.check_equal(env.ingest.column(rows, "score"), [2.5, 3.0, 10.0])


@suite.unit(
    "ingest",
    description="fields quoted only in part still parse as single fields",
)
def u_ingest_partial_quotes(env):
    lines = env.case(['k-1,plan "b, mid",4.5,2', 'k-2,ad"hoc,futures",1.0,1'])
    rows = env.ingest.parse_records(lines, SCHEMA)
    env.check_equal(env.ingest.column(rows, "region"), ["plan b, mid", "adhoc,futures"])
    env.check_equal(env.ingest.column(rows, "units"), [2, 1])


@suite.unit("ingest", description="flag fields and empty fields coerce per the schema")
def u_ingest_flags_empty(env):
    schema = [("id", "str"), ("active", "flag"), ("score", "float")]
    lines = env.case(["f-1,YES,1.0", "f-2,0,2.0", "f-3,,3.0"])
    rows = env.ingest.parse_records(lines, schema)
    env.check_equal(env.ingest.column(rows, "active"), [True, False, None])
    env.check(env.ingest.coerce(env.case("   "), "int") is None, "blank field must be missing")


# --- Unit: transform --------------------------------------------------------
@suite.unit("transform", description="whole-stream dedup keeps one row per key, in order")
def u_transform_global_dedup(env):
    rows = env.case([{"id": "x", "v": 1}, {"id": "y", "v": 2}, {"id": "x", "v": 3}])
    kept = env.transform.window_dedup(rows, "id")
    env.check_equal([r["id"] for r in kept], ["x", "y"])
    env.check_equal(kept[0]["v"], 1)


@suite.unit(
    "transform",
    description="windowed dedup of a bursty key stream keeps the right occurrences",
)
def u_transform_window_dedup(env):
    events = env.case(
        [
            {"ev": "e0", "key": "a"},
            {"ev": "e1", "key": "b"},
            {"ev": "e2", "key": "a"},
            {"ev": "e3", "key": "b"},
            {"ev": "e4", "key": "c"},
            {"ev": "e5", "key": "a"},
            {"ev": "e6", "key": "c"},
            {"ev": "e7", "key": "b"},
        ]
    )
    kept = env.transform.window_dedup(events, "key", window=3)
    env.check_equal([r["ev"] for r in kept], ["e0", "e1", "e4", "e5", "e7"])


@suite.unit(
    "transform",
    description="windowed dedup behaves on a sparse, spread-out key stream",
)
def u_transform_dedup_spread(env):
    rows = env.case(
        [
            {"ev": "g0", "key": "x"},
            {"ev": "g1", "key": "y"},
            {"ev": "g2", "key": "x"},
            {"ev": "g3", "key": "z"},
            {"ev": "g4", "key": "y"},
        ]
    )
    kept = env.transform.window_dedup(rows, "key", window=2)
    env.check_equal([r["ev"] for r in kept], ["g0", "g1", "g3", "g4"])


@suite.unit(
    "transform",
    description="enrich is deterministic when the lookup table contains duplicate keys",
)
def u_transform_enrich_duplicates(env):
    rows = [{"sku": "p1", "cost": None}, {"sku": "p2", "cost": None}]
    lookup = env.case(
        [{"sku": "p1", "cost": 5}, {"sku": "p1", "cost": 9}, {"sku": "p2", "cost": 4}]
    )
    out = env.transform.enrich(rows, lookup, "sku", ["cost"])
    env.check_equal([r["cost"] for r in out], [5, 4])


@suite.unit(
    "transform",
    description="enrich fills only what is missing and never mutates its input",
)
def u_transform_enrich_fill(env):
    rows = env.case(
        [
            {"sku": "q1", "cost": 7, "origin": None},
            {"sku": "q2", "cost": None, "origin": "x"},
            {"sku": "q9", "cost": None, "origin": None},
        ]
    )
    lookup = [{"sku": "q1", "cost": 1, "origin": "a"}, {"sku": "q2", "cost": 2, "origin": "b"}]
    out = env.transform.enrich(rows, lookup, "sku", ["cost", "origin"])
    env.check_equal([r["cost"] for r in out], [7, 2, None], "present values are kept")
    env.check_equal([r["origin"] for r in out], ["a", "x", None])
    env.check(rows[0]["origin"] is None, "input rows must not be mutated")


@suite.unit(
    "transform",
    description="range filtering over several fields, plus coalesce fallbacks",
)
def u_transform_filter_coalesce(env):
    rows = env.case([{"v": 1, "w": 10}, {"v": 5, "w": 3}, {"v": None, "w": 2}, {"v": 7, "w": None}])
    kept = env.transform.filter_ranges(rows, [("v", 1, 5), ("w", 3, None)])
    env.check_equal([r["v"] for r in kept], [1, 5])
    pairs = env.case([{"a": None, "b": None, "c": 3}, {"a": 4, "b": 9, "c": 1}])
    env.check_equal([r["a"] for r in env.transform.coalesce(pairs, "a", ["b", "c"])], [3, 4])
    env.check_equal(
        env.transform.project(pairs, ["a", "c"]), [{"a": None, "c": 3}, {"a": 4, "c": 1}]
    )


# --- Unit: aggregate --------------------------------------------------------
@suite.unit(
    "aggregate",
    description="weighted mean over a batch with missing values and zero weights",
)
def u_agg_weighted_mean(env):
    rows = env.case(
        [
            {"v": 10.0, "w": 2},
            {"v": None, "w": 5},
            {"v": 4.0, "w": 3},
            {"v": 6.0, "w": 0},
            {"v": 2.0, "w": None},
        ]
    )
    env.check_close(env.aggregate.weighted_mean(rows, "v", "w"), 6.4)


@suite.unit(
    "aggregate",
    description="top_k ranks tied values deterministically using the tie field",
)
def u_agg_top_k_ties(env):
    rows = env.case(
        [
            {"id": "a", "score": 5.0, "cost": 7},
            {"id": "b", "score": 9.0, "cost": 4},
            {"id": "c", "score": 5.0, "cost": 2},
            {"id": "d", "score": 5.0, "cost": 2},
            {"id": "e", "score": None, "cost": 1},
        ]
    )
    picked = env.aggregate.top_k(rows, "score", 3, tie_field="cost")
    env.check_equal([r["id"] for r in picked], ["b", "c", "d"])


@suite.unit("aggregate", description="rankings work over label-valued fields too")
def u_agg_top_k_labels(env):
    rows = env.case(
        [
            {"id": "w1", "tier": "gold", "cost": 3},
            {"id": "w2", "tier": "bronze", "cost": 1},
            {"id": "w3", "tier": "silver", "cost": 2},
        ]
    )
    picked = env.aggregate.top_k(rows, "tier", 2, tie_field="cost")
    env.check_equal([r["id"] for r in picked], ["w3", "w1"])


@suite.unit("aggregate", description="percentiles interpolate over the usable values")
def u_agg_percentile(env):
    env.check_close(env.aggregate.percentile(env.case([4.0, 1.0, 3.0, 2.0]), 50), 2.5)
    env.check_close(env.aggregate.percentile(env.case([1.0, None, 3.0]), 100), 3.0)
    env.check_close(env.aggregate.percentile(env.case([1.0, 2.0, 3.0, 4.0]), 25), 1.75)
    env.check_close(env.aggregate.percentile(env.case([5.0]), 10), 5.0)
    env.check(env.aggregate.percentile(env.case([]), 50) is None)


@suite.unit(
    "aggregate",
    description="grouping preserves first-seen order; degenerate weights and "
    "untied rankings behave",
)
def u_agg_grouping(env):
    rows = env.case(
        [{"g": "x", "v": 1.0, "w": 1}, {"g": "y", "v": 2.0, "w": 2}, {"g": "x", "v": 3.0, "w": 1}]
    )
    env.check_equal(list(env.aggregate.group_rows(rows, "g")), ["x", "y"])
    env.check_equal(env.aggregate.group_weighted_means(rows, "g", "v", "w"), {"x": 2.0, "y": 2.0})
    env.check(
        env.aggregate.weighted_mean(env.case([{"v": 1.0, "w": 0}]), "v", "w") is None,
        "all-zero weights leave nothing to average",
    )
    env.check_equal(
        [
            r["v"]
            for r in env.aggregate.top_k(env.case([{"v": 1.0}, {"v": 3.0}, {"v": 2.0}]), "v", 2)
        ],
        [3.0, 2.0],
    )


# --- Integration ------------------------------------------------------------
@suite.integration(
    "transform",
    modules=["ingest", "transform"],
    description="parsed feed survives windowed dedup and range filtering with "
    "the right rows intact",
)
def i_ingest_transform(env):
    lines = env.case(
        [
            "s-1,west,4.0,2",
            "s-2,east,6.5,1",
            "s-1,west,4.0,2",
            "s-3,north,2.0,3",
            "s-1,west,5.0,1",
            "bad line",
        ]
    )
    rows = env.ingest.parse_records(lines, SCHEMA)
    rows = env.transform.window_dedup(rows, "id", window=2)
    rows = env.transform.filter_ranges(rows, [("score", 2.0, 6.0)])
    env.check_equal(env.ingest.column(rows, "id"), ["s-1", "s-3", "s-1"])
    env.check_equal(env.ingest.column(rows, "score"), [4.0, 2.0, 5.0])


@suite.integration(
    "aggregate",
    modules=["transform", "aggregate"],
    description="deduped, enriched event batch yields the expected grouped " "means and ranking",
)
def i_transform_aggregate(env):
    events = [
        {"id": "m1", "grp": "x", "score": 4.0, "units": 2, "cost": None},
        {"id": "m2", "grp": "x", "score": None, "units": 3, "cost": 5},
        {"id": "m1", "grp": "x", "score": 4.0, "units": 2, "cost": None},
        {"id": "m3", "grp": "y", "score": 8.0, "units": 1, "cost": 2},
        {"id": "m1", "grp": "x", "score": 6.0, "units": 2, "cost": None},
        {"id": "m4", "grp": "y", "score": 8.0, "units": 1, "cost": 1},
    ]
    lookup = [{"id": "m1", "cost": 3}, {"id": "m1", "cost": 9}, {"id": "m2", "cost": 6}]
    env.case({"events": events, "lookup": lookup})
    rows = env.transform.window_dedup(events, "id", window=3)
    rows = env.transform.enrich(rows, lookup, "id", ["cost"])
    env.check_equal([r["id"] for r in rows], ["m1", "m2", "m3", "m1", "m4"])
    env.check_equal([r["cost"] for r in rows], [3, 5, 2, 3, 1])
    means = env.aggregate.group_weighted_means(rows, "grp", "score", "units")
    env.check_close(means["x"], 5.0)
    env.check_close(means["y"], 8.0)
    picked = env.aggregate.top_k(rows, "score", 3, tie_field="cost")
    env.check_equal([r["id"] for r in picked], ["m4", "m3", "m1"])


# --- System -----------------------------------------------------------------
_REPORT_LINES = [
    "o-1,west,7.5,2",
    'o-2,"east ""dock"" 9",6.0,3',
    "o-3,west,,4",
    "o-1,west,7.5,2",
    "o-4,south,9.0,1.5",
    "o-5,west,6.0,1",
    "o-1,west,8.0,2",
    "# nightly batch",
    'o-6,"east ""dock"" 9",6.0,2',
    "o-7,south,4.0,2",
    "garbage line",
    "o-5,west,6.0,1",
]

_REGION_COSTS = [
    {"region": "west", "cost": 5},
    {"region": "west", "cost": 11},
    {"region": 'east "dock" 9', "cost": 3},
    {"region": "south", "cost": 8},
]


@suite.system(
    "aggregate",
    modules=["ingest", "transform", "aggregate"],
    description="end-to-end shipment report: parse, window-dedup, enrich with "
    "region costs, filter, grouped weighted means and top-3",
)
def s_shipment_report(env):
    env.case(_REPORT_LINES)
    parsed = env.ingest.parse_records(_REPORT_LINES, SCHEMA)
    env.check_equal(len(parsed), 9, "exactly the conforming records are ingested")
    deduped = env.transform.window_dedup(parsed, "id", window=4)
    env.check_equal(
        env.ingest.column(deduped, "id"),
        ["o-1", "o-2", "o-3", "o-5", "o-1", "o-6", "o-7"],
    )
    enriched = env.transform.enrich(deduped, _REGION_COSTS, "region", ["cost"])
    filtered = env.transform.filter_ranges(enriched, [("cost", 1, 10)])
    env.check_equal(
        sorted(env.aggregate.group_rows(filtered, "region")),
        ['east "dock" 9', "south", "west"],
    )
    means = env.aggregate.group_weighted_means(filtered, "region", "score", "units")
    env.check_close(means["west"], 7.4)
    env.check_close(means['east "dock" 9'], 6.0)
    env.check_close(means["south"], 4.0)
    picked = env.aggregate.top_k(filtered, "score", 3, tie_field="units")
    env.check_equal([r["id"] for r in picked], ["o-1", "o-1", "o-5"])


_AUDIT_LINES = [
    "v-1,north,5.0,2",
    '"v-2 ""beta""",north,5.0,1',
    "v-3,west,6.5,2",
    "v-1,north,4.0,2",
    "",
    "v-4,west,,3",
    "v-5,south,7.0,1.2",
    "v-1,north,3.0,1",
    "v-6,west,5.0,2",
    "#audit",
    "v-7,south,2.0,2",
    "not,a,record",
]

_VENDOR_COSTS = [
    {"id": "v-3", "cost": 4},
    {"id": "v-3", "cost": 12},
    {"id": "v-6", "cost": 4},
    {"id": "v-1", "cost": 2},
    {"id": 'v-2 "beta"', "cost": 6},
    {"id": "v-4", "cost": 1},
    {"id": "v-5", "cost": 3},
    {"id": "v-7", "cost": 9},
]


@suite.system(
    "ingest",
    modules=["ingest", "transform", "aggregate"],
    description="end-to-end vendor audit: noisy feed to overall weighted score, "
    "cost-tie-broken top-4 and median",
)
def s_vendor_audit(env):
    env.case(_AUDIT_LINES)
    parsed = env.ingest.parse_records(_AUDIT_LINES, SCHEMA)
    env.check_equal(
        env.ingest.column(parsed, "id"),
        ["v-1", 'v-2 "beta"', "v-3", "v-1", "v-4", "v-1", "v-6", "v-7"],
    )
    deduped = env.transform.window_dedup(parsed, "id", window=3)
    env.check_equal(
        env.ingest.column(deduped, "id"),
        ["v-1", 'v-2 "beta"', "v-3", "v-4", "v-1", "v-6", "v-7"],
    )
    enriched = env.transform.enrich(deduped, _VENDOR_COSTS, "id", ["cost"])
    env.check_equal(env.ingest.column(enriched, "cost"), [2, 6, 4, 1, 2, 4, 9])
    env.check_close(env.aggregate.weighted_mean(enriched, "score", "units"), 4.5)
    picked = env.aggregate.top_k(enriched, "score", 4, tie_field="cost")
    env.check_equal([r["id"] for r in picked], ["v-3", "v-1", "v-6", 'v-2 "beta"'])
    env.check_close(env.aggregate.percentile(env.ingest.column(enriched, "score"), 50), 5.0)
