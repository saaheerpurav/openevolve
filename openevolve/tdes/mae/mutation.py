"""
LLM mutator for the ``masking`` module.

Full-rewrite based (the function is ~20 lines; diffs buy nothing) and driven
by the domain prompt in ``prompts.py``. Mirrors the base ``LLMMutator``
contract so the unmodified TDES controller can drive it.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from openevolve.tdes.mae import prompts
from openevolve.tdes.mutation import MutationProposal
from openevolve.tdes.types import Candidate, FeedbackTuple
from openevolve.utils.code_utils import parse_full_rewrite

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"SUMMARY:\s*(.+)", re.IGNORECASE)


class MaskLLMMutator:
    def __init__(self, llm_ensemble):
        self.llm = llm_ensemble

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
        user = prompts.build_user_prompt(source, feedback, memory_text)
        response = await self.llm.generate_with_context(
            system_message=prompts.SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": user}],
        )
        if not response:
            return None
        rewritten = parse_full_rewrite(response, "python")
        if not rewritten or "def generate_mask" not in rewritten:
            logger.warning("MaskLLMMutator: no usable rewrite in response")
            return None
        m = _SUMMARY_RE.search(response)
        approach = m.group(1).strip() if m else "unlabeled mask strategy"
        if rewritten.strip() == source.strip():
            return None
        return MutationProposal(module=module, new_source=rewritten, approach=approach)
