"""
Core data types for Test-Driven Evolutionary Synthesis (TDES).

These structures replace OpenEvolve's scalar fitness with a *hierarchical
test-pass vector* (paper section 3.1) and model a candidate as a multi-module
codebase rather than a single program (section 3.5).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


class TestLevel(enum.IntEnum):
    """Test hierarchy levels.

    Integer values encode the hierarchy used for lexicographic selection
    (section 3.1): system passes outweigh integration passes, which outweigh
    unit passes. Higher value == higher precedence.
    """

    UNIT = 1
    INTEGRATION = 2
    SYSTEM = 3

    @classmethod
    def from_str(cls, name: str) -> "TestLevel":
        return cls[name.strip().upper()]


@dataclass(frozen=True)
class FeedbackTuple:
    """CEGIS-style counterexample feedback for a single failing test (section 3.2).

    The test *source code* is deliberately withheld; only a natural-language
    description, the concrete failing input, and the error message are exposed
    to the mutator. This prevents the LLM from Goodharting against test
    internals while still giving it a directed, concrete signal.
    """

    description: str
    failing_input: str
    error: str

    def render(self) -> str:
        return (
            f"- {self.description}\n"
            f"    failing input: {self.failing_input}\n"
            f"    error: {self.error}"
        )


@dataclass
class TestResult:
    """Outcome of running one test against one candidate."""

    test_id: str
    level: TestLevel
    module: str
    passed: bool
    description: str
    feedback: Optional[FeedbackTuple] = None  # populated only on failure


@dataclass
class TestVector:
    """The hierarchical test-pass vector f(p) from section 3.1.

    Maps each test id to its TestResult, preserving insertion order. Provides
    the lexicographic ordering key (system > integration > unit) used for
    selection and the set-based superset checks used by crossover (section 3.3)
    and mutation regression checks (section 3.5).
    """

    results: Dict[str, TestResult] = field(default_factory=dict)

    # -- pass sets -------------------------------------------------------
    def passes(self) -> Set[str]:
        """Set of test ids this candidate passes."""
        return {tid for tid, r in self.results.items() if r.passed}

    def failures(self) -> List[TestResult]:
        """Failing TestResults, in order."""
        return [r for r in self.results.values() if not r.passed]

    def failing_modules(self) -> List[str]:
        """Distinct modules that have at least one failing test, in order."""
        seen: List[str] = []
        for r in self.results.values():
            if not r.passed and r.module not in seen:
                seen.append(r.module)
        return seen

    # -- hierarchical ordering -------------------------------------------
    def level_counts(self) -> Dict[TestLevel, int]:
        """Count of passing tests per level."""
        counts = {lvl: 0 for lvl in TestLevel}
        for r in self.results.values():
            if r.passed:
                counts[r.level] += 1
        return counts

    @property
    def score_key(self) -> Tuple[int, int, int]:
        """Lexicographic ordering key: (system, integration, unit) passes.

        Larger tuples are strictly better. This realizes the hierarchical
        ordering of section 3.1 where higher-level correctness is always
        preferred and ties are broken by the next level down.
        """
        c = self.level_counts()
        return (c[TestLevel.SYSTEM], c[TestLevel.INTEGRATION], c[TestLevel.UNIT])

    @property
    def total_passes(self) -> int:
        return len(self.passes())

    # -- set relations used by crossover / mutation ----------------------
    def is_superset_of(self, other: "TestVector") -> bool:
        """True if this candidate passes (at least) every test `other` passes."""
        return self.passes() >= other.passes()

    def is_strict_superset_of(self, other: "TestVector") -> bool:
        """True if this candidate passes every test `other` does AND strictly more.

        This is the acceptance criterion for complementary-coverage crossover
        (section 3.3, step 5).
        """
        return self.passes() > other.passes()

    def complementary_to(self, other: "TestVector") -> Set[str]:
        """C(self, other): tests `self` passes that `other` does not (section 3.3)."""
        return self.passes() - other.passes()

    def summary(self) -> str:
        c = self.level_counts()
        return (
            f"system {c[TestLevel.SYSTEM]}, "
            f"integration {c[TestLevel.INTEGRATION]}, "
            f"unit {c[TestLevel.UNIT]} "
            f"({self.total_passes}/{len(self.results)} total)"
        )


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Candidate:
    """A candidate solution: a codebase mapped as module name -> source code.

    Representing a candidate as a dict of modules (rather than one program) is
    what makes modular scope isolation (section 3.5) and module grafting in
    crossover (section 3.3) natural operations.
    """

    modules: Dict[str, str]
    id: str = field(default_factory=_short_id)
    generation: int = 0
    parent_id: Optional[str] = None
    vector: Optional[TestVector] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def clone(self, **overrides) -> "Candidate":
        """Shallow-copy with a fresh id, optionally overriding fields."""
        data = dict(
            modules=dict(self.modules),
            generation=self.generation,
            parent_id=self.parent_id,
            metadata=dict(self.metadata),
        )
        data.update(overrides)
        return Candidate(**data)

    @property
    def passes(self) -> Set[str]:
        return self.vector.passes() if self.vector else set()


@dataclass
class NegativeMemoryEntry:
    """One entry in the per-module negative exemplar memory (section 3.4).

    Stores *why* an approach failed in natural language, functioning as a
    semantic tabu list entry.
    """

    generation: int
    approach: str
    failure_mode: str
    triggering_input: str

    def render(self) -> str:
        return f"- Gen {self.generation}: {self.approach} " f"→ {self.failure_mode}" + (
            f" on input {self.triggering_input}" if self.triggering_input else ""
        )
