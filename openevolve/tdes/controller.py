"""
TDES controller — the generational evolutionary loop from Appendix A.

Orchestrates the five TDES mechanisms against a hierarchical test suite:

    seed population
      └─ for each generation:
           EVALUATE   run the suite -> test-pass vector + CEGIS feedback
           SELECT     hierarchical top-k survivors
           CROSSOVER  complementary-coverage grafting (conditional)
           MUTATE     modular scope isolation + negative memory
           STAGNATION early exit + human escalation package

This is intentionally a *generational* loop (distinct from OpenEvolve's
continuous MAP-Elites iteration loop) to faithfully match the paper.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from openevolve.tdes import selection
from openevolve.tdes.config import TDESConfig
from openevolve.tdes.crossover import complementary_crossover
from openevolve.tdes.memory import NegativeMemory
from openevolve.tdes.mutation import Mutator
from openevolve.tdes.test_suite import TDESTestSuite
from openevolve.tdes.types import Candidate, TestVector

logger = logging.getLogger(__name__)


@dataclass
class TDESResult:
    """Outcome of a TDES run."""

    best: Candidate
    generations_run: int
    escalated: bool
    history: List[Dict]  # per-generation summary


def load_seed_codebase(seed_dir: str, module_names: List[str]) -> Candidate:
    """Load a seed Candidate from a directory of ``<module>.py`` files."""
    modules: Dict[str, str] = {}
    for name in module_names:
        path = os.path.join(seed_dir, f"{name}.py")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"seed module '{name}' not found at {path} "
                f"(suite declares modules: {module_names})"
            )
        with open(path, "r", encoding="utf-8") as f:
            modules[name] = f.read()
    return Candidate(modules=modules, generation=0, metadata={"origin": "seed"})


def _codebase_hash(candidate: Candidate) -> str:
    h = hashlib.sha256()
    for name in sorted(candidate.modules):
        h.update(name.encode())
        h.update(b"\0")
        h.update(candidate.modules[name].encode())
        h.update(b"\0")
    return h.hexdigest()


class TDESController:
    """Runs the TDES generational loop."""

    def __init__(
        self,
        seed: Candidate,
        suite: TDESTestSuite,
        mutator: Mutator,
        config: Optional[TDESConfig] = None,
    ):
        self.seed = seed
        self.suite = suite
        self.mutator = mutator
        self.config = config or TDESConfig()
        self.memory = NegativeMemory(window_size=self.config.window_size)
        self.history: List[Dict] = []
        self._rng = random.Random(self.config.random_seed)
        os.makedirs(self.config.output_dir, exist_ok=True)

    # -- public API ------------------------------------------------------
    def run(self) -> TDESResult:
        """Synchronous entry point."""
        return asyncio.run(self.run_async())

    async def run_async(self) -> TDESResult:
        cfg = self.config
        # Initialize: seed all population slots (Appendix A).
        population: List[Candidate] = [self.seed.clone(generation=0) for _ in range(cfg.pop_size)]

        prev_union: Optional[Set[str]] = None
        escalated = False
        generations_run = 0

        for gen in range(1, cfg.max_generations + 1):
            generations_run = gen
            logger.info("=== TDES generation %d/%d ===", gen, cfg.max_generations)

            # EVALUATE -----------------------------------------------------
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

            # STAGNATION CHECK (no new test passed anywhere since last gen) -
            if prev_union is not None and current_union <= prev_union:
                logger.warning(
                    "Stagnation detected at generation %d: no new tests passed "
                    "across the population. Escalating to human.",
                    gen,
                )
                self._write_escalation(best, gen)
                escalated = True
                self._record_history(gen, population, stagnated=True)
                break

            # If everything passes, we are done early.
            if best.vector.total_passes == len(self.suite.tests):
                logger.info("All %d tests pass at generation %d.", len(self.suite.tests), gen)
                self._record_history(gen, population, solved=True)
                break

            # SELECT -------------------------------------------------------
            survivors = selection.top_k(population, max(1, math.ceil(cfg.pop_size / 2)))

            # CROSSOVER (conditional, complementary-coverage) --------------
            crossover_children = self._crossover_phase(survivors, gen)

            # MUTATE (modular scope isolation + negative memory) -----------
            mutated = await self._mutation_phase(survivors, gen)

            self._record_history(gen, population)

            # Assemble next generation: elitist carryover of survivors plus
            # accepted crossover children and mutated candidates, capped to
            # pop_size by hierarchical ranking (deduped by codebase content).
            population = self._next_generation(
                survivors + crossover_children + mutated, cfg.pop_size
            )
            prev_union = current_union

        # Output: best candidate by hierarchical ordering.
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

    # -- phases ----------------------------------------------------------
    def _evaluate_all(self, population: List[Candidate]) -> None:
        """Run the suite for any candidate lacking a cached test vector."""
        for cand in population:
            if cand.vector is None:
                cand.vector = self.suite.run(
                    cand, sandbox=self.config.sandbox, timeout=self.config.suite_timeout
                )

    def _crossover_phase(self, survivors: List[Candidate], gen: int) -> List[Candidate]:
        children: List[Candidate] = []
        ranked = selection.rank(survivors)
        # Each ordered pair where the first ranks higher than the second.
        for i, higher in enumerate(ranked):
            for lower in ranked[i + 1 :]:
                outcome = complementary_crossover(
                    higher,
                    lower,
                    self.suite,
                    generation=gen,
                    sandbox=self.config.sandbox,
                    timeout=self.config.suite_timeout,
                )
                if outcome.accepted and outcome.child is not None:
                    children.append(outcome.child)
        return children

    async def _mutation_phase(self, survivors: List[Candidate], gen: int) -> List[Candidate]:
        mutated: List[Candidate] = []
        for parent in survivors:
            child = await self._mutate_candidate(parent, gen)
            if child is not None:
                mutated.append(child)
        return mutated

    async def _mutate_candidate(self, parent: Candidate, gen: int) -> Optional[Candidate]:
        """Evolve a candidate one failing module at a time (section 3.5)."""
        baseline_passes = parent.passes
        working = parent.clone(generation=gen, parent_id=parent.id, metadata={"origin": "mutation"})
        working.vector = parent.vector
        changed = False

        failing_modules = parent.vector.failing_modules()
        limit = self.config.mutate_modules_per_candidate
        if limit is not None:
            failing_modules = failing_modules[:limit]

        for module in failing_modules:
            feedback = [
                r.feedback
                for r in working.vector.results.values()
                if not r.passed and r.module == module and r.feedback is not None
            ]
            proposal = await self.mutator.propose(
                candidate=working,
                module=module,
                feedback=feedback,
                memory_text=self.memory.render(module),
                generation=gen,
            )
            if proposal is None:
                continue

            trial = working.clone(generation=gen, parent_id=parent.id)
            trial.modules[module] = proposal.new_source
            trial.vector = self.suite.run(
                trial, sandbox=self.config.sandbox, timeout=self.config.suite_timeout
            )

            # Accept iff no regression relative to the working candidate.
            if trial.vector.is_superset_of(working.vector):
                if trial.vector.passes() != working.vector.passes():
                    changed = True
                working = trial
                working.metadata["origin"] = "mutation"
            else:
                # Record why this approach failed into the semantic tabu list.
                self._record_failure(module, gen, proposal.approach, trial.vector, working)

        if changed and working.passes > baseline_passes:
            return working
        # Even if not strictly better, return the no-regression result so the
        # mutated lineage survives (it is deduped/ranked in _next_generation).
        return working if changed else None

    def _record_failure(self, module, gen, approach, trial_vector, working) -> None:
        """Summarize a rejected mutation into negative memory (section 3.4)."""
        # Find a test that the working candidate passed but the trial broke
        # (a regression), or otherwise the first still-failing test on module.
        regressed = working.vector.passes() - trial_vector.passes()
        failure_mode = "no net improvement"
        triggering_input = ""
        if regressed:
            tid = sorted(regressed)[0]
            res = trial_vector.results.get(tid)
            failure_mode = "regressed a passing test"
            if res and res.feedback:
                failure_mode = f"regressed test ({res.feedback.error})"
                triggering_input = res.feedback.failing_input
        else:
            for r in trial_vector.results.values():
                if not r.passed and r.module == module and r.feedback is not None:
                    failure_mode = r.feedback.error
                    triggering_input = r.feedback.failing_input
                    break
        self.memory.record(
            module=module,
            generation=gen,
            approach=approach,
            failure_mode=failure_mode,
            triggering_input=triggering_input,
        )

    def _next_generation(self, pool: List[Candidate], pop_size: int) -> List[Candidate]:
        """Dedupe by codebase content, rank, and cap/pad to pop_size."""
        self._evaluate_all(pool)
        seen: Set[str] = set()
        unique: List[Candidate] = []
        for cand in selection.rank(pool):
            h = _codebase_hash(cand)
            if h not in seen:
                seen.add(h)
                unique.append(cand)
        survivors = unique[:pop_size]
        # Pad with clones of the best to keep a constant population size.
        while len(survivors) < pop_size and survivors:
            survivors.append(survivors[0].clone(generation=survivors[0].generation))
        return survivors

    # -- bookkeeping -----------------------------------------------------
    def _union_passes(self, population: List[Candidate]) -> Set[str]:
        union: Set[str] = set()
        for c in population:
            if c.vector is not None:
                union |= c.vector.passes()
        return union

    def _record_history(self, gen, population, *, stagnated=False, solved=False) -> None:
        best = selection.best(population)
        self.history.append(
            {
                "generation": gen,
                "best_score_key": list(best.vector.score_key),
                "best_summary": best.vector.summary(),
                "population_union_passes": sorted(self._union_passes(population)),
                "stagnated": stagnated,
                "solved": solved,
            }
        )

    def _write_escalation(self, best: Candidate, gen: int) -> None:
        """Write the human-in-the-loop escalation package (section 3.6)."""
        package = {
            "reason": "stagnation",
            "generation": gen,
            "best_candidate": {
                "id": best.id,
                "score_key": list(best.vector.score_key),
                "summary": best.vector.summary(),
                "modules": best.modules,
            },
            "failing_tests": [
                {
                    "test_id": r.test_id,
                    "level": r.level.name,
                    "module": r.module,
                    "description": r.description,
                    "failing_input": r.feedback.failing_input if r.feedback else None,
                    "error": r.feedback.error if r.feedback else None,
                }
                for r in best.vector.failures()
            ],
            "negative_memory": self.memory.as_dict(),
        }
        path = os.path.join(self.config.output_dir, "escalation.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(package, f, indent=2)
        logger.warning("Escalation package written to %s", path)

    def _write_best(self, best: Candidate) -> None:
        best_dir = os.path.join(self.config.output_dir, "best")
        os.makedirs(best_dir, exist_ok=True)
        for name, source in best.modules.items():
            with open(os.path.join(best_dir, f"{name}.py"), "w", encoding="utf-8") as f:
                f.write(source)
        with open(os.path.join(best_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "id": best.id,
                    "score_key": list(best.vector.score_key),
                    "summary": best.vector.summary(),
                    "passes": sorted(best.vector.passes()),
                    "history": self.history,
                },
                f,
                indent=2,
            )
