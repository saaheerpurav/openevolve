"""
Tests for the ablation controller, crossover instrumentation, and the
complementary-coverage crossover firing on real Verilog candidates.

The pure-logic tests need no tools; the crossover-firing test is gated on
iverilog/vvp.
"""

import unittest

from openevolve.tdes.fpga import ablation
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.verilog_runner import tools_available
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.crossover import complementary_crossover
from openevolve.tdes.mutation import ScriptedMutator
from openevolve.tdes.types import Candidate, TestLevel

ADDER_GOOD = "module adder(input [7:0] a, b, output [8:0] sum);\n assign sum = a + b;\nendmodule\n"
ADDER_BAD = "module adder(input [7:0] a, b, output [8:0] sum);\n assign sum = a & b;\nendmodule\n"
CMP_GOOD = "module cmp(input [7:0] a, b, output gt);\n assign gt = (a > b);\nendmodule\n"
CMP_BAD = "module cmp(input [7:0] a, b, output gt);\n assign gt = (a < b);\nendmodule\n"

TB_ADD = (
    "`timescale 1ns/1ps\nmodule tb;\n reg [7:0] a,b; wire [8:0] sum;\n adder uut(.a(a),.b(b),.sum(sum));\n"
    " initial begin a=8'd3; b=8'd4; #5;\n"
    '  if (sum!==9\'d7) $display("TDES_FAIL: test_id=u_add | input=a=3,b=4 | expected=7 | got=%d", sum);\n'
    '  else $display("TDES_PASS: test_id=u_add"); $finish; end\nendmodule\n'
)
TB_CMP = (
    "`timescale 1ns/1ps\nmodule tb;\n reg [7:0] a,b; wire gt;\n cmp uut(.a(a),.b(b),.gt(gt));\n"
    " initial begin a=8'd5; b=8'd3; #5;\n"
    '  if (gt!==1\'b1) $display("TDES_FAIL: test_id=u_cmp | input=a=5,b=3 | expected=1 | got=%b", gt);\n'
    '  else $display("TDES_PASS: test_id=u_cmp"); $finish; end\nendmodule\n'
)


def _suite():
    return VerilogTestSuite(
        module_names=["adder", "cmp"],
        tests=[
            VerilogTest("u_add", TestLevel.UNIT, "adder", "adder 3+4=7", TB_ADD),
            VerilogTest("u_cmp", TestLevel.UNIT, "cmp", "cmp 5>3", TB_CMP),
        ],
    )


class PureLogicTests(unittest.TestCase):
    def test_crossover_stats_math(self):
        s = ablation.CrossoverStats(pairs_considered=10, attempts=4, accepted=2, lift_total=6)
        self.assertAlmostEqual(s.attempt_rate, 0.4)
        self.assertAlmostEqual(s.success_rate, 0.5)
        self.assertAlmostEqual(s.mean_lift, 3.0)

    def test_flatten_levels(self):
        suite = _suite()
        flat = ablation.flatten_levels(suite)
        self.assertTrue(all(t.level == TestLevel.UNIT for t in flat.tests))
        self.assertEqual([t.id for t in flat.tests], [t.id for t in suite.tests])

    def test_no_crossover_toggle_returns_empty(self):
        ctrl = ablation.AblationController(
            Candidate(modules={"adder": ADDER_BAD, "cmp": CMP_BAD}),
            _suite(),
            ScriptedMutator(lambda *a: None),
            FPGAConfig(output_dir="_x", sandbox=False),
            enable_crossover=False,
        )
        # Disabled crossover never touches the suite and yields no children.
        self.assertEqual(ctrl._crossover_phase([Candidate(modules={})], 1), [])
        self.assertEqual(ctrl.crossover_stats.pairs_considered, 0)


@unittest.skipUnless(tools_available(), "iverilog/vvp not on PATH")
class CrossoverFiresOnVerilog(unittest.TestCase):
    def test_complementary_crossover_grafts_verilog_module(self):
        suite = _suite()
        # A passes adder only; B passes cmp only -> complementary coverage.
        a = Candidate(modules={"adder": ADDER_GOOD, "cmp": CMP_BAD})
        b = Candidate(modules={"adder": ADDER_BAD, "cmp": CMP_GOOD})
        a.vector = suite.run(a, timeout=30)
        b.vector = suite.run(b, timeout=30)
        self.assertEqual(a.vector.passes(), {"u_add"})
        self.assertEqual(b.vector.passes(), {"u_cmp"})

        outcome = complementary_crossover(a, b, suite, generation=1, sandbox=False, timeout=30)
        self.assertTrue(outcome.attempted)
        self.assertTrue(outcome.accepted)
        self.assertEqual(outcome.grafted_modules, ["cmp"])
        self.assertEqual(outcome.child.passes, {"u_add", "u_cmp"})


if __name__ == "__main__":
    unittest.main()
