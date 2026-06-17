"""
EnhancedFPGAController — four additive improvements over DiverseScheduleController.

Implements the four mechanisms from the ICML-workshop paper revision that
maximise complementary-coverage crossover firing on Level 3-4 ArchXBench designs:

  1. **Diverse seeding** (``use_diverse_seed``): replaces the default
     ``[seed.clone() * pop_size]`` with LLM-generated candidates using varied
     prompting strategies (zero-shot / chain-of-thought / minimal / alternative).
     Each starts with a different approach → different partial correctness →
     crossover has complementary material from generation 1.

  2. **Semantic crossover fallback** (``use_semantic_crossover``): when structural
     module grafting fails the strict-superset gate, falls back to LLM-mediated
     merge — shows both implementations + per-module pass/fail to the LLM and asks
     it to fuse the working approaches. One extra LLM call per rejected graft.

  3. **Priority-ordered mutation with early exit** (``use_priority_mutation``):
     sorts failing modules by current pass fraction (highest first — closest to
     complete) and breaks after the first mutation that gains new passes. This
     concentrates LLM calls where marginal progress is most likely.

  4. **Positive memory / insight broadcast** (``use_positive_memory``): after any
     mutation that gains new passes, records the approach in a per-module positive
     memory (analogous to NegativeMemory). Subsequent mutation prompts include
     "what worked elsewhere in the population" so candidates benefit from each
     other's discoveries without waiting for crossover.

Base files (``tdes/*``) are untouched; this module extends only the FPGA layer.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Dict, List, Optional, Set, Tuple

from openevolve.tdes import selection
from openevolve.tdes.crossover import complementary_crossover
from openevolve.tdes.fpga import ablation
from openevolve.tdes.fpga.diverse_seed import generate_diverse_seeds
from openevolve.tdes.fpga.positive_memory import PositiveMemory
from openevolve.tdes.fpga.semantic_crossover import semantic_merge
from openevolve.tdes.types import Candidate, TestVector
from openevolve.tdes.controller import TDESResult, _codebase_hash

logger = logging.getLogger(__name__)


class EnhancedFPGAController(ablation.DiverseScheduleController):
    """DiverseScheduleController + diverse seeding + semantic crossover
    + priority mutation + positive memory."""

    def __init__(
        self,
        *args,
        ensemble=None,
        use_diverse_seed: bool = True,
        use_semantic_crossover: bool = True,
        use_priority_mutation: bool = True,
        use_positive_memory: bool = True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.ensemble = ensemble
        self.use_diverse_seed = use_diverse_seed
        self.use_semantic_crossover = use_semantic_crossover
        self.use_priority_mutation = use_priority_mutation
        self.use_positive_memory = use_positive_memory

        self.positive_memory = PositiveMemory(window_size=self.config.window_size) if use_positive_memory else None
        self._rejected_graft_outcomes: List[Tuple] = []  # (higher, lower, outcome)

        # Extended crossover stats
        self.semantic_attempts: int = 0
        self.semantic_accepted: int = 0

    # -----------------------------------------------------------------------
    # run_async override — only two changes vs TDESController.run_async:
    #   (a) diverse seeding at init
    #   (b) semantic crossover phase appended after structural crossover
    # -----------------------------------------------------------------------
    async def run_async(self) -> TDESResult:
        cfg = self.config

        # INITIALIZE population ---------------------------------------------
        if self.use_diverse_seed and self.ensemble is not None:
            population = await generate_diverse_seeds(
                self.seed,
                self.suite,
                self.ensemble,
                cfg.pop_size,
                sandbox=cfg.sandbox,
                timeout=cfg.suite_timeout,
            )
        else:
            population = [self.seed.clone(generation=0) for _ in range(cfg.pop_size)]

        prev_union: Optional[Set[str]] = None
        escalated = False
        generations_run = 0

        for gen in range(1, cfg.max_generations + 1):
            generations_run = gen
            logger.info("=== TDES(Enhanced) generation %d/%d ===", gen, cfg.max_generations)

            # EVALUATE -------------------------------------------------------
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

            # STAGNATION CHECK -----------------------------------------------
            if prev_union is not None and current_union <= prev_union:
                logger.warning(
                    "Stagnation detected at generation %d. Escalating.", gen
                )
                self._write_escalation(best, gen)
                escalated = True
                self._record_history(gen, population, stagnated=True)
                break

            if best.vector.total_passes == len(self.suite.tests):
                logger.info("All %d tests pass at generation %d.", len(self.suite.tests), gen)
                self._record_history(gen, population, solved=True)
                break

            # SELECT --------------------------------------------------------
            survivors = selection.top_k(population, max(1, math.ceil(cfg.pop_size / 2)))

            # CROSSOVER — structural graft (sync) ---------------------------
            crossover_children = self._crossover_phase(survivors, gen)

            # CROSSOVER — semantic fallback (async) -------------------------
            if self.use_semantic_crossover and self._rejected_graft_outcomes:
                semantic_children = await self._semantic_crossover_phase(survivors, gen)
                crossover_children.extend(semantic_children)

            # MUTATE --------------------------------------------------------
            mutated = await self._mutation_phase(survivors, gen)

            self._record_history(gen, population)

            population = self._next_generation(
                survivors + crossover_children + mutated, cfg.pop_size
            )
            prev_union = current_union

        # Final evaluation + output
        self._evaluate_all(population)
        best = selection.best(population)
        self._write_best(best)
        logger.info(
            "TDES(Enhanced) finished after %d gen(s). Best: %s%s",
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

    # -----------------------------------------------------------------------
    # Crossover phase overrides
    # -----------------------------------------------------------------------

    def _crossover_phase(self, survivors: List[Candidate], gen: int) -> List[Candidate]:
        """Structural complementary-coverage graft; tracks rejected outcomes for semantic fallback."""
        if not self.enable_crossover:
            self._rejected_graft_outcomes = []
            return []

        children: List[Candidate] = []
        self._rejected_graft_outcomes = []
        ranked = selection.rank(survivors)

        for i, higher in enumerate(ranked):
            for lower in ranked[i + 1:]:
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
                elif (
                    outcome.attempted
                    and not outcome.accepted
                    and self.use_semantic_crossover
                    and outcome.grafted_modules  # has identified modules to merge
                ):
                    # Queue for semantic fallback; one attempt per rejected pair
                    self._rejected_graft_outcomes.append((higher, lower, outcome))

        return children

    async def _semantic_crossover_phase(
        self, survivors: List[Candidate], gen: int
    ) -> List[Candidate]:
        """LLM-mediated merge fallback for pairs where structural graft failed."""
        children: List[Candidate] = []
        for higher, lower, outcome in self._rejected_graft_outcomes:
            module = outcome.grafted_modules[0]  # try the primary graft module
            self.semantic_attempts += 1
            merge_outcome = await semantic_merge(
                higher,
                lower,
                module,
                self.suite,
                self.ensemble,
                generation=gen,
                sandbox=self.config.sandbox,
                timeout=self.config.suite_timeout,
            )
            if merge_outcome.accepted and merge_outcome.child is not None:
                self.semantic_accepted += 1
                # Mirror structural crossover stats for the semantic acceptance
                self.crossover_stats.accepted += 1
                lift = len(merge_outcome.child.vector.passes()) - len(higher.vector.passes())
                self.crossover_stats.lift_total += max(0, lift)
                children.append(merge_outcome.child)
                logger.info(
                    "Semantic crossover accepted: %s + %s[%s] -> %s",
                    higher.id, lower.id, module, merge_outcome.child.id,
                )
        return children

    # -----------------------------------------------------------------------
    # Mutation phase override
    # -----------------------------------------------------------------------

    def _priority_sorted_modules(self, vector: TestVector) -> List[str]:
        """Sort failing modules by pass fraction descending (most progress first)."""
        module_total: Dict[str, int] = {}
        module_passing: Dict[str, int] = {}
        for r in vector.results.values():
            m = r.module
            module_total[m] = module_total.get(m, 0) + 1
            if r.passed:
                module_passing[m] = module_passing.get(m, 0) + 1

        failing = vector.failing_modules()

        def _priority(mod: str) -> float:
            total = module_total.get(mod, 1)
            passing = module_passing.get(mod, 0)
            return passing / total

        return sorted(failing, key=_priority, reverse=True)

    async def _mutate_candidate(self, parent: Candidate, gen: int) -> Optional[Candidate]:
        """Priority mutation with early exit and positive-memory injection."""
        baseline_passes = parent.passes
        working = parent.clone(
            generation=gen, parent_id=parent.id, metadata={"origin": "mutation"}
        )
        working.vector = parent.vector
        changed = False

        # Module order: priority sort if enabled, else DiverseSchedule shuffle
        if self.use_priority_mutation:
            failing_modules = self._priority_sorted_modules(parent.vector)
        else:
            failing_modules = parent.vector.failing_modules()
            self._rng.shuffle(failing_modules)

        limit = self.config.mutate_modules_per_candidate
        if limit is not None:
            failing_modules = failing_modules[:limit]

        for module in failing_modules:
            feedback = [
                r.feedback
                for r in working.vector.results.values()
                if not r.passed and r.module == module and r.feedback is not None
            ]
            pos_text = (
                self.positive_memory.render(module)
                if self.positive_memory is not None
                else ""
            )
            proposal = await self.mutator.propose(
                candidate=working,
                module=module,
                feedback=feedback,
                memory_text=self.memory.render(module),
                generation=gen,
                positive_memory_text=pos_text,
            )
            if proposal is None:
                continue

            trial = working.clone(generation=gen, parent_id=parent.id)
            trial.modules[module] = proposal.new_source
            trial.vector = self.suite.run(
                trial, sandbox=self.config.sandbox, timeout=self.config.suite_timeout
            )

            if trial.vector.is_superset_of(working.vector):
                new_passes = trial.vector.passes() - working.vector.passes()
                if new_passes:
                    changed = True
                    # Record success in positive memory before updating working
                    if self.positive_memory is not None:
                        self.positive_memory.record(
                            module, gen, proposal.approach, sorted(new_passes)
                        )
                working = trial
                working.metadata["origin"] = "mutation"
                # Priority mutation: early exit after first new-pass gain
                if self.use_priority_mutation and new_passes:
                    break
            else:
                self._record_failure(module, gen, proposal.approach, trial.vector, working)

        if changed and working.passes > baseline_passes:
            return working
        return working if changed else None

    # -----------------------------------------------------------------------
    # extended_crossover_stats: include semantic counts in the as_dict()
    # -----------------------------------------------------------------------

    def crossover_stats_as_dict(self) -> dict:
        d = self.crossover_stats.as_dict()
        d["semantic_attempts"] = self.semantic_attempts
        d["semantic_accepted"] = self.semantic_accepted
        return d


# ---------------------------------------------------------------------------
# Condition registry
# ---------------------------------------------------------------------------

ENHANCED_CONDITIONS: Dict[str, dict] = {
    "tdes_enhanced": dict(
        use_diverse_seed=True,
        use_semantic_crossover=True,
        use_priority_mutation=True,
        use_positive_memory=True,
    ),
    "tdes_no_diverse_seed": dict(
        use_diverse_seed=False,
        use_semantic_crossover=True,
        use_priority_mutation=True,
        use_positive_memory=True,
    ),
    "tdes_no_semantic_xo": dict(
        use_diverse_seed=True,
        use_semantic_crossover=False,
        use_priority_mutation=True,
        use_positive_memory=True,
    ),
    "tdes_no_priority_mut": dict(
        use_diverse_seed=True,
        use_semantic_crossover=True,
        use_priority_mutation=False,
        use_positive_memory=True,
    ),
    "tdes_no_positive_mem": dict(
        use_diverse_seed=True,
        use_semantic_crossover=True,
        use_priority_mutation=True,
        use_positive_memory=False,
    ),
}
