"""
Semantic (LLM-mediated) crossover fallback for TDES-FPGA.

Standard complementary-coverage crossover grafts entire modules from the donor
parent into the recipient. On complex Level 3-4 designs the useful insight in a
module is often a *technique* (a carry-lookahead scheme, a specific FSM state
encoding) rather than the module as a whole; grafting the full module brings the
donor's bugs along with its insight and the strict-superset gate rejects the
child.

This module implements a fallback: when structural grafting fails the
regression check, the LLM is asked to *merge* the two implementations
semantically — it sees both source texts and their per-module pass/fail
breakdowns, and is asked to combine the working approaches from each without
access to the test source. The merged candidate is still accepted only if it
is a strict superset of the higher-ranked parent (same gate as structural graft)
so correctness is never sacrificed.

This is an LLM-in-the-loop crossover operator; it costs one additional LLM
call per rejected structural graft.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from openevolve.tdes.crossover import CrossoverOutcome
from openevolve.tdes.fpga import prompts as verilog_prompts
from openevolve.tdes.fpga.verilog_suite import VerilogTestSuite
from openevolve.tdes.types import Candidate, TestVector
from openevolve.utils.code_utils import parse_full_rewrite

logger = logging.getLogger(__name__)

_SEMANTIC_SYSTEM = (
    "You are an expert digital design engineer. "
    "You are shown two implementations of the same Verilog module and a description "
    "of which tests each passes and fails. "
    "Your task is to write a MERGED implementation that passes ALL tests that either "
    "implementation passes. "
    "You are NOT given the test source — reason about the underlying RTL behavior "
    "the test descriptions and pass/fail patterns imply. "
    "Produce synthesizable Verilog only. Respond with the merged module in a single "
    "```verilog code block, followed by a line beginning with 'SUMMARY:' giving a "
    "one-line description of your merging approach."
)


def _fmt_tests(vec: TestVector, module: str) -> str:
    """Format per-module test outcomes for the merge prompt."""
    passing = [
        f"  ✓ {r.description}"
        for r in vec.results.values()
        if r.passed and r.module == module
    ]
    failing = [
        f"  ✗ {r.description}"
        for r in vec.results.values()
        if not r.passed and r.module == module
    ]
    lines: List[str] = []
    if passing:
        lines.append("Passes:")
        lines.extend(passing)
    if failing:
        lines.append("Fails:")
        lines.extend(failing)
    return "\n".join(lines) if lines else "(no test results for this module)"


def _build_merge_prompt(
    module: str,
    src_a: str,
    src_b: str,
    vec_a: TestVector,
    vec_b: TestVector,
) -> str:
    """Build the LLM prompt for semantic merging of two module implementations."""
    return f"""# Semantic Crossover: Merge two implementations of `{module}`

## Implementation A

Test results for `{module}`:
{_fmt_tests(vec_a, module)}

```verilog
{src_a}
```

## Implementation B

Test results for `{module}`:
{_fmt_tests(vec_b, module)}

```verilog
{src_b}
```

## Task

Implementation A passes tests that B fails; Implementation B passes tests that A fails.
Write a merged implementation of `{module}` that combines the working approaches from BOTH.

Do NOT access test source code — reason from the descriptions and pass/fail patterns above.
The merged module must be synthesizable and must not regress any test that A already passes.

Respond with the complete merged module in a single ```verilog code block, then:
SUMMARY: <one-line description of your merging approach>
"""


import re as _re
_SUMMARY_RE = _re.compile(r"SUMMARY:\s*(.+)", _re.IGNORECASE)


async def semantic_merge(
    higher: Candidate,
    lower: Candidate,
    module: str,
    suite: VerilogTestSuite,
    ensemble,
    *,
    generation: int,
    sandbox: bool = True,
    timeout: int = 120,
) -> CrossoverOutcome:
    """Attempt LLM-mediated semantic merge of ``module`` from two parents.

    Accepts only when the merged child strictly supersedes the higher-ranked
    parent (same gate as structural complementary-coverage crossover).

    Args:
        higher:     Better-ranked parent (its passes must not regress).
        lower:      Lower-ranked parent (complementary-coverage donor).
        module:     Module to semantically merge.
        suite:      VerilogTestSuite for evaluation.
        ensemble:   LLMEnsemble (or _CountingEnsemble wrapper).
        generation: Generation tag for the produced child.
        sandbox:    Forward to suite runner.
        timeout:    Forward to suite runner.

    Returns:
        CrossoverOutcome with ``attempted=True`` always; ``accepted=True`` only
        when the merged child is a strict superset of higher's pass set.
    """
    if higher.vector is None or lower.vector is None:
        return CrossoverOutcome(
            False, False, higher.id, lower.id, [], [module],
            reason="missing test vectors",
        )

    src_a = higher.modules.get(module, "")
    src_b = lower.modules.get(module, "")

    if src_a == src_b:
        return CrossoverOutcome(
            False, False, higher.id, lower.id, [], [module],
            reason="module sources identical, no merge possible",
        )

    comp_tests = sorted(lower.vector.complementary_to(higher.vector))
    prompt = _build_merge_prompt(module, src_a, src_b, higher.vector, lower.vector)

    try:
        response = await ensemble.generate_with_context(
            system_message=_SEMANTIC_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.warning("semantic_merge: LLM call failed for module %s: %s", module, e)
        return CrossoverOutcome(
            True, False, higher.id, lower.id, comp_tests, [module],
            reason=f"LLM error: {e}",
        )

    if not response:
        return CrossoverOutcome(
            True, False, higher.id, lower.id, comp_tests, [module],
            reason="empty LLM response",
        )

    merged_src = parse_full_rewrite(response, "verilog")
    if not merged_src or not merged_src.strip():
        logger.debug("semantic_merge: no verilog block in response for module %s", module)
        return CrossoverOutcome(
            True, False, higher.id, lower.id, comp_tests, [module],
            reason="no verilog block in LLM response",
        )

    # Extract summary for logging
    m = _SUMMARY_RE.search(response)
    approach = m.group(1).strip() if m else f"semantic merge of {module}"

    # Build and evaluate merged child
    child = higher.clone(
        generation=generation,
        parent_id=higher.id,
        metadata={
            "origin": "semantic_crossover",
            "donor_id": lower.id,
            "merged_module": module,
            "approach": approach,
        },
    )
    child.modules[module] = merged_src
    child.vector = suite.run(child, sandbox=sandbox, timeout=timeout)

    if child.vector.is_strict_superset_of(higher.vector):
        lift = child.vector.total_passes - higher.vector.total_passes
        logger.info(
            "semantic_merge accepted: %s + %s[%s] -> %s (+%d passes)",
            higher.id, lower.id, module, child.id, lift,
        )
        return CrossoverOutcome(
            True, True, higher.id, lower.id, comp_tests, [module], child,
            reason=f"semantic merge accepted (+{lift})",
        )

    logger.debug(
        "semantic_merge rejected: %s + %s[%s] (no net gain or regression)",
        higher.id, lower.id, module,
    )
    return CrossoverOutcome(
        True, False, higher.id, lower.id, comp_tests, [module], None,
        reason="semantic merge: no net gain after merge",
    )
