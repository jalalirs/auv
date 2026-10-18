"""Where in a place a reef rebuilt from a video goes: near the spot its coral
cover matched, wherever the place's own ground fits the ground it measured.

    python place_choose.py PLACE SURFACE_DIR OUT.json --near X,Y [--within 400] [--depth-slack 3]

A reef from a video is a strip: the Red Sea dive is 99 m by 14 m, 6 to 9 m
deep. Its cover matched Al Fahal best at (-172.5, -592.5), where the ground
drops from 1 m to 22 m in 100 m, so a strip laid there stands in the air at
one end and under the reef at the other. So: for centres on a 10 m grid
within --within metres of --near, and headings every 10 degrees, the place's
heightfield under the strip is compared with the strip's own ground (its
height shifted to fit, the median of the difference): the rms of what is
left, plus how far the shift takes it from its own depth beyond
--depth-slack metres. The least wins.

Written: OUT.json {headingDeg, at (the strip's centre in the place), dz,
centre (in the strip's own frame), matrix (4 x 4, column convention, the
strip's frame to the place's), fit}.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np


def ground_of(place: pathlib.Path):
    s = json.loads((place / "site.json").read_text())
    hf = s["mesh"]["heightfield"]
    h = np.fromfile(place / hf["file"], dtype="<f4").reshape(hf["rows"], hf["columns"]).astype(float)
    across = float(s["from"]["acrossMetres"])

    def under(x, y):
        u = np.clip((np.asarray(x) / across + 0.5) * (hf["columns"] - 1), 0, hf["columns"] - 1.0001)
        v = np.clip((np.asarray(y) / across + 0.5) * (hf["rows"] - 1), 0, hf["rows"] - 1.0001)
        c, r = u.astype(int), v.astype(int)
        fu, fv = u - c, v - r
        return (h[r, c] * (1 - fu) * (1 - fv) + h[r, c + 1] * fu * (1 - fv)
                + h[r + 1, c] * (1 - fu) * fv + h[r + 1, c + 1] * fu * fv)
    return under


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("place", type=pathlib.Path)
    ap.add_argument("surface", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--near", required=True)
    ap.add_argument("--within", type=float, default=400.0)
    ap.add_argument("--depth-slack", type=float, default=3.0)
    a = ap.parse_args()
    nx, ny = (float(v) for v in a.near.split(","))

    said = json.loads((a.surface / "surface.json").read_text())
    grid = np.fromfile(a.surface / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell = float(said["cellM"])
    ox, oy = said["origin"]
    step = max(1, int(round(1.0 / cell)))                 # a sample a metre
    rr, cc = np.mgrid[0:said["rows"]:step, 0:said["columns"]:step]
    hs = grid[rr, cc]
    keep = np.isfinite(hs)
    xs, ys, hs = ox + cc[keep] * cell, oy + rr[keep] * cell, hs[keep].astype(float)
    cx, cy = float(xs.mean()), float(ys.mean())
    own_depth = float(np.median(hs))
    under = ground_of(a.place)

    best = None
    for X in np.arange(nx - a.within, nx + a.within + 1, 10.0):
        for Y in np.arange(ny - a.within, ny + a.within + 1, 10.0):
            if math.hypot(X - nx, Y - ny) > a.within:
                continue
            for deg in range(0, 180, 10):
                t = math.radians(deg)
                c, s = math.cos(t), math.sin(t)
                mx = X + c * (xs - cx) - s * (ys - cy)
                my = Y + s * (xs - cx) + c * (ys - cy)
                g = under(mx, my)
                dz = float(np.median(g - hs))
                rms = float(np.sqrt(np.mean((g - hs - dz) ** 2)))
                off = max(0.0, abs((own_depth + dz) - own_depth) - a.depth_slack)
                score = rms + off
                if best is None or score < best[0]:
                    best = (score, float(X), float(Y), deg, dz, rms, float(np.median(g)))
    score, X, Y, deg, dz, rms, ground = best
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    m = np.eye(4)
    m[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    m[:3, 3] = [X - (c * cx - s * cy), Y - (s * cx + c * cy), dz]
    out = {"headingDeg": deg, "at": [X, Y], "dz": dz, "centre": [cx, cy], "matrix": m.tolist(),
           "fit": {"rmsM": round(rms, 3), "score": round(score, 3), "placeGroundM": round(ground, 2),
                   "ownGroundM": round(own_depth, 2), "near": [nx, ny], "withinM": a.within,
                   "how": "the place's heightfield under the strip against the strip's own ground, "
                          "least rms after the best vertical shift, penalised past the depth slack"}}
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("headingDeg", "at", "dz")} | out["fit"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
