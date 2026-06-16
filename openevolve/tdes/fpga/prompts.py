"""
Verilog-specific mutation prompts for TDES-FPGA.

Mirrors the structure of ``openevolve.tdes.prompts`` but targets synthesizable
Verilog RTL. The testbench source is never included — only the description,
failing input, and error from each :class:`~openevolve.tdes.types.FeedbackTuple`
(section 3.2 CEGIS constraint).
"""

from __future__ import annotations

from typing import List

from openevolve.tdes.types import FeedbackTuple

SYSTEM_MESSAGE_VERILOG = """You are an expert digital design engineer operating \
inside a Test-Driven Evolutionary Synthesis (TDES) loop. You improve ONE Verilog \
module at a time so it passes more of a hierarchical test suite: unit tests per \
module, integration tests across modules, and system-level synthesis constraints \
(resource/timing budgets).

For each failing test you are given a description of what it checks, the concrete \
input stimulus that failed, and the error (expected vs actual). You are NOT given \
the testbench source — do not guess at testbench internals. Fix the underlying \
RTL behavior the description and counterexample imply.

You may also be shown previously attempted approaches that FAILED, with the \
reason each failed. Do not repeat them; reason about what remains unexplored.

Constraints:
- Produce SYNTHESIZABLE Verilog. No `$display`, `$finish`, `initial` blocks, or \
delays (`#`) in design code — those belong only in testbenches.
- Keep the module name and port list exactly as given unless a failing test \
implies they are wrong.
- Make the smallest change that fixes the failing tests without breaking passing \
ones."""


DIFF_INSTRUCTIONS = """Respond with one or more SEARCH/REPLACE diff blocks:

<<<<<<< SEARCH
// exact existing Verilog lines
=======
// replacement Verilog lines
>>>>>>> REPLACE

Then a final line beginning with "SUMMARY:" giving a one-line description of your \
approach."""


REWRITE_INSTRUCTIONS = """Respond with the complete rewritten module in a single \
fenced block:

```verilog
// full module source
```

Then a final line beginning with "SUMMARY:" giving a one-line description of your \
approach."""


def render_feedback(feedback: List[FeedbackTuple]) -> str:
    if not feedback:
        return "(no failing tests for this module)"
    return "\n".join(f.render() for f in feedback)


def build_user_prompt(
    *,
    module_name: str,
    module_source: str,
    feedback: List[FeedbackTuple],
    memory_text: str,
    diff_based: bool,
    generation: int,
    positive_memory_text: str = "",
) -> str:
    instructions = DIFF_INSTRUCTIONS if diff_based else REWRITE_INSTRUCTIONS
    memory_block = (
        f"\n# Previously attempted approaches that FAILED (avoid these)\n{memory_text}\n"
        if memory_text
        else ""
    )
    positive_block = (
        f"\n# Approaches that WORKED elsewhere in the population (consider these)\n{positive_memory_text}\n"
        if positive_memory_text
        else ""
    )
    return f"""# Generation {generation}

# Verilog module to improve: `{module_name}`

```verilog
{module_source}
```

# Failing tests (description, failing input, error) — testbench source withheld
{render_feedback(feedback)}
{memory_block}{positive_block}
# Task
Edit the `{module_name}` module so it passes the failing tests above while \
keeping the tests it already passes green. Produce synthesizable RTL.

{instructions}
"""
