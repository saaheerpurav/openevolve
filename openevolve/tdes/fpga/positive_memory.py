"""
Positive exemplar memory for TDES-FPGA enhanced controller.

Symmetric counterpart to NegativeMemory: records *successful* mutation
approaches per module so subsequent mutation calls can build on what worked
elsewhere in the population (population-wide insight broadcast).

When candidate 3 discovers a carry-lookahead technique that newly passes
two unit tests on the ``adder_4bit`` module, candidates 1, 2, and 4 receive
that signal in their next mutation prompt — without waiting for crossover to
fire. This is cheap (one prompt block), additive, and compatible with the
existing CEGIS negative-memory mechanism.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List


@dataclass
class PositiveMemoryEntry:
    """One recorded success in the per-module positive memory."""

    generation: int
    approach: str
    new_passes: List[str] = field(default_factory=list)

    def render(self) -> str:
        passes_str = ", ".join(self.new_passes) if self.new_passes else "some tests"
        return f"- Gen {self.generation}: {self.approach} → newly passed: {passes_str}"


class PositiveMemory:
    """Per-module sliding window of successful-approach summaries.

    Analogous to ``NegativeMemory`` but records approaches that *gained* new
    test passes.  Rendered as a prompt block injected before the Task section,
    after the negative-memory block.
    """

    def __init__(self, window_size: int = 3):
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.window_size = window_size
        self._by_module: Dict[str, Deque[PositiveMemoryEntry]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

    def record(
        self,
        module: str,
        generation: int,
        approach: str,
        new_passes: List[str],
    ) -> PositiveMemoryEntry:
        """Append a success summary for ``module``, evicting the oldest if full."""
        entry = PositiveMemoryEntry(
            generation=generation,
            approach=approach.strip(),
            new_passes=list(new_passes),
        )
        self._by_module[module].append(entry)
        return entry

    def entries(self, module: str) -> List[PositiveMemoryEntry]:
        return list(self._by_module.get(module, ()))

    def render(self, module: str) -> str:
        """Render the window for ``module`` as a prompt block."""
        entries = self.entries(module)
        if not entries:
            return ""
        lines = [
            f"Module: {module}",
            f"Approaches that WORKED (last {self.window_size} successes — consider these directions):",
        ]
        lines.extend(e.render() for e in entries)
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, List[dict]]:
        return {
            module: [
                {"generation": e.generation, "approach": e.approach, "new_passes": e.new_passes}
                for e in entries
            ]
            for module, entries in self._by_module.items()
            if entries
        }
