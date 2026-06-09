"""
The evolved artifact: ``generate_mask()``.

TDES evolves the *source text* below (a candidate's single module
``"masking"``). The baseline is plain per-sample random masking — the standard
MAE strategy and the control arm of every comparison. The module-level
``generate_mask`` here is the compiled baseline, importable for standalone
training runs.
"""

from __future__ import annotations

import torch  # noqa: F401  (the exec namespace below provides it to candidates)

BASELINE_SOURCE = '''\
import torch


def generate_mask(batch_size, num_patches, mask_ratio, epoch, device):
    """Uniform random masking: independently mask `mask_ratio` of patches per sample."""
    num_mask = int(mask_ratio * num_patches)
    mask = torch.zeros(batch_size, num_patches, dtype=torch.bool, device=device)
    for i in range(batch_size):
        indices = torch.randperm(num_patches, device=device)[:num_mask]
        mask[i, indices] = True
    return mask
'''


def compile_mask_fn(source: str):
    """Compile a candidate ``masking`` module; returns its ``generate_mask``.

    Candidates get ``torch`` and ``math`` (the declared dependency surface).
    Raises on syntax errors or a missing/uncallable ``generate_mask``.
    """
    import math

    namespace = {"torch": torch, "math": math}
    exec(compile(source, "<masking>", "exec"), namespace)
    fn = namespace.get("generate_mask")
    if not callable(fn):
        raise ValueError("module does not define a callable generate_mask()")
    return fn


generate_mask = compile_mask_fn(BASELINE_SOURCE)
