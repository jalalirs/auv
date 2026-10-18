"""Where in a place a reef rebuilt from a video goes: near the spot its coral
cover matched, wherever the place's own ground fits the ground it measured.

    python place_choose.py PLACE SURFACE_DIR OUT.json [--near X,Y] [--within 400] [--depth-slack 3]
        [--start X,Y,Z] [--depth M] [--count 1] [--step 10]

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

For a reconstruction in its own frame (iocean_reconstruct), where its own
depth is nothing: --start is where the swim began in the strip's frame, and
--near is then where that start should land in the place (the coordinate the
video was said to start at), not the strip's centre; without --near the whole
place is searched. --depth is how deep the reef was said to be: a shift that
takes the strip's ground further from it than --depth-slack is penalised, and
without it nothing is, except ground shallower than 1.5 m, where the reef
would stand out of the water. --count keeps that many candidates, each at
least 20 m from a better one, best first, in OUT.json's "candidates" (the
best is also at the top level, as before).
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


def candidates(place: pathlib.Path, surface: pathlib.Path, *, near=None, within=400.0, depth_slack=3.0,
               start=None, depth=None, count=1, step=10.0, own_depth_penalty=True) -> list[dict]:
    """The best placements of the strip in the place, best first."""
    said = json.loads((surface / "surface.json").read_text())
    grid = np.fromfile(surface / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell = float(said["cellM"])
    ox, oy = said["origin"]
    every = max(1, int(round(1.0 / cell)))                # a sample a metre
    rr, cc = np.mgrid[0:said["rows"]:every, 0:said["columns"]:every]
    hs = grid[rr, cc]
    keep = np.isfinite(hs)
    xs, ys, hs = ox + cc[keep] * cell, oy + rr[keep] * cell, hs[keep].astype(float)
    cx, cy = float(xs.mean()), float(ys.mean())
    own_depth = float(np.median(hs))
    under = ground_of(place)
    s = json.loads((place / "site.json").read_text())
    half = float(s["from"]["acrossMetres"]) / 2
    if near is None:
        nx, ny, within = 0.0, 0.0, half * math.sqrt(2)
    else:
        nx, ny = near
    sx, sy = (start[0] - cx, start[1] - cy) if start is not None else (0.0, 0.0)

    found = []
    headings = range(0, 360, 10) if start is not None or not own_depth_penalty else range(0, 180, 10)
    for deg in headings:
        t = math.radians(deg)
        c, si = math.cos(t), math.sin(t)
        rx, ry = c * (xs - cx) - si * (ys - cy), si * (xs - cx) + c * (ys - cy)
        # Where the strip's centre goes so that its start (or its centre) is
        # within reach of --near.
        ox_, oy_ = c * sx - si * sy, si * sx + c * sy
        for X0 in np.arange(nx - within, nx + within + 1, step):
            for Y0 in np.arange(ny - within, ny + within + 1, step):
                if math.hypot(X0 - nx, Y0 - ny) > within:
                    continue
                X, Y = X0 - ox_, Y0 - oy_
                mx, my = X + rx, Y + ry
                if np.abs(mx).max() > half or np.abs(my).max() > half:
                    continue
                g = under(mx, my)
                ground = float(np.median(g))
                if ground > -1.5:
                    continue
                dz = float(np.median(g - hs))
                rms = float(np.sqrt(np.mean((g - hs - dz) ** 2)))
                if depth is not None:
                    off = max(0.0, abs(ground + abs(depth)) - depth_slack)
                elif own_depth_penalty:
                    off = max(0.0, abs((own_depth + dz) - own_depth) - depth_slack)
                else:
                    off = 0.0
                found.append((rms + off, float(X), float(Y), deg, dz, rms, ground))
    found.sort()
    kept = []
    for one in found:
        if all(math.hypot(one[1] - k[1], one[2] - k[2]) >= 20.0 for k in kept):
            kept.append(one)
        if len(kept) >= count:
            break
    out = []
    for score, X, Y, deg, dz, rms, ground in kept:
        t = math.radians(deg)
        c, si = math.cos(t), math.sin(t)
        m = np.eye(4)
        m[:3, :3] = [[c, -si, 0], [si, c, 0], [0, 0, 1]]
        m[:3, 3] = [X - (c * cx - si * cy), Y - (si * cx + c * cy), dz]
        one = {"headingDeg": deg, "at": [X, Y], "dz": dz, "centre": [cx, cy], "matrix": m.tolist(),
               "fit": {"rmsM": round(rms, 3), "score": round(score, 3), "placeGroundM": round(ground, 2),
                       "ownGroundM": round(own_depth, 2), "near": None if near is None else [nx, ny],
                       "withinM": round(within, 1),
                       "how": "the place's heightfield under the strip against the strip's own ground, "
                              "least rms after the best vertical shift, penalised past the depth slack"}}
        if start is not None:
            one["startAt"] = [round(float(v), 2) for v in (m @ np.array([start[0], start[1], 0.0, 1.0]))[:2]]
        out.append(one)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("place", type=pathlib.Path)
    ap.add_argument("surface", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--near", default="")
    ap.add_argument("--within", type=float, default=400.0)
    ap.add_argument("--depth-slack", type=float, default=3.0)
    ap.add_argument("--start", default="", help="X,Y[,Z]: where the swim began, in the strip's own frame")
    ap.add_argument("--depth", type=float, default=None, help="metres the reef was said to be at")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--step", type=float, default=10.0)
    a = ap.parse_args()
    near = tuple(float(v) for v in a.near.split(",")) if a.near else None
    start = tuple(float(v) for v in a.start.split(","))[:2] if a.start else None
    if near is None and start is None:
        raise SystemExit("give --near, or --start for a reconstruction in its own frame")
    found = candidates(a.place, a.surface, near=near, within=a.within, depth_slack=a.depth_slack, start=start,
                       depth=a.depth, count=a.count, step=a.step, own_depth_penalty=start is None)
    if not found:
        raise SystemExit("nowhere in the place fits: every spot is outside it or out of the water")
    out = dict(found[0], candidates=found)
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("headingDeg", "at", "dz")} | out["fit"] | {"candidates": len(found)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
