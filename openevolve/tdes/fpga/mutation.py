"""
Verilog mutation operator for TDES-FPGA.

``VerilogLLMMutator`` is the Verilog analog of ``openevolve.tdes.mutation.LLMMutator``:
same ``propose(...)`` protocol and same reuse of ``code_utils`` diff/rewrite
parsing, but with the Verilog system prompt + ``language="verilog"``. The
offline ``ScriptedMutator`` from the base package is reused unchanged for tests.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from openevolve.tdes.fpga import prompts
from openevolve.tdes.mutation import MutationProposal, ScriptedMutator  # noqa: F401 (re-export)
from openevolve.tdes.types import Candidate, FeedbackTuple
from openevolve.utils.code_utils import apply_diff, extract_diffs, parse_full_rewrite

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"SUMMARY:\s*(.+)", re.IGNORECASE)
_DEFAULT_DIFF = r"<<<<<<< SEARCH\n(.*?)=======\n(.*?)>>>>>>> REPLACE"


def _extract_summary(response: str, default: str) -> str:
    m = _SUMMARY_RE.search(response)
    return m.group(1).strip() if m else default


class VerilogLLMMutator:
    """LLM-driven mutator over isolated Verilog modules."""

    def __init__(
        self, llm_ensemble, *, diff_based: bool = True, diff_pattern: Optional[str] = None
    ):
        self.llm = llm_ensemble
        self.diff_based = diff_based
        self.diff_pattern = diff_pattern or _DEFAULT_DIFF

    async def propose(
        self,
        *,
        candidate: Candidate,
        module: str,
        feedback: List[FeedbackTuple],
        memory_text: str,
        generation: int,
        positive_memory_text: str = "",
    ) -> Optional[MutationProposal]:
        source = candidate.modules[module]
        user = prompts.build_user_prompt(
            module_name=module,
            module_source=source,
            feedback=feedback,
            memory_text=memory_text,
            diff_based=self.diff_based,
            generation=generation,
            positive_memory_text=positive_memory_text,
        )
        response = await self.llm.generate_with_context(
            system_message=prompts.SYSTEM_MESSAGE_VERILOG,
            messages=[{"role": "user", "content": user}],
        )
        if not response:
            return None

        approach = _extract_summary(response, default=f"LLM edit to {module}")

        if self.diff_based:
            diffs = extract_diffs(response, self.diff_pattern)
            if not diffs:
                rewritten = parse_full_rewrite(response, "verilog")
                if rewritten and rewritten.strip() and rewritten != response:
                    return MutationProposal(module, rewritten, approach)
                logger.warning("VerilogLLMMutator: no diffs/rewrite for module %s", module)
                return None
            new_source = apply_diff(source, response, self.diff_pattern)
            if new_source == source:
                return None
            return MutationProposal(module, new_source, approach)

        rewritten = parse_full_rewrite(response, "verilog")
        if not rewritten or rewritten == source:
            logger.warning("VerilogLLMMutator: no full rewrite for module %s", module)
            return None
        return MutationProposal(module, rewritten, approach)
