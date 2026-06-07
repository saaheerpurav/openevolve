"""
Benchmark loaders for TDES-FPGA.

Each loader turns a published RTL-generation benchmark design into the
``(seed Candidate, VerilogTestSuite, scripted_mutator)`` triple the controller
needs:

  * **seed** — a skeleton module with the correct name + ports but no logic
    (so it compiles and fails meaningfully, giving the LLM a clean start).
  * **suite** — the benchmark testbench, either wrapped as a single system-level
    test (native) or split into a hierarchy by ``testbench_decomposer`` (best
    effort; falls back to native).
  * **scripted_mutator** — an offline mutator that injects the *reference* RTL,
    used to validate the pipeline end-to-end without an LLM.

Supported: RTLLM v2 (``hkust-zhiyao/RTLLM``), ArchXBench
(``sureshpurini/ArchXBench``), ResBench (``jultrishyyy/ResBench``).
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Tuple

from openevolve.tdes.fpga import testbench_decomposer as decomp
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.mutation import ScriptedMutator
from openevolve.tdes.types import Candidate, TestLevel

_HERE = os.path.dirname(os.path.abspath(__file__))
_BENCH_ROOT = os.path.join(_HERE, "benchmarks")

LoaderResult = Tuple[Candidate, VerilogTestSuite, Optional[ScriptedMutator]]


# ---------------------------------------------------------------------------
# Shared Verilog helpers
# ---------------------------------------------------------------------------

_MODULE_DECL_RE = re.compile(r"\bmodule\s+(\w+)", re.IGNORECASE)
_INST_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_DECL_LINE_RE = re.compile(
    r"^\s*(input|output|inout|reg|wire|logic|parameter|localparam)\b", re.IGNORECASE
)
_TB_KEYWORDS = {
    "module",
    "reg",
    "wire",
    "integer",
    "initial",
    "always",
    "task",
    "function",
    "assign",
    "if",
    "for",
    "while",
    "begin",
    "end",
    "repeat",
    "case",
    "real",
    "logic",
    "localparam",
    "parameter",
}


def parse_dut_module_name(testbench: str) -> Optional[str]:
    """The module name instantiated inside the testbench (the DUT)."""
    for m in _INST_RE.finditer(testbench):
        type_name, inst_name = m.group(1), m.group(2)
        if type_name.lower() in _TB_KEYWORDS:
            continue
        if inst_name.lower() in {"begin"}:
            continue
        return type_name
    return None


def rename_top_module(source: str, new_name: str, design_hint: str = "") -> str:
    """Rename the design's top module to ``new_name``.

    Prefers a module named ``verified_<hint>`` / containing the hint; otherwise
    renames the first module declared.
    """
    names = _MODULE_DECL_RE.findall(source)
    if not names:
        return source
    target = None
    for n in names:
        if n == new_name:
            return source  # already correct
        if design_hint and design_hint.lower() in n.lower():
            target = n
            break
        if n.lower().startswith("verified"):
            target = n
            break
    if target is None:
        target = names[0]
    return re.sub(rf"\bmodule\s+{re.escape(target)}\b", f"module {new_name}", source, count=1)


def make_skeleton(reference_src: str, module_name: str) -> str:
    """Build a compilable, logic-free skeleton with the correct interface."""
    ref = rename_top_module(reference_src, module_name)
    m = re.search(r"\bmodule\s+" + re.escape(module_name) + r"\b(.*?);", ref, re.DOTALL)
    if not m:
        # Fall back to an empty module shell.
        return f"module {module_name}();\n  // TODO: implement\nendmodule\n"
    header = ref[m.start() : m.end()]
    ansi = bool(re.search(r"\b(input|output|inout)\b", header))
    lines = [header]
    if not ansi:
        # Non-ANSI: copy port/decl lines so the interface is declared.
        body = ref[m.end() :]
        for line in body.splitlines():
            if _DECL_LINE_RE.match(line):
                lines.append(line.rstrip())
    lines.append("  // TODO: implement")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def _reference_injecting_mutator(module_name: str, reference_src: str) -> ScriptedMutator:
    def fix(module, source, feedback, memory_text):
        if module == module_name:
            return reference_src, "inject reference RTL"
        return None

    mutator = ScriptedMutator(fix)
    mutator.reference = {module_name: reference_src}  # introspectable by experiments
    return mutator


def apply_reference(seed: Candidate) -> Optional[Candidate]:
    """Return a candidate with the reference RTL (from ``seed.metadata``) applied."""
    reference = seed.metadata.get("reference")
    if not reference:
        return None
    return Candidate(modules=dict(reference), metadata={"origin": "reference"})


def is_usable(seed: Candidate, suite: VerilogTestSuite, *, timeout: int = 60) -> bool:
    """True if the design is a sound evolution target.

    A design is usable when its known-good reference passes the entire suite and
    the skeleton seed fails at least one test (so there is something to evolve).
    Designs whose reference fails under the open-source toolchain, or whose
    testbench is too weak to fail an empty skeleton, are excluded.
    """
    ref = apply_reference(seed)
    if ref is None:
        return False
    rv = suite.run(ref, timeout=timeout)
    if rv.total_passes != len(suite.tests):
        return False
    sv = suite.run(seed, timeout=timeout)
    return sv.total_passes < rv.total_passes


def _native_suite(module_name: str, testbench: str, description: str) -> VerilogTestSuite:
    test = VerilogTest(
        id=f"{module_name}_system",
        level=TestLevel.SYSTEM,
        module=module_name,
        description=description or f"Full benchmark testbench for {module_name}",
        testbench_source=testbench,
    )
    return VerilogTestSuite(module_names=[module_name], tests=[test], top_module=module_name)


def _reference_passes(suite: VerilogTestSuite, module_name: str, reference: str) -> bool:
    """True if the known-good reference passes every test in ``suite``."""
    vec = suite.run(Candidate(modules={module_name: reference}), timeout=60)
    return vec.total_passes == len(suite.tests) and len(suite.tests) > 0


def _build_suite(
    module_name: str,
    testbench: str,
    description: str,
    *,
    decompose: bool,
    reference: str = "",
) -> VerilogTestSuite:
    """Build a suite, preferring a hierarchical decomposition when it is sound.

    A decomposed suite is only used if it is *reference-sound*: the known-good
    reference RTL must pass every generated test (validated when a reference and
    the EDA toolchain are both available). Otherwise we fall back to running the
    native benchmark testbench as a single system-level test, so a correct
    design is never scored as failing.
    """
    if decompose:
        from openevolve.tdes.fpga.verilog_runner import tools_available

        tests = decomp.decompose(testbench, module_name, description)
        if tests:
            decomposed = VerilogTestSuite(
                module_names=[module_name], tests=tests, top_module=module_name
            )
            if not reference or not tools_available():
                return decomposed  # cannot validate; trust the decomposer + clk guard
            if _reference_passes(decomposed, module_name, reference):
                return decomposed
    return _native_suite(module_name, testbench, description)


# ---------------------------------------------------------------------------
# RTLLM
# ---------------------------------------------------------------------------


def _find_rtllm_design(name: str, root: str) -> str:
    for category in ("Arithmetic", "Control", "Memory", "Miscellaneous"):
        cat = os.path.join(root, category)
        if not os.path.isdir(cat):
            continue
        for dirpath, dirnames, filenames in os.walk(cat):
            if os.path.basename(dirpath) == name and "testbench.v" in filenames:
                return dirpath
    raise FileNotFoundError(f"RTLLM design '{name}' not found under {root}")


def load_rtllm(
    design: str,
    *,
    bench_dir: Optional[str] = None,
    with_mutator: bool = False,
    decompose: bool = False,
) -> LoaderResult:
    root = bench_dir or os.path.join(_BENCH_ROOT, "rtllm")
    ddir = _find_rtllm_design(design, root)

    with open(os.path.join(ddir, "testbench.v"), "r", encoding="utf-8", errors="ignore") as f:
        testbench = f.read()
    desc_path = os.path.join(ddir, "design_description.txt")
    description = ""
    if os.path.exists(desc_path):
        with open(desc_path, "r", encoding="utf-8", errors="ignore") as f:
            description = _first_sentence(f.read())

    module_name = parse_dut_module_name(testbench) or design
    ref_file = next(
        (fn for fn in os.listdir(ddir) if fn.startswith("verified") and fn.endswith(".v")), None
    )
    reference = ""
    if ref_file:
        with open(os.path.join(ddir, ref_file), "r", encoding="utf-8", errors="ignore") as f:
            reference = rename_top_module(f.read(), module_name, design_hint=design)

    skeleton = make_skeleton(reference, module_name) if reference else _empty_module(module_name)
    meta = {"origin": "seed", "design": design}
    if reference:
        meta["reference"] = {module_name: reference}
    seed = Candidate(modules={module_name: skeleton}, metadata=meta)
    suite = _build_suite(
        module_name, testbench, description, decompose=decompose, reference=reference
    )
    mutator = (
        _reference_injecting_mutator(module_name, reference)
        if (with_mutator and reference)
        else None
    )
    return seed, suite, mutator


# ---------------------------------------------------------------------------
# ArchXBench
# ---------------------------------------------------------------------------


def _find_archxbench_design(name: str, root: str) -> str:
    for level in sorted(os.listdir(root)):
        ldir = os.path.join(root, level)
        if not os.path.isdir(ldir) or not level.lower().startswith("level"):
            continue
        cand = os.path.join(ldir, name)
        if os.path.isdir(cand):
            return cand
    raise FileNotFoundError(f"ArchXBench design '{name}' not found under {root}")


def load_archxbench(
    design: str,
    *,
    bench_dir: Optional[str] = None,
    with_mutator: bool = False,
    decompose: bool = False,
) -> LoaderResult:
    root = bench_dir or os.path.join(_BENCH_ROOT, "archxbench")
    ddir = _find_archxbench_design(design, root)

    tb_file = next((fn for fn in os.listdir(ddir) if fn.endswith(".v")), "tb.v")
    with open(os.path.join(ddir, tb_file), "r", encoding="utf-8", errors="ignore") as f:
        testbench = f.read()
    spec_path = os.path.join(ddir, "design-specs.txt")
    description, header = "", ""
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8", errors="ignore") as f:
            spec_text = f.read()
        description = _first_sentence(spec_text)
        header = _extract_module_header(spec_text)

    module_name = parse_dut_module_name(testbench) or design
    skeleton = make_skeleton(header, module_name) if header else _empty_module(module_name)
    seed = Candidate(modules={module_name: skeleton}, metadata={"origin": "seed", "design": design})
    suite = _build_suite(module_name, testbench, description, decompose=decompose)
    # ArchXBench ships no reference RTL, so there is no reference-injecting mutator.
    return seed, suite, None


# ---------------------------------------------------------------------------
# ResBench (problems.json driven)
# ---------------------------------------------------------------------------


def load_resbench(
    design: str,
    *,
    bench_dir: Optional[str] = None,
    with_mutator: bool = False,
    decompose: bool = False,
) -> LoaderResult:
    root = bench_dir or os.path.join(_BENCH_ROOT, "resbench")
    with open(os.path.join(root, "problems.json"), "r", encoding="utf-8") as f:
        problems = json.load(f)

    problem = None
    for _domain, items in problems.items():
        for item in items:
            if item.get("module") == design:
                problem = item
                break
        if problem:
            break
    if problem is None:
        raise FileNotFoundError(f"ResBench design '{design}' not found in problems.json")

    module_name = problem["module"]
    testbench = problem["Testbench"]
    description = _first_sentence(problem.get("Problem", ""))
    header = problem.get("Module header", "")
    skeleton = (
        make_skeleton(header + "\nendmodule\n", module_name)
        if header
        else _empty_module(module_name)
    )
    seed = Candidate(modules={module_name: skeleton}, metadata={"origin": "seed", "design": design})

    # Reference solution, if present, enables the offline mutator + decomposition gating.
    reference = _resbench_reference(root, design, module_name)
    if reference:
        seed.metadata["reference"] = {module_name: reference}
    suite = _build_suite(
        module_name, testbench, description, decompose=decompose, reference=reference
    )
    mutator = (
        _reference_injecting_mutator(module_name, reference)
        if (with_mutator and reference)
        else None
    )
    return seed, suite, mutator


def _resbench_reference(root: str, design: str, module_name: str) -> str:
    sol_dir = os.path.join(root, "solutions")
    for fn in ("solutions.json", "sample.json"):
        path = os.path.join(sol_dir, fn)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        code = _search_solution(data, design)
        if code:
            return rename_top_module(code, module_name, design_hint=design)
    return ""


def _search_solution(data, design: str) -> str:
    if isinstance(data, dict):
        if data.get("module") == design and isinstance(
            data.get("code") or data.get("solution"), str
        ):
            return data.get("code") or data.get("solution")
        for v in data.values():
            found = _search_solution(v, design)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _search_solution(item, design)
            if found:
                return found
    return ""


# ---------------------------------------------------------------------------
# misc helpers
# ---------------------------------------------------------------------------


def _empty_module(name: str) -> str:
    return f"module {name}();\n  // TODO: implement\nendmodule\n"


def _first_sentence(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return text[:limit]


def _extract_module_header(spec_text: str) -> str:
    """Extract a ``module ... );`` header from a spec file (ends at endmodule shell)."""
    m = re.search(r"\bmodule\s+\w+.*?\)\s*;", spec_text, re.DOTALL)
    if not m:
        return ""
    return m.group(0) + "\nendmodule\n"
