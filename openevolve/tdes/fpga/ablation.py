"""
Ablation + metrics controller for TDES-FPGA experiments.

``AblationController`` subclasses the unmodified ``TDESController`` to (a) toggle
individual TDES mechanisms for ablation studies and (b) instrument the
complementary-coverage crossover so the paper's crossover metrics
(attempt/success rate, fitness lift) can be reported. It overrides only
``_crossover_phase`` and ``_record_failure`` — no base files are touched.

Ablation conditions (paper section 3.2):
  * TDES-full        : enable_crossover=True,  enable_memory=True,  hierarchical levels
  * TDES-no-crossover: enable_crossover=False
  * TDES-no-memory   : enable_memory=False
  * TDES-scalar      : run on a level-flattened suite (see ``flatten_levels``)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from openevolve.tdes.controller import TDESController
from openevolve.tdes.crossover import complementary_crossover
from openevolve.tdes import selection
from openevolve.tdes.fpga.verilog_suite import VerilogTest, VerilogTestSuite
from openevolve.tdes.types import Candidate, TestLevel


@dataclass
class CrossoverStats:
    pairs_considered: int = 0
    attempts: int = 0  # complementary coverage existed
    accepted: int = 0  # produced a strict-superset child
    lift_total: int = 0  # sum of (child passes - higher-parent passes)

    @property
    def attempt_rate(self) -> float:
        return self.attempts / self.pairs_considered if self.pairs_considered else 0.0

    @property
    def success_rate(self) -> float:
        return self.accepted / self.attempts if self.attempts else 0.0

    @property
    def mean_lift(self) -> float:
        return self.lift_total / self.accepted if self.accepted else 0.0

    def as_dict(self) -> dict:
        return {
            "pairs_considered": self.pairs_considered,
            "attempts": self.attempts,
            "accepted": self.accepted,
            "attempt_rate": round(self.attempt_rate, 4),
            "success_rate": round(self.success_rate, 4),
            "mean_lift": round(self.mean_lift, 4),
        }


class AblationController(TDESController):
    """TDESController with per-mechanism toggles and crossover instrumentation."""

    def __init__(self, *args, enable_crossover: bool = True, enable_memory: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.enable_crossover = enable_crossover
        self.enable_memory = enable_memory
        self.crossover_stats = CrossoverStats()

    def _crossover_phase(self, survivors: List[Candidate], gen: int) -> List[Candidate]:
        if not self.enable_crossover:
            return []
        children: List[Candidate] = []
        ranked = selection.rank(survivors)
        for i, higher in enumerate(ranked):
            for lower in ranked[i + 1 :]:
                self.crossover_stats.pairs_considered += 1
                outcome = complementary_crossover(
                    higher,
                    lower,
                    self.suite,
                    generation=gen,
                    sandbox=self.config.sandbox,
                    timeout=self.config.suite_timeout,
                )
                if outcome.attempted:
                    self.crossover_stats.attempts += 1
                if outcome.accepted and outcome.child is not None:
                    self.crossover_stats.accepted += 1
                    lift = len(outcome.child.vector.passes()) - len(higher.vector.passes())
                    self.crossover_stats.lift_total += max(0, lift)
                    children.append(outcome.child)
        return children

    def _record_failure(self, *args, **kwargs) -> None:
        if not self.enable_memory:
            return
        return super()._record_failure(*args, **kwargs)


def flatten_levels(suite: VerilogTestSuite) -> VerilogTestSuite:
    """Return a copy of ``suite`` with every test at UNIT level.

    With a single level, hierarchical ordering degenerates to ranking by total
    pass count — i.e. the *scalar fitness* ablation, achieved without touching
    selection.
    """
    flat_tests = [
        VerilogTest(
            id=t.id,
            level=TestLevel.UNIT,
            module=t.module,
            description=t.description,
            testbench_source=t.testbench_source,
            modules=t.modules,
        )
        for t in suite.tests
    ]
    return VerilogTestSuite(
        module_names=list(suite.module_names),
        tests=flat_tests,
        top_module=suite.top_module,
        synth_config=dict(suite.synth_config),
        verilog_std=suite.verilog_std,
    )


# Registry of ablation conditions -> (controller kwargs, suite transform).
CONDITIONS = {
    "tdes_full": (dict(enable_crossover=True, enable_memory=True), None),
    "tdes_no_crossover": (dict(enable_crossover=False, enable_memory=True), None),
    "tdes_no_memory": (dict(enable_crossover=True, enable_memory=False), None),
    "tdes_scalar": (dict(enable_crossover=True, enable_memory=True), flatten_levels),
}
