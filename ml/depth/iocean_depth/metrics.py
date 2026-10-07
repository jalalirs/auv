"""How wrong, and whether the model knows how wrong: rms, mean absolute
error, bias, by depth band, and the share of cells within one stated sigma
(about 0.68 if the stated uncertainty is honest)."""

from __future__ import annotations

import numpy as np

BANDS = ((0, 5), (5, 10), (10, 15), (15, 20), (20, 40))


def scores(pred: np.ndarray, depth: np.ndarray, mask: np.ndarray, sigma: np.ndarray | None = None) -> dict:
    if not mask.any():
        return {"cells": 0}
    e, d = (pred - depth)[mask], depth[mask]
    out = {"cells": int(mask.sum()), "rmsM": round(float(np.sqrt(np.mean(e ** 2))), 3),
           "maeM": round(float(np.mean(np.abs(e))), 3), "biasM": round(float(np.mean(e)), 3)}
    if sigma is not None:
        s = sigma[mask]
        out["withinOneSigma"] = round(float(np.mean(np.abs(e) <= s)), 3)
        out["medianSigmaM"] = round(float(np.median(s)), 3)
    out["byDepth"] = [{"fromM": lo, "toM": hi, "cells": int(b.sum()), "rmsM": round(float(np.sqrt(np.mean(e[b] ** 2))), 3)}
                      for lo, hi in BANDS for b in [(d >= lo) & (d < hi)] if b.sum() > 100]
    return out
