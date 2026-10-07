"""The baseline: depth as one linear function of the log bands and the
log-ratio, fitted over every training cell. It is the per-pixel colour model
the places use, made global; the U-Net is worth having by what it beats this by."""

from __future__ import annotations

import numpy as np


class LinearBaseline:
    def __init__(self, columns: int = 8):
        self.columns, self.coef = columns, None

    def fit(self, X: np.ndarray, Y: np.ndarray, M: np.ndarray, most: int = 2_000_000, seed: int = 0) -> "LinearBaseline":
        use = M & (X[:, -1] > 0)
        A = X[:, :self.columns].transpose(0, 2, 3, 1)[use]
        b = Y[use]
        pick = np.random.default_rng(seed).choice(len(b), min(len(b), most), replace=False)
        self.coef, *_ = np.linalg.lstsq(np.c_[A[pick], np.ones(len(pick))], b[pick], rcond=None)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        Z = X[:, :self.columns].transpose(0, 2, 3, 1)
        return np.clip(Z @ self.coef[:-1] + self.coef[-1], 0, None)
