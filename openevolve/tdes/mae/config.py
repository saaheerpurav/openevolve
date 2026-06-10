"""
All TDES-MAE hyperparameters in one place.

``MAEConfig`` covers the *fixed evaluation infrastructure* (model, training,
data subsets, tier thresholds). The evolutionary parameters live in the usual
``TDESConfig`` (loaded from ``configs/*.yaml``); the two are deliberately
separate so the evaluator can be used standalone.

The tier thresholds (``integration_loss_max``, ``system_acc_rungs``) are
calibrated against the *baseline random mask* — see ``calibrate.py`` and the
numbers recorded in RESULTS.md. The accuracy ladder turns the scalar probe
accuracy into multiple SYSTEM-level tests so hierarchical selection sees a
gradient ("higher accuracy" = "more system tests passed") without touching
base selection code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Tuple


def _default_data_dir() -> str:
    # Cached tensors + the torchvision download live next to this package
    # (gitignored); results go to ./tdes_mae_results by default.
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@dataclass
class MAEConfig:
    # -- model -------------------------------------------------------------
    img_size: int = 32
    patch_size: int = 8  # -> 4x4 grid of 16 patches, 192 dims each
    embed_dim: int = 64
    encoder_depth: int = 3
    decoder_depth: int = 1
    num_heads: int = 4
    mlp_ratio: int = 2
    mask_ratio: float = 0.75

    # -- training ----------------------------------------------------------
    batch_size: int = 128
    integration_epochs: int = 10
    system_epochs: int = 30
    probe_epochs: int = 30  # on precomputed frozen features: cheap
    lr: float = 1.5e-3
    weight_decay: float = 0.05
    probe_lr: float = 1e-2
    device: str = "cpu"  # safe default; set "cuda" if available

    # -- data subsets (CPU budget; full CIFAR-10 is unnecessary at 75K params)
    n_pretrain: int = 5000
    n_probe_test: int = 2000
    data_dir: str = field(default_factory=_default_data_dir)

    # -- evaluation determinism / tiers -------------------------------------
    eval_seed: int = 1234  # fixed per-eval seed: same source -> same vector
    unit_timeout_s: float = 30.0  # tier-1 only (catches hangs in the mask fn)
    full_timeout_s: float = 600.0  # tiers 1-3
    integration_loss_max: float = 0.85  # baseline reaches ~0.65 at 10 epochs; gate = divergence
    # SYSTEM accuracy ladder: floor (sanity) then rungs around/above the measured
    # baseline (random mask, 30 epochs: 0.360 +/- 0.007 over 3 seeds; random
    # encoder: 0.292).
    # Rung spacing lesson (first run): trials reached 0.369 with the next rung
    # at 0.37 — real progress was invisible to selection (equal-rung candidates
    # are discarded by the no-regression filter), so the run "stagnated" while
    # improving. Rungs near the baseline must be finer than the gains a single
    # mutation can plausibly make.
    system_acc_rungs: Tuple[float, ...] = (
        0.20,  # above-random sanity floor (CIFAR-10 random = 10%)
        0.30,
        0.34,
        0.355,  # last rung the baseline (0.360-0.362 @ eval seed) passes
        0.365,
        0.375,
        0.385,
        0.40,
        0.42,
        0.44,
        0.46,
        0.48,
    )

    @property
    def num_patches(self) -> int:
        return (self.img_size // self.patch_size) ** 2

    @property
    def patch_dim(self) -> int:
        return 3 * self.patch_size * self.patch_size

    @property
    def grid(self) -> int:
        return self.img_size // self.patch_size


DEFAULT = MAEConfig()
