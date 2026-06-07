"""
Tests for the benchmark loaders against the cloned RTLLM repo.

Requires both the EDA toolchain and the RTLLM clone under
``openevolve/tdes/fpga/benchmarks/rtllm``; skipped otherwise.
"""

import os
import unittest

from openevolve.tdes.fpga import benchmark_loader as bl
from openevolve.tdes.fpga.verilog_runner import tools_available

_RTLLM = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks", "rtllm"
)
_HAVE_RTLLM = os.path.isdir(_RTLLM)


@unittest.skipUnless(tools_available() and _HAVE_RTLLM, "needs EDA tools + RTLLM clone")
class RTLLMLoaderTests(unittest.TestCase):
    def test_native_adder_loads_and_is_usable(self):
        seed, suite, mutator = bl.load_rtllm("adder_8bit", with_mutator=True, decompose=False)
        self.assertEqual(list(seed.modules), ["adder_8bit"])
        self.assertIsNotNone(mutator)
        # seed fails, reference passes -> usable evolution target
        self.assertTrue(bl.is_usable(seed, suite))
        self.assertEqual(len(suite.tests), 1)  # native -> single system test

    def test_decomposed_adder_is_hierarchical_and_sound(self):
        seed, suite, _ = bl.load_rtllm("adder_8bit", with_mutator=True, decompose=True)
        # decomposition should have been accepted (reference-validated)
        self.assertGreater(len(suite.tests), 1)
        ref = bl.apply_reference(seed)
        self.assertIsNotNone(ref)
        ref_vec = suite.run(ref, timeout=60)
        self.assertEqual(ref_vec.total_passes, len(suite.tests))  # reference-sound
        seed_vec = suite.run(seed, timeout=60)
        self.assertLess(seed_vec.total_passes, ref_vec.total_passes)  # seed has work to do

    def test_skeleton_has_correct_interface(self):
        seed, _suite, _ = bl.load_rtllm("adder_8bit", decompose=False)
        skel = seed.modules["adder_8bit"]
        self.assertIn("module adder_8bit", skel)
        for port in ("a", "b", "cin", "sum", "cout"):
            self.assertIn(port, skel)


if __name__ == "__main__":
    unittest.main()
