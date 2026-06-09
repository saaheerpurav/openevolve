"""
TinyMAE: a minimal masked autoencoder over 16 CIFAR-10 patches.

This is the *fixed* evaluation infrastructure, not the evolved artifact. The
encoder genuinely cannot use masked-patch content: masked positions are
excluded as attention keys (``src_key_padding_mask``) and their encoder
outputs are discarded — the decoder sees a shared mask token there instead.
So the masking strategy fully controls what the encoder learns from.

~130K parameters total; a CPU forward+backward on a 128-image batch takes a
few milliseconds.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from openevolve.tdes.mae.config import MAEConfig


def _block(cfg: MAEConfig) -> nn.TransformerEncoderLayer:
    return nn.TransformerEncoderLayer(
        d_model=cfg.embed_dim,
        nhead=cfg.num_heads,
        dim_feedforward=cfg.embed_dim * cfg.mlp_ratio,
        dropout=0.0,
        activation="gelu",
        batch_first=True,
        norm_first=True,
    )


class TinyMAE(nn.Module):
    def __init__(self, cfg: MAEConfig | None = None):
        super().__init__()
        cfg = cfg or MAEConfig()
        self.cfg = cfg
        n, d = cfg.num_patches, cfg.embed_dim

        self.patch_embed = nn.Linear(cfg.patch_dim, d)
        self.pos_embed = nn.Parameter(torch.zeros(1, n, d))
        self.encoder = nn.TransformerEncoder(_block(cfg), num_layers=cfg.encoder_depth)

        self.mask_token = nn.Parameter(torch.zeros(1, 1, d))
        self.decoder_pos = nn.Parameter(torch.zeros(1, n, d))
        self.decoder = nn.TransformerEncoder(_block(cfg), num_layers=cfg.decoder_depth)
        self.head = nn.Linear(d, cfg.patch_dim)

        nn.init.trunc_normal_(self.pos_embed, std=0.02)
        nn.init.trunc_normal_(self.decoder_pos, std=0.02)
        nn.init.trunc_normal_(self.mask_token, std=0.02)

    def _encode(self, patches: torch.Tensor, mask: torch.Tensor | None) -> torch.Tensor:
        x = self.patch_embed(patches) + self.pos_embed
        # True in src_key_padding_mask = "not attendable": visible tokens can
        # never read masked-patch content. (Masked rows still produce outputs;
        # forward_pretrain overwrites them before the decoder.)
        return self.encoder(x, src_key_padding_mask=mask)

    def forward_pretrain(self, patches: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """Returns the mean MSE over masked patches. ``mask``: (B, N) bool, True=masked.

        Requires every sample to have >=1 visible and >=1 masked patch
        (``trainer.sanitize_mask`` enforces this).
        """
        enc = self._encode(patches, mask)
        dec_in = torch.where(mask.unsqueeze(-1), self.mask_token.to(enc.dtype), enc)
        dec = self.decoder(dec_in + self.decoder_pos)
        pred = self.head(dec)
        return ((pred - patches) ** 2).mean(dim=-1)[mask].mean()

    @torch.no_grad()
    def encode_features(self, patches: torch.Tensor) -> torch.Tensor:
        """Frozen-encoder features for the linear probe: mean-pooled, no mask."""
        return self._encode(patches, mask=None).mean(dim=1)
