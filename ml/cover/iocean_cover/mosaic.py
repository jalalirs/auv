"""A cover map from a photo mosaic.

A photogrammetric survey's orthomosaic (USGS SQUID-5 at Looe Key: 5 mm, in
200 m GeoTIFF tiles with an alpha band) is read at `metres_per_pixel`, in
blocks with a margin the model sees but the result drops, so a block's edge
never shows. Every pixel gets its most likely group, as a point count gives
every point one label, and the pixels are counted into cells of `cell_m`:

    cover.tif    one band per seabed group, its share of the cell's seabed
                 (NaN where the cell holds no imaged seabed), then `seabed`,
                 the share of the cell that is imaged seabed
    cover.json   the model and its revision, the mosaic's tiles, the settings,
                 and the share of every group over the whole map
    groups.png   the group of every 10 cm, coloured, beside the mosaic, to look at

Tiles must share one coordinate system; the map is in it. `only_seabed` rules
out the classes that are not seabed (a mosaic is all seabed); `stretch`
stretches each block's contrast first.
"""

from __future__ import annotations

import json
import math
import pathlib
import time

import numpy as np

COLOURS = {
    "hard_coral": (236, 128, 255), "soft_coral": (86, 184, 94), "other_coral": (224, 118, 119),
    "bleached_coral": (250, 236, 240), "dead_coral": (114, 15, 203), "algae": (125, 163, 125),
    "seagrass": (40, 120, 40), "sand": (194, 178, 128), "rubble": (161, 153, 128),
    "hard_substrate": (125, 125, 125), "other_life": (0, 255, 255), "not_seabed": (31, 31, 31),
}
PREVIEW_M = 0.1


def _union(tiles) -> tuple:
    left = min(t.bounds.left for t in tiles); right = max(t.bounds.right for t in tiles)
    bottom = min(t.bounds.bottom for t in tiles); top = max(t.bounds.top for t in tiles)
    return left, bottom, right, top


def read(tiles, left: float, top: float, cols: int, rows: int, res: float) -> tuple[np.ndarray, np.ndarray]:
    """RGB and whether imaged, over a box in the tiles' coordinates at `res`
    metres a pixel, composited from every tile it touches (rasterio reads a
    coarser resolution from the tiles' overviews)."""
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds

    rgb = np.zeros((rows, cols, 3), np.uint8)
    seen = np.zeros((rows, cols), bool)
    right, bottom = left + cols * res, top - rows * res
    for t in tiles:
        b = t.bounds
        if b.right <= left or b.left >= right or b.top <= bottom or b.bottom >= top:
            continue
        window = from_bounds(left, bottom, right, top, t.transform)
        data = t.read(indexes=[1, 2, 3, 4], window=window, out_shape=(4, rows, cols), boundless=True, fill_value=0,
                      resampling=Resampling.average)
        here = (data[3] > 0) & ~seen
        rgb[here] = np.moveaxis(data[:3], 0, -1)[here]
        seen |= here
    return rgb, seen


def make(segmenter, groups, paths: list[pathlib.Path], out: pathlib.Path, settings: dict, about: dict) -> dict:
    import rasterio
    import torch
    from PIL import Image
    from rasterio.transform import from_origin

    from .segment import gather_matrix, seabed_only, stretch

    res, cell = float(settings["metres_per_pixel"]), float(settings["cell_m"])
    per = int(round(cell / res))
    if abs(per * res - cell) > 1e-9:
        raise ValueError(f"cell_m {cell} must be a whole number of {res} m pixels")
    block = max(1, int(settings["block"]) // per) * per
    margin = int(settings["margin"])
    tiles = [rasterio.open(p) for p in paths]
    crs = {t.crs.to_string() for t in tiles}
    if len(crs) != 1:
        raise ValueError(f"the tiles are in {len(crs)} coordinate systems: {sorted(crs)}")
    left, bottom, right, top = _union(tiles)
    left, top = math.floor(left / cell) * cell, math.ceil(top / cell) * cell
    ncols, nrows = math.ceil((right - left) / cell), math.ceil((top - bottom) / cell)
    G = len(groups.names)
    not_seabed = groups.names.index("not_seabed")
    counts = np.zeros((G, nrows, ncols), np.int64)
    imaged = np.zeros((nrows, ncols), np.int64)
    step = int(round(PREVIEW_M / res))
    pview = np.full((nrows * per // step, ncols * per // step), not_seabed, np.uint8)
    rview = np.zeros(pview.shape + (3,), np.uint8)
    gather = gather_matrix(groups, segmenter.id2label)
    allowed = seabed_only(groups, segmenter.id2label) if settings.get("only_seabed") else None
    cells_per_block = block // per
    t0, done, skipped = time.time(), 0, 0
    for br in range(0, nrows, cells_per_block):
        for bc in range(0, ncols, cells_per_block):
            rc, cc = min(cells_per_block, nrows - br), min(cells_per_block, ncols - bc)
            x0, y0 = left + bc * cell - margin * res, top - br * cell + margin * res
            rgb, seen = read(tiles, x0, y0, cc * per + 2 * margin, rc * per + 2 * margin, res)
            ri, ci = slice(margin, margin + rc * per), slice(margin, margin + cc * per)
            inner = seen[ri, ci]
            if not inner.any():
                skipped += 1
                continue
            if settings.get("stretch"):
                rgb = stretch(rgb, seen)
            p = segmenter.probabilities(rgb, into=gather, allowed=allowed)[:, ri, ci]
            g = p.argmax(0)
            v = torch.from_numpy(inner).to(g.device)
            g = torch.where(v, g, torch.full_like(g, not_seabed))
            onehot = torch.nn.functional.one_hot(g.long(), G).permute(2, 0, 1).float()
            per_cell = onehot.reshape(G, rc, per, cc, per).sum((2, 4)).round().long().cpu().numpy()
            counts[:, br:br + rc, bc:bc + cc] += per_cell
            imaged[br:br + rc, bc:bc + cc] += inner.reshape(rc, per, cc, per).sum((1, 3))
            pr, pc = br * per // step, bc * per // step
            small = g[::step, ::step].cpu().numpy().astype(np.uint8)
            pview[pr:pr + small.shape[0], pc:pc + small.shape[1]] = small
            rview[pr:pr + small.shape[0], pc:pc + small.shape[1]] = rgb[ri, ci][::step, ::step]
            done += 1
            if done % 20 == 0:
                print(json.dumps({"blocks": done, "empty": skipped, "seconds": round(time.time() - t0)}), flush=True)

    seabed = counts.sum(0) - counts[not_seabed]
    names = list(groups.seabed)
    shares = np.full((len(names) + 1, nrows, ncols), np.nan, np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        for k, name in enumerate(names):
            shares[k] = np.where(seabed > 0, counts[groups.names.index(name)] / seabed, np.nan)
    shares[-1] = seabed / (per * per)
    out.mkdir(parents=True, exist_ok=True)
    profile = {"driver": "GTiff", "width": ncols, "height": nrows, "count": len(names) + 1, "dtype": "float32",
               "crs": tiles[0].crs, "transform": from_origin(left, top, cell, cell), "nodata": float("nan"),
               "compress": "deflate", "tiled": True}
    with rasterio.open(out / "cover.tif", "w", **profile) as dst:
        dst.write(shares)
        for k, name in enumerate(names + ["seabed"]):
            dst.set_band_description(k + 1, name)
    total = int(seabed.sum())
    said = {
        **about, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0),
        "tiles": [str(p) for p in paths], "crs": tiles[0].crs.to_string(), "bands": names + ["seabed"],
        "metresPerPixel": res, "cellM": cell, "origin": [left, top], "cells": [nrows, ncols],
        "imagedM2": round(float(imaged.sum()) * res * res, 1), "seabedM2": round(total * res * res, 1),
        "shares": {name: round(float(counts[groups.names.index(name)].sum() / max(total, 1)), 4) for name in names},
    }
    (out / "cover.json").write_text(json.dumps(said, indent=1) + "\n")
    palette = np.array([COLOURS.get(n, (255, 255, 255)) for n in groups.names], np.uint8)
    Image.fromarray(np.concatenate([rview, palette[pview]], 0)).save(out / "groups.png")
    return said
