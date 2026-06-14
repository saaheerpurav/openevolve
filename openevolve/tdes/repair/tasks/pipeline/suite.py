"""
Pipeline repair test suite — 3 unit + 2 integration + 1 system test.

Bugs seeded:
  ingest.py   : float(record["qty"]) crashes on None
  transform.py: parse_date reads parts[0] (year) instead of parts[1] (month);
                transform() emits "count" instead of "quantity"
  aggregate.py: group_by ignores key param (always uses "id");
                aggregate() sums quantity + price instead of quantity

Bug independence: ingest unit test only calls ingest; transform unit test only
calls parse_date (no ingest). A candidate that fixes ingest but not transform
passes the ingest unit test and fails the transform unit test — complementary
coverage arises naturally and crossover can combine partial repairs.
"""

from openevolve.tdes.test_suite import TDESTestSuite, TestEnv

suite = TDESTestSuite(modules=["ingest", "transform", "aggregate"])


# ── UNIT TESTS ────────────────────────────────────────────────────────────────

@suite.unit("ingest", description="ingest converts None qty to 0.0 instead of crashing")
def test_ingest_none(env: TestEnv):
    records = [
        {"id": 1, "qty": 10, "price": 2.0, "date": "2024-06-15", "category": "A"},
        {"id": 2, "qty": None, "price": 3.0, "date": "2024-03-10", "category": "B"},
    ]
    env.case(records)
    result = env.ingest.ingest(records)
    env.check_equal(len(result), 2)
    env.check_equal(result[0]["qty"], 10.0)
    env.check_equal(result[1]["qty"], 0.0, "None qty should become 0.0")


@suite.unit("transform", description="parse_date extracts month (index 1) not year (index 0)")
def test_transform_parse_date(env: TestEnv):
    env.case("2024-06-15")
    result = env.transform.parse_date("2024-06-15")
    env.check_equal(result, "06-15", "2024-06-15 should parse to 06-15")


@suite.unit("aggregate", description="aggregate groups by the provided key, not hardcoded 'id'")
def test_aggregate_groupby_key(env: TestEnv):
    records = [
        {"id": 1, "quantity": 5, "price": 10.0, "category": "Electronics"},
        {"id": 2, "quantity": 3, "price": 8.0,  "category": "Electronics"},
        {"id": 3, "quantity": 7, "price": 5.0,  "category": "Books"},
    ]
    env.case(records)
    result = env.aggregate.aggregate(records, "category")
    groups = {r["group"]: r["total_quantity"] for r in result}
    env.check_equal(groups.get("Electronics"), 8, "Electronics: 5+3=8")
    env.check_equal(groups.get("Books"), 7, "Books: 7")


# ── INTEGRATION TESTS ─────────────────────────────────────────────────────────

@suite.integration(
    "ingest",
    modules=["ingest", "transform"],
    description="ingest None-handling flows into transform's field renaming",
)
def test_ingest_then_transform(env: TestEnv):
    raw = [
        {"id": 1, "qty": 10, "price": 2.0, "date": "2024-06-15", "category": "A"},
        {"id": 2, "qty": None, "price": 3.0, "date": "2024-03-10", "category": "B"},
    ]
    env.case(raw)
    ingested = env.ingest.ingest(raw)
    transformed = env.transform.transform(ingested)
    # transform should emit "quantity" (not "count") and parse the date correctly
    env.check("quantity" in transformed[0], "transform should emit 'quantity' field")
    env.check_equal(transformed[1]["quantity"], 0.0, "None->0.0 should carry through transform")
    env.check_equal(transformed[0]["date"], "06-15", "date should be parsed as MM-DD")


@suite.integration(
    "transform",
    modules=["transform", "aggregate"],
    description="transform's 'quantity' field feeds aggregate's group sum",
)
def test_transform_then_aggregate(env: TestEnv):
    pre_ingested = [
        {"id": 1, "qty": 5.0, "price": 10.0, "date": "2024-06-15", "category": "Electronics"},
        {"id": 2, "qty": 3.0, "price": 8.0,  "date": "2024-03-20", "category": "Electronics"},
        {"id": 3, "qty": 7.0, "price": 5.0,  "date": "2024-06-01", "category": "Books"},
    ]
    env.case(pre_ingested)
    transformed = env.transform.transform(pre_ingested)
    result = env.aggregate.aggregate(transformed, "category")
    groups = {r["group"]: r["total_quantity"] for r in result}
    env.check_equal(groups.get("Electronics"), 8, "Electronics: 5+3=8")
    env.check_equal(groups.get("Books"), 7, "Books: 7")


# ── SYSTEM TEST ───────────────────────────────────────────────────────────────

@suite.system(
    "aggregate",
    modules=["ingest", "transform", "aggregate"],
    description="end-to-end: raw records with None -> correct grouped totals",
)
def test_end_to_end(env: TestEnv):
    raw = [
        {"id": 1, "qty": 10,   "price": 2.0, "date": "2024-06-15", "category": "Electronics"},
        {"id": 2, "qty": None, "price": 3.0, "date": "2024-03-10", "category": "Books"},
        {"id": 3, "qty": 5,    "price": 4.0, "date": "2024-06-20", "category": "Electronics"},
    ]
    env.case(raw)
    ingested = env.ingest.ingest(raw)
    transformed = env.transform.transform(ingested)
    result = env.aggregate.aggregate(transformed, "category")
    groups = {r["group"]: r["total_quantity"] for r in result}
    env.check_equal(groups.get("Electronics"), 15, "Electronics: 10+5=15")
    env.check_equal(groups.get("Books"), 0, "Books: None->0.0")
