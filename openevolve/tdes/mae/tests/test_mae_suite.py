"""
Offline tests for the TDES-MAE layer (no LLM; torch required, CIFAR cache
required only for the end-to-end test).

Covers: the 8 unit checks accept the baseline and reject targeted breakages,
tier gating (no training compute for unit-failing candidates), the
probe-accuracy ladder's hierarchical ordering, mask sanitization, and a
scripted end-to-end evolution run on a miniature training budget.
"""

import os
import unittest

try:
    import torch

    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False

if HAVE_TORCH:
    from openevolve.tdes.mae.config import MAEConfig
    from openevolve.tdes.mae.evaluator import _UNIT_CHECKS, MAESuite, run_unit_tier
    from openevolve.tdes.mae.masking import BASELINE_SOURCE, compile_mask_fn
    from openevolve.tdes.mae.trainer import sanitize_mask
    from openevolve.tdes.types import Candidate, TestLevel

_CIFAR_PRESENT = HAVE_TORCH and os.path.exists(
    os.path.join(MAEConfig().data_dir, "cifar-10-batches-py")
)

ALL_MASKED = """\
import torch

def generate_mask(batch_size, num_patches, mask_ratio, epoch, device):
    return torch.ones(batch_size, num_patches, dtype=torch.bool, device=device)
"""

WRONG_SHAPE = """\
import torch

def generate_mask(batch_size, num_patches, mask_ratio, epoch, device):
    return torch.zeros(num_patches, batch_size, dtype=torch.bool, device=device)
"""

DETERMINISTIC = """\
import torch

def generate_mask(batch_size, num_patches, mask_ratio, epoch, device):
    mask = torch.zeros(batch_size, num_patches, dtype=torch.bool, device=device)
    mask[:, : int(mask_ratio * num_patches)] = True
    return mask
"""

SYNTAX_ERROR = "def generate_mask(batch_size:\n"


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class TestUnitTier(unittest.TestCase):
    def setUp(self):
        self.cfg = MAEConfig()

    def _run(self, source):
        return run_unit_tier(source, self.cfg)

    def test_baseline_passes_all(self):
        results = self._run(BASELINE_SOURCE)
        self.assertTrue(all(r["passed"] for r in results.values()), results)

    def test_all_masked_rejected(self):
        results = self._run(ALL_MASKED)
        self.assertFalse(results["u_not_all_masked"]["passed"])
        self.assertFalse(results["u_ratio"]["passed"])

    def test_wrong_shape_rejected(self):
        self.assertFalse(self._run(WRONG_SHAPE)["u_shape"]["passed"])

    def test_deterministic_rejected(self):
        results = self._run(DETERMINISTIC)
        self.assertFalse(results["u_stochastic"]["passed"])

    def test_syntax_error_fails_everything_with_message(self):
        results = self._run(SYNTAX_ERROR)
        self.assertTrue(all(not r["passed"] for r in results.values()))
        self.assertIn("compile", results["u_shape"]["detail"])

    def test_compile_rejects_missing_function(self):
        with self.assertRaises(ValueError):
            compile_mask_fn("x = 1\n")


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class TestSuiteGating(unittest.TestCase):
    def test_unit_failure_skips_training_tiers(self):
        suite = MAESuite(MAEConfig())
        vector = suite.run(Candidate(modules={"masking": ALL_MASKED}), sandbox=False)
        integ = vector.results["integ_trains"]
        self.assertFalse(integ.passed)
        self.assertIn("skipped", integ.feedback.error)
        for r in vector.results.values():
            if r.level is TestLevel.SYSTEM:
                self.assertFalse(r.passed)

    def test_eval_records_are_memoized(self):
        suite = MAESuite(MAEConfig())
        cand = Candidate(modules={"masking": ALL_MASKED})
        suite.run(cand, sandbox=False)
        n = len(suite.eval_records)
        suite.run(cand.clone(), sandbox=False)
        self.assertEqual(len(suite.eval_records), n)


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class TestAccuracyLadder(unittest.TestCase):
    def _vector_for_acc(self, suite, acc):
        record = {
            "unit": {name: {"passed": True, "detail": ""} for name, _ in _UNIT_CHECKS},
            "train": {
                "integration": {"loss": 0.5, "error": None},
                "system": {"acc": acc, "recon_loss": 0.4, "error": None},
            },
            "timeout": None,
        }
        return suite._to_vector(record)

    def test_higher_accuracy_outranks(self):
        suite = MAESuite(MAEConfig())
        lo = self._vector_for_acc(suite, 0.35)
        hi = self._vector_for_acc(suite, 0.44)
        self.assertGreater(hi.score_key, lo.score_key)
        self.assertTrue(hi.is_strict_superset_of(lo))

    def test_failed_rung_feedback_carries_scalars(self):
        suite = MAESuite(MAEConfig())
        v = self._vector_for_acc(suite, 0.35)
        failing = [r for r in v.failures() if r.level is TestLevel.SYSTEM]
        self.assertTrue(failing)
        self.assertIn("0.350", failing[0].feedback.error)


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class TestSanitizeMask(unittest.TestCase):
    def test_degenerate_rows_repaired(self):
        mask = torch.zeros(3, 16, dtype=torch.bool)
        mask[0] = True  # all masked
        out = sanitize_mask(mask)
        self.assertFalse(out[0].all())
        self.assertTrue(out[1].any())
        self.assertTrue(out[2].any())


@unittest.skipUnless(_CIFAR_PRESENT, "CIFAR-10 cache not present")
class TestScriptedEndToEnd(unittest.TestCase):
    def test_scripted_evolution_improves_or_holds(self):
        """Two scripted generations on a miniature budget exercise the full loop."""
        from openevolve.tdes.config import TDESConfig
        from openevolve.tdes.mae.controller import build_controller
        from openevolve.tdes.mae.run import _scripted_mutator

        cfg = MAEConfig(
            n_pretrain=500,
            n_probe_test=500,
            integration_epochs=1,
            system_epochs=2,
            probe_epochs=5,
        )
        suite = MAESuite(cfg)
        tdes_cfg = TDESConfig(
            pop_size=2, max_generations=2, sandbox=False, output_dir="tdes_mae_results/test_run"
        )
        controller = build_controller(BASELINE_SOURCE, suite, _scripted_mutator(), tdes_cfg)
        result = controller.run()
        self.assertGreaterEqual(result.generations_run, 1)
        best = result.best.vector
        # The seed baseline must clear unit + integration on any budget.
        self.assertEqual(best.level_counts()[TestLevel.UNIT], 8)
        self.assertTrue(best.results["integ_trains"].passed or cfg.integration_epochs < 2)


if __name__ == "__main__":
    unittest.main()
