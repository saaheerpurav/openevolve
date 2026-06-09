"""
LLM prompts for evolving ``generate_mask()``.

Domain-specific where the base ``tdes/prompts.py`` is generic: the prompt
teaches the 4x4 patch-grid geometry and the MAE training context, because
spatially-structured strategies (blocks, rows, correlated masks, curricula)
are exactly the search space we want the model to explore. The CEGIS feedback
and negative-memory sections follow the base layer's conventions, including
the ``SUMMARY:`` line used to label approaches in the semantic tabu list.
"""

from __future__ import annotations

from typing import List

from openevolve.tdes.types import FeedbackTuple

SYSTEM_MESSAGE = """\
You are an expert in self-supervised learning and masking strategies for
vision transformers. You are evolving the `generate_mask()` function for a
Masked Autoencoder trained on CIFAR-10 (32x32 images split into a 4x4 grid of
8x8 patches = 16 patches per image).

The mask decides which patches the encoder CANNOT see during pretraining.
A good masking strategy makes reconstruction challenging but not impossible,
forcing the encoder to learn representations that transfer to classification
(the final metric is frozen-encoder linear probe accuracy on CIFAR-10).

The 16 patches are laid out row-major in a 4x4 grid:
    [ 0  1  2  3 ]
    [ 4  5  6  7 ]
    [ 8  9 10 11 ]
    [12 13 14 15 ]
Adjacent indices in a row, and indices 4 apart across rows, are spatial
neighbors. Strategies worth considering include (but are not limited to):
contiguous block masking, row/column masking, spatially-correlated masking,
epoch-dependent curricula (the `epoch` argument runs 0..29), and mixtures of
strategies. Be creative; incremental tweaks rarely beat the random baseline.

Hard requirements:
1. Keep the exact signature:
   generate_mask(batch_size, num_patches, mask_ratio, epoch, device) -> torch.BoolTensor
2. Return shape (batch_size, num_patches), dtype torch.bool, True = masked.
3. Mask approximately mask_ratio of the patches (within +/-0.10) at every epoch.
4. Different calls must return different masks (stochastic), and no two images
   in a batch should be forced to share one fixed mask pattern forever.
5. Use only `torch` and `math` (already imported). No other imports, no I/O,
   no randomness seeding, and keep it fast (it runs every training step).
"""

USER_TEMPLATE = """\
Current generate_mask() implementation (module `masking`):
```python
{source}
```

Evaluation results for this implementation:
{results}
{memory_section}
Write an improved generate_mask() function targeting higher linear probe
accuracy. First write one line:
SUMMARY: <a short description of the strategy you are trying>
then the complete replacement module in a single ```python fenced block
(imports included). No other text.
"""


def render_feedback(feedback: List[FeedbackTuple]) -> str:
    if not feedback:
        return "All tests passed at the current rung; aim for a higher probe accuracy."
    return "\n".join(f.render() for f in feedback)


def build_user_prompt(source: str, feedback: List[FeedbackTuple], memory_text: str) -> str:
    memory_section = (
        f"\nPrevious failed approaches (do NOT repeat these):\n{memory_text}\n"
        if memory_text
        else ""
    )
    return USER_TEMPLATE.format(
        source=source, results=render_feedback(feedback), memory_section=memory_section
    )
