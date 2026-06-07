"""
VerilogTestSuite — a drop-in replacement for ``TDESTestSuite`` that evaluates
candidates by compiling and simulating Verilog instead of importing Python.

It produces the *same* :class:`~openevolve.tdes.types.TestVector` /
:class:`~openevolve.tdes.types.TestResult` / :class:`~openevolve.tdes.types.FeedbackTuple`
objects the existing controller, selection, and crossover code consume, so the
entire TDES loop above the test runner is reused unchanged.

Interface parity with ``TDESTestSuite`` (the only members the controller and
``crossover.py`` touch):

    * ``run(candidate, sandbox=, timeout=) -> TestVector``
    * ``tests``           (list, used via ``len(...)``)
    * ``module_names``    (list, read by the CLI)
    * ``modules_for_tests(ids) -> list[str]``

A test whose ``testbench_source`` is the sentinel ``"__synthesis__"`` is
dispatched to the Yosys path in ``synthesis.py`` (system-level resource checks).
The testbench source is **never** exposed to the LLM mutator — only the test
description, failing input, and error reach a FeedbackTuple (the section 3.2
CEGIS constraint).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from openevolve.tdes.fpga import verilog_runner
from openevolve.tdes.types import (
    Candidate,
    FeedbackTuple,
    TestLevel,
    TestResult,
    TestVector,
)

logger = logging.getLogger(__name__)

SYNTHESIS_SENTINEL = "__synthesis__"


@dataclass
class VerilogTest:
    """One hierarchical Verilog test (analog of ``TDESTest``)."""

    id: str
    level: TestLevel
    module: str  # primary module under test (tests -> modules map)
    description: str  # natural-language; shown to the LLM
    testbench_source: str  # Verilog testbench OR the synthesis sentinel; NOT shown to LLM
    modules: Optional[List[str]] = None  # all modules touched; defaults to [module]

    def touched_modules(self) -> List[str]:
        return list(self.modules) if self.modules else [self.module]

    @property
    def is_synthesis(self) -> bool:
        return self.testbench_source.strip().startswith(SYNTHESIS_SENTINEL)


class VerilogTestSuite:
    """A hierarchical suite over a fixed set of Verilog modules."""

    def __init__(
        self,
        module_names: Sequence[str],
        tests: Sequence[VerilogTest],
        *,
        top_module: Optional[str] = None,
        synth_config: Optional[dict] = None,
        verilog_std: str = "2012",
    ):
        self.module_names: List[str] = list(module_names)
        self.tests: List[VerilogTest] = list(tests)
        self.top_module = top_module or (self.module_names[-1] if self.module_names else None)
        # synth_config: {"target": "ice40", "lut_budget": 500, ...}
        self.synth_config = synth_config or {}
        self.verilog_std = verilog_std
        self.source_path: Optional[str] = None  # parity with TDESTestSuite (unused here)

    # -- introspection (parity with TDESTestSuite) -----------------------
    def modules_for_tests(self, test_ids) -> List[str]:
        wanted = set(test_ids)
        out: List[str] = []
        for t in self.tests:
            if t.id in wanted:
                for m in t.touched_modules():
                    if m not in out:
                        out.append(m)
        return out

    def tests_for_module(self, module: str) -> List[VerilogTest]:
        return [t for t in self.tests if module in t.touched_modules()]

    # -- execution -------------------------------------------------------
    def run(self, candidate: Candidate, *, sandbox: bool = True, timeout: int = 60) -> TestVector:
        """Compile+simulate (or synthesize) the candidate against every test.

        ``sandbox`` is accepted for interface parity but is implicit: each test
        runs in its own iverilog/vvp subprocess with a timeout. The flag is
        otherwise ignored (the EDA subprocess *is* the sandbox).
        """
        vector = TestVector()
        for test in self.tests:
            if test.is_synthesis:
                outcome = self._run_synthesis_test(candidate, test)
            else:
                outcome = verilog_runner.run_single_test(
                    test.id,
                    candidate.modules,
                    test.testbench_source,
                    timeout=timeout,
                    verilog_std=self.verilog_std,
                )
            feedback = None
            if not outcome.passed:
                feedback = FeedbackTuple(
                    description=test.description,
                    failing_input=outcome.failing_input,
                    error=outcome.error,
                )
            vector.results[test.id] = TestResult(
                test_id=test.id,
                level=test.level,
                module=test.module,
                passed=outcome.passed,
                description=test.description,
                feedback=feedback,
            )
        return vector

    def _run_synthesis_test(self, candidate: Candidate, test: VerilogTest):
        # Imported lazily so the suite can be constructed without Yosys present.
        from openevolve.tdes.fpga import synthesis

        return synthesis.evaluate_synthesis_test(
            candidate.modules,
            top_module=self.top_module,
            spec=self._parse_synth_spec(test.testbench_source),
            config=self.synth_config,
        )

    @staticmethod
    def _parse_synth_spec(sentinel_text: str) -> dict:
        """Parse ``__synthesis__ key=value ...`` budgets from the sentinel string.

        Example: ``"__synthesis__ lut<500 ff<200"``.
        """
        spec: dict = {}
        tokens = sentinel_text.strip().split()[1:]  # drop the sentinel itself
        for tok in tokens:
            for key in ("lut", "ff", "cells"):
                if tok.startswith(f"{key}<"):
                    try:
                        spec[key] = int(tok.split("<", 1)[1])
                    except ValueError:
                        pass
        return spec
