"""The ground a reef trained from a video stands on: the top of its opaque
splats on a fine grid, for a vehicle to rest on and measure altitude from.

    python splat_surface.py ALIGN_BAKED OUT_DIR CKPT [CKPT ...] [--cell 0.05] [--reach 6]

Splats are drawn, not solid: a vehicle flies through them and its altimeter
reads whatever ground is under them. This is that ground, from the splats
themselves: in each cell of --cell metres, the 85th percentile of the
heights of its opaque, compact splats (so the top of the reef, not a stray
splat in the water above it), at least six of them, a 5 x 5 median taken
over that, within --reach metres of the swim (ALIGN_BAKED's frames) and
nowhere else, holes inside it filled from the nearest measured cell. Cells
outside are NaN: there the place's own ground stands (runner.Surface).

The splats are moved into the place's frame by ALIGN_BAKED's bakedTransform
(bake_splats.py), so the grid is in the same metres as the drawn splats.
Written: OUT_DIR/surface.f32 (float32, rows x columns, row 0 at the lowest y)
and surface.json (origin, cellM, rows, columns, heights' range). Run inside
iocean/3dgrut.
"""

from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
import torch
from scipy import ndimage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("align", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("checkpoints", nargs="+")
    ap.add_argument("--cell", type=float, default=0.05)
    ap.add_argument("--reach", type=float, default=6.0)
    ap.add_argument("--percentile", type=float, default=85.0)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    told = json.loads(a.align.read_text())
    L = np.array(told["bakedTransform"]["linear"])
    b = np.array(told["bakedTransform"]["offset"])
    eyes = np.array([f["eye"] for f in told["frames"]])

    pts = []
    for path in a.checkpoints:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        p = ck["positions"].detach().double().numpy()
        op = torch.sigmoid(ck["density"].detach()).double().numpy()[:, 0]
        size = np.exp(ck["scale"].detach().double().numpy()).max(1)
        keep = (op > 0.5) & (size < np.percentile(size, 90))
        pts.append(p[keep] @ L.T + b)
        del ck
    pts = np.concatenate(pts)

    # Only near the swim: what the camera looked at closely enough to stand on.
    from scipy.spatial import cKDTree

    near, _ = cKDTree(eyes[:, :2]).query(pts[:, :2])
    pts = pts[near < a.reach]
    lo = pts[:, :2].min(0)
    n = (np.ceil((pts[:, :2].max(0) - lo) / a.cell).astype(int) + 1)
    ij = ((pts[:, :2] - lo) / a.cell).astype(int)
    key = ij[:, 1] * n[0] + ij[:, 0]
    order = np.argsort(key, kind="stable")
    key, z = key[order], pts[order, 2]
    cells, starts, counts = np.unique(key, return_index=True, return_counts=True)
    height = np.full(n[1] * n[0], np.nan)
    for c, s0, k in zip(cells, starts, counts):
        if k >= 6:
            height[c] = np.percentile(z[s0:s0 + k], a.percentile)
    grid = height.reshape(n[1], n[0])
    known = np.isfinite(grid)
    # A median over 5 x 5, holes filled from their neighbours only for it.
    filled = np.where(known, grid, ndimage.grey_closing(np.nan_to_num(grid, nan=-1e3), size=3))
    filled = np.where(np.isfinite(filled) & (filled > -1e2), filled, np.nanmedian(grid))
    smooth = ndimage.median_filter(filled, size=5)
    # Holes inside what it measured are ground too, the nearest measured
    # cell's: left empty, the place's own coarse ground showed through as pits.
    inside = ndimage.binary_fill_holes(ndimage.binary_closing(known, structure=np.ones((5, 5))))
    _, (ri, ci) = ndimage.distance_transform_edt(~known, return_indices=True)
    out = np.where(inside, np.where(known, smooth, smooth[ri, ci]), np.nan).astype("<f4")
    out.tofile(a.out / "surface.f32")
    said = {"origin": [float(lo[0]), float(lo[1])], "cellM": a.cell, "rows": int(n[1]), "columns": int(n[0]),
            "measuredShare": round(float(np.isfinite(out).mean()), 3),
            "heightM": [round(float(np.nanmin(out)), 2), round(float(np.nanmax(out)), 2)],
            "from": (f"the {a.percentile:g}th percentile of the opaque splats' heights in each {a.cell:g} m cell "
                     f"within {a.reach:g} m of the swim, a 5 x 5 median over it")}
    (a.out / "surface.json").write_text(json.dumps(said, indent=1))
    print(json.dumps(said))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
