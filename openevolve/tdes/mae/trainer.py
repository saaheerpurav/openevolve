"""
Training loops: MAE pretraining with a pluggable mask function, and the
frozen-encoder linear probe that produces the system-test metric.

Everything is seeded (`torch.manual_seed` + seeded shuffles) so a given
(mask source, seed) pair yields a reproducible test vector — required for
TDES's no-regression acceptance checks to be meaningful.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import torch

from openevolve.tdes.mae import masking
from openevolve.tdes.mae.config import MAEConfig
from openevolve.tdes.mae.data import load_subsets
from openevolve.tdes.mae.model import TinyMAE

MaskFn = Callable[[int, int, float, int, str], torch.Tensor]


def sanitize_mask(mask: torch.Tensor) -> torch.Tensor:
    """Guarantee >=1 visible and >=1 masked patch per sample.

    Degenerate rows would NaN the attention/loss; the unit tier already rejects
    batch-level degeneracy, but a per-row slip in an otherwise-valid strategy
    should not crash training.
    """
    mask = mask.clone()
    n = mask.shape[1]
    all_masked = mask.all(dim=1)
    if all_masked.any():
        mask[all_masked, torch.randint(n, (int(all_masked.sum()),))] = False
    none_masked = ~mask.any(dim=1)
    if none_masked.any():
        mask[none_masked, torch.randint(n, (int(none_masked.sum()),))] = True
    return mask


def train_mae(
    model: TinyMAE,
    mask_fn: Optional[MaskFn],
    epochs: int,
    cfg: MAEConfig,
    data: Optional[Dict[str, torch.Tensor]] = None,
    seed: int = 0,
) -> float:
    """Pretrain; returns the mean reconstruction loss over the final epoch."""
    torch.manual_seed(seed)
    mask_fn = mask_fn or masking.generate_mask
    data = data or load_subsets(cfg)
    patches = data["pretrain_patches"].to(cfg.device)
    model = model.to(cfg.device).train()
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)

    n = patches.shape[0]
    final_epoch_loss = float("inf")
    for epoch in range(epochs):
        perm = torch.randperm(n)
        total, batches = 0.0, 0
        for start in range(0, n, cfg.batch_size):
            batch = patches[perm[start : start + cfg.batch_size]]
            mask = mask_fn(batch.shape[0], cfg.num_patches, cfg.mask_ratio, epoch, cfg.device)
            mask = sanitize_mask(mask.to(device=cfg.device, dtype=torch.bool))
            loss = model.forward_pretrain(batch, mask)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.detach())
            batches += 1
        final_epoch_loss = total / batches
    return final_epoch_loss


def linear_probe(
    model: TinyMAE,
    cfg: MAEConfig,
    data: Optional[Dict[str, torch.Tensor]] = None,
    seed: int = 0,
) -> float:
    """Freeze the encoder, fit a linear head on train features, return test accuracy."""
    torch.manual_seed(seed)
    data = data or load_subsets(cfg)
    model = model.to(cfg.device).eval()

    def features(patches: torch.Tensor) -> torch.Tensor:
        out = []
        for start in range(0, patches.shape[0], 512):
            out.append(model.encode_features(patches[start : start + 512].to(cfg.device)))
        return torch.cat(out)

    x_train = features(data["pretrain_patches"])
    y_train = data["pretrain_labels"].to(cfg.device)
    x_test = features(data["test_patches"])
    y_test = data["test_labels"].to(cfg.device)

    head = torch.nn.Linear(cfg.embed_dim, 10).to(cfg.device)
    opt = torch.optim.Adam(head.parameters(), lr=cfg.probe_lr)
    n = x_train.shape[0]
    for _ in range(cfg.probe_epochs):
        perm = torch.randperm(n)
        for start in range(0, n, 256):
            idx = perm[start : start + 256]
            loss = torch.nn.functional.cross_entropy(head(x_train[idx]), y_train[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()

    with torch.no_grad():
        acc = (head(x_test).argmax(dim=1) == y_test).float().mean()
    return float(acc)


def pretrain_and_probe(
    mask_source: str, epochs: int, cfg: MAEConfig, seed: int = 0
) -> Dict[str, float]:
    """One full (pretrain, probe) evaluation of a mask-module source string."""
    mask_fn = masking.compile_mask_fn(mask_source)
    data = load_subsets(cfg)
    torch.manual_seed(seed)
    model = TinyMAE(cfg)
    loss = train_mae(model, mask_fn, epochs, cfg, data, seed=seed)
    acc = linear_probe(model, cfg, data, seed=seed)
    return {"recon_loss": loss, "probe_acc": acc}
