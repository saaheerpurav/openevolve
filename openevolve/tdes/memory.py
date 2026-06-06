"""
Negative exemplar memory for TDES (section 3.4).

A semantic tabu list: per module, a sliding window of recent *failed* approaches
stored as concise natural-language summaries. Appended to the mutation prompt so
the LLM can reason about which directions remain unexplored, rather than
re-proposing the same "obvious" fix every generation.

Unlike classical attribute-based tabu lists (Glover [6,7]), entries record the
*reason* a thing failed — a capability unique to LLM-based search.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List

from openevolve.tdes.types import NegativeMemoryEntry


class NegativeMemory:
    """Per-module sliding window of failed-approach summaries."""

    def __init__(self, window_size: int = 3):
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.window_size = window_size
        self._by_module: Dict[str, Deque[NegativeMemoryEntry]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

    def record(
        self,
        module: str,
        generation: int,
        approach: str,
        failure_mode: str,
        triggering_input: str = "",
    ) -> NegativeMemoryEntry:
        """Append a failure summary for `module`, evicting the oldest if full."""
        entry = NegativeMemoryEntry(
            generation=generation,
            approach=approach.strip(),
            failure_mode=failure_mode.strip(),
            triggering_input=str(triggering_input).strip(),
        )
        self._by_module[module].append(entry)
        return entry

    def entries(self, module: str) -> List[NegativeMemoryEntry]:
        return list(self._by_module.get(module, ()))

    def render(self, module: str) -> str:
        """Render the window for `module` in the paper's compact format (section 3.4)."""
        entries = self.entries(module)
        if not entries:
            return ""
        lines = [
            f"Module: {module}",
            f"Failed approaches (window: last {self.window_size} generations):",
        ]
        lines.extend(e.render() for e in entries)
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, List[dict]]:
        """Serializable view, used in the escalation package (section 3.6)."""
        return {
            module: [vars(e) for e in entries]
            for module, entries in self._by_module.items()
            if entries
        }
