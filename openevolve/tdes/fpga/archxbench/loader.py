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
_FP_ADDER_TOP = "floating_point_adder"


def _fp_adder_suite() -> VerilogTestSuite:
    base = _design_path("fp_adder")
    tests_dir = os.path.join(base, "tests")
    ref_dir = os.path.join(base, "reference")

    unit_special_tb = _read(os.path.join(tests_dir, "unit_special_tb.v"))
    unit_core_tb = _read(os.path.join(tests_dir, "unit_core_tb.v"))
    system_tb = _read(os.path.join(tests_dir, "system_tb.v"))

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
    ref_dir = os.path.join(base, "reference")

    seed = Candidate(
        modules={m: _read(os.path.join(seed_dir, m + ".v")) for m in _FP_ADDER_MODULES},
        metadata={"origin": "seed", "design": "fp_adder"},
    )

    suite = _fp_adder_suite()

    mutator = None
    if with_mutator:
        references = {m: _read(os.path.join(ref_dir, m + ".v")) for m in _FP_ADDER_MODULES}

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
_FP_MULT_TOP = "floating_point_multiplier"


def _fp_multiplier_suite() -> VerilogTestSuite:
    base = _design_path("fp_multiplier")
    tests_dir = os.path.join(base, "tests")
    ref_dir = os.path.join(base, "reference")

    unit_special_tb = _read(os.path.join(tests_dir, "unit_special_tb.v"))
    unit_core_tb = _read(os.path.join(tests_dir, "unit_core_tb.v"))
    system_tb = _read(os.path.join(tests_dir, "system_tb.v"))
    top_src = _read(os.path.join(ref_dir, _FP_MULT_TOP + ".v"))

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
    ref_dir = os.path.join(base, "reference")

    seed = Candidate(
        modules={m: _read(os.path.join(seed_dir, m + ".v")) for m in _FP_MULT_MODULES},
        metadata={"origin": "seed", "design": "fp_multiplier"},
    )

    suite = _fp_multiplier_suite()

    mutator = None
    if with_mutator:
        references = {m: _read(os.path.join(ref_dir, m + ".v")) for m in _FP_MULT_MODULES}

        def _fix(module, source, feedback, memory_text):
            if module in references:
                return references[module], f"inject reference {module}"
            return None

        mutator = ScriptedMutator(_fix)
        mutator.reference = dict(references)

    return seed, suite, mutator


# ---------------------------------------------------------------------------
# fp_multiplier_fine — 7+7+10 = 24 granular VerilogTests
# ---------------------------------------------------------------------------

_FP_MULT_SPECIAL_CASES = [
    ("mspec_zero_times_zero", "fp_mult_special: 0×0 → special zero, flags=001"),
    ("mspec_zero_times_one", "fp_mult_special: 0×1.0 → special zero, flags=001"),
    ("mspec_inf_times_one", "fp_mult_special: +Inf×1.0 → special +Inf, flags=010"),
    ("mspec_inf_times_zero", "fp_mult_special: +Inf×0 → special NaN (invalid), flags=100"),
    ("mspec_nan_propagate", "fp_mult_special: NaN×1.0 → special NaN, flags=100"),
    ("mspec_neg_inf_sq", "fp_mult_special: -Inf×-Inf → special +Inf, flags=010"),
    ("mspec_normal_not_special", "fp_mult_special: 1.5×2.0 → is_special=0 (not a special case)"),
]

_FP_MULT_CORE_CASES = [
    ("mcore_1p5x2", "fp_mult_core: 1.5×2.0 = 3.0"),
    ("mcore_negxneg", "fp_mult_core: -2.5×-0.5 = 1.25"),
    ("mcore_1x1", "fp_mult_core: 1.0×1.0 = 1.0"),
    ("mcore_neg1xneg1", "fp_mult_core: -1.0×-1.0 = +1.0"),
    ("mcore_2x3", "fp_mult_core: 2.0×3.0 = 6.0"),
    ("mcore_overflow", "fp_mult_core: MAX_NORMAL×2.0 = +Inf (overflow), flags=010"),
    ("mcore_underflow", "fp_mult_core: MIN_DENORM×MIN_DENORM = 0 (flush-to-zero), flags=001"),
]

_FP_MULT_SYSTEM_CASES = [
    ("system_t0", "floating_point_multiplier: 0×0 = 0"),
    ("system_t1", "floating_point_multiplier: 0×1.0 = 0 (zero×normal)"),
    ("system_t2", "floating_point_multiplier: +Inf×1.0 = +Inf"),
    ("system_t3", "floating_point_multiplier: +Inf×0 = NaN (invalid)"),
    ("system_t4", "floating_point_multiplier: NaN×1.0 = NaN (propagate)"),
    ("system_t5", "floating_point_multiplier: 1.5×2.0 = 3.0"),
    ("system_t6", "floating_point_multiplier: -2.5×-0.5 = 1.25"),
    ("system_t7", "floating_point_multiplier: MAX×2.0 = +Inf (overflow)"),
    ("system_t8", "floating_point_multiplier: MIN_DENORM×MIN_DENORM = 0 (underflow)"),
    ("system_t9", "floating_point_multiplier: -1.0×-1.0 = +1.0"),
]


def _fp_multiplier_fine_suite() -> VerilogTestSuite:
    """Suite with 7+7+10=24 individual sub-case VerilogTests.

    Each sub-case gets its own VerilogTest with a test_id matching what the
    existing testbenches already emit (``mspec_*``, ``mcore_*``, ``system_t*``).
    A single simulation of the testbench produces all sub-case TDES_PASS/FAIL
    lines; ``interpret()`` extracts just the one it needs — giving TDES a
    fine-grained gradient rather than the 7-or-0 all-or-nothing scoring.
    """
    base = _design_path("fp_multiplier")
    tests_dir = os.path.join(base, "tests")
    ref_dir = os.path.join(base, "reference")

    unit_special_tb = _read(os.path.join(tests_dir, "unit_special_tb.v"))
    unit_core_tb = _read(os.path.join(tests_dir, "unit_core_tb.v"))
    system_tb = _read(os.path.join(tests_dir, "system_tb.v"))
    top_src = _read(os.path.join(ref_dir, _FP_MULT_TOP + ".v"))
    system_combined = top_src + "\n" + system_tb

    tests = []
    for tid, desc in _FP_MULT_SPECIAL_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.UNIT,
                module="fp_mult_special",
                description=desc,
                testbench_source=unit_special_tb,
                modules=["fp_mult_special"],
            )
        )
    for tid, desc in _FP_MULT_CORE_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.UNIT,
                module="fp_mult_core",
                description=desc,
                testbench_source=unit_core_tb,
                modules=["fp_mult_core"],
            )
        )
    for tid, desc in _FP_MULT_SYSTEM_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.SYSTEM,
                module="fp_mult_core",
                description=desc,
                testbench_source=system_combined,
                modules=["fp_mult_special", "fp_mult_core"],
            )
        )
    return VerilogTestSuite(
        module_names=list(_FP_MULT_MODULES),
        tests=tests,
        top_module=_FP_MULT_TOP,
        isolate_modules=True,
    )


def load_fp_multiplier_fine(
    *, with_mutator: bool = True
) -> Tuple[Candidate, VerilogTestSuite, Optional[ScriptedMutator]]:
    """Fine-grained fp_multiplier: 7+7+10=24 individual VerilogTests."""
    base = _design_path("fp_multiplier")
    seed_dir = os.path.join(base, "seed")
    ref_dir = os.path.join(base, "reference")

    seed = Candidate(
        modules={m: _read(os.path.join(seed_dir, m + ".v")) for m in _FP_MULT_MODULES},
        metadata={"origin": "seed", "design": "fp_multiplier_fine"},
    )
    suite = _fp_multiplier_fine_suite()

    mutator = None
    if with_mutator:
        references = {m: _read(os.path.join(ref_dir, m + ".v")) for m in _FP_MULT_MODULES}

        def _fix(module, source, feedback, memory_text):
            if module in references:
                return references[module], f"inject reference {module}"
            return None

        mutator = ScriptedMutator(_fix)
        mutator.reference = dict(references)

    return seed, suite, mutator


# ---------------------------------------------------------------------------
# fp_mult_pipeline — decomposed Level-4 pipelined FP multiplier (5 modules)
# ---------------------------------------------------------------------------

_FPM_PIPE_MODULES = (
    "fpm_unpack",
    "fpm_multiply",
    "fpm_normalize",
    "fpm_round_pack",
    "fpm_special",
)
_FPM_PIPE_TOP = "fp_mult_pipeline"

_FPM_PIPE_UNPACK_CASES = [
    ("unpack_normal_pos", "fpm_unpack: 1.0 → sign=0, exp=127, mant with implicit 1"),
    ("unpack_negative", "fpm_unpack: -2.0 → sign=1, exp=128"),
    ("unpack_zero", "fpm_unpack: +0.0 → is_zero=1"),
    ("unpack_nan", "fpm_unpack: NaN (7FC00000) → is_nan=1"),
    ("unpack_inf", "fpm_unpack: +Inf → is_inf=1"),
    ("unpack_neg_zero", "fpm_unpack: -0.0 → sign=1, is_zero=1"),
    ("unpack_denorm", "fpm_unpack: denormal → exp=0, mant without implicit 1"),
    ("unpack_b_nan", "fpm_unpack: b-channel NaN detection"),
]

_FPM_PIPE_MULTIPLY_CASES = [
    ("mult_1x1", "fpm_multiply: 1.0×1.0 product and exponent"),
    ("mult_1p5x2", "fpm_multiply: 1.5×2.0 product and exponent"),
    ("mult_neg_sign", "fpm_multiply: -1.0×1.0 → result_sign=1"),
    ("mult_neg_neg", "fpm_multiply: -1.0×-1.0 → result_sign=0"),
    ("mult_2x3", "fpm_multiply: 2.0×3.0 product and exponent"),
    ("mult_large_exp", "fpm_multiply: large exponents → raw_exp=381"),
]

_FPM_PIPE_NORMALIZE_CASES = [
    ("norm_1x1", "fpm_normalize: product from 1.0×1.0 (bit47=0)"),
    ("norm_1p5x2", "fpm_normalize: product from 1.5×2.0 frac=400000"),
    ("norm_msb_set", "fpm_normalize: bit47=1 → exp+1"),
    ("norm_guard_sticky", "fpm_normalize: guard=1, sticky=1"),
    ("norm_guard_only", "fpm_normalize: guard=1, sticky=0"),
]

_FPM_PIPE_ROUND_PACK_CASES = [
    ("rpack_one", "fpm_round_pack: 1.0 (no rounding) → 3F800000"),
    ("rpack_three", "fpm_round_pack: 3.0 → 40400000"),
    ("rpack_neg", "fpm_round_pack: -2.0 → C0000000"),
    ("rpack_overflow", "fpm_round_pack: exp=255 → overflow → +Inf"),
    ("rpack_underflow", "fpm_round_pack: exp=0 → underflow → zero"),
    ("rpack_round_up", "fpm_round_pack: guard=1, sticky=1 → round up"),
    ("rpack_ties_even", "fpm_round_pack: guard=1, sticky=0, frac[0]=0 → no round"),
    ("rpack_ties_odd", "fpm_round_pack: guard=1, sticky=0, frac[0]=1 → round up"),
]

_FPM_PIPE_SPECIAL_CASES = [
    ("spec_nan_prop", "fpm_special: NaN × anything → NaN"),
    ("spec_inf_x_zero", "fpm_special: Inf × 0 → NaN"),
    ("spec_zero_x_inf", "fpm_special: 0 × Inf → NaN"),
    ("spec_inf_result", "fpm_special: Inf × normal → Inf"),
    ("spec_neg_inf_sq", "fpm_special: -Inf × -Inf → +Inf"),
    ("spec_zero_result", "fpm_special: 0 × normal → signed zero"),
    ("spec_not_special", "fpm_special: normal × normal → is_special=0"),
]

_FPM_PIPE_SYSTEM_CASES = [
    ("sys_1x2", "fp_mult_pipeline: 1.0×2.0 = 2.0"),
    ("sys_2x3", "fp_mult_pipeline: 2.0×3.0 = 6.0"),
    ("sys_0p5x0p5", "fp_mult_pipeline: 0.5×0.5 = 0.25"),
    ("sys_4x0p25", "fp_mult_pipeline: 4.0×0.25 = 1.0"),
    ("sys_neg1x2", "fp_mult_pipeline: -1.0×2.0 = -2.0"),
    ("sys_negxneg", "fp_mult_pipeline: -1.0×-2.0 = 2.0"),
    ("sys_1xneg2", "fp_mult_pipeline: 1.0×-2.0 = -2.0"),
    ("sys_neg1xneg1", "fp_mult_pipeline: -1.0×-1.0 = 1.0"),
    ("sys_32x1", "fp_mult_pipeline: 32.0×1.0 = 32.0"),
    ("sys_large_sm", "fp_mult_pipeline: large×small = 1.0"),
    ("sys_sm_large", "fp_mult_pipeline: small×large = 0.5"),
    ("sys_nan_a", "fp_mult_pipeline: NaN×1.0 = NaN"),
    ("sys_nan_b", "fp_mult_pipeline: 1.0×NaN = NaN"),
    ("sys_zero_a", "fp_mult_pipeline: 0×1.0 = 0"),
    ("sys_negz_a", "fp_mult_pipeline: -0×1.0 = -0"),
    ("sys_zeroxinf", "fp_mult_pipeline: 0×Inf = NaN"),
    ("sys_inf_pos", "fp_mult_pipeline: +Inf×1.0 = +Inf"),
    ("sys_inf_neg", "fp_mult_pipeline: +Inf×-1.0 = -Inf"),
    ("sys_denorm", "fp_mult_pipeline: min_normal×1.0 = min_normal"),
    ("sys_overflow", "fp_mult_pipeline: large×large = +Inf (overflow)"),
    ("sys_underflow", "fp_mult_pipeline: tiny×tiny = 0 (underflow)"),
    ("sys_tiny_sq", "fp_mult_pipeline: tiny²"),
    ("sys_third_x2", "fp_mult_pipeline: ⅓×2 = ⅔ (rounding)"),
    ("sys_1x1", "fp_mult_pipeline: 1.0×1.0 = 1.0"),
    ("sys_2x2", "fp_mult_pipeline: 2.0×2.0 = 4.0"),
]


def _fp_mult_pipeline_suite() -> VerilogTestSuite:
    base = _design_path("fp_mult_pipeline")
    tests_dir = os.path.join(base, "tests")
    ref_dir = os.path.join(base, "reference")

    unit_unpack_tb = _read(os.path.join(tests_dir, "unit_unpack_tb.v"))
    unit_multiply_tb = _read(os.path.join(tests_dir, "unit_multiply_tb.v"))
    unit_normalize_tb = _read(os.path.join(tests_dir, "unit_normalize_tb.v"))
    unit_round_pack_tb = _read(os.path.join(tests_dir, "unit_round_pack_tb.v"))
    unit_special_tb = _read(os.path.join(tests_dir, "unit_special_tb.v"))
    system_tb = _read(os.path.join(tests_dir, "system_tb.v"))
    top_src = _read(os.path.join(ref_dir, _FPM_PIPE_TOP + ".v"))

    tests = []

    for tid, desc in _FPM_PIPE_UNPACK_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.UNIT,
                module="fpm_unpack",
                description=desc,
                testbench_source=unit_unpack_tb,
                modules=["fpm_unpack"],
            )
        )

    for tid, desc in _FPM_PIPE_MULTIPLY_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.UNIT,
                module="fpm_multiply",
                description=desc,
                testbench_source=unit_multiply_tb,
                modules=["fpm_multiply"],
            )
        )

    for tid, desc in _FPM_PIPE_NORMALIZE_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.UNIT,
                module="fpm_normalize",
                description=desc,
                testbench_source=unit_normalize_tb,
                modules=["fpm_normalize"],
            )
        )

    for tid, desc in _FPM_PIPE_ROUND_PACK_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.UNIT,
                module="fpm_round_pack",
                description=desc,
                testbench_source=unit_round_pack_tb,
                modules=["fpm_round_pack"],
            )
        )

    for tid, desc in _FPM_PIPE_SPECIAL_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.UNIT,
                module="fpm_special",
                description=desc,
                testbench_source=unit_special_tb,
                modules=["fpm_special"],
            )
        )

    system_combined = top_src + "\n" + system_tb
    for tid, desc in _FPM_PIPE_SYSTEM_CASES:
        tests.append(
            VerilogTest(
                id=tid,
                level=TestLevel.SYSTEM,
                module="fpm_round_pack",
                description=desc,
                testbench_source=system_combined,
                modules=list(_FPM_PIPE_MODULES),
            )
        )

    return VerilogTestSuite(
        module_names=list(_FPM_PIPE_MODULES),
        tests=tests,
        top_module=_FPM_PIPE_TOP,
        isolate_modules=True,
    )


def load_fp_mult_pipeline(
    *, with_mutator: bool = True
) -> Tuple[Candidate, VerilogTestSuite, Optional[ScriptedMutator]]:
    """Decomposed Level-4 pipelined FP multiplier: 5 sub-modules, 59 tests."""
    base = _design_path("fp_mult_pipeline")
    seed_dir = os.path.join(base, "seed")
    ref_dir = os.path.join(base, "reference")

    seed = Candidate(
        modules={m: _read(os.path.join(seed_dir, m + ".v")) for m in _FPM_PIPE_MODULES},
        metadata={"origin": "seed", "design": "fp_mult_pipeline"},
    )

    suite = _fp_mult_pipeline_suite()

    mutator = None
    if with_mutator:
        references = {m: _read(os.path.join(ref_dir, m + ".v")) for m in _FPM_PIPE_MODULES}

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
    "fp_adder": load_fp_adder,
    "fp_multiplier": load_fp_multiplier,
    "fp_multiplier_fine": load_fp_multiplier_fine,
    "fp_mult_pipeline": load_fp_mult_pipeline,
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
