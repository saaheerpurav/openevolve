"""
Hierarchical selection for TDES (section 3.1).

Candidates are ranked by their test-pass vector using a lexicographic ordering
that respects the test hierarchy: count of passing system tests first, then
integration, then unit. This ensures higher-level correctness is always
preferred and prevents the population from optimizing trivial unit tests at the
expense of integration/system behavior.

This adapts the lexicase insight (Spector [10]) — individual test-case
performance matters — to a coarse, engineering-motivated hierarchy.
"""

from __future__ import annotations

from typing import List, Tuple

from openevolve.tdes.types import Candidate, TestVector


def _empty_key() -> Tuple[int, int, int]:
    return (0, 0, 0)


def vector_key(vector) -> Tuple[int, int, int]:
    """Lexicographic ordering key for a (possibly None) TestVector."""
    if vector is None:
        return _empty_key()
    return vector.score_key


def rank(population: List[Candidate]) -> List[Candidate]:
    """Return candidates sorted best-first by hierarchical ordering.

    Ties on the (system, integration, unit) key are broken by total passes then
    by lower generation (older/simpler preferred), keeping the order stable and
    deterministic.
    """

    def key(c: Candidate):
        sk = vector_key(c.vector)
        total = c.vector.total_passes if c.vector else 0
        return (sk[0], sk[1], sk[2], total, -c.generation)

    return sorted(population, key=key, reverse=True)


def top_k(population: List[Candidate], k: int) -> List[Candidate]:
    """Top-k survivors by hierarchical ordering (k clamped to >= 1)."""
    k = max(1, k)
    return rank(population)[:k]


def best(population: List[Candidate]) -> Candidate:
    """Single best candidate by hierarchical ordering."""
    return rank(population)[0]
