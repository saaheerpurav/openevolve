"""
Complementary-coverage crossover (section 3.3) — the primary novel contribution
of TDES.

Standard GP crossover recombines two high-fitness parents semi-randomly. TDES
instead *gates* crossover on complementary test coverage: recombination between
a higher-ranked candidate A and a lower-ranked candidate B is attempted only
when B passes tests that A does not. The modules responsible for those passes
are grafted from B into A, the full suite is re-run, and the result is accepted
only if its pass set is a *strict superset* of A's — no regressions tolerated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from openevolve.tdes.test_suite import TDESTestSuite
from openevolve.tdes.types import Candidate

logger = logging.getLogger(__name__)


@dataclass
class CrossoverOutcome:
    """Diagnostic record for a single crossover attempt (for logging/metrics)."""

    attempted: bool
    accepted: bool
    higher_id: str
    lower_id: str
    complementary_tests: List[str]
    grafted_modules: List[str]
    child: Optional[Candidate] = None
    reason: str = ""


def complementary_crossover(
    higher: Candidate,
    lower: Candidate,
    suite: TDESTestSuite,
    *,
    generation: int,
    sandbox: bool = True,
    timeout: int = 60,
) -> CrossoverOutcome:
    """Attempt complementary-coverage crossover grafting `lower` into `higher`.

    Args:
        higher: the better-ranked parent A (its passes must not regress).
        lower: the lower-ranked parent B (donor of complementary modules).
        suite: the hierarchical test suite (oracle + tests->modules map).
        generation: generation tag for the produced child.
        sandbox/timeout: forwarded to the suite runner.

    Returns:
        A CrossoverOutcome. ``accepted`` is True (and ``child`` is set) only when
        the grafted candidate strictly supersedes `higher`'s passes.
    """
    if higher.vector is None or lower.vector is None:
        return CrossoverOutcome(
            False, False, higher.id, lower.id, [], [], reason="missing test vectors"
        )

    # Step 1: C(B, A) — tests B passes that A does not.
    complementary = sorted(lower.vector.complementary_to(higher.vector))
    if not complementary:
        return CrossoverOutcome(
            False, False, higher.id, lower.id, [], [], reason="no complementary coverage"
        )

    # Step 2: identify the modules in B responsible for those passing tests.
    candidate_modules = suite.modules_for_tests(complementary)
    # Only graft modules that B actually contains and that differ from A's.
    graft_modules = [
        m
        for m in candidate_modules
        if m in lower.modules and lower.modules[m] != higher.modules.get(m)
    ]
    if not graft_modules:
        return CrossoverOutcome(
            False,
            False,
            higher.id,
            lower.id,
            complementary,
            [],
            reason="complementary modules identical or absent in donor",
        )

    # Step 3: graft those modules from B into A.
    grafted = graft(higher, lower, graft_modules, generation=generation)

    # Step 4: re-run the full suite on the grafted candidate.
    grafted.vector = suite.run(grafted, sandbox=sandbox, timeout=timeout)

    # Step 5: accept only on a strict superset of A's passes (no regressions).
    if grafted.vector.is_strict_superset_of(higher.vector):
        logger.info(
            "Crossover accepted: %s + %s[%s] -> %s (%s)",
            higher.id,
            lower.id,
            ",".join(graft_modules),
            grafted.id,
            grafted.vector.summary(),
        )
        return CrossoverOutcome(
            True,
            True,
            higher.id,
            lower.id,
            complementary,
            graft_modules,
            grafted,
            "strict superset",
        )

    reason = "regression or no net gain after graft"
    logger.debug("Crossover rejected (%s): %s + %s[%s]", reason, higher.id, lower.id, graft_modules)
    return CrossoverOutcome(
        True, False, higher.id, lower.id, complementary, graft_modules, None, reason
    )


def graft(higher: Candidate, lower: Candidate, modules: List[str], *, generation: int) -> Candidate:
    """Produce A' by replacing `modules` in A with B's versions (section 3.3, step 3)."""
    merged = dict(higher.modules)
    for m in modules:
        merged[m] = lower.modules[m]
    child = Candidate(
        modules=merged,
        generation=generation,
        parent_id=higher.id,
        metadata={
            "origin": "crossover",
            "donor_id": lower.id,
            "grafted_modules": list(modules),
        },
    )
    return child
