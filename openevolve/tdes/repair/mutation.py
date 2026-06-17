"""
LLM mutator for TDES-Repair with robust full-rewrite extraction.

The base ``LLMMutator`` (via ``parse_full_rewrite``) takes the FIRST fenced
code block in the response; models often precede the rewritten module with an
explanatory fragment ("the bug is here: ```python ...```"), which then replaces
the whole module and fails to even parse. This mutator considers every fenced
block, keeps only those that compile, and picks the one that looks most like a
full module (most ``def``s, then longest). Used by every condition — the
evolutionary controllers and the single-shot baseline — so extraction quality
is identical across the comparison.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from openevolve.tdes import prompts
from openevolve.tdes.mutation import LLMMutator, MutationProposal, _extract_summary
from openevolve.tdes.types import Candidate, FeedbackTuple

logger = logging.getLogger(__name__)

_CODE_BLOCK_RE = re.compile(r"```(?:python)?[ \t]*\n(.*?)```", re.DOTALL)


def extract_module_source(response: str) -> Optional[str]:
    """Best compilable fenced code block: most top-level defs, then longest."""
    candidates: List[str] = []
    for block in _CODE_BLOCK_RE.findall(response):
        source = block.strip()
        if not source:
            continue
        try:
            compile(source, "<rewrite>", "exec")
        except SyntaxError:
            continue
        candidates.append(source)
    if not candidates:
        return None
    return max(candidates, key=lambda s: (len(re.findall(r"^def ", s, re.M)), len(s)))


class RepairLLMMutator(LLMMutator):
    """Full-rewrite LLM mutator with compile-checked block extraction."""

    def __init__(self, llm_ensemble):
        super().__init__(llm_ensemble, diff_based=False)

    async def propose(
        self,
        *,
        candidate: Candidate,
        module: str,
        feedback: List[FeedbackTuple],
        memory_text: str,
        generation: int,
    ) -> Optional[MutationProposal]:
        source = candidate.modules[module]
        user = prompts.build_user_prompt(
            module_name=module,
            module_source=source,
            feedback=feedback,
            memory_text=memory_text,
            diff_based=False,
            generation=generation,
        )
        response = await self.llm.generate_with_context(
            system_message=prompts.SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": user}],
        )
        if not response:
            return None
        rewritten = extract_module_source(response)
        if not rewritten:
            logger.warning("RepairLLMMutator: no compilable rewrite for module %s", module)
            return None
        if rewritten == source:
            return None
        approach = _extract_summary(response, default=f"LLM rewrite of {module}")
        return MutationProposal(module, rewritten, approach)
