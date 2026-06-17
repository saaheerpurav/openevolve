"""
Benchmark loader for TDES-Repair.

Mirrors the ``(seed, suite, reference-mutator)`` contract of
``fpga/benchmark_loader.py`` / ``combopt/benchmark_loader.py``: a variant's
seed candidate is the task's reference modules with the manifest's pre-written
buggy sources substituted, the suite is the task's hierarchical
``TDESTestSuite`` (loaded from its file so sandboxed runs work), and the
mutator deterministically injects reference modules for offline validation.

Two loader-level gates back the paper's claims:
  * :func:`is_usable` — the reference passes every test, the seed fails at
    least one, and every buggy module fails at least one of its own UNIT tests
    (which is what lets ``suite.modules_for_tests`` route crossover grafts).
  * :func:`verify_complementary` — split variants: fixing any single buggy
    module yields pass sets pairwise incomparable with the other single-module
    fixes (genuine complementary coverage exists); co-located variants: fixing
    the one buggy module solves the whole suite (nothing to graft).
"""

from __future__ import annotations

import importlib
import os
from typing import Dict, Optional, Tuple

from openevolve.tdes.mutation import ScriptedMutator
from openevolve.tdes.test_suite import TDESTestSuite
from openevolve.tdes.types import Candidate, TestLevel

_BASE = os.path.dirname(os.path.abspath(__file__))

TASKS = ("pipeline", "api")

LoaderResult = Tuple[Candidate, TDESTestSuite, Optional[ScriptedMutator]]


def _bench_dir(task: str) -> str:
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {TASKS}")
    return os.path.join(_BASE, "benchmarks", task)


def _manifest(task: str):
    _bench_dir(task)  # validate the task name
    return importlib.import_module(f"openevolve.tdes.repair.benchmarks.{task}.manifest")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def reference_modules(task: str) -> Dict[str, str]:
    ref_dir = os.path.join(_bench_dir(task), "reference")
    return {m: _read(os.path.join(ref_dir, f"{m}.py")) for m in _manifest(task).MODULES}


def load_suite(task: str) -> TDESTestSuite:
    return TDESTestSuite.load_from_file(os.path.join(_bench_dir(task), "suite.py"))


def list_variants(task: str) -> Dict[str, dict]:
    return dict(_manifest(task).VARIANTS)


def reference_mutator(task: str) -> ScriptedMutator:
    reference = reference_modules(task)

    def fix(module, source, feedback, memory_text):
        ref = reference.get(module)
        if ref is None or ref == source:
            return None
        return ref, f"replace {module} with the reference implementation"

    return ScriptedMutator(fix)


def load_variant(task: str, variant: str, with_mutator: bool = True) -> LoaderResult:
    variants = _manifest(task).VARIANTS
    if variant not in variants:
        raise ValueError(f"unknown variant {variant!r} for task {task!r}")
    spec = variants[variant]
    modules = reference_modules(task)
    buggy_dir = os.path.join(_bench_dir(task), "buggy")
    for module, fname in spec["overrides"].items():
        modules[module] = _read(os.path.join(buggy_dir, fname))
    seed = Candidate(
        modules=modules,
        generation=0,
        metadata={"origin": "seed", "task": task, "variant": variant, "kind": spec["kind"]},
    )
    return seed, load_suite(task), (reference_mutator(task) if with_mutator else None)


def is_usable(task: str, variant: str, *, sandbox: bool = False, timeout: int = 60) -> bool:
    seed, suite, _ = load_variant(task, variant, with_mutator=False)
    reference = Candidate(modules=reference_modules(task), metadata={"origin": "reference"})
    ref_vector = suite.run(reference, sandbox=sandbox, timeout=timeout)
    if len(ref_vector.passes()) != len(suite.tests):
        return False
    seed_vector = suite.run(seed, sandbox=sandbox, timeout=timeout)
    if len(seed_vector.passes()) == len(suite.tests):
        return False
    for module in _manifest(task).VARIANTS[variant]["overrides"]:
        unit_failure = any(
            not r.passed and r.module == module and r.level == TestLevel.UNIT
            for r in seed_vector.results.values()
        )
        if not unit_failure:
            return False
    return True


def verify_complementary(
    task: str, variant: str, *, sandbox: bool = False, timeout: int = 60
) -> bool:
    seed, suite, _ = load_variant(task, variant, with_mutator=False)
    spec = _manifest(task).VARIANTS[variant]
    reference = reference_modules(task)
    buggy_modules = list(spec["overrides"])

    vectors = {}
    for module in buggy_modules:
        cand = seed.clone(metadata={"origin": f"single_fix_{module}"})
        cand.modules[module] = reference[module]
        vectors[module] = suite.run(cand, sandbox=sandbox, timeout=timeout)

    if spec["kind"] == "colocated":
        return len(vectors[buggy_modules[0]].passes()) == len(suite.tests)

    for i, m1 in enumerate(buggy_modules):
        for m2 in buggy_modules[i + 1 :]:
            p1, p2 = vectors[m1].passes(), vectors[m2].passes()
            if not (p1 - p2) or not (p2 - p1):
                return False
    return True
