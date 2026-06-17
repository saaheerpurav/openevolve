"""
Offline tests for TDES-FPGA Level 3-4 ArchXBench integration.
No API key required. EDA-gated tests skip when iverilog is absent.
"""

import unittest

from openevolve.tdes.fpga.archxbench import loader as archx_loader
from openevolve.tdes.fpga.verilog_runner import tools_available


class TestLoaderGates(unittest.TestCase):
    """Loader returns correct structures (no EDA needed)."""

    def test_fp_adder_structure(self):
        seed, suite, mutator = archx_loader.load("fp_adder")
        self.assertIn("fp_special_case", seed.modules)
        self.assertIn("fp_adder_core", seed.modules)
        self.assertEqual(len(suite.tests), 3)
        test_ids = {t.id for t in suite.tests}
        self.assertIn("unit_special", test_ids)
        self.assertIn("unit_core", test_ids)
        self.assertIn("system_full", test_ids)
        self.assertIsNotNone(mutator)

    def test_fp_multiplier_structure(self):
        seed, suite, mutator = archx_loader.load("fp_multiplier")
        self.assertIn("fp_mult_special", seed.modules)
        self.assertIn("fp_mult_core", seed.modules)
        self.assertEqual(len(suite.tests), 3)
        self.assertIsNotNone(mutator)

    def test_unknown_design_raises(self):
        with self.assertRaises(KeyError):
            archx_loader.load("nonexistent_design")

    def test_seed_skeletons_are_stubs(self):
        seed, _, _ = archx_loader.load("fp_adder")
        # Skeletons should not contain the full algorithm
        for m, src in seed.modules.items():
            self.assertIn("TODO", src)

    def test_mutator_has_reference(self):
        _, _, mutator = archx_loader.load("fp_adder")
        self.assertTrue(hasattr(mutator, "reference"))
        self.assertIn("fp_special_case", mutator.reference)
        self.assertIn("fp_adder_core", mutator.reference)


@unittest.skipUnless(tools_available(), "iverilog/vvp not on PATH")
class TestReferencePassesAll(unittest.TestCase):
    """Reference implementations must pass all TDES test tiers."""

    def _check_design(self, design: str):
        from openevolve.tdes.fpga.verilog_suite import VerilogTestSuite
        seed, suite, mutator = archx_loader.load(design)
        # Build reference candidate from mutator.reference
        from openevolve.tdes.types import Candidate
        ref_cand = Candidate(modules=dict(mutator.reference))
        vec = suite.run(ref_cand, sandbox=False, timeout=60)
        fails = vec.failures()
        self.assertEqual(
            len(fails), 0,
            f"{design}: reference fails {[r.test_id for r in fails]}"
        )

    def test_fp_adder_reference_passes_all(self):
        self._check_design("fp_adder")

    def test_fp_multiplier_reference_passes_all(self):
        self._check_design("fp_multiplier")


@unittest.skipUnless(tools_available(), "iverilog/vvp not on PATH")
class TestSeedFailsSome(unittest.TestCase):
    """Seed skeletons must fail at least one test (usable for evolution)."""

    def _check_seed_fails(self, design: str):
        from openevolve.tdes.types import Candidate
        seed, suite, _ = archx_loader.load(design)
        vec = suite.run(seed, sandbox=False, timeout=60)
        self.assertGreater(len(vec.failures()), 0,
                           f"{design}: seed passed all tests (too easy)")

    def test_fp_adder_seed_fails(self):
        self._check_seed_fails("fp_adder")

    def test_fp_multiplier_seed_fails(self):
        self._check_seed_fails("fp_multiplier")


@unittest.skipUnless(tools_available(), "iverilog/vvp not on PATH")
class TestScriptedEvolution(unittest.TestCase):
    """Scripted (no LLM) TDES run solves both designs using the reference mutator."""

    def _run_scripted(self, design: str, gens: int = 4, pop: int = 4):
        from openevolve.tdes.fpga.ablation import DiverseScheduleController
        from openevolve.tdes.fpga.config import FPGAConfig

        seed, suite, mutator = archx_loader.load(design)
        cfg = FPGAConfig(
            output_dir=f"_test_l3l4_{design}",
            sandbox=False,
            max_generations=gens,
            pop_size=pop,
            mutate_modules_per_candidate=1,
        )
        ctrl = DiverseScheduleController(
            seed, suite, mutator, cfg,
            enable_crossover=True,
            enable_memory=True,
        )
        result = ctrl.run()
        total = len(suite.tests)
        self.assertEqual(
            result.best.vector.total_passes, total,
            f"{design}: scripted run solved {result.best.vector.total_passes}/{total} tests"
        )

    def test_fp_adder_scripted_solves(self):
        self._run_scripted("fp_adder")

    def test_fp_multiplier_scripted_solves(self):
        self._run_scripted("fp_multiplier")


if __name__ == "__main__":
    unittest.main()
