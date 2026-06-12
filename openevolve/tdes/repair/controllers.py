"""
Controllers and the condition registry for TDES-Repair.

Reuses the suite-agnostic ``AblationController`` family from the FPGA layer
unchanged (the combopt precedent) and adds the unconstrained random-crossover
GA baseline. All evolutionary conditions run the ``DiverseScheduleController``
mutation scheduling, so the only delta between them is the crossover
mechanism itself.
"""

from __future__ import annotations

from typing import List, Optional

from openevolve.tdes import selection
from openevolve.tdes.controller import _codebase_hash
from openevolve.tdes.fpga.ablation import AblationController, DiverseScheduleController
from openevolve.tdes.types import Candidate, TestLevel, TestVector

__all__ = [
    "AblationController",
    "DiverseScheduleController",
    "UnitDiverseController",
    "RandomCrossoverController",
    "unit_failing_modules",
    "CONDITIONS",
]


def unit_failing_modules(vector: TestVector) -> List[str]:
    """Modules with at least one failing UNIT test, in result order.

    Integration/system tests carry a *primary* module tag that may point at a
    module whose code is already correct (the true culprit is upstream), so
    they alone do not nominate a module here. Falls back to the base
    ``failing_modules()`` when no unit test fails but higher levels do.
    """
    seen: List[str] = []
    for r in vector.results.values():
        if not r.passed and r.level == TestLevel.UNIT and r.module not in seen:
            seen.append(r.module)
    return seen or vector.failing_modules()


class UnitDiverseController(DiverseScheduleController):
    """DiverseScheduleController with unit-level module attribution.

    Identical mutation scheduling (random per-candidate module order — the
    population diversity crossover needs), but a candidate only spends its
    mutation budget on modules whose own unit tests fail. Without this, the
    primary-module tags of failing integration/system tests nominate
    already-correct modules; under ``mutate_modules_per_candidate=1`` whole
    generations can be wasted on them and the stagnation rule ends the run.
    """

    async def _mutate_candidate(self, parent: Candidate, gen: int) -> Optional[Candidate]:
        baseline_passes = parent.passes
        working = parent.clone(generation=gen, parent_id=parent.id, metadata={"origin": "mutation"})
        working.vector = parent.vector
        changed = False

        failing_modules = unit_failing_modules(parent.vector)
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
            if trial.vector.is_superset_of(working.vector):
                if trial.vector.passes() != working.vector.passes():
                    changed = True
                working = trial
                working.metadata["origin"] = "mutation"
            else:
                self._record_failure(module, gen, proposal.approach, trial.vector, working)

        if changed and working.passes > baseline_passes:
            return working
        return working if changed else None

    def _next_generation(self, pool: List[Candidate], pop_size: int) -> List[Candidate]:
        """Dedupe and rank like the base, but pad by cycling through DISTINCT
        lineages instead of cloning only the best.

        Base padding floods the population with copies of the single top
        candidate; when complementary partial fixes rank asymmetrically (one
        also clears an integration test), the lower one is crowded out of the
        survivor pool before crossover can ever pair them. Diversity-preserving
        padding applies to every evolutionary condition equally.
        """
        self._evaluate_all(pool)
        seen, unique = set(), []
        for cand in selection.rank(pool):
            h = _codebase_hash(cand)
            if h not in seen:
                seen.add(h)
                unique.append(cand)
        survivors = unique[:pop_size]
        i = 0
        while len(survivors) < pop_size and unique:
            source = unique[i % len(unique)]
            survivors.append(source.clone(generation=source.generation))
            i += 1
        return survivors


class RandomCrossoverController(UnitDiverseController):
    """Unconstrained-crossover GA baseline.

    Enumerates the same ranked survivor pairs as the complementary-coverage
    controller (so pair counts are comparable), but grafts a *random* nonempty
    subset of the modules whose sources differ and accepts the child
    UNCONDITIONALLY — no strict-superset gate. Regressed children are pruned
    by ranked selection at the next generation, making this a fair
    genetic-algorithm foil for the targeted crossover.

    ``crossover_stats.lift_total`` keeps the clamped-at-zero semantics of
    :class:`CrossoverStats` for table compatibility; ``raw_lift_total``
    accumulates the actual (possibly negative) lift over receivers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_lift_total = 0

    def _crossover_phase(self, survivors: List[Candidate], gen: int) -> List[Candidate]:
        if not self.enable_crossover:
            return []
        children: List[Candidate] = []
        ranked = selection.rank(survivors)
        for i, higher in enumerate(ranked):
            for lower in ranked[i + 1 :]:
                self.crossover_stats.pairs_considered += 1
                differing = [
                    m
                    for m in self.suite.module_names
                    if higher.modules.get(m) != lower.modules.get(m)
                ]
                if not differing:
                    continue
                self.crossover_stats.attempts += 1
                graft = self._rng.sample(differing, self._rng.randint(1, len(differing)))
                child = higher.clone(
                    generation=gen,
                    parent_id=higher.id,
                    metadata={
                        "origin": "random_crossover",
                        "donor_id": lower.id,
                        "grafted_modules": sorted(graft),
                    },
                )
                for module in graft:
                    child.modules[module] = lower.modules[module]
                child.vector = self.suite.run(
                    child, sandbox=self.config.sandbox, timeout=self.config.suite_timeout
                )
                self.crossover_stats.accepted += 1
                lift = child.vector.total_passes - higher.vector.total_passes
                self.raw_lift_total += lift
                self.crossover_stats.lift_total += max(0, lift)
                children.append(child)
        return children


# Condition name -> (controller class, controller kwargs). The single_shot
# baseline is not controller-based; see baselines.single_shot. All three
# evolutionary conditions share the unit-attributed diverse scheduling, so the
# only delta between them is the crossover mechanism.
CONDITIONS = {
    "tdes_full": (UnitDiverseController, dict(enable_crossover=True, enable_memory=True)),
    "tdes_no_crossover": (
        UnitDiverseController,
        dict(enable_crossover=False, enable_memory=True),
    ),
    "random_crossover": (
        RandomCrossoverController,
        dict(enable_crossover=True, enable_memory=True),
    ),
}
