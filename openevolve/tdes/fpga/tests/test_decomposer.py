"""
Tests for the testbench decomposer (pure parsing/codegen; no EDA tools needed).
"""

import unittest

from openevolve.tdes.fpga import testbench_decomposer as decomp
from openevolve.tdes.types import TestLevel

ADDER_TB = r"""
`timescale 1ns / 1ps
module testbench;
  reg [7:0] a;
  reg [7:0] b;
  reg cin;
  wire [7:0] sum;
  wire cout;
  integer error = 0;
  adder_8bit uut (.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));
  initial begin
    a = 8'h12; b = 8'h34; cin = 0; #10;
    error = (sum !== a + b + cin) ? error + 1 : error;
  end
endmodule
"""

CLOCKED_TB = r"""
module tb;
  reg clk; reg [7:0] d; wire [7:0] q;
  counter uut(.clk(clk), .d(d), .q(q));
  initial begin d = 0; #10; if (q !== d + 1) $display("bad"); end
endmodule
"""

NO_GOLDEN_TB = r"""
module tb;
  reg [7:0] a; wire [7:0] y;
  thing uut(.a(a), .y(y));
  initial begin a = 1; #10; $display("done"); end
endmodule
"""


class DecomposerTests(unittest.TestCase):
    def test_decomposes_combinational_adder(self):
        tests = decomp.decompose(ADDER_TB, "adder_8bit", "8-bit adder")
        self.assertTrue(tests)
        levels = {t.level for t in tests}
        self.assertIn(TestLevel.UNIT, levels)
        self.assertIn(TestLevel.INTEGRATION, levels)
        self.assertIn(TestLevel.SYSTEM, levels)
        # every generated testbench carries the TDES protocol and the DUT name
        for t in tests:
            self.assertIn("TDES_PASS", t.testbench_source)
            self.assertIn("adder_8bit uut", t.testbench_source)
            # golden expression reused; only input signals referenced in stimulus
            self.assertIn("a + b + cin", t.testbench_source)

    def test_skips_clocked_design(self):
        self.assertEqual(decomp.decompose(CLOCKED_TB, "counter", ""), [])

    def test_skips_when_no_golden(self):
        self.assertEqual(decomp.decompose(NO_GOLDEN_TB, "thing", ""), [])


if __name__ == "__main__":
    unittest.main()
