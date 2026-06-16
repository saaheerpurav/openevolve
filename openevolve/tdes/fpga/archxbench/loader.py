"""
ArchXBench Level 3-4 TDES loader.

Builds (seed Candidate, VerilogTestSuite, ScriptedMutator) triples for each
design, following the same contract as ``fpga.benchmark_loader`` and
``fpga.experiments.hierarchical_archx``.

Each design is split into two sub-modules:
  - Module A: special-case handler (combinational)
  - Module B: arithmetic core (combinational)
  - Top: registered integrator (instantiates A+B, picked up via include in suite)

The three-tier TDES test hierarchy:
  UNIT(module_a): special-case inputs only
  UNIT(module_b): normal arithmetic inputs
  SYSTEM: full ArchXBench test vector set (uses the clocked top module)
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.mutation import ScriptedMutator
from openevolve.tdes.types import Candidate, TestLevel

_HERE = os.path.dirname(os.path.abspath(__file__))
_DESIGNS_DIR = os.path.join(_HERE, "designs")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _design_path(design: str) -> str:
    return os.path.join(_DESIGNS_DIR, design)


# ---------------------------------------------------------------------------
# fp_adder
# ---------------------------------------------------------------------------

_FP_ADDER_MODULES = ("fp_special_case", "fp_adder_core")
_FP_ADDER_TOP     = "floating_point_adder"


def _fp_adder_suite() -> VerilogTestSuite:
    base = _design_path("fp_adder")
    tests_dir = os.path.join(base, "tests")
    ref_dir   = os.path.join(base, "reference")

    unit_special_tb = _read(os.path.join(tests_dir, "unit_special_tb.v"))
    unit_core_tb    = _read(os.path.join(tests_dir, "unit_core_tb.v"))
    system_tb       = _read(os.path.join(tests_dir, "system_tb.v"))

    # The SYSTEM test requires the top module alongside both sub-modules.
    top_src = _read(os.path.join(ref_dir, _FP_ADDER_TOP + ".v"))

    tests = [
        VerilogTest(
            id="unit_special",
            level=TestLevel.UNIT,
            module="fp_special_case",
            description="fp_special_case: NaN/Inf/zero detection and output",
            testbench_source=unit_special_tb,
            modules=["fp_special_case"],
        ),
        VerilogTest(
            id="unit_core",
            level=TestLevel.UNIT,
            module="fp_adder_core",
            description="fp_adder_core: normal/denormal IEEE-754 addition",
            testbench_source=unit_core_tb,
            modules=["fp_adder_core"],
        ),
        VerilogTest(
            id="system_full",
            level=TestLevel.SYSTEM,
            # Primary module for CEGIS routing: when system fails, mutate core first.
            # The top integrator is fixed (embedded in testbench_source), not evolved.
            module="fp_adder_core",
            description="floating_point_adder: all 36 ArchXBench test vectors",
            # Top integrator source prepended so iverilog sees all modules.
            testbench_source=top_src + "\n" + system_tb,
            modules=["fp_special_case", "fp_adder_core"],  # only evolved modules
        ),
    ]
    return VerilogTestSuite(
        module_names=list(_FP_ADDER_MODULES),
        tests=tests,
        top_module=_FP_ADDER_TOP,
        isolate_modules=True,  # unit tests only compile relevant modules
    )


def load_fp_adder(
    *, with_mutator: bool = True
) -> Tuple[Candidate, VerilogTestSuite, Optional[ScriptedMutator]]:
    base = _design_path("fp_adder")
    seed_dir = os.path.join(base, "seed")
    ref_dir  = os.path.join(base, "reference")

    seed = Candidate(
        modules={
            m: _read(os.path.join(seed_dir, m + ".v"))
            for m in _FP_ADDER_MODULES
        },
        metadata={"origin": "seed", "design": "fp_adder"},
    )

    suite = _fp_adder_suite()

    mutator = None
    if with_mutator:
        references = {
            m: _read(os.path.join(ref_dir, m + ".v"))
            for m in _FP_ADDER_MODULES
        }

        def _fix(module, source, feedback, memory_text):
            if module in references:
                return references[module], f"inject reference {module}"
            return None

        mutator = ScriptedMutator(_fix)
        mutator.reference = dict(references)

    return seed, suite, mutator


# ---------------------------------------------------------------------------
# fp_multiplier
# ---------------------------------------------------------------------------

_FP_MULT_MODULES = ("fp_mult_special", "fp_mult_core")
_FP_MULT_TOP     = "floating_point_multiplier"


def _fp_multiplier_suite() -> VerilogTestSuite:
    base = _design_path("fp_multiplier")
    tests_dir = os.path.join(base, "tests")
    ref_dir   = os.path.join(base, "reference")

    unit_special_tb = _read(os.path.join(tests_dir, "unit_special_tb.v"))
    unit_core_tb    = _read(os.path.join(tests_dir, "unit_core_tb.v"))
    system_tb       = _read(os.path.join(tests_dir, "system_tb.v"))
    top_src         = _read(os.path.join(ref_dir, _FP_MULT_TOP + ".v"))

    tests = [
        VerilogTest(
            id="unit_special",
            level=TestLevel.UNIT,
            module="fp_mult_special",
            description="fp_mult_special: NaN/Inf/zero detection for multiplication",
            testbench_source=unit_special_tb,
            modules=["fp_mult_special"],
        ),
        VerilogTest(
            id="unit_core",
            level=TestLevel.UNIT,
            module="fp_mult_core",
            description="fp_mult_core: normal IEEE-754 significand multiply+normalize",
            testbench_source=unit_core_tb,
            modules=["fp_mult_core"],
        ),
        VerilogTest(
            id="system_full",
            level=TestLevel.SYSTEM,
            module="fp_mult_core",  # CEGIS routing: mutate core when system fails
            description="floating_point_multiplier: all 10 ArchXBench test vectors",
            testbench_source=top_src + "\n" + system_tb,
            modules=["fp_mult_special", "fp_mult_core"],  # only evolved modules
        ),
    ]
    return VerilogTestSuite(
        module_names=list(_FP_MULT_MODULES),
        tests=tests,
        top_module=_FP_MULT_TOP,
        isolate_modules=True,
    )


def load_fp_multiplier(
    *, with_mutator: bool = True
) -> Tuple[Candidate, VerilogTestSuite, Optional[ScriptedMutator]]:
    base = _design_path("fp_multiplier")
    seed_dir = os.path.join(base, "seed")
    ref_dir  = os.path.join(base, "reference")

    seed = Candidate(
        modules={
            m: _read(os.path.join(seed_dir, m + ".v"))
            for m in _FP_MULT_MODULES
        },
        metadata={"origin": "seed", "design": "fp_multiplier"},
    )

    suite = _fp_multiplier_suite()

    mutator = None
    if with_mutator:
        references = {
            m: _read(os.path.join(ref_dir, m + ".v"))
            for m in _FP_MULT_MODULES
        }

        def _fix(module, source, feedback, memory_text):
            if module in references:
                return references[module], f"inject reference {module}"
            return None

        mutator = ScriptedMutator(_fix)
        mutator.reference = dict(references)

    return seed, suite, mutator


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DESIGNS = {
    "fp_adder":       load_fp_adder,
    "fp_multiplier":  load_fp_multiplier,
}


def load(design: str, *, with_mutator: bool = True):
    """Load a design by name. Returns (seed, suite, mutator)."""
    if design not in DESIGNS:
        raise KeyError(f"Unknown design '{design}'. Available: {list(DESIGNS)}")
    return DESIGNS[design](with_mutator=with_mutator)


def is_usable(seed: Candidate, suite: VerilogTestSuite, *, sandbox: bool = True) -> bool:
    """Gate: reference passes all tests and seed fails at least one UNIT test per module."""
    from openevolve.tdes.fpga.benchmark_loader import is_usable as _fpga_usable
    return _fpga_usable(seed, suite)
