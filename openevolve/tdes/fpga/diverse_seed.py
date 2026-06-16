"""
Diverse population seeding for TDES-FPGA.

Replaces the default ``[seed.clone() for _ in range(pop_size)]``
initialization with a set of candidates generated from varied LLM prompting
strategies. When all candidates start from the same skeleton, they converge
to the same approach in 1-2 generations and complementary-coverage crossover
never fires. Starting from diverse initial implementations — each with a
different approach and therefore different partial correctness — gives
crossover material to combine from generation 1.

The seed skeleton is always kept as candidate 0 (the safest starting point).
Additional candidates are generated with strategies that vary architectural
reasoning depth and implementation style.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from openevolve.tdes.fpga import prompts as verilog_prompts
from openevolve.tdes.fpga.verilog_suite import VerilogTestSuite
from openevolve.tdes.types import Candidate
from openevolve.utils.code_utils import parse_full_rewrite

logger = logging.getLogger(__name__)

_STRATEGIES = ["zero_shot", "chain_of_thought", "minimal", "alternative"]

_STRATEGY_INTRO = {
    "zero_shot": "Write a complete synthesizable implementation of the module.",
    "chain_of_thought": (
        "Think step by step about the hardware architecture before writing the "
        "implementation. Consider the data flow, any required sub-operations, and "
        "edge cases first, then write the final module."
    ),
    "minimal": (
        "Write the simplest possible implementation that covers the core behaviour, "
        "even if some edge cases are not yet handled. Aim for clarity over completeness."
    ),
    "alternative": (
        "Write an alternative implementation that takes a DIFFERENT architectural "
        "approach from the most obvious one — e.g. if the straightforward approach "
        "is combinational, consider a registered/pipelined design; if it would "
        "naturally use addition, consider bitwise or shift-based alternatives."
    ),
}

_GEN_SYSTEM = (
    "You are an expert digital design engineer. "
    "Write a single synthesizable Verilog module that implements the described specification. "
    "Respond with the complete module inside one ```verilog code block and nothing else — "
    "no explanations, no extra text before or after the code block."
)


def _module_spec(seed: Candidate, suite: VerilogTestSuite, module_name: str) -> str:
    """Build a concise specification for ``module_name`` from the suite's test descriptions."""
    tests_for_module = [
        t for t in suite.tests
        if t.module == module_name or (t.modules and module_name in t.modules)
    ]
    if not tests_for_module:
        return "(no test descriptions available)"
    lines = []
    for t in tests_for_module:
        lines.append(f"- {t.description}")
    return "\n".join(lines)


def _build_seed_prompt(
    seed: Candidate,
    suite: VerilogTestSuite,
    module_name: str,
    strategy: str,
) -> str:
    skeleton = seed.modules.get(module_name, "")
    spec = _module_spec(seed, suite, module_name)
    intro = _STRATEGY_INTRO.get(strategy, _STRATEGY_INTRO["zero_shot"])
    return (
        f"Module interface (fill in the implementation):\n"
        f"```verilog\n{skeleton}\n```\n\n"
        f"Tests this module must pass:\n{spec}\n\n"
        f"{intro}\n\n"
        "Respond with the complete module in a single ```verilog code block."
    )


async def _generate_module(
    seed: Candidate,
    suite: VerilogTestSuite,
    ensemble,
    module_name: str,
    strategy: str,
) -> Optional[str]:
    """Ask the LLM to generate one module implementation using ``strategy``."""
    user = _build_seed_prompt(seed, suite, module_name, strategy)
    try:
        response = await ensemble.generate_with_context(
            system_message=_GEN_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:
        logger.warning("diverse_seed: LLM call failed for %s/%s: %s", module_name, strategy, e)
        return None
    if not response:
        return None
    code = parse_full_rewrite(response, "verilog")
    if not code or not code.strip():
        logger.debug("diverse_seed: no verilog block for %s/%s", module_name, strategy)
        return None
    return code


async def generate_diverse_seeds(
    seed: Candidate,
    suite: VerilogTestSuite,
    ensemble,
    n: int,
    *,
    sandbox: bool = True,
    timeout: int = 120,
) -> List[Candidate]:
    """Generate ``n`` diverse initial candidates for the TDES population.

    - Candidate 0: the skeleton seed (no LLM call, guaranteed safe start).
    - Candidates 1..n-1: LLM-generated using varied prompting strategies.

    Each generated candidate has its test vector evaluated immediately so it
    participates in ranked selection from generation 1.

    Args:
        seed:     The skeleton candidate (all modules contain stub code).
        suite:    VerilogTestSuite (provides per-module test descriptions).
        ensemble: LLMEnsemble (or _CountingEnsemble wrapper).
        n:        Desired population size.
        sandbox:  Forward to suite runner.
        timeout:  Forward to suite runner.

    Returns:
        List of ``n`` candidates with vectors evaluated.
    """
    if n <= 1:
        cand = seed.clone(generation=0)
        cand.vector = suite.run(cand, sandbox=sandbox, timeout=timeout)
        return [cand]

    candidates: List[Candidate] = []

    # Candidate 0: skeleton (evaluated, not LLM-generated)
    skeleton = seed.clone(generation=0, metadata={"origin": "seed_skeleton"})
    skeleton.vector = suite.run(skeleton, sandbox=sandbox, timeout=timeout)
    candidates.append(skeleton)

    for i in range(1, n):
        strategy = _STRATEGIES[(i - 1) % len(_STRATEGIES)]
        cand = seed.clone(generation=0, metadata={"origin": f"diverse_seed_{strategy}"})
        generated_any = False
        for module_name in list(seed.modules.keys()):
            new_src = await _generate_module(seed, suite, ensemble, module_name, strategy)
            if new_src:
                cand.modules[module_name] = new_src
                generated_any = True
        if generated_any:
            cand.vector = suite.run(cand, sandbox=sandbox, timeout=timeout)
        else:
            # Fallback to evaluated skeleton if all LLM calls failed
            cand.vector = skeleton.vector
            logger.warning("diverse_seed: all LLM calls failed for strategy=%s, using skeleton", strategy)
        candidates.append(cand)

    logger.info(
        "diverse_seed: generated %d candidates (skeleton + %d LLM); "
        "pass counts: %s",
        len(candidates),
        len(candidates) - 1,
        [c.vector.total_passes if c.vector else "?" for c in candidates],
    )
    return candidates
