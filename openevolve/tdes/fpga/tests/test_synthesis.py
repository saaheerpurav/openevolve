"""
Tests for the Yosys synthesis wrapper and the ``__synthesis__`` system-test path.

Requires Yosys on PATH; skipped otherwise.
"""

import unittest

from openevolve.tdes.fpga import synthesis
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.types import Candidate, TestLevel

AND_GATE = "module and_gate(input a, b, output y);\n  assign y = a & b;\nendmodule\n"
# A wider design that uses clearly more than 1 LUT.
ADDER = "module top(input [7:0] a, b, output [8:0] s);\n  assign s = a + b;\nendmodule\n"


@unittest.skipUnless(synthesis.yosys_available(), "yosys not on PATH")
class SynthesisTests(unittest.TestCase):
    def test_resource_extraction(self):
        r = synthesis.synthesize({"and_gate": AND_GATE}, top_module="and_gate", target="ice40")
        self.assertTrue(r.ok, r.error)
        self.assertIsNotNone(r.luts)
        self.assertGreaterEqual(r.luts, 1)

    def test_budget_pass(self):
        out = synthesis.evaluate_synthesis_test(
            {"and_gate": AND_GATE}, top_module="and_gate", spec={"lut": 100}
        )
        self.assertTrue(out.passed)

    def test_budget_violation_reports_counts(self):
        out = synthesis.evaluate_synthesis_test({"top": ADDER}, top_module="top", spec={"lut": 1})
        self.assertFalse(out.passed)
        self.assertIn("LUT", out.error)

    def test_synthesis_sentinel_through_suite(self):
        suite = VerilogTestSuite(
            module_names=["and_gate"],
            tests=[
                VerilogTest(
                    id="synth_budget",
                    level=TestLevel.SYSTEM,
                    module="and_gate",
                    description="Design must fit a tiny LUT budget",
                    testbench_source="__synthesis__ lut<100",
                )
            ],
            top_module="and_gate",
            synth_config={"target": "ice40"},
        )
        vec = suite.run(Candidate(modules={"and_gate": AND_GATE}))
        self.assertTrue(vec.results["synth_budget"].passed)


if __name__ == "__main__":
    unittest.main()
