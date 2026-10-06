"""Which source to believe, cell by cell.

In each cell the sources that cover it are ranked by their error there, and the
best one is believed. Near the edge of what a source covers its say tapers to
nothing over `feather` cells, and what it does not say is taken from the next
best, so where a survey ends and a satellite guess begins a dive meets a slope,
not a step. Each cell keeps the source that said most in it, and the error of
what was taken.

A model that turns some layers into another (colour into depth, imagery into
coral cover) is not fusion: it makes a layer, with its own checked error, and
that layer then takes its turn here like any other.
"""

from __future__ import annotations

import numpy as np

from .layer import Layer


def _taper(covers: np.ndarray, feather: int) -> np.ndarray:
    """0 on the outermost cell a layer covers, rising to 1 `feather` cells
    further in: the profile tools/ground feathered Looe Key's survey with, so
    the place rebuilt here is the place that was built there."""
    if feather <= 0 or covers.all() or not covers.any():
        return covers.astype("float64")
    from scipy.ndimage import distance_transform_edt

    inside = distance_transform_edt(covers)
    return np.clip((inside - 1) / feather, 0.0, 1.0)


def fuse(layers: list[Layer], feather: int = 3) -> Layer:
    """One layer from several of the same quantity on the same grid."""
    if not layers:
        raise ValueError("nothing to fuse")
    quantity, grid = layers[0].quantity, layers[0].grid
    for one in layers:
        if one.quantity != quantity or one.grid != grid:
            raise ValueError("fusion is of one quantity on one grid")
    provenance = [p for one in layers for p in one.provenance]
    offsets = np.cumsum([0] + [len(one.provenance) for one in layers])[:-1]

    errors = np.stack([np.where(one.covers(), one.error, np.inf).astype("float64") for one in layers])
    values = np.stack([np.where(one.covers(), one.value, 0.0).astype("float64") for one in layers])
    tapers = np.stack([_taper(one.covers(), feather) for one in layers])
    sources = np.stack([np.where(one.covers(), one.source.astype(int) + off, Layer.NONE)
                        for one, off in zip(layers, offsets)])

    # A model ranks by its overall held-out error, not cell by cell. At
    # Shushah, choosing between the colour fit and the curve by each one's
    # error at its own predicted depth never changed a held-out ICESat-2
    # point, and moved 6% of the cells no laser crossed by up to 11 m, with
    # cliffs where the choice flipped: a choice nobody can check, not taken.
    # Each cell still carries its own error.
    ranks = np.stack([np.where(one.covers(), one.rank, np.inf) if one.rank is not None else e
                      for one, e in zip(layers, errors)])
    rank = np.argsort(ranks, axis=0, kind="stable")
    rows, cols = np.indices(errors.shape[1:])
    value = np.zeros(errors.shape[1:])
    error = np.zeros(errors.shape[1:])
    said = np.zeros(errors.shape[1:])
    left = np.ones(errors.shape[1:])            # what the better sources have not said
    source = np.full(errors.shape[1:], Layer.NONE, dtype=int)
    for k in range(len(layers)):
        at = rank[k], rows, cols
        weight = left * tapers[at]
        value += weight * values[at]
        error += weight * np.where(np.isfinite(errors[at]), errors[at], 0.0)
        source = np.where(weight > said, sources[at], source)
        said = np.maximum(said, weight)
        left -= weight
    total = 1.0 - left
    some = total > 1e-9
    value = np.where(some, value / np.where(some, total, 1.0), np.nan).astype("float32")
    error = np.where(some, error / np.where(some, total, 1.0), np.nan).astype("float32")
    source = np.where(some, source, Layer.NONE).astype("u1")
    return Layer(grid, quantity, value, error, source, provenance)
