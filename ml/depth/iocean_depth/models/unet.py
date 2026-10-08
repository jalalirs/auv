"""A U-Net from the band features to depth and the log of its variance.

Four levels (base, 2x, 4x, 8x channels), GroupNorm and SiLU, a 128-cell chip
down to 16 and back. Depth comes out through softplus, never negative; the log
variance is clamped to a sane range so a confident model cannot divide by zero.
"""

from __future__ import annotations

import torch
from torch import nn


def _block(a: int, b: int) -> nn.Sequential:
    return nn.Sequential(nn.Conv2d(a, b, 3, padding=1), nn.GroupNorm(8, b), nn.SiLU(),
                         nn.Conv2d(b, b, 3, padding=1), nn.GroupNorm(8, b), nn.SiLU())


class UNet(nn.Module):
    def __init__(self, channels: int, base: int = 32):
        super().__init__()
        w = [base, base * 2, base * 4, base * 8]
        self.down = nn.ModuleList([_block(channels, w[0]), _block(w[0], w[1]), _block(w[1], w[2]), _block(w[2], w[3])])
        self.pool = nn.MaxPool2d(2)
        self.up = nn.ModuleList([nn.ConvTranspose2d(w[3], w[2], 2, 2), nn.ConvTranspose2d(w[2], w[1], 2, 2),
                                 nn.ConvTranspose2d(w[1], w[0], 2, 2)])
        self.merge = nn.ModuleList([_block(w[2] * 2, w[2]), _block(w[1] * 2, w[1]), _block(w[0] * 2, w[0])])
        self.head = nn.Conv2d(w[0], 2, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        skips = []
        for i, down in enumerate(self.down):
            x = down(x)
            if i < len(self.down) - 1:
                skips.append(x)
                x = self.pool(x)
        for up, merge, skip in zip(self.up, self.merge, reversed(skips)):
            x = merge(torch.cat([up(x), skip], 1))
        out = self.head(x)
        return nn.functional.softplus(out[:, 0]), out[:, 1].clamp(-6.0, 6.0)


def gaussian_nll(depth, log_var, target, mask, weight=None) -> torch.Tensor:
    """The negative log likelihood of the measured depth, over measured cells,
    each counted by `weight` when one is given."""
    nll = 0.5 * (torch.exp(-log_var) * (depth - target) ** 2 + log_var)
    if weight is None:
        return nll[mask].mean()
    return (nll * weight)[mask].sum() / weight[mask].sum()
