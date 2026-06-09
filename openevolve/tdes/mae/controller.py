"""
TDES controller specialization for the MAE experiment.

Two deliberate deviations from the base generational loop, both additive:

* **No crossover.** The candidate has a single module (``masking``), so
  complementary-coverage grafting has nothing to graft — but each attempted
  graft would still cost a full training evaluation. ``_crossover_phase``
  returns no children. (Crossover was validated on the FPGA layer; this layer
  validates hierarchical selection + CEGIS + memory on an ML component.)

* **Stagnation patience.** The base loop escalates on the *first* generation
  with no new union test passes. With a probe-accuracy ladder as the SYSTEM
  tier, a flat generation is routine (LLM proposals get rejected by the
  no-regression check), so we only escalate after ``stagnation_patience``
  consecutive flat generations. ``run_async`` is re-stated here for that one
  change; the phase methods are all inherited.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set

from openevolve.tdes import selection
from openevolve.tdes.config import TDESConfig
from openevolve.tdes.controller import TDESController, TDESResult
from openevolve.tdes.types import Candidate

logger = logging.getLogger(__name__)


class MAEEvolutionController(TDESController):
    def __init__(self, *args, stagnation_patience: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.stagnation_patience = stagnation_patience

    def _crossover_phase(self, survivors: List[Candidate], gen: int) -> List[Candidate]:
        return []  # single-module candidate: nothing to graft

    def _record_history(self, gen, population, *, stagnated=False, solved=False) -> None:
        super()._record_history(gen, population, stagnated=stagnated, solved=solved)
        # Enrich with per-candidate detail for evolution_log.json.
        self.history[-1]["population"] = [
            {
                "id": c.id,
                "origin": c.metadata.get("origin"),
                "score_key": list(c.vector.score_key) if c.vector else None,
                "total_passes": c.vector.total_passes if c.vector else 0,
                "source": c.modules.get("masking"),
            }
            for c in selection.rank(population)
        ]

    async def run_async(self) -> TDESResult:
        cfg = self.config
        population = [self.seed.clone(generation=0) for _ in range(cfg.pop_size)]

        prev_union: Optional[Set[str]] = None
        flat_generations = 0
        escalated = False
        generations_run = 0

        for gen in range(1, cfg.max_generations + 1):
            generations_run = gen
            logger.info("=== TDES-MAE generation %d/%d ===", gen, cfg.max_generations)

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
                flat_generations += 1
                logger.info(
                    "Flat generation (%d/%d before escalation)",
                    flat_generations,
                    self.stagnation_patience,
                )
                if flat_generations >= self.stagnation_patience:
                    logger.warning(
                        "Stagnation: %d consecutive generations without a new "
                        "test pass. Escalating to human.",
                        flat_generations,
                    )
                    self._write_escalation(best, gen)
                    escalated = True
                    self._record_history(gen, population, stagnated=True)
                    break
            else:
                flat_generations = 0

            if best.vector.total_passes == len(self.suite.tests):
                logger.info("All %d tests pass at generation %d.", len(self.suite.tests), gen)
                self._record_history(gen, population, solved=True)
                break

            import math

            survivors = selection.top_k(population, max(1, math.ceil(cfg.pop_size / 2)))
            mutated = await self._mutation_phase(survivors, gen)
            self._record_history(gen, population)
            population = self._next_generation(survivors + mutated, cfg.pop_size)
            prev_union = current_union

        self._evaluate_all(population)
        best = selection.best(population)
        self._write_best(best)
        logger.info(
            "TDES-MAE finished after %d generation(s). Best: %s%s",
            generations_run,
            best.vector.summary(),
            " (escalated)" if escalated else "",
        )
        return TDESResult(
            best=best, generations_run=generations_run, escalated=escalated, history=self.history
        )


def build_controller(
    seed_source: str,
    suite,
    mutator,
    config: Optional[TDESConfig] = None,
    *,
    stagnation_patience: int = 3,
) -> MAEEvolutionController:
    seed = Candidate(modules={"masking": seed_source}, generation=0, metadata={"origin": "seed"})
    return MAEEvolutionController(
        seed, suite, mutator, config, stagnation_patience=stagnation_patience
    )
