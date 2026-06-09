"""
CIFAR-10 subsets, cached as pre-patchified tensors.

The first call downloads CIFAR-10 via torchvision (~170MB) into
``cfg.data_dir`` and writes a single ``subsets.pt`` holding normalized,
already-patchified float32 tensors:

    pretrain_patches  (n_pretrain, 16, 192)   + pretrain_labels
    test_patches      (n_probe_test, 16, 192) + test_labels

Patchifying once at cache time removes all per-batch unfold/transform cost,
which matters on CPU. Subset selection is class-balanced and seeded, so every
evaluation sees the identical data.
"""

from __future__ import annotations

import os
from typing import Dict

import torch

from openevolve.tdes.mae.config import MAEConfig

_CIFAR_MEAN = torch.tensor([0.4914, 0.4822, 0.4465]).view(1, 3, 1, 1)
_CIFAR_STD = torch.tensor([0.2470, 0.2435, 0.2616]).view(1, 3, 1, 1)

_cache: Dict[str, torch.Tensor] = {}


def patchify(images: torch.Tensor, patch_size: int) -> torch.Tensor:
    """(B, 3, H, W) -> (B, num_patches, 3*p*p), row-major patch order."""
    b, c, h, w = images.shape
    p = patch_size
    x = images.unfold(2, p, p).unfold(3, p, p)  # (B, 3, gh, gw, p, p)
    x = x.permute(0, 2, 3, 1, 4, 5).reshape(b, (h // p) * (w // p), c * p * p)
    return x.contiguous()


def _balanced_indices(labels: torch.Tensor, n_total: int, generator: torch.Generator):
    per_class = n_total // 10
    chosen = []
    for cls in range(10):
        idx = (labels == cls).nonzero(as_tuple=True)[0]
        perm = idx[torch.randperm(len(idx), generator=generator)]
        chosen.append(perm[:per_class])
    return torch.cat(chosen)


def _build_subsets(cfg: MAEConfig) -> Dict[str, torch.Tensor]:
    from torchvision.datasets import CIFAR10

    os.makedirs(cfg.data_dir, exist_ok=True)
    train = CIFAR10(cfg.data_dir, train=True, download=True)
    test = CIFAR10(cfg.data_dir, train=False, download=True)

    def to_patches(ds, indices):
        imgs = torch.from_numpy(ds.data[indices.numpy()]).permute(0, 3, 1, 2).float() / 255.0
        imgs = (imgs - _CIFAR_MEAN) / _CIFAR_STD
        labels = torch.tensor(ds.targets)[indices]
        return patchify(imgs, cfg.patch_size), labels

    g = torch.Generator().manual_seed(0)  # subset choice is part of the benchmark
    train_idx = _balanced_indices(torch.tensor(train.targets), cfg.n_pretrain, g)
    test_idx = _balanced_indices(torch.tensor(test.targets), cfg.n_probe_test, g)

    pre_p, pre_l = to_patches(train, train_idx)
    test_p, test_l = to_patches(test, test_idx)
    return {
        "pretrain_patches": pre_p,
        "pretrain_labels": pre_l,
        "test_patches": test_p,
        "test_labels": test_l,
    }


def load_subsets(cfg: MAEConfig) -> Dict[str, torch.Tensor]:
    """Load (building + caching on first use) the patchified subsets."""
    cache_path = os.path.join(
        cfg.data_dir, f"subsets_{cfg.n_pretrain}_{cfg.n_probe_test}_p{cfg.patch_size}.pt"
    )
    if _cache.get("path") == cache_path:
        return _cache["data"]
    if os.path.exists(cache_path):
        data = torch.load(cache_path, weights_only=True)
    else:
        data = _build_subsets(cfg)
        torch.save(data, cache_path)
    _cache["path"] = cache_path
    _cache["data"] = data
    return data
