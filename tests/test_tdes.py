"""
Unit tests for the TDES framework (openevolve/tdes).

These run fully offline (no LLM / no API key) using the in-process suite runner
and a scripted mutator. They verify each of the paper's mechanisms:
hierarchical selection, CEGIS feedback capture, complementary-coverage
crossover (accept on strict superset, reject on regression, skip when no
complementary coverage), negative memory windowing, and the end-to-end
generational controller.
"""

import importlib.util
import os
import tempfile
import unittest

from openevolve.tdes import (
    Candidate,
    NegativeMemory,
    ScriptedMutator,
    TDESConfig,
    TDESController,
    TDESTestSuite,
    TestLevel,
    load_seed_codebase,
)
from openevolve.tdes import selection
from openevolve.tdes.crossover import complementary_crossover
from openevolve.tdes.types import TestResult, TestVector

EXAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples",
    "tdes_example",
)


def make_vector(spec):
    """spec: iterable of (test_id, TestLevel, module, passed)."""
    v = TestVector()
    for tid, lvl, mod, passed in spec:
        v.results[tid] = TestResult(tid, lvl, mod, passed, f"desc {tid}")
    return v


# --------------------------------------------------------------------------
# TestVector + hierarchical selection (section 3.1)
# --------------------------------------------------------------------------
class TestVectorOrdering(unittest.TestCase):
    def test_score_key_is_system_integration_unit(self):
        v = make_vector(
            [
                ("u1", TestLevel.UNIT, "a", True),
                ("u2", TestLevel.UNIT, "a", False),
                ("i1", TestLevel.INTEGRATION, "b", True),
                ("s1", TestLevel.SYSTEM, "c", False),
            ]
        )
        self.assertEqual(v.score_key, (0, 1, 1))  # (system, integration, unit)

    def test_system_pass_outranks_many_unit_passes(self):
        many_unit = make_vector([(f"u{i}", TestLevel.UNIT, "a", True) for i in range(10)])
        one_system = make_vector([("s1", TestLevel.SYSTEM, "c", True)])
        ranked = selection.rank(
            [
                many_unit_c := Candidate({}, vector=many_unit),
                one_system_c := Candidate({}, vector=one_system),
            ]
        )
        self.assertIs(ranked[0], one_system_c)
        self.assertIs(ranked[1], many_unit_c)

    def test_superset_relations(self):
        small = make_vector([("a", TestLevel.UNIT, "m", True), ("b", TestLevel.UNIT, "m", False)])
        big = make_vector([("a", TestLevel.UNIT, "m", True), ("b", TestLevel.UNIT, "m", True)])
        self.assertTrue(big.is_strict_superset_of(small))
        self.assertTrue(big.is_superset_of(small))
        self.assertFalse(small.is_strict_superset_of(big))
        self.assertTrue(big.is_superset_of(big))
        self.assertFalse(big.is_strict_superset_of(big))

    def test_complementary_set(self):
        a = make_vector([("a", TestLevel.UNIT, "m", True), ("b", TestLevel.UNIT, "m", False)])
        b = make_vector([("a", TestLevel.UNIT, "m", False), ("b", TestLevel.UNIT, "m", True)])
        self.assertEqual(b.complementary_to(a), {"b"})
        self.assertEqual(a.complementary_to(b), {"a"})


# --------------------------------------------------------------------------
# Negative exemplar memory (section 3.4)
# --------------------------------------------------------------------------
class NegativeMemoryTests(unittest.TestCase):
    def test_sliding_window_evicts_oldest(self):
        mem = NegativeMemory(window_size=2)
        mem.record("m", 1, "approach1", "fail1")
        mem.record("m", 2, "approach2", "fail2")
        mem.record("m", 3, "approach3", "fail3")
        entries = mem.entries("m")
        self.assertEqual(len(entries), 2)
        self.assertEqual([e.generation for e in entries], [2, 3])

    def test_render_includes_reason_and_input(self):
        mem = NegativeMemory(window_size=3)
        mem.record("price_calc", 1, "recursive memoization", "stack overflow", "input > 1000")
        rendered = mem.render("price_calc")
        self.assertIn("price_calc", rendered)
        self.assertIn("recursive memoization", rendered)
        self.assertIn("stack overflow", rendered)
        self.assertIn("input > 1000", rendered)

    def test_empty_render(self):
        self.assertEqual(NegativeMemory().render("nope"), "")


# --------------------------------------------------------------------------
# Test-suite runner: CEGIS capture, no source leak (section 3.2)
# --------------------------------------------------------------------------
def _build_ab_suite():
    """Suite over modules a, b with tests t_a (a), t_b (b), t_c (b)."""
    suite = TDESTestSuite(modules=["a", "b"])

    @suite.unit("a", id="t_a", description="a.f_a returns 'ta'")
    def t_a(env):
        env.check_equal(env.a.f_a(), env.case("ta"))

    @suite.unit("b", id="t_b", description="b.f returns 'tb'")
    def t_b(env):
        env.check_equal(env.b.f(), env.case("tb"))

    @suite.unit("b", id="t_c", description="b.g returns 'tc'")
    def t_c(env):
        env.check_equal(env.b.g(), env.case("tc"))

    return suite


A_GOOD = "def f_a():\n    return 'ta'\n"
A_BAD = "def f_a():\n    return 'WRONG'\n"
B_BOTH = "def f():\n    return 'tb'\ndef g():\n    return 'tc'\n"
B_TB_ONLY = "def f():\n    return 'tb'\ndef g():\n    return 'WRONG'\n"
B_TC_ONLY = "def f():\n    return 'WRONG'\ndef g():\n    return 'tc'\n"
B_NEITHER = "def f():\n    return 'WRONG'\ndef g():\n    return 'WRONG'\n"


class SuiteRunnerTests(unittest.TestCase):
    def setUp(self):
        self.suite = _build_ab_suite()

    def _run(self, a_src, b_src):
        cand = Candidate(modules={"a": a_src, "b": b_src})
        return self.suite.run(cand, sandbox=False)

    def test_pass_fail_vector(self):
        v = self._run(A_GOOD, B_TC_ONLY)
        self.assertEqual(v.passes(), {"t_a", "t_c"})
        self.assertEqual(v.score_key, (0, 0, 2))

    def test_cegis_feedback_captured_without_source(self):
        v = self._run(A_BAD, B_BOTH)
        fb = v.results["t_a"].feedback
        self.assertIsNotNone(fb)
        # concrete failing input + error are captured
        self.assertIn("ta", fb.failing_input)
        self.assertIn("WRONG", fb.error)
        # the test's source code is never exposed in the feedback
        blob = f"{fb.description}\n{fb.failing_input}\n{fb.error}"
        self.assertNotIn("check_equal", blob)
        self.assertNotIn("def t_a", blob)

    def test_candidate_crash_is_captured_as_failure(self):
        v = self._run("def f_a():\n    raise ValueError('boom')\n", B_BOTH)
        self.assertFalse(v.results["t_a"].passed)
        self.assertIn("boom", v.results["t_a"].feedback.error)


# --------------------------------------------------------------------------
# Complementary-coverage crossover (section 3.3) — primary contribution
# --------------------------------------------------------------------------
class CrossoverTests(unittest.TestCase):
    def setUp(self):
        self.suite = _build_ab_suite()

    def _cand(self, a_src, b_src):
        c = Candidate(modules={"a": a_src, "b": b_src})
        c.vector = self.suite.run(c, sandbox=False)
        return c

    def test_accept_on_strict_superset(self):
        higher = self._cand(A_GOOD, B_NEITHER)  # passes {t_a}
        lower = self._cand(A_BAD, B_BOTH)  # passes {t_b, t_c}
        self.assertEqual(higher.passes, {"t_a"})
        outcome = complementary_crossover(higher, lower, self.suite, generation=1, sandbox=False)
        self.assertTrue(outcome.attempted)
        self.assertTrue(outcome.accepted)
        self.assertEqual(outcome.grafted_modules, ["b"])
        self.assertEqual(outcome.child.passes, {"t_a", "t_b", "t_c"})

    def test_reject_on_regression(self):
        higher = self._cand(A_GOOD, B_TC_ONLY)  # passes {t_a, t_c}
        lower = self._cand(A_BAD, B_TB_ONLY)  # passes {t_b}
        outcome = complementary_crossover(higher, lower, self.suite, generation=1, sandbox=False)
        self.assertTrue(outcome.attempted)  # complementary coverage exists ({t_b})
        self.assertFalse(outcome.accepted)  # but grafting loses t_c -> regression
        self.assertIsNone(outcome.child)

    def test_skip_when_no_complementary_coverage(self):
        higher = self._cand(A_GOOD, B_BOTH)  # passes all
        lower = self._cand(A_BAD, B_TB_ONLY)  # passes {t_b} ⊆ higher
        outcome = complementary_crossover(higher, lower, self.suite, generation=1, sandbox=False)
        self.assertFalse(outcome.attempted)
        self.assertFalse(outcome.accepted)


# --------------------------------------------------------------------------
# Stagnation detection + escalation (section 3.6)
# --------------------------------------------------------------------------
class _NullMutator:
    """A mutator that never proposes a change -> forces stagnation."""

    async def propose(self, **kwargs):
        return None


class StagnationTests(unittest.TestCase):
    def test_escalation_package_written_on_stagnation(self):
        suite = _build_ab_suite()
        seed = Candidate(modules={"a": A_BAD, "b": B_NEITHER})  # passes nothing
        with tempfile.TemporaryDirectory() as out:
            cfg = TDESConfig(
                pop_size=2, max_generations=5, sandbox=False, output_dir=out, random_seed=1
            )
            controller = TDESController(seed, suite, _NullMutator(), cfg)
            result = controller.run()
            self.assertTrue(result.escalated)
            self.assertTrue(os.path.exists(os.path.join(out, "escalation.json")))


# --------------------------------------------------------------------------
# End-to-end controller run on the example (sections 3.1–3.5)
# --------------------------------------------------------------------------
class EndToEndTests(unittest.TestCase):
    def _load_example_mutator(self):
        path = os.path.join(EXAMPLE_DIR, "suite.py")
        spec = importlib.util.spec_from_file_location("_example_suite", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.get_scripted_mutator()

    def test_example_converges_to_all_passing(self):
        suite = TDESTestSuite.load_from_file(os.path.join(EXAMPLE_DIR, "suite.py"))
        seed = load_seed_codebase(os.path.join(EXAMPLE_DIR, "seed"), suite.module_names)
        mutator = self._load_example_mutator()
        with tempfile.TemporaryDirectory() as out:
            cfg = TDESConfig(
                pop_size=4, max_generations=6, sandbox=False, output_dir=out, random_seed=7
            )
            controller = TDESController(seed, suite, mutator, cfg)
            result = controller.run()
            self.assertFalse(result.escalated)
            self.assertEqual(result.best.vector.total_passes, len(suite.tests))
            self.assertTrue(os.path.exists(os.path.join(out, "best", "result.json")))

    def test_seed_starts_partially_failing(self):
        suite = TDESTestSuite.load_from_file(os.path.join(EXAMPLE_DIR, "suite.py"))
        seed = load_seed_codebase(os.path.join(EXAMPLE_DIR, "seed"), suite.module_names)
        v = suite.run(seed, sandbox=False)
        self.assertLess(v.total_passes, len(suite.tests))
        self.assertGreater(v.total_passes, 0)  # some tests pass at the seed


if __name__ == "__main__":
    unittest.main()
