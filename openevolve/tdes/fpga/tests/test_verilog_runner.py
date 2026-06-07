"""
Tests for the Verilog EDA runner + VerilogTestSuite.

Requires Icarus Verilog (iverilog/vvp) on PATH; skipped otherwise.
"""

import unittest

from openevolve.tdes.fpga.verilog_runner import tools_available
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.types import Candidate, TestLevel

AND_GATE_GOOD = "module and_gate(input a, b, output y);\n  assign y = a & b;\nendmodule\n"
AND_GATE_BAD = "module and_gate(input a, b, output y);\n  assign y = a | b;\nendmodule\n"
AND_GATE_BROKEN = "module and_gate(input a, b, output y)\n  assign y = a & b;\n"  # syntax error

TB_AND = r"""
`timescale 1ns/1ps
module tb;
  reg a, b;
  wire y;
  integer fails = 0;
  and_gate uut(.a(a), .b(b), .y(y));
  task chk(input ra, input rb, input exp);
    begin
      a = ra; b = rb; #5;
      if (y !== exp) begin
        $display("TDES_FAIL: test_id=and_all | input=a=%b,b=%b | expected=%b | got=%b", ra, rb, exp, y);
        fails = fails + 1;
      end
    end
  endtask
  initial begin
    chk(0,0,0); chk(0,1,0); chk(1,0,0); chk(1,1,1);
    if (fails == 0) $display("TDES_PASS: test_id=and_all");
    $finish;
  end
endmodule
"""


def _suite():
    return VerilogTestSuite(
        module_names=["and_gate"],
        tests=[
            VerilogTest(
                id="and_all",
                level=TestLevel.UNIT,
                module="and_gate",
                description="2-input AND gate truth table",
                testbench_source=TB_AND,
            )
        ],
    )


@unittest.skipUnless(tools_available(), "iverilog/vvp not on PATH")
class VerilogRunnerTests(unittest.TestCase):
    def test_correct_design_passes(self):
        suite = _suite()
        cand = Candidate(modules={"and_gate": AND_GATE_GOOD})
        vec = suite.run(cand, timeout=30)
        self.assertTrue(vec.results["and_all"].passed)
        self.assertEqual(vec.total_passes, 1)

    def test_buggy_design_fails_with_cegis_feedback(self):
        suite = _suite()
        cand = Candidate(modules={"and_gate": AND_GATE_BAD})
        vec = suite.run(cand, timeout=30)
        res = vec.results["and_all"]
        self.assertFalse(res.passed)
        self.assertIsNotNone(res.feedback)
        # first failing case is a=0,b=1 -> expected 0, got 1
        self.assertIn("a=0,b=1", res.feedback.failing_input)
        self.assertIn("expected 0", res.feedback.error)
        self.assertIn("got 1", res.feedback.error)
        # testbench source is never leaked into feedback
        blob = f"{res.feedback.description}{res.feedback.failing_input}{res.feedback.error}"
        self.assertNotIn("$display", blob)
        self.assertNotIn("TDES_FAIL", blob)

    def test_compile_error_is_failure_with_message(self):
        suite = _suite()
        cand = Candidate(modules={"and_gate": AND_GATE_BROKEN})
        vec = suite.run(cand, timeout=30)
        res = vec.results["and_all"]
        self.assertFalse(res.passed)
        self.assertIn("compilation failed", res.feedback.error)


if __name__ == "__main__":
    unittest.main()
