"""
Test-Driven Evolutionary Synthesis (TDES).

An additive evolutionary mode for OpenEvolve that guides LLM-based code
evolution with a *hierarchical test suite* instead of a scalar fitness
function. See the package modules for each mechanism:

  * ``types``       — hierarchical test-pass vector, candidate codebase
  * ``test_suite``  — hierarchical tests + sandboxed runner with CEGIS capture
  * ``selection``   — hierarchical (system > integration > unit) ordering
  * ``crossover``   — complementary-coverage crossover (primary contribution)
  * ``memory``      — negative exemplar memory (semantic tabu list)
  * ``mutation``    — modular scope isolation mutators (LLM + scripted)
  * ``controller``  — the generational loop from the paper's Appendix A
"""

from openevolve.tdes.config import TDESConfig
from openevolve.tdes.controller import (
    TDESController,
    TDESResult,
    load_seed_codebase,
)
from openevolve.tdes.crossover import complementary_crossover
from openevolve.tdes.memory import NegativeMemory
from openevolve.tdes.mutation import LLMMutator, MutationProposal, Mutator, ScriptedMutator
from openevolve.tdes.test_suite import (
    TDESAssertionError,
    TDESTest,
    TDESTestSuite,
    TestEnv,
)
from openevolve.tdes.types import (
    Candidate,
    FeedbackTuple,
    NegativeMemoryEntry,
    TestLevel,
    TestResult,
    TestVector,
)

__all__ = [
    "TDESConfig",
    "TDESController",
    "TDESResult",
    "load_seed_codebase",
    "complementary_crossover",
    "NegativeMemory",
    "LLMMutator",
    "ScriptedMutator",
    "Mutator",
    "MutationProposal",
    "TDESTestSuite",
    "TDESTest",
    "TestEnv",
    "TDESAssertionError",
    "Candidate",
    "FeedbackTuple",
    "NegativeMemoryEntry",
    "TestLevel",
    "TestResult",
    "TestVector",
]
