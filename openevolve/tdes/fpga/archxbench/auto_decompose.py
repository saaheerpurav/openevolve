"""Auto-decompose-then-evolve harness for ArchXBench RTL tasks.

This module implements the two-stage paper direction:

Stage 1:
    Given only a task spec plus the original ArchXBench system testbench, ask an
    LLM to produce a decomposition scaffold: submodule interfaces, reference
    implementations, empty seeds, a top wrapper, and module-level tests.
    The composed reference implementation must pass the original system
    testbench before the scaffold can be used.

Stage 2:
    Feed the generated seeds and generated local tests into the existing TDES
    controller. Report final success only against the original system testbench.

The generated unit tests are search scaffolding, not the benchmark judge.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from openevolve.tdes import selection
from openevolve.tdes.fpga import ablation, baselines, metrics, verilog_runner
from openevolve.tdes.fpga.archxbench import loader as archx_loader
from openevolve.tdes.fpga.archxbench.probe_module_solvability import CodexCLIBackend
from openevolve.tdes.fpga.archxbench.run_decompose import _CountingEnsemble, build_ensemble
from openevolve.tdes.fpga.config import FPGAConfig
from openevolve.tdes.fpga.experiments._explib import IncrementalWriter, setup_logging
from openevolve.tdes.fpga.mutation import VerilogLLMMutator
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.types import Candidate, TestLevel

logger = logging.getLogger(__name__)

MANIFEST = "manifest.json"
AUTO_SYSTEM = (
    "You are an expert RTL architect and verification engineer. Your task is to "
    "convert a hard monolithic Verilog design task into a modular scaffold for "
    "agentic synthesis. You must preserve the original top-level behavior. "
    "Generated unit tests are only internal guidance; the final judge is the "
    "original ArchXBench system testbench."
)


@dataclass(frozen=True)
class AutoModule:
    name: str
    seed_path: str
    reference_path: str
    description: str = ""


@dataclass(frozen=True)
class AutoTest:
    id: str
    level: TestLevel
    module: str
    description: str
    testbench_path: str
    modules: Tuple[str, ...]
    original_system: bool = False


@dataclass
class AutoScaffold:
    name: str
    top_module: str
    top_path: str
    modules: List[AutoModule]
    tests: List[AutoTest]
    root: Path
    source_design: Optional[str] = None
    notes: str = ""

    @property
    def module_names(self) -> List[str]:
        return [m.name for m in self.modules]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _candidate_from(scaffold: AutoScaffold, kind: str) -> Candidate:
    if kind not in {"seed", "reference"}:
        raise ValueError(f"unknown candidate kind: {kind}")
    modules: Dict[str, str] = {}
    for mod in scaffold.modules:
        rel = mod.seed_path if kind == "seed" else mod.reference_path
        modules[mod.name] = _read(scaffold.root / rel)
    return Candidate(
        modules=modules,
        metadata={"origin": kind, "design": scaffold.name, "auto_decomposed": True},
    )


def build_suite(scaffold: AutoScaffold) -> VerilogTestSuite:
    """Build a VerilogTestSuite from a generated scaffold manifest."""
    tests: List[VerilogTest] = []
    top_src = _read(scaffold.root / scaffold.top_path)
    evolvable = set(scaffold.module_names)
    for spec in scaffold.tests:
        tb_src = _read(scaffold.root / spec.testbench_path)
        if spec.original_system:
            tb_src = top_src + "\n" + tb_src
        primary_module = spec.module
        if primary_module not in evolvable:
            primary_module = next((m for m in spec.modules if m in evolvable), scaffold.module_names[-1])
        tests.append(
            VerilogTest(
                id=spec.id,
                level=spec.level,
                module=primary_module,
                description=spec.description,
                testbench_source=tb_src,
                modules=list(spec.modules),
            )
        )
    return VerilogTestSuite(
        module_names=scaffold.module_names,
        tests=tests,
        top_module=scaffold.top_module,
        isolate_modules=True,
    )


def load_scaffold(root: str | Path) -> AutoScaffold:
    root = Path(root)
    data = json.loads(_read(root / MANIFEST))
    modules = [
        AutoModule(
            name=m["name"],
            seed_path=m["seed_path"],
            reference_path=m["reference_path"],
            description=m.get("description", ""),
        )
        for m in data["modules"]
    ]
    tests = [
        AutoTest(
            id=t["id"],
            level=TestLevel.from_str(t["level"]),
            module=t["module"],
            description=t["description"],
            testbench_path=t["testbench_path"],
            modules=tuple(t.get("modules") or [t["module"]]),
            original_system=bool(t.get("original_system", False)),
        )
        for t in data["tests"]
    ]
    return AutoScaffold(
        name=data["name"],
        top_module=data["top_module"],
        top_path=data["top_path"],
        modules=modules,
        tests=tests,
        root=root,
        source_design=data.get("source_design"),
        notes=data.get("notes", ""),
    )


def save_scaffold(scaffold: AutoScaffold) -> None:
    data = {
        "schema": "tdes.auto_decompose.v1",
        "name": scaffold.name,
        "source_design": scaffold.source_design,
        "top_module": scaffold.top_module,
        "top_path": scaffold.top_path,
        "notes": scaffold.notes,
        "modules": [
            {
                "name": m.name,
                "seed_path": m.seed_path,
                "reference_path": m.reference_path,
                "description": m.description,
            }
            for m in scaffold.modules
        ],
        "tests": [
            {
                "id": t.id,
                "level": t.level.name.lower(),
                "module": t.module,
                "description": t.description,
                "testbench_path": t.testbench_path,
                "modules": list(t.modules),
                "original_system": t.original_system,
            }
            for t in scaffold.tests
        ],
    }
    _write(scaffold.root / MANIFEST, json.dumps(data, indent=2, sort_keys=True))


def materialize_existing_archxbench_design(design: str, out_dir: str | Path) -> AutoScaffold:
    """Copy an existing hand-written decomposition into the auto-scaffold format.

    This is a harness smoke test and a manual-decomposition upper bound. It is
    not an auto-decomposition result.
    """
    seed, suite, mutator = archx_loader.load(design, with_mutator=True)
    references = getattr(mutator, "reference", None)
    if references is None:
        raise ValueError(f"design '{design}' does not expose reference modules")

    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    base = Path(archx_loader._design_path(design))  # test harness in same package
    ref_dir = base / "reference"
    top_module = suite.top_module or design
    top_file = ref_dir / f"{top_module}.v"
    if not top_file.exists():
        raise FileNotFoundError(f"top reference not found: {top_file}")
    _write(out / "top" / top_file.name, _read(top_file))

    modules: List[AutoModule] = []
    for name in suite.module_names:
        seed_path = Path("seed") / f"{name}.v"
        ref_path = Path("reference") / f"{name}.v"
        _write(out / seed_path, seed.modules[name])
        _write(out / ref_path, references[name])
        modules.append(
            AutoModule(
                name=name,
                seed_path=seed_path.as_posix(),
                reference_path=ref_path.as_posix(),
            )
        )

    test_seen: Dict[str, str] = {}
    tests: List[AutoTest] = []
    for test in suite.tests:
        is_system = test.level == TestLevel.SYSTEM
        key = "original_system" if is_system else f"{test.module}_{test.id}"
        if key not in test_seen:
            rel = Path("tests") / f"{key}.v"
            src = test.testbench_source
            if is_system:
                top_src = _read(top_file)
                if src.startswith(top_src):
                    src = src[len(top_src) :].lstrip()
            _write(out / rel, src)
            test_seen[key] = rel.as_posix()
        tests.append(
            AutoTest(
                id=test.id,
                level=test.level,
                module=test.module,
                description=test.description,
                testbench_path=test_seen[key],
                modules=tuple(test.touched_modules()),
                original_system=is_system,
            )
        )

    scaffold = AutoScaffold(
        name=f"auto_{design}",
        source_design=design,
        top_module=top_module,
        top_path=f"top/{top_file.name}",
        modules=modules,
        tests=tests,
        root=out,
        notes="Materialized from existing manual ArchXBench decomposition; upper bound only.",
    )
    save_scaffold(scaffold)
    return scaffold


def _extract_fenced_blocks(text: str) -> List[Tuple[str, Optional[str], str]]:
    pat = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
    blocks: List[Tuple[str, Optional[str], str]] = []
    for m in pat.finditer(text or ""):
        header = (m.group(1) or "").strip()
        body = m.group(2).strip() + "\n"
        lang = header.split()[0] if header else ""
        file_match = re.search(r"file\s*:\s*([^\s]+)", header)
        blocks.append((lang.lower(), file_match.group(1) if file_match else None, body))
    return blocks


def parse_llm_scaffold_response(response: str, out_dir: str | Path) -> AutoScaffold:
    """Parse the strict scaffold protocol emitted by the Stage-1 LLM."""
    blocks = _extract_fenced_blocks(response)
    manifest_text = None
    files: Dict[str, str] = {}
    for lang, file_name, body in blocks:
        if lang == "json" and manifest_text is None:
            manifest_text = body
        if file_name:
            clean = file_name.replace("\\", "/").lstrip("/")
            if Path(clean).is_absolute() or re.match(r"^[A-Za-z]:", clean) or ".." in Path(clean).parts:
                raise ValueError(f"unsafe generated file path: {file_name}")
            files[clean] = body
    if manifest_text is None:
        raise ValueError("LLM response did not contain a json manifest block")
    data = json.loads(manifest_text)

    root = Path(out_dir)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    required_files = [data["top_path"]]
    for m in data["modules"]:
        required_files += [m["seed_path"], m["reference_path"]]
    for t in data["tests"]:
        required_files.append(t["testbench_path"])

    missing = [p for p in required_files if p not in files]
    if missing:
        raise ValueError(f"LLM response omitted required file block(s): {missing}")

    for rel, body in files.items():
        _write(root / rel, body)

    scaffold = AutoScaffold(
        name=data["name"],
        top_module=data["top_module"],
        top_path=data["top_path"],
        modules=[
            AutoModule(
                name=m["name"],
                seed_path=m["seed_path"],
                reference_path=m["reference_path"],
                description=m.get("description", ""),
            )
            for m in data["modules"]
        ],
        tests=[
            AutoTest(
                id=t["id"],
                level=TestLevel.from_str(t["level"]),
                module=t["module"],
                description=t["description"],
                testbench_path=t["testbench_path"],
                modules=tuple(t.get("modules") or [t["module"]]),
                original_system=bool(t.get("original_system", False)),
            )
            for t in data["tests"]
        ],
        root=root,
        source_design=data.get("source_design"),
        notes=data.get("notes", ""),
    )
    save_scaffold(scaffold)
    return scaffold


def enforce_original_system_testbench(scaffold: AutoScaffold, system_tb: str) -> None:
    """Replace generated original-system test files with the benchmark file.

    This is the guard against test hacking: the LLM may decide where the original
    system testbench sits in the generated scaffold, but it does not get to
    change that testbench's contents.
    """
    paths = {t.testbench_path for t in scaffold.tests if t.original_system}
    for rel in paths:
        _write(scaffold.root / rel, system_tb)


def _system_failures(scaffold: AutoScaffold, candidate: Candidate, timeout: int) -> str:
    suite = build_suite(scaffold)
    system_tests = [t for t in suite.tests if t.level == TestLevel.SYSTEM]
    if not system_tests:
        return "No SYSTEM tests were generated; scaffold is invalid."
    system_suite = VerilogTestSuite(
        module_names=suite.module_names,
        tests=system_tests,
        top_module=suite.top_module,
        isolate_modules=True,
    )
    vector = system_suite.run(candidate, timeout=timeout)
    failures = [r.feedback.render() for r in vector.failures() if r.feedback]
    return "\n".join(failures[:12]) or vector.summary()


def validate_reference_gate(scaffold: AutoScaffold, *, timeout: int = 120) -> Tuple[bool, str]:
    """Return True only if generated references pass original/system tests."""
    ref = _candidate_from(scaffold, "reference")
    suite = build_suite(scaffold)
    system_count = sum(1 for t in suite.tests if t.level == TestLevel.SYSTEM)
    if system_count == 0:
        return False, "no SYSTEM tests in generated scaffold"
    system_suite = VerilogTestSuite(
        module_names=suite.module_names,
        tests=[t for t in suite.tests if t.level == TestLevel.SYSTEM],
        top_module=suite.top_module,
        isolate_modules=True,
    )
    try:
        vector = system_suite.run(ref, timeout=timeout)
    except Exception as e:
        return False, f"system-gate execution failed: {e}"
    ok = vector.total_passes == len(system_suite.tests)
    return ok, vector.summary()


def validate_training_suite_gate(
    scaffold: AutoScaffold, *, timeout: int = 120
) -> Tuple[bool, str]:
    """Return True only if generated unit tests provide useful TDES feedback."""
    suite = build_suite(scaffold)
    ref = _candidate_from(scaffold, "reference")
    seed = _candidate_from(scaffold, "seed")
    try:
        ref.vector = suite.run(ref, timeout=timeout)
        seed.vector = suite.run(seed, timeout=timeout)
    except Exception as e:
        return False, f"training-suite execution failed: {e}"

    if ref.vector.total_passes != len(suite.tests):
        return False, f"reference fails generated suite: {ref.vector.summary()}"

    unit_modules = {
        t.module for t in suite.tests if t.level == TestLevel.UNIT and t.module in scaffold.module_names
    }
    missing_unit_tests = [m for m in scaffold.module_names if m not in unit_modules]
    if missing_unit_tests:
        return False, f"missing UNIT tests for modules: {', '.join(missing_unit_tests)}"

    seed_unit_fail_modules = {
        r.module
        for r in seed.vector.failures()
        if r.level == TestLevel.UNIT and r.module in scaffold.module_names
    }
    weak_modules = [m for m in scaffold.module_names if m not in seed_unit_fail_modules]
    if weak_modules:
        return (
            False,
            "seed passes all UNIT tests for module(s): "
            + ", ".join(weak_modules)
            + f"; seed summary: {seed.vector.summary()}",
        )

    return True, f"reference {ref.vector.summary()}; seed {seed.vector.summary()}"


def _build_stage1_prompt(
    *,
    design_name: str,
    spec_text: str,
    system_tb: str,
    previous_feedback: str = "",
) -> str:
    feedback = (
        "\nPrevious scaffold failed the original system testbench. Fix the scaffold.\n"
        f"Failure feedback:\n{previous_feedback}\n"
        if previous_feedback
        else ""
    )
    return f"""
Design name: {design_name}

Task:
Create an auto-decomposition scaffold for this RTL task.

Inputs you may rely on:
1. Design specification below.
2. Original ArchXBench system testbench below.

Hard requirements:
- Preserve the original top-level interface expected by the system testbench.
- Produce submodule interfaces, reference implementations, empty/broken seeds,
  unit or integration testbenches for each submodule, and a top wrapper.
- The generated reference modules composed with the generated top wrapper must
  pass the original system testbench.
- The generated reference modules must pass every generated unit test.
- The generated empty/broken seed for each submodule must fail at least one
  UNIT test for that same submodule. Do not write trivial unit tests that a
  zero-output seed can pass.
- Unit tests are search guidance only. They are not the final judge.
- Do not use DPI, real-number operations, tasks inside synthesizable modules, or
  non-synthesizable behavior in design modules.

Output protocol:
Return exactly one ```json block with this manifest schema:
{{
  "name": "auto_<short_name>",
  "source_design": "{design_name}",
  "top_module": "<top module name expected by the original tb>",
  "top_path": "top/<top>.v",
  "modules": [
    {{"name": "<submodule>", "seed_path": "seed/<submodule>.v",
      "reference_path": "reference/<submodule>.v",
      "description": "<responsibility>"}}
  ],
  "tests": [
    {{"id": "<test id>", "level": "unit", "module": "<primary module>",
      "description": "<what it checks>", "testbench_path": "tests/<name>.v",
      "modules": ["<compiled candidate modules>"], "original_system": false}},
    {{"id": "system_<case_or_all>", "level": "system", "module": "<routing module>",
      "description": "original ArchXBench system testbench",
      "testbench_path": "tests/original_system_tb.v",
      "modules": ["<all submodules>"], "original_system": true}}
  ],
  "notes": "<short rationale>"
}}

Then return one fenced ```verilog file:<path> block for every path named in the
manifest. The file paths must match exactly.
{feedback}
Design specification:
```text
{spec_text}
```

Original ArchXBench system testbench:
```verilog
{system_tb}
```
""".strip()


async def generate_scaffold_with_llm(
    *,
    ensemble,
    design_name: str,
    spec_text: str,
    system_tb: str,
    out_dir: str | Path,
    retries: int,
    timeout: int,
) -> AutoScaffold:
    feedback = ""
    last_error = ""
    for attempt in range(retries + 1):
        prompt = _build_stage1_prompt(
            design_name=design_name,
            spec_text=spec_text,
            system_tb=system_tb,
            previous_feedback=feedback,
        )
        response = await ensemble.generate_with_context(
            system_message=AUTO_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            scaffold = parse_llm_scaffold_response(response or "", out_dir)
            enforce_original_system_testbench(scaffold, system_tb)
        except Exception as e:
            last_error = f"parse failed: {e}"
            feedback = last_error
            continue
        ok, summary = validate_reference_gate(scaffold, timeout=timeout)
        if ok:
            train_ok, train_summary = validate_training_suite_gate(scaffold, timeout=timeout)
            if train_ok:
                return scaffold
            last_error = f"training-suite gate failed: {train_summary}"
            feedback = last_error
            _write(Path(out_dir) / f"stage1_failed_attempt_{attempt}.txt", feedback)
            continue
        last_error = f"reference gate failed: {summary}"
        feedback = _system_failures(scaffold, _candidate_from(scaffold, "reference"), timeout)
        _write(Path(out_dir) / f"stage1_failed_attempt_{attempt}.txt", feedback)
    raise RuntimeError(f"auto-decomposition failed after {retries + 1} attempt(s): {last_error}")


class _InstrumentedMixin:
    _counter = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls_trajectory = []
        self.system_calls_trajectory = []
        self.module_first_solved = {}

    def _record_history(self, gen, population, *, stagnated=False, solved=False):
        super()._record_history(gen, population, stagnated=stagnated, solved=solved)
        calls = getattr(self._counter, "calls", 0)
        best = selection.best(population)
        bp = best.vector.total_passes if best and best.vector else 0
        self.calls_trajectory.append((gen, calls, bp))
        sp = 0
        st = 0
        if best and best.vector:
            system_results = [
                res for res in best.vector.results.values() if res.level == TestLevel.SYSTEM
            ]
            sp = sum(1 for res in system_results if res.passed)
            st = len(system_results)
        self.system_calls_trajectory.append((gen, calls, sp, st))
        for cand in population:
            if cand.vector is None:
                continue
            for res in cand.vector.results.values():
                if res.passed:
                    self.module_first_solved.setdefault(res.module, gen)


class _InstrumentedDiverse(_InstrumentedMixin, ablation.DiverseScheduleController):
    pass


def _with_system_metrics(
    rm: metrics.RunMetrics,
    best: Candidate,
    system_calls_trajectory: Optional[Sequence[Tuple[int, int, int, int]]] = None,
) -> metrics.RunMetrics:
    if best.vector is None:
        rm.system_passes = 0
        rm.system_tests = 0
        rm.system_solved = False
        return rm
    system_results = [
        res for res in best.vector.results.values() if res.level == TestLevel.SYSTEM
    ]
    rm.system_tests = len(system_results)
    rm.system_passes = sum(1 for res in system_results if res.passed)
    rm.system_solved = rm.system_tests > 0 and rm.system_passes == rm.system_tests
    rm.calls_to_system_solve = None
    for _gen, calls, passes, total in system_calls_trajectory or []:
        if total > 0 and passes == total:
            rm.calls_to_system_solve = calls
            break
    return rm


def run_tdes_cell(
    scaffold: AutoScaffold,
    condition: str,
    cfg: FPGAConfig,
    *,
    seed_idx: int,
    ensemble=None,
) -> metrics.RunMetrics:
    seed = _candidate_from(scaffold, "seed")
    suite = build_suite(scaffold)
    counter = _CountingEnsemble(ensemble) if ensemble is not None else None

    if condition in {"tdes_full", "tdes_no_crossover"}:
        mutator = VerilogLLMMutator(counter, diff_based=cfg.diff_based)
        ctrl = _InstrumentedDiverse(
            seed,
            suite,
            mutator,
            cfg,
            enable_crossover=(condition == "tdes_full"),
            enable_memory=True,
        )
        ctrl._counter = counter
        result = ctrl.run()
        rm = metrics.from_result(
            scaffold.name,
            condition,
            seed_idx,
            result,
            total_tests=len(suite.tests),
            crossover=ctrl.crossover_stats.as_dict(),
            llm_calls=getattr(counter, "calls", 0),
            calls_trajectory=ctrl.calls_trajectory,
            module_first_solved=ctrl.module_first_solved,
        )
        return _with_system_metrics(rm, result.best, ctrl.system_calls_trajectory)

    if condition == "single_agent_30":
        br = baselines.single_agent_repair(
            seed,
            suite,
            counter,
            rounds=cfg.max_generations,
            timeout=cfg.suite_timeout,
            diff_based=cfg.diff_based,
        )
        rm = metrics.RunMetrics(
            design=scaffold.name,
            condition=condition,
            seed=seed_idx,
            solved=br.solved,
            total_passes=br.total_passes,
            total_tests=br.total_tests,
            generations_run=br.rounds_used,
            escalated=False,
            trajectory=br.trajectory,
            crossover=None,
            llm_calls=getattr(counter, "calls", 0),
            calls_to_solve=getattr(counter, "calls", 0) if br.solved else None,
        )
        return _with_system_metrics(rm, br.best)
    raise ValueError(f"unknown condition: {condition}")


def run_tdes_matrix(
    scaffold: AutoScaffold,
    cfg: FPGAConfig,
    *,
    seeds: Sequence[int],
    conditions: Sequence[str],
    writer: IncrementalWriter,
    ensemble=None,
) -> List[metrics.RunMetrics]:
    ensemble = ensemble or build_ensemble(cfg)
    out: List[metrics.RunMetrics] = []
    for condition in conditions:
        for seed_idx in seeds:
            if any(
                m.design == scaffold.name and m.condition == condition and m.seed == seed_idx
                for m in writer.results
            ):
                logger.info("skip completed: %s/%s/seed=%s", scaffold.name, condition, seed_idx)
                continue
            cell_cfg = copy.copy(cfg)
            cell_cfg.random_seed = (cfg.random_seed or 0) + seed_idx
            cell_cfg.output_dir = os.path.join(
                cfg.output_dir, scaffold.name, condition, f"seed_{seed_idx}"
            )
            logger.info("running generated scaffold: %s/%s/seed=%s", scaffold.name, condition, seed_idx)
            rm = run_tdes_cell(scaffold, condition, cell_cfg, seed_idx=seed_idx, ensemble=ensemble)
            writer(rm)
            out.append(rm)
            logger.info(
                "%s/%s/seed=%s -> %d/%d %s calls=%d",
                scaffold.name,
                condition,
                seed_idx,
                rm.total_passes,
                rm.total_tests,
                "SOLVED" if rm.solved else "",
                rm.llm_calls,
            )
    return out


def _render_results(scaffold: AutoScaffold, rows: Iterable[metrics.RunMetrics]) -> str:
    rows = list(rows)
    lines = [
        "# Auto-Decompose-Then-Evolve Results",
        "",
        f"Scaffold: `{scaffold.name}`",
        f"Top: `{scaffold.top_module}`",
        f"Modules: {', '.join(scaffold.module_names)}",
        "",
        "Final success is counted only when the integrated design passes the",
        "SYSTEM tests derived from the original ArchXBench testbench.",
        "",
        "| Condition | Seed | System | All scaffold tests | Calls to system | LLM calls |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(rows, key=lambda x: (x.condition, x.seed)):
        system_passes = r.system_passes if r.system_passes is not None else "?"
        system_tests = r.system_tests if r.system_tests is not None else "?"
        system_solved = "yes" if r.system_solved else "no"
        lines.append(
            f"| {r.condition} | {r.seed} | {system_passes}/{system_tests} "
            f"({'yes' if system_solved == 'yes' else 'no'}) | "
            f"{r.total_passes}/{r.total_tests} ({'yes' if r.solved else 'no'}) | "
            f"{r.calls_to_system_solve if r.calls_to_system_solve is not None else 'n/a'} | "
            f"{r.llm_calls} |"
        )
    return "\n".join(lines)


def _default_spec_for_design(design: str) -> str:
    if design == "fp_mult_pipeline":
        return (
            "Implement an IEEE-754 single-precision pipelined floating-point "
            "multiplier with valid_in/valid_out flow control. It must handle "
            "normal numbers, signs, NaN propagation, Inf, signed zero, overflow, "
            "underflow, denormals used in the ArchXBench tests, and "
            "round-to-nearest-even behavior."
        )
    return f"Implement the ArchXBench RTL design named {design}."


def _system_tb_for_design(design: str) -> str:
    base = Path(archx_loader._design_path(design))
    tb = base / "tests" / "system_tb.v"
    if not tb.exists():
        raise FileNotFoundError(f"system testbench not found: {tb}")
    return _read(tb)


def build_llm_backend(args, cfg: FPGAConfig):
    if args.backend == "codex":
        return CodexCLIBackend(
            model=args.codex_model,
            reasoning_effort=args.reasoning_effort,
            timeout=args.llm_timeout,
            cwd=str(Path.cwd()),
        )
    return build_ensemble(cfg)


def main(argv=None) -> None:
    setup_logging()
    p = argparse.ArgumentParser(description="Auto-decompose ArchXBench and run TDES")
    p.add_argument("--backend", choices=["codex", "config"], default="codex")
    p.add_argument("--config", help="YAML config for Stage 1 and Stage 2 LLM calls")
    p.add_argument("--codex-model", default="gpt-5.5")
    p.add_argument("--reasoning-effort", default="low")
    p.add_argument("--llm-timeout", type=int, default=600)
    p.add_argument("--design", default="fp_mult_pipeline")
    p.add_argument("--spec-file", help="Optional design spec text file")
    p.add_argument("--system-tb", help="Optional original ArchXBench system testbench")
    p.add_argument("--scaffold-in", help="Existing accepted scaffold directory")
    p.add_argument("--scaffold-out", default="tdes_fpga_auto_scaffold")
    p.add_argument("--results-out", default="tdes_fpga_auto_results")
    p.add_argument("--stage1-retries", type=int, default=2)
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    p.add_argument(
        "--conditions",
        nargs="+",
        default=["single_agent_30", "tdes_no_crossover", "tdes_full"],
    )
    p.add_argument("--gens", type=int, default=8)
    p.add_argument("--pop", type=int, default=5)
    p.add_argument("--bootstrap-existing", action="store_true",
                   help="Materialize existing manual decomposition instead of calling an LLM")
    p.add_argument("--skip-stage2", action="store_true")
    p.add_argument("--skip-reference-gate", action="store_true",
                   help="Only for parser/debugging; do not use for reported experiments")
    p.add_argument("--skip-training-gate", action="store_true",
                   help="Only for debugging; allows weak generated unit tests")
    args = p.parse_args(argv)

    cfg = FPGAConfig.from_yaml(args.config) if args.config else FPGAConfig()
    cfg.max_generations = args.gens
    cfg.pop_size = args.pop
    cfg.output_dir = os.path.join(args.results_out, "runs")

    if args.scaffold_in:
        scaffold = load_scaffold(args.scaffold_in)
        args.scaffold_out = args.scaffold_in
    elif args.bootstrap_existing:
        scaffold = materialize_existing_archxbench_design(args.design, args.scaffold_out)
    else:
        spec_text = _read(Path(args.spec_file)) if args.spec_file else _default_spec_for_design(args.design)
        system_tb = _read(Path(args.system_tb)) if args.system_tb else _system_tb_for_design(args.design)
        ensemble = build_llm_backend(args, cfg)
        scaffold = asyncio.run(
            generate_scaffold_with_llm(
                ensemble=ensemble,
                design_name=args.design,
                spec_text=spec_text,
                system_tb=system_tb,
                out_dir=args.scaffold_out,
                retries=args.stage1_retries,
                timeout=cfg.suite_timeout,
            )
        )

    ok, summary = (True, "skipped") if args.skip_reference_gate else validate_reference_gate(
        scaffold, timeout=cfg.suite_timeout
    )
    gate_path = Path(args.scaffold_out) / "reference_gate.json"
    _write(gate_path, json.dumps({"passed": ok, "summary": summary}, indent=2))
    logger.info("reference gate: %s (%s)", "PASS" if ok else "FAIL", summary)
    if not ok:
        raise SystemExit("reference gate failed; refusing to feed scaffold into TDES")

    train_ok, train_summary = (
        (True, "skipped")
        if args.skip_training_gate
        else validate_training_suite_gate(scaffold, timeout=cfg.suite_timeout)
    )
    train_gate_path = Path(args.scaffold_out) / "training_suite_gate.json"
    _write(train_gate_path, json.dumps({"passed": train_ok, "summary": train_summary}, indent=2))
    logger.info("training-suite gate: %s (%s)", "PASS" if train_ok else "FAIL", train_summary)
    if not train_ok:
        raise SystemExit("training-suite gate failed; refusing to feed weak suite into TDES")

    if args.skip_stage2:
        print(f"Scaffold ready: {Path(args.scaffold_out).resolve()}")
        return

    os.makedirs(args.results_out, exist_ok=True)
    metrics_path = os.path.join(args.results_out, "metrics_auto_decompose.json")
    writer = IncrementalWriter(metrics_path)
    if os.path.exists(metrics_path):
        writer.results = metrics.load_metrics(metrics_path)

    ensemble = build_llm_backend(args, cfg)
    run_tdes_matrix(
        scaffold,
        cfg,
        seeds=args.seeds,
        conditions=args.conditions,
        writer=writer,
        ensemble=ensemble,
    )
    md = _render_results(scaffold, writer.results)
    results_path = Path(args.results_out) / "results.md"
    _write(results_path, md)
    print(md)


if __name__ == "__main__":
    main()
