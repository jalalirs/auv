"""The splats' transform into a place made by splat_place.py and tools/video-reef,
and the video's own camera path in the place, for a path tour.

    python splat_path.py SPLAT_PLACE TOOLS OUT [--across 100] [--most 1024] [--depth 8]

Written: OUT/align.json, {usdMatrix, frames: [{name, eye, matrix}], focalMm,
apertureMm}, the shape tools/video-reef --splat-align and the path tour read.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import pathlib
import sys

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("place", type=pathlib.Path, help="splat_place.py's output")
    ap.add_argument("tools", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--across", type=float, default=100.0)
    ap.add_argument("--most", type=int, default=1024)
    ap.add_argument("--depth", type=float, default=8.0)
    a = ap.parse_args()

    loader = importlib.machinery.SourceFileLoader("video_reef", str(a.tools / "video-reef"))
    spec = importlib.util.spec_from_loader("video_reef", loader)
    video_reef = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(a.tools))
    loader.exec_module(video_reef)
    _, _, origin, shift = video_reef.seabed(a.place, a.across, a.most, a.depth)

    fz = np.load(a.place / "frame.npz")
    L = float(fz["scale"]) * fz["rotation"]                      # COLMAP -> place, linear
    b = -L @ fz["centre"] + np.array([-origin[0], -origin[1], shift])
    turn = fz["rotation"]
    usd = np.eye(4)
    usd[:3, :3], usd[3, :3] = L.T, b
    cams = json.loads((a.place / "cameras.json").read_text())
    frames = []
    for name in sorted(cams["poses"]):
        m = np.array(cams["poses"][name])
        R = m[:3, :3]
        x, y_down, z_fwd = (turn @ R[:, i] for i in range(3))
        out = np.eye(4)
        out[:3, 0], out[:3, 1], out[:3, 2], out[:3, 3] = x, -y_down, -z_fwd, L @ m[:3, 3] + b
        frames.append({"name": name, "eye": [float(v) for v in out[:3, 3]], "matrix": out.tolist()})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "align.json").write_text(json.dumps({
        "usdMatrix": usd.tolist(), "frames": frames, "fitResidualMedianM": 0.0,
        "focalMm": 20.955 * cams["fx"] / cams["width"], "apertureMm": 20.955,
        "image": [cams["width"], cams["height"]]}, indent=1))
    print(json.dumps({"frames": len(frames), "first": frames[0]["eye"], "scale": float(fz["scale"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
