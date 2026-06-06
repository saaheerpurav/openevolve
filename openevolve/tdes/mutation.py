"""
Mutation operators for TDES with modular scope isolation (section 3.5).

A mutator proposes a new version of a *single* module given that module's
source, the CEGIS feedback for its failing tests (section 3.2), and the
negative exemplar memory for it (section 3.4). The controller is responsible
for reintegration, the no-regression acceptance check, and recording failures
back into negative memory.

Two implementations are provided:
  * ``LLMMutator``  — uses OpenEvolve's ``LLMEnsemble`` and parses diff or full
    rewrite responses via ``openevolve.utils.code_utils``.
  * ``ScriptedMutator`` — deterministic, offline, for examples and tests
    (no API key required).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol

from openevolve.tdes import prompts
from openevolve.tdes.types import Candidate, FeedbackTuple
from openevolve.utils.code_utils import apply_diff, extract_diffs, parse_full_rewrite

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"SUMMARY:\s*(.+)", re.IGNORECASE)


@dataclass
class MutationProposal:
    """A proposed new version of one module plus a short label of the approach."""

    module: str
    new_source: str
    approach: str


class Mutator(Protocol):
    async def propose(
        self,
        *,
        candidate: Candidate,
        module: str,
        feedback: List[FeedbackTuple],
        memory_text: str,
        generation: int,
    ) -> Optional[MutationProposal]: ...


def _extract_summary(response: str, default: str) -> str:
    m = _SUMMARY_RE.search(response)
    return m.group(1).strip() if m else default


class LLMMutator:
    """LLM-driven mutator over isolated modules."""

    def __init__(
        self, llm_ensemble, *, diff_based: bool = True, diff_pattern: Optional[str] = None
    ):
        self.llm = llm_ensemble
        self.diff_based = diff_based
        self.diff_pattern = diff_pattern or r"<<<<<<< SEARCH\n(.*?)=======\n(.*?)>>>>>>> REPLACE"

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
            diff_based=self.diff_based,
            generation=generation,
        )
        response = await self.llm.generate_with_context(
            system_message=prompts.SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": user}],
        )
        if not response:
            return None

        approach = _extract_summary(response, default=f"LLM edit to {module}")

        if self.diff_based:
            diffs = extract_diffs(response, self.diff_pattern)
            if not diffs:
                # Some models ignore the diff instruction and rewrite; try that.
                rewritten = parse_full_rewrite(response, "python")
                if rewritten:
                    return MutationProposal(module, rewritten, approach)
                logger.warning("LLMMutator: no diffs/rewrite found for module %s", module)
                return None
            new_source = apply_diff(source, response, self.diff_pattern)
            if new_source == source:
                return None
            return MutationProposal(module, new_source, approach)

        rewritten = parse_full_rewrite(response, "python")
        if not rewritten:
            logger.warning("LLMMutator: no full rewrite found for module %s", module)
            return None
        return MutationProposal(module, rewritten, approach)


# Signature for a scripted fix:
#   (module, source, feedback, memory_text) -> (new_source, approach) | None
ScriptedFix = Callable[[str, str, List[FeedbackTuple], str], Optional["tuple[str, str]"]]


class ScriptedMutator:
    """Deterministic mutator driven by a user-supplied fix function.

    Enables fully offline runs (examples, unit tests) without an LLM. The fix
    function receives the failing module's name, its current source, the CEGIS
    feedback, and the rendered negative-memory text (so it can avoid
    previously-failed approaches just as an LLM would), and returns
    ``(new_source, approach)`` or ``None`` to skip.
    """

    def __init__(self, fix: ScriptedFix):
        self._fix = fix

    async def propose(
        self,
        *,
        candidate: Candidate,
        module: str,
        feedback: List[FeedbackTuple],
        memory_text: str,
        generation: int,
    ) -> Optional[MutationProposal]:
        result = self._fix(module, candidate.modules[module], feedback, memory_text)
        if result is None:
            return None
        new_source, approach = result
        if new_source == candidate.modules[module]:
            return None
        return MutationProposal(module, new_source, approach)
