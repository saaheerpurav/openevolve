"""
Non-evolutionary baseline for TDES-Repair: the single-shot LLM repair.

Information parity with TDES generation 0: the model sees each failing
module's source plus that module's CEGIS feedback from the seed evaluation
(the same prompt path as ``LLMMutator`` inside the controller), makes exactly
one proposal per failing module, and the patched codebase is evaluated once.
No iteration, no population, no memory.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

from openevolve.tdes.mutation import Mutator
from openevolve.tdes.repair.controllers import unit_failing_modules
from openevolve.tdes.test_suite import TDESTestSuite
from openevolve.tdes.types import Candidate


@dataclass
class BaselineResult:
    solved: bool
    total_passes: int
    total_tests: int
    rounds_used: int
    trajectory: List[int] = field(default_factory=list)


async def single_shot_async(
    seed: Candidate,
    suite: TDESTestSuite,
    ensemble=None,
    *,
    mutator: Optional[Mutator] = None,
    sandbox: bool = True,
    timeout: int = 60,
) -> BaselineResult:
    if mutator is None:
        from openevolve.tdes.repair.mutation import RepairLLMMutator

        mutator = RepairLLMMutator(ensemble)
    candidate = seed.clone(metadata={"origin": "single_shot"})
    before = suite.run(candidate, sandbox=sandbox, timeout=timeout)
    # Unit-level attribution, same as the evolutionary controllers: only
    # modules whose own unit tests fail get a repair attempt.
    for module in unit_failing_modules(before):
        feedback = [
            r.feedback
            for r in before.results.values()
            if not r.passed and r.module == module and r.feedback is not None
        ]
        proposal = await mutator.propose(
            candidate=candidate,
            module=module,
            feedback=feedback,
            memory_text="",
            generation=0,
        )
        if proposal is not None:
            candidate.modules[module] = proposal.new_source
    after = suite.run(candidate, sandbox=sandbox, timeout=timeout)
    total = len(suite.tests)
    return BaselineResult(
        solved=after.total_passes == total and total > 0,
        total_passes=after.total_passes,
        total_tests=total,
        rounds_used=1,
        trajectory=[before.total_passes, after.total_passes],
    )


def single_shot(seed, suite, ensemble=None, **kwargs) -> BaselineResult:
    return asyncio.run(single_shot_async(seed, suite, ensemble, **kwargs))
