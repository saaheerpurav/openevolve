"""
Offline tests for the four enhanced TDES-FPGA mechanisms.

All tests run without an API key or EDA tools; EDA-gated tests
are annotated with @skipUnless(tools_available()).

Covers:
  - PositiveMemory: record / render / window eviction
  - build_user_prompt: positive_memory_text param wired through
  - VerilogLLMMutator: positive_memory_text forwarded to prompt
  - _priority_sorted_modules: sort order is pass-fraction descending
  - ENHANCED_CONDITIONS registry: all five keys present, correct flag set/unset
  - EnhancedFPGAController: scripted run solves a split design (EDA-gated)
  - Semantic crossover prompt: includes both source texts and per-module test outcomes
"""

import asyncio
import unittest

from openevolve.tdes.fpga.enhanced import ENHANCED_CONDITIONS, EnhancedFPGAController
from openevolve.tdes.fpga.positive_memory import PositiveMemory, PositiveMemoryEntry
from openevolve.tdes.fpga.prompts import build_user_prompt
from openevolve.tdes.fpga.semantic_crossover import _build_merge_prompt, _fmt_tests
from openevolve.tdes.fpga.verilog_runner import tools_available
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.mutation import ScriptedMutator
from openevolve.tdes.types import Candidate, TestLevel, TestResult, TestVector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vector(results):
    """Build a TestVector from a list of (test_id, level, module, passed) tuples."""
    vec = TestVector()
    for tid, level, mod, passed in results:
        vec.results[tid] = TestResult(
            test_id=tid,
            level=level,
            module=mod,
            passed=passed,
            description=f"desc_{tid}",
        )
    return vec


# ---------------------------------------------------------------------------
# PositiveMemory unit tests (no EDA needed)
# ---------------------------------------------------------------------------

class TestPositiveMemory(unittest.TestCase):

    def test_record_and_render(self):
        pm = PositiveMemory(window_size=3)
        pm.record("adder", 1, "used ripple carry", ["u_add_basic", "u_add_carry"])
        rendered = pm.render("adder")
        self.assertIn("WORKED", rendered)
        self.assertIn("used ripple carry", rendered)
        self.assertIn("u_add_basic", rendered)

    def test_render_empty_returns_empty_string(self):
        pm = PositiveMemory()
        self.assertEqual(pm.render("nonexistent"), "")

    def test_window_eviction(self):
        pm = PositiveMemory(window_size=2)
        pm.record("m", 1, "approach_A", ["t1"])
        pm.record("m", 2, "approach_B", ["t2"])
        pm.record("m", 3, "approach_C", ["t3"])  # evicts approach_A
        entries = pm.entries("m")
        self.assertEqual(len(entries), 2)
        approaches = [e.approach for e in entries]
        self.assertNotIn("approach_A", approaches)
        self.assertIn("approach_B", approaches)
        self.assertIn("approach_C", approaches)

    def test_multiple_modules_independent(self):
        pm = PositiveMemory()
        pm.record("mod_a", 1, "approach_X", ["ta1"])
        pm.record("mod_b", 1, "approach_Y", ["tb1"])
        self.assertIn("approach_X", pm.render("mod_a"))
        self.assertNotIn("approach_X", pm.render("mod_b"))
        self.assertIn("approach_Y", pm.render("mod_b"))

    def test_as_dict(self):
        pm = PositiveMemory()
        pm.record("adder", 2, "lookahead", ["t1"])
        d = pm.as_dict()
        self.assertIn("adder", d)
        self.assertEqual(d["adder"][0]["approach"], "lookahead")
        self.assertEqual(d["adder"][0]["new_passes"], ["t1"])


# ---------------------------------------------------------------------------
# Prompt building with positive_memory_text
# ---------------------------------------------------------------------------

class TestPromptPositiveMemory(unittest.TestCase):

    def test_positive_block_appears_in_prompt(self):
        prompt = build_user_prompt(
            module_name="adder",
            module_source="module adder(input a, output b); endmodule",
            feedback=[],
            memory_text="",
            diff_based=False,
            generation=2,
            positive_memory_text="Approaches that WORKED: Gen 1: use ripple carry → passed t1",
        )
        self.assertIn("WORKED", prompt)
        self.assertIn("ripple carry", prompt)

    def test_no_positive_block_when_empty(self):
        prompt = build_user_prompt(
            module_name="adder",
            module_source="module adder; endmodule",
            feedback=[],
            memory_text="",
            diff_based=False,
            generation=1,
            positive_memory_text="",
        )
        self.assertNotIn("WORKED", prompt)

    def test_positive_block_before_task_section(self):
        prompt = build_user_prompt(
            module_name="adder",
            module_source="module adder; endmodule",
            feedback=[],
            memory_text="",
            diff_based=False,
            generation=1,
            positive_memory_text="positive info",
        )
        pos_idx = prompt.index("positive info")
        task_idx = prompt.index("# Task")
        self.assertLess(pos_idx, task_idx)


# ---------------------------------------------------------------------------
# Priority-sorted modules
# ---------------------------------------------------------------------------

class TestPrioritySortedModules(unittest.TestCase):

    def _make_controller(self):
        seed = Candidate(modules={"a": "", "b": "", "c": ""})
        suite = VerilogTestSuite(
            module_names=["a", "b", "c"],
            tests=[
                VerilogTest("t_a1", TestLevel.UNIT, "a", "a test 1", ""),
                VerilogTest("t_a2", TestLevel.UNIT, "a", "a test 2", ""),
                VerilogTest("t_b1", TestLevel.UNIT, "b", "b test 1", ""),
                VerilogTest("t_b2", TestLevel.UNIT, "b", "b test 2", ""),
                VerilogTest("t_c1", TestLevel.UNIT, "c", "c test 1", ""),
                VerilogTest("t_c2", TestLevel.UNIT, "c", "c test 2", ""),
            ],
        )
        cfg = FPGAConfig(output_dir="_test_enhanced_tmp", sandbox=False, max_generations=1)
        ctrl = EnhancedFPGAController(
            seed, suite, ScriptedMutator(lambda *a: None), cfg,
            use_diverse_seed=False, use_semantic_crossover=False,
            use_priority_mutation=True, use_positive_memory=False,
        )
        return ctrl

    def test_priority_sorts_by_pass_fraction_descending(self):
        ctrl = self._make_controller()
        # module a: 1/2 passing (50%), module b: 0/2 passing (0%), module c: 1/2 (50%)
        vector = _make_vector([
            ("t_a1", TestLevel.UNIT, "a", True),
            ("t_a2", TestLevel.UNIT, "a", False),
            ("t_b1", TestLevel.UNIT, "b", False),
            ("t_b2", TestLevel.UNIT, "b", False),
            ("t_c1", TestLevel.UNIT, "c", True),
            ("t_c2", TestLevel.UNIT, "c", False),
        ])
        order = ctrl._priority_sorted_modules(vector)
        # b has 0/2 (0%), a and c have 1/2 (50%) — b should be last
        self.assertEqual(order[-1], "b")
        # a and c should be before b
        self.assertIn("a", order[:2])
        self.assertIn("c", order[:2])

    def test_priority_with_all_failing(self):
        ctrl = self._make_controller()
        vector = _make_vector([
            ("t_a1", TestLevel.UNIT, "a", False),
            ("t_b1", TestLevel.UNIT, "b", False),
        ])
        order = ctrl._priority_sorted_modules(vector)
        self.assertEqual(set(order), {"a", "b"})

    def test_priority_excludes_fully_passing_modules(self):
        ctrl = self._make_controller()
        vector = _make_vector([
            ("t_a1", TestLevel.UNIT, "a", True),
            ("t_a2", TestLevel.UNIT, "a", True),
            ("t_b1", TestLevel.UNIT, "b", False),
        ])
        order = ctrl._priority_sorted_modules(vector)
        # 'a' passes all its tests — should not appear as failing
        self.assertNotIn("a", order)
        self.assertIn("b", order)


# ---------------------------------------------------------------------------
# ENHANCED_CONDITIONS registry
# ---------------------------------------------------------------------------

class TestEnhancedConditionsRegistry(unittest.TestCase):

    def test_all_five_keys_present(self):
        expected = {
            "tdes_enhanced",
            "tdes_no_diverse_seed",
            "tdes_no_semantic_xo",
            "tdes_no_priority_mut",
            "tdes_no_positive_mem",
        }
        self.assertEqual(set(ENHANCED_CONDITIONS.keys()), expected)

    def test_enhanced_has_all_enabled(self):
        kwargs = ENHANCED_CONDITIONS["tdes_enhanced"]
        self.assertTrue(kwargs["use_diverse_seed"])
        self.assertTrue(kwargs["use_semantic_crossover"])
        self.assertTrue(kwargs["use_priority_mutation"])
        self.assertTrue(kwargs["use_positive_memory"])

    def test_each_ablation_disables_exactly_one(self):
        flags = ["use_diverse_seed", "use_semantic_crossover",
                 "use_priority_mutation", "use_positive_memory"]
        ablation_keys = [k for k in ENHANCED_CONDITIONS if k != "tdes_enhanced"]
        for key in ablation_keys:
            kwargs = ENHANCED_CONDITIONS[key]
            disabled = [f for f in flags if not kwargs.get(f, True)]
            self.assertEqual(
                len(disabled), 1,
                f"{key} should disable exactly one flag; disabled: {disabled}"
            )


# ---------------------------------------------------------------------------
# Semantic crossover prompt structure
# ---------------------------------------------------------------------------

class TestSemanticCrossoverPrompt(unittest.TestCase):

    def _make_vectors(self):
        vec_a = _make_vector([
            ("t_sub_unit", TestLevel.UNIT, "sub", True),
            ("t_top_integ", TestLevel.UNIT, "top", False),
            ("t_system", TestLevel.SYSTEM, "top", False),
        ])
        vec_b = _make_vector([
            ("t_sub_unit", TestLevel.UNIT, "sub", False),
            ("t_top_integ", TestLevel.UNIT, "top", True),
            ("t_system", TestLevel.SYSTEM, "top", False),
        ])
        return vec_a, vec_b

    def test_prompt_includes_both_sources(self):
        vec_a, vec_b = self._make_vectors()
        src_a = "module sub(input a, output b); assign b=a; endmodule"
        src_b = "module sub(input a, output b); assign b=~a; endmodule"
        prompt = _build_merge_prompt("sub", src_a, src_b, vec_a, vec_b)
        self.assertIn(src_a, prompt)
        self.assertIn(src_b, prompt)
        self.assertIn("Implementation A", prompt)
        self.assertIn("Implementation B", prompt)

    def test_prompt_includes_pass_fail_info(self):
        vec_a, vec_b = self._make_vectors()
        prompt = _build_merge_prompt("sub", "src_a", "src_b", vec_a, vec_b)
        self.assertIn("✓", prompt)  # passing tests
        self.assertIn("✗", prompt)  # failing tests

    def test_fmt_tests_for_module(self):
        vec_a, _ = self._make_vectors()
        fmt = _fmt_tests(vec_a, "sub")
        self.assertIn("✓", fmt)  # t_sub_unit passes
        self.assertNotIn("top", fmt)  # other modules excluded

    def test_prompt_does_not_include_test_source(self):
        vec_a, vec_b = self._make_vectors()
        prompt = _build_merge_prompt("sub", "src_a", "src_b", vec_a, vec_b)
        self.assertIn("Do NOT access test source", prompt)


# ---------------------------------------------------------------------------
# Scripted integration: EnhancedFPGAController solves a two-module design
# (requires EDA tools; skipped when absent)
# ---------------------------------------------------------------------------

@unittest.skipUnless(tools_available(), "iverilog/vvp not on PATH")
class TestEnhancedScriptedHier(unittest.TestCase):
    """Scripted (no LLM) run of EnhancedFPGAController on one hier design."""

    def test_enhanced_solves_comparator_8bit_scripted(self):
        from openevolve.tdes.fpga.experiments.hierarchical_archx import load_hierarchical

        seed, suite, ref_mutator = load_hierarchical("comparator-8bit", with_mutator=True)
        cfg = FPGAConfig(
            output_dir="_test_enhanced_scripted",
            sandbox=False,
            max_generations=3,
            pop_size=3,
            mutate_modules_per_candidate=1,
        )
        ctrl = EnhancedFPGAController(
            seed, suite, ref_mutator, cfg,
            ensemble=None,
            use_diverse_seed=False,  # no LLM for seeding in scripted mode
            use_semantic_crossover=False,  # no LLM for semantic merge
            use_priority_mutation=True,
            use_positive_memory=True,
            enable_crossover=True,
            enable_memory=True,
        )
        result = ctrl.run()
        self.assertEqual(result.best.vector.total_passes, len(suite.tests))

    def test_positive_memory_populated_after_scripted_run(self):
        from openevolve.tdes.fpga.experiments.hierarchical_archx import load_hierarchical

        seed, suite, ref_mutator = load_hierarchical("decoder-3to8", with_mutator=True)
        cfg = FPGAConfig(
            output_dir="_test_enhanced_pm",
            sandbox=False,
            max_generations=3,
            pop_size=3,
            mutate_modules_per_candidate=1,
        )
        ctrl = EnhancedFPGAController(
            seed, suite, ref_mutator, cfg,
            ensemble=None,
            use_diverse_seed=False,
            use_semantic_crossover=False,
            use_priority_mutation=True,
            use_positive_memory=True,
            enable_crossover=True,
            enable_memory=True,
        )
        result = ctrl.run()
        # Positive memory should have at least one entry across all modules
        all_entries = sum(
            len(ctrl.positive_memory.entries(mod))
            for mod in suite.module_names
        )
        # If we solved it, there must have been successful mutations recorded
        if result.best.vector.total_passes == len(suite.tests):
            self.assertGreater(all_entries, 0)


if __name__ == "__main__":
    unittest.main()
