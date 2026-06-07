"""
End-to-end reuse-integrity test: the unmodified TDESController (via
FPGAController) drives a VerilogTestSuite to convergence using an offline
ScriptedMutator. This proves selection/crossover/negative-memory operate on
Verilog TestVectors with no changes to the base package.

Requires iverilog/vvp on PATH; skipped otherwise.
"""

import tempfile
import unittest

from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.fpga_controller import FPGAController
from openevolve.tdes.fpga.verilog_runner import tools_available
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.mutation import ScriptedMutator
from openevolve.tdes.types import Candidate, TestLevel

ADDER_BAD = "module adder(input [7:0] a, b, output [8:0] sum);\n  assign sum = a & b;\nendmodule\n"
ADDER_GOOD = "module adder(input [7:0] a, b, output [8:0] sum);\n  assign sum = a + b;\nendmodule\n"
CMP_BAD = "module cmp(input [7:0] a, b, output gt);\n  assign gt = (a < b);\nendmodule\n"
CMP_GOOD = "module cmp(input [7:0] a, b, output gt);\n  assign gt = (a > b);\nendmodule\n"


def _tb_adder(test_id):
    return (
        "`timescale 1ns/1ps\nmodule tb;\n reg [7:0] a,b; wire [8:0] sum;\n"
        " adder uut(.a(a),.b(b),.sum(sum));\n initial begin\n"
        "  a=8'd3; b=8'd4; #5;\n"
        f'  if (sum!==9\'d7) $display("TDES_FAIL: test_id={test_id} | input=a=3,b=4 | expected=7 | got=%d", sum);\n'
        f'  else $display("TDES_PASS: test_id={test_id}");\n'
        "  $finish;\n end\nendmodule\n"
    )


def _tb_cmp(test_id):
    return (
        "`timescale 1ns/1ps\nmodule tb;\n reg [7:0] a,b; wire gt;\n"
        " cmp uut(.a(a),.b(b),.gt(gt));\n initial begin\n"
        "  a=8'd5; b=8'd3; #5;\n"
        f'  if (gt!==1\'b1) $display("TDES_FAIL: test_id={test_id} | input=a=5,b=3 | expected=1 | got=%b", gt);\n'
        f'  else $display("TDES_PASS: test_id={test_id}");\n'
        "  $finish;\n end\nendmodule\n"
    )


def _suite():
    return VerilogTestSuite(
        module_names=["adder", "cmp"],
        tests=[
            VerilogTest("u_add", TestLevel.UNIT, "adder", "8-bit add 3+4=7", _tb_adder("u_add")),
            VerilogTest("u_cmp", TestLevel.UNIT, "cmp", "greater-than 5>3", _tb_cmp("u_cmp")),
        ],
    )


def _scripted_fix(module, source, feedback, memory_text):
    if module == "adder":
        return ADDER_GOOD, "use + instead of &"
    if module == "cmp":
        return CMP_GOOD, "use > instead of <"
    return None


@unittest.skipUnless(tools_available(), "iverilog/vvp not on PATH")
class FPGAControllerE2E(unittest.TestCase):
    def test_converges_on_buggy_verilog(self):
        seed = Candidate(modules={"adder": ADDER_BAD, "cmp": CMP_BAD})
        suite = _suite()
        with tempfile.TemporaryDirectory() as out:
            cfg = FPGAConfig(
                pop_size=3, max_generations=4, output_dir=out, random_seed=3, suite_timeout=30
            )
            controller = FPGAController(seed, suite, ScriptedMutator(_scripted_fix), cfg)
            result = controller.run()
            self.assertFalse(result.escalated)
            self.assertEqual(result.best.vector.total_passes, len(suite.tests))

    def test_seed_is_partially_failing(self):
        suite = _suite()
        vec = suite.run(Candidate(modules={"adder": ADDER_BAD, "cmp": CMP_BAD}), timeout=30)
        self.assertEqual(vec.total_passes, 0)


if __name__ == "__main__":
    unittest.main()
