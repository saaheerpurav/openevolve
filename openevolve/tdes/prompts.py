"""
Prompt construction for TDES LLM mutation.

Assembles the modular-scope-isolation prompt (section 3.5): a single module's
source, the CEGIS feedback tuples for its failing tests (section 3.2), and the
rendered negative exemplar memory (section 3.4). Test source is never included.
"""

from __future__ import annotations

from typing import List

from openevolve.tdes.types import FeedbackTuple

SYSTEM_MESSAGE = """You are an expert software engineer operating inside a \
Test-Driven Evolutionary Synthesis (TDES) loop. You improve ONE module of a \
codebase at a time so that it passes more of a hierarchical test suite (unit, \
integration, system tests).

You are given, for each currently failing test: a natural-language description \
of what it checks, the concrete input it failed on, and the error message. You \
are NOT given the test source code — do not try to guess or pattern-match \
against test internals. Fix the underlying behavior the tests describe.

You may also be shown a list of previously attempted approaches that FAILED, \
with the reason each failed. Do not repeat those approaches; reason about which \
directions remain unexplored.

Make the smallest change that addresses the failing tests without breaking \
behavior the module already gets right."""


DIFF_INSTRUCTIONS = """Respond with one or more SEARCH/REPLACE diff blocks that \
edit the module. Use exactly this format:

<<<<<<< SEARCH
# exact existing lines to find
=======
# replacement lines
>>>>>>> REPLACE

Then, on a final line, give a one-line summary of your approach prefixed with \
"SUMMARY:"."""


REWRITE_INSTRUCTIONS = """Respond with the complete, rewritten module inside a \
single fenced code block:

```python
# full module source here
```

Then, on a final line, give a one-line summary of your approach prefixed with \
"SUMMARY:"."""


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
) -> str:
    """Build the user message for mutating one module."""
    instructions = DIFF_INSTRUCTIONS if diff_based else REWRITE_INSTRUCTIONS
    memory_block = (
        f"\n# Previously attempted approaches that FAILED (avoid these)\n{memory_text}\n"
        if memory_text
        else ""
    )
    return f"""# Generation {generation}

# Module to improve: `{module_name}`

```python
{module_source}
```

# Failing tests (description, failing input, error) — test source withheld
{render_feedback(feedback)}
{memory_block}
# Task
Edit the `{module_name}` module so it passes the failing tests above while \
keeping the tests it already passes green.

{instructions}
"""
