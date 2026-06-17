"""
Offline tests for the TDES-Repair layer (no API key, no LLM, no network).

Covers the loader gates for every variant of both tasks, the scripted
end-to-end evolutionary runs (full TDES with crossover firing on a split
variant and staying silent on a co-located control), the random-crossover GA
baseline, the single-shot baseline, the experiment runner cell + resumable
metrics writer, and one sandboxed (subprocess) suite execution.
"""

import os
import tempfile
import unittest

from openevolve.tdes.config import TDESConfig
from openevolve.tdes.repair import baselines, controllers, loader
from openevolve.tdes.repair.experiments import analysis
from openevolve.tdes.repair.experiments import runner as exp_runner
from openevolve.tdes.types import Candidate

ALL_VARIANTS = [(task, variant) for task in loader.TASKS for variant in loader.list_variants(task)]


def _config(tmpdir: str, **overrides) -> TDESConfig:
    params = dict(
        pop_size=6,
        max_generations=6,
        sandbox=False,
        suite_timeout=30,
        mutate_modules_per_candidate=1,
        random_seed=7,
        output_dir=os.path.join(tmpdir, "out"),
    )
    params.update(overrides)
    return TDESConfig(**params)


class TestLoaderGates(unittest.TestCase):
    def test_reference_passes_all_tests(self):
        for task in loader.TASKS:
            with self.subTest(task=task):
                suite = loader.load_suite(task)
                reference = Candidate(modules=loader.reference_modules(task))
                vector = suite.run(reference, sandbox=False)
                self.assertEqual(
                    sorted(vector.passes()),
                    sorted(t.id for t in suite.tests),
                    f"reference for {task} must pass every test; "
                    f"failures: {[r.test_id for r in vector.failures()]}",
                )

    def test_every_variant_is_usable(self):
        for task, variant in ALL_VARIANTS:
            with self.subTest(task=task, variant=variant):
                self.assertTrue(loader.is_usable(task, variant))

    def test_complementarity_gates(self):
        for task, variant in ALL_VARIANTS:
            with self.subTest(task=task, variant=variant):
                self.assertTrue(loader.verify_complementary(task, variant))

    def test_seed_fails_only_buggy_module_units(self):
        # Unit tests of un-overridden modules must stay green on the seed, so
        # the failure signal points exactly at the planted bugs.
        from openevolve.tdes.types import TestLevel

        for task, variant in ALL_VARIANTS:
            seed, suite, _ = loader.load_variant(task, variant, with_mutator=False)
            buggy = set(loader.list_variants(task)[variant]["overrides"])
            vector = suite.run(seed, sandbox=False)
            for result in vector.results.values():
                if result.level == TestLevel.UNIT and not result.passed:
                    with self.subTest(task=task, variant=variant, test=result.test_id):
                        self.assertIn(result.module, buggy)


class TestScriptedEvolution(unittest.TestCase):
    def _run(self, task, variant, condition, tmpdir, **config_overrides):
        seed, suite, mutator = loader.load_variant(task, variant)
        cls, kwargs = controllers.CONDITIONS[condition]
        ctrl = cls(seed, suite, mutator, _config(tmpdir, **config_overrides), **kwargs)
        return ctrl, ctrl.run()

    def test_tdes_full_solves_split_variant_with_crossover(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl, result = self._run("pipeline", "v1_split", "tdes_full", tmpdir)
            self.assertEqual(result.best.vector.total_passes, len(ctrl.suite.tests))
            self.assertGreaterEqual(
                ctrl.crossover_stats.accepted,
                1,
                "complementary-coverage crossover must fire on a split variant "
                "(single-module-per-generation scripted regime)",
            )

    def test_tdes_full_on_colocated_control_no_crossover_needed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl, result = self._run("pipeline", "v5_coloc", "tdes_full", tmpdir)
            self.assertEqual(result.best.vector.total_passes, len(ctrl.suite.tests))
            self.assertEqual(
                ctrl.crossover_stats.accepted,
                0,
                "with one buggy module there is nothing complementary to graft",
            )

    def test_tdes_no_crossover_still_solves(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl, result = self._run("api", "v2_split", "tdes_no_crossover", tmpdir)
            self.assertEqual(result.best.vector.total_passes, len(ctrl.suite.tests))
            self.assertEqual(ctrl.crossover_stats.pairs_considered, 0)

    def test_random_crossover_accepts_unconditionally(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl, result = self._run("api", "v1_split", "random_crossover", tmpdir)
            self.assertEqual(result.best.vector.total_passes, len(ctrl.suite.tests))
            self.assertEqual(
                ctrl.crossover_stats.accepted,
                ctrl.crossover_stats.attempts,
                "random crossover has no acceptance gate",
            )
            self.assertIsInstance(ctrl.raw_lift_total, int)


class TestSingleShotBaseline(unittest.TestCase):
    def test_scripted_single_shot_solves(self):
        seed, suite, mutator = loader.load_variant("pipeline", "v2_split")
        br = baselines.single_shot(seed, suite, mutator=mutator, sandbox=False)
        self.assertTrue(br.solved)
        self.assertEqual(br.total_passes, len(suite.tests))
        self.assertEqual(br.rounds_used, 1)
        self.assertEqual(len(br.trajectory), 2)
        self.assertLess(br.trajectory[0], br.trajectory[1])


class TestExperimentRunner(unittest.TestCase):
    def test_run_cell_scripted_and_resumable_writer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _config(tmpdir)
            rm = exp_runner.run_cell(
                "pipeline", "v1_split", "single_shot", config, seed=0, scripted=True
            )
            self.assertEqual(rm.design, "pipeline/v1_split")
            self.assertTrue(rm.solved)

            out = os.path.join(tmpdir, "metrics.json")
            writer = exp_runner.ResumableWriter(out)
            self.assertFalse(writer.done(rm.design, rm.condition, rm.seed))
            writer(rm)
            resumed = exp_runner.ResumableWriter(out)
            self.assertTrue(resumed.done(rm.design, rm.condition, rm.seed))

    def test_run_matrix_scripted_skips_done_cells(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _config(tmpdir)
            out = os.path.join(tmpdir, "metrics.json")
            cells = [("pipeline", "v5_coloc")]
            writer = exp_runner.ResumableWriter(out)
            first = exp_runner.run_matrix(
                cells, ["single_shot"], config, seeds=[0], scripted=True, writer=writer
            )
            self.assertEqual(len(first), 1)
            again = exp_runner.run_matrix(
                cells,
                ["single_shot"],
                config,
                seeds=[0],
                scripted=True,
                writer=exp_runner.ResumableWriter(out),
            )
            self.assertEqual(again, [])

    def test_analysis_report_renders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _config(tmpdir)
            rms = [
                exp_runner.run_cell(
                    "pipeline", "v1_split", "tdes_full", config, seed=0, scripted=True
                ),
                exp_runner.run_cell(
                    "pipeline", "v5_coloc", "single_shot", config, seed=0, scripted=True
                ),
            ]
            report = analysis.render_report(rms)
            self.assertIn("Table 1", report)
            self.assertIn("crossover", report)


class TestSandboxSmoke(unittest.TestCase):
    def test_sandboxed_reference_run(self):
        suite = loader.load_suite("pipeline")
        reference = Candidate(modules=loader.reference_modules("pipeline"))
        vector = suite.run(reference, sandbox=True, timeout=120)
        self.assertEqual(vector.total_passes, len(suite.tests))


if __name__ == "__main__":
    unittest.main()
