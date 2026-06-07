"""
Non-evolutionary baselines for TDES-FPGA comparison.

  * ``single_agent_repair`` — the "Claude Code" baseline: one candidate, iterate
    run-tests → send failures to the LLM → fix → repeat for N rounds.
  * ``pass_at_k`` — the standard LLM benchmark baseline: generate k independent
    implementations from the design description, keep the best by the suite.

Both reuse the same ``LLMEnsemble`` as TDES so the comparison is apples-to-apples
(same model, same testbenches, same CEGIS feedback for single-agent).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

from openevolve.tdes.fpga import prompts
from openevolve.tdes.fpga.mutation import VerilogLLMMutator
from openevolve.tdes.fpga.verilog_suite import VerilogTestSuite
from openevolve.tdes.types import Candidate
from openevolve.utils.code_utils import parse_full_rewrite


@dataclass
class BaselineResult:
    solved: bool
    total_passes: int
    total_tests: int
    rounds_used: int
    best: Candidate
    trajectory: List[int] = field(default_factory=list)


def single_agent_repair(
    seed: Candidate,
    suite: VerilogTestSuite,
    ensemble,
    *,
    rounds: int = 5,
    timeout: int = 60,
    diff_based: bool = False,
) -> BaselineResult:
    """Iterative single-candidate repair using CEGIS feedback (no population)."""
    return asyncio.run(_single_agent_async(seed, suite, ensemble, rounds, timeout, diff_based))


async def _single_agent_async(seed, suite, ensemble, rounds, timeout, diff_based) -> BaselineResult:
    mutator = VerilogLLMMutator(ensemble, diff_based=diff_based)
    current = seed.clone()
    current.vector = suite.run(current, timeout=timeout)
    trajectory = [current.vector.total_passes]
    total = len(suite.tests)

    for r in range(rounds):
        if current.vector.total_passes == total:
            break
        for module in current.vector.failing_modules():
            feedback = [
                res.feedback
                for res in current.vector.results.values()
                if not res.passed and res.module == module and res.feedback is not None
            ]
            proposal = await mutator.propose(
                candidate=current,
                module=module,
                feedback=feedback,
                memory_text="",  # single-agent baseline has no negative memory
                generation=r + 1,
            )
            if proposal is None:
                continue
            current.modules[module] = proposal.new_source
        current.vector = suite.run(current, timeout=timeout)
        trajectory.append(current.vector.total_passes)

    passes = current.vector.total_passes
    return BaselineResult(
        solved=passes == total and total > 0,
        total_passes=passes,
        total_tests=total,
        rounds_used=len(trajectory) - 1,
        best=current,
        trajectory=trajectory,
    )


_GEN_SYSTEM = (
    "You are an expert digital design engineer. Write a single synthesizable "
    "Verilog module that implements the described specification. Respond with the "
    "module inside one ```verilog code block and nothing else."
)


def pass_at_k(
    module_name: str,
    description: str,
    suite: VerilogTestSuite,
    ensemble,
    *,
    k: int = 5,
    timeout: int = 60,
) -> BaselineResult:
    """Generate k independent implementations; keep the best by the suite."""
    return asyncio.run(_pass_at_k_async(module_name, description, suite, ensemble, k, timeout))


async def _pass_at_k_async(module_name, description, suite, ensemble, k, timeout) -> BaselineResult:
    total = len(suite.tests)
    best: Optional[Candidate] = None
    best_passes = -1
    user = (
        f"Module name: {module_name}\n\nSpecification:\n{description}\n\n"
        "Write the complete module."
    )
    for _ in range(k):
        resp = await ensemble.generate_with_context(
            system_message=_GEN_SYSTEM, messages=[{"role": "user", "content": user}]
        )
        code = parse_full_rewrite(resp or "", "verilog")
        if not code:
            continue
        cand = Candidate(modules={module_name: code})
        cand.vector = suite.run(cand, timeout=timeout)
        if cand.vector.total_passes > best_passes:
            best_passes = cand.vector.total_passes
            best = cand
        if best_passes == total:
            break

    if best is None:
        best = Candidate(modules={module_name: ""})
        best_passes = 0
    return BaselineResult(
        solved=best_passes == total and total > 0,
        total_passes=best_passes,
        total_tests=total,
        rounds_used=k,
        best=best,
        trajectory=[best_passes],
    )
