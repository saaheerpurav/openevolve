"""
Repair-specific ablation controllers and metrics tracking.

Follows the same pattern as tdes/fpga/ablation.py: subclass TDESController,
override only _crossover_phase and _record_failure. Base files untouched.

Four conditions:
  tdes_full         — complementary-coverage crossover + memory (DiverseSchedule)
  tdes_no_crossover — crossover disabled; selection + mutation + memory only
  unconstrained_evo — random crossover (no set-difference gate, unconditional)
  single_shot       — handled separately in experiments/run_repair.py (no loop)
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional

from openevolve.tdes import selection
from openevolve.tdes.controller import TDESController, TDESResult
from openevolve.tdes.crossover import complementary_crossover, graft
from openevolve.tdes.fpga.ablation import AblationController, DiverseScheduleController
from openevolve.tdes.types import Candidate

logger = logging.getLogger(__name__)


# ── Lexicase selection (repair layer) ─────────────────────────────────────────

def lexicase_select(
    population: List[Candidate], k: int, rng, test_ids: List[str]
) -> List[Candidate]:
    """Select k candidates using lexicase selection (Spector 2012).

    Shuffles test order independently per slot. A candidate that passes a
    distinct subset of tests (e.g. blockmatrix-only) survives in slots where
    those tests appear early in the shuffle, even if another candidate passes
    more tests in total. This maintains complementary partial solvers in the
    survivor set so complementary-coverage crossover can fire without widening
    the crossover pool beyond survivors.
    """
    evaluated = [c for c in population if c.vector is not None]
    if not evaluated:
        return list(population[:k])

    selected: List[Candidate] = []
    for _ in range(k):
        pool = list(evaluated)
        order = list(test_ids)
        rng.shuffle(order)
        for tid in order:
            passing = [c for c in pool if tid in c.passes]
            if passing:  # skip tests no one passes; keep current pool intact
                pool = passing
            if len(pool) == 1:
                break
        selected.append(rng.choice(pool))
    return selected


# ── Metrics wrapper ────────────────────────────────────────────────────────────

@dataclass
class RepairRunMetrics:
    condition: str
    task: str
    seed: int
    test_pass_rate_per_generation: List[float] = field(default_factory=list)
    llm_calls_to_solution: int = 0
    crossover_attempts: Optional[int] = None
    crossover_successes: Optional[int] = None
    regression_rate: Optional[float] = None
    stagnation_gen: Optional[int] = None
    wall_clock_seconds_per_gen: List[float] = field(default_factory=list)
    solved: bool = False
    model: str = ""

    def as_dict(self) -> dict:
        return {
            "condition": self.condition,
            "task": self.task,
            "seed": self.seed,
            "test_pass_rate_per_generation": self.test_pass_rate_per_generation,
            "llm_calls_to_solution": self.llm_calls_to_solution,
            "crossover_attempts": self.crossover_attempts,
            "crossover_successes": self.crossover_successes,
            "regression_rate": self.regression_rate,
            "stagnation_gen": self.stagnation_gen,
            "wall_clock_seconds_per_gen": self.wall_clock_seconds_per_gen,
            "solved": self.solved,
            "model": self.model,
        }


class CountingMutator:
    """Wraps any Mutator to count propose() calls."""

    def __init__(self, inner):
        self.inner = inner
        self.call_count = 0

    async def propose(self, **kwargs):
        self.call_count += 1
        return await self.inner.propose(**kwargs)


# ── Full TDES (with metrics, diverse module order) ─────────────────────────────

class RepairTDESController(DiverseScheduleController):
    """
    Full TDES for repair: complementary-coverage crossover + memory + diverse
    module scheduling. Instruments crossover and wall-clock time per generation.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, enable_crossover=True, enable_memory=True, **kwargs)
        self._gen_start: Optional[float] = None
        self._wall_times: List[float] = []
        self._pass_rates: List[float] = []

    def _evaluate_all(self, population):
        super()._evaluate_all(population)
        total = len(self.suite.tests)
        if total:
            best_passes = max(
                (c.vector.total_passes for c in population if c.vector), default=0
            )
            self._pass_rates.append(round(best_passes / total, 4))

    def _crossover_phase(self, survivors, gen):
        self._gen_start = time.perf_counter()
        return super()._crossover_phase(survivors, gen)

    def _record_history(self, gen, population, **kwargs):
        if self._gen_start is not None:
            self._wall_times.append(round(time.perf_counter() - self._gen_start, 2))
            self._gen_start = None
        super()._record_history(gen, population, **kwargs)

    def build_metrics(self, condition: str, task: str, seed: int, model: str) -> RepairRunMetrics:
        total = len(self.suite.tests)
        best_passes = 0
        if self.history:
            last = self.history[-1]
            best_passes = len(last.get("population_union_passes", []))
        stagnated = any(h.get("stagnated") for h in self.history)
        stagnation_gen = next(
            (h["generation"] for h in self.history if h.get("stagnated")), None
        )
        solved = any(h.get("solved") for h in self.history) or best_passes == total

        xo = self.crossover_stats
        regression_rate = None
        if xo.attempts > 0:
            regression_rate = round(1.0 - xo.success_rate, 4)

        return RepairRunMetrics(
            condition=condition,
            task=task,
            seed=seed,
            test_pass_rate_per_generation=self._pass_rates,
            llm_calls_to_solution=self.mutator.call_count if isinstance(self.mutator, CountingMutator) else 0,
            crossover_attempts=xo.attempts,
            crossover_successes=xo.accepted,
            regression_rate=regression_rate,
            stagnation_gen=stagnation_gen,
            wall_clock_seconds_per_gen=self._wall_times,
            solved=solved,
            model=model,
        )

    async def run_async(self) -> TDESResult:
        """Override base loop with windowed stagnation patience.

        Fires escalation only after cfg.window_size consecutive flat
        generations instead of the base controller's immediate-fire policy.
        """
        cfg = self.config
        population = [self.seed.clone(generation=0) for _ in range(cfg.pop_size)]
        prev_union = None
        escalated = False
        generations_run = 0
        stagnant_streak = 0
        patience = cfg.window_size  # reuse window_size as stagnation patience

        for gen in range(1, cfg.max_generations + 1):
            generations_run = gen
            logger.info("=== TDES generation %d/%d ===", gen, cfg.max_generations)

            self._evaluate_all(population)
            ranked = selection.rank(population)
            current_union = self._union_passes(population)
            best = ranked[0]
            logger.info(
                "Gen %d best: %s | population union passes: %d",
                gen,
                best.vector.summary(),
                len(current_union),
            )

            if prev_union is not None and current_union <= prev_union:
                stagnant_streak += 1
                if stagnant_streak >= patience:
                    logger.warning(
                        "Stagnation detected at generation %d: no new tests passed "
                        "for %d consecutive generation(s). Escalating to human.",
                        gen,
                        stagnant_streak,
                    )
                    self._write_escalation(best, gen)
                    escalated = True
                    self._record_history(gen, population, stagnated=True)
                    break
                logger.info(
                    "Flat generation %d/%d (streak %d/%d) — continuing.",
                    gen,
                    cfg.max_generations,
                    stagnant_streak,
                    patience,
                )
            else:
                stagnant_streak = 0

            if best.vector.total_passes == len(self.suite.tests):
                logger.info("All %d tests pass at generation %d.", len(self.suite.tests), gen)
                self._record_history(gen, population, solved=True)
                break

            test_ids = [t.id for t in self.suite.tests]
            survivors = lexicase_select(
                population, max(1, math.ceil(cfg.pop_size / 2)), self._rng, test_ids
            )
            crossover_children = self._crossover_phase(survivors, gen)
            mutated = await self._mutation_phase(survivors, gen)
            self._record_history(gen, population)
            population = self._next_generation(survivors + crossover_children + mutated, cfg.pop_size)
            prev_union = current_union

        self._evaluate_all(population)
        best = selection.best(population)
        self._write_best(best)
        logger.info(
            "TDES finished after %d generation(s). Best: %s%s",
            generations_run,
            best.vector.summary(),
            " (escalated)" if escalated else "",
        )
        return TDESResult(
            best=best,
            generations_run=generations_run,
            escalated=escalated,
            history=self.history,
        )


# ── Ablation: no crossover ─────────────────────────────────────────────────────

class RepairNoCrossoverController(RepairTDESController):
    """Full TDES with crossover disabled (ablation condition)."""

    def __init__(self, *args, **kwargs):
        # Override enable_crossover=False after super().__init__ sets it True.
        super().__init__(*args, **kwargs)
        self.enable_crossover = False

    def build_metrics(self, condition, task, seed, model):
        m = super().build_metrics(condition, task, seed, model)
        m.crossover_attempts = None
        m.crossover_successes = None
        m.regression_rate = None
        return m


# ── Baseline B: unconstrained crossover ───────────────────────────────────────

class UnconstrainedCrossoverController(RepairTDESController):
    """
    Baseline B: random crossover with no set-difference gate and no acceptance
    check — two candidates from the top half are picked at random and modules
    are grafted unconditionally.
    """

    def _crossover_phase(self, survivors: List[Candidate], gen: int) -> List[Candidate]:
        self._gen_start = time.perf_counter()
        if len(survivors) < 2:
            return []

        ranked = selection.rank(survivors)
        top_half = ranked[: max(2, len(ranked) // 2 + 1)]
        a, b = self._rng.sample(top_half, 2)

        # Graft a random subset of b's modules into a (at least one).
        candidates = list(b.modules.keys())
        n = max(1, self._rng.randint(1, len(candidates)))
        modules_to_graft = self._rng.sample(candidates, n)

        child = graft(a, b, modules_to_graft, generation=gen)
        child.vector = self.suite.run(
            child, sandbox=self.config.sandbox, timeout=self.config.suite_timeout
        )

        self.crossover_stats.pairs_considered += 1
        self.crossover_stats.attempts += 1
        self.crossover_stats.accepted += 1  # unconditional
        return [child]
