"""A place's ground and frame made from Gaussian splats trained on a dive video.

    python splat_place.py CHECKPOINT SPLATS_USDZ COLMAP_TEXT OUT [--camera-height 1.92] [--from "..."]

3DGRUT trains splats on a video's frames and COLMAP's cameras. A place built
from them has to have its seabed exactly where the splats are, or the drawn
ground cuts through them; so the ground is taken from the splats themselves:

  the surface   the centres of the opaque splats, in the frame the exported
                USD draws them in (its Gaussians transform applied)
  the frame     levelled by a plane fit (up towards the cameras, right-handed),
                along the swim, in metres by the camera's height over the reef
  the seabed    a 4 cm grid under the surface (a low percentile of its
                height in each cell), gaps filled, coloured with the splats'
                own base colour: it shows only through the splats' holes

Written into OUT in the shape tools/video-reef reads (seabed.npz, frame.npz,
model.ply holding the seabed grid's colours, patch/patch.json), with
cameras.json: every COLMAP camera, by name, as world_from_camera in COLMAP's
frame, for the path tour.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import zipfile

import numpy as np
import torch

SH_C0 = 0.28209479177387814


def gaussians_transform(usdz: pathlib.Path) -> np.ndarray:
    """The exported Gaussians prim's own transform (row-vector, USD's)."""
    import tempfile

    from pxr import Usd, UsdGeom

    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(usdz).extractall(tmp)
        stage = Usd.Stage.Open(str(pathlib.Path(tmp) / "default.usda"))
        prim = stage.GetPrimAtPath("/World/gaussians/Gaussians")
        if not prim:
            return np.eye(4)
        m = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        return np.array([[m[r][c] for c in range(4)] for r in range(4)])


def colmap_cameras(text: pathlib.Path) -> dict:
    out = {}
    lines = [ln for ln in (text / "images.txt").read_text().splitlines() if ln and not ln.startswith("#")]
    for line in lines[::2]:
        p = line.split()
        qw, qx, qy, qz = (float(v) for v in p[1:5])
        R = np.array([[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                      [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                      [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])
        t = np.array([float(v) for v in p[5:8]])
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = R.T, -R.T @ t                     # world from camera
        out[pathlib.Path(p[9]).stem] = m
    cam = [ln.split() for ln in (text / "cameras.txt").read_text().splitlines() if ln and not ln.startswith("#")][0]
    return {"poses": out, "width": int(cam[2]), "height": int(cam[3]), "fx": float(cam[4])}


def _fill(grid, known, rounds=3000):
    g, k = grid.copy(), known.copy()
    for _ in range(rounds):
        if k.all():
            break
        total, count = np.zeros_like(g), np.zeros_like(g)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            total += np.roll(np.roll(np.where(k[..., None] if g.ndim == 3 else k, g, 0), dy, 0), dx, 1)
            count += np.roll(np.roll(k, dy, 0), dx, 1)[..., None] if g.ndim == 3 else np.roll(np.roll(k, dy, 0), dx, 1)
        c0 = count[..., 0] if g.ndim == 3 else count
        fresh = ~k & (c0 > 0)
        g[fresh] = (total / np.maximum(count, 1))[fresh]
        k = k | fresh
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint", type=pathlib.Path)
    ap.add_argument("usdz", type=pathlib.Path)
    ap.add_argument("colmap", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--camera-height", type=float, default=1.92)
    ap.add_argument("--camera-height-from", default="")
    ap.add_argument("--video", default="{}")
    ap.add_argument("--cell", type=float, default=0.04)
    ap.add_argument("--under", type=float, default=5.0,
                    help="the percentile of a cell's splat heights the seabed sits at; the median drew it through half the reef")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    as_array = lambda t: t.detach().cpu().numpy()
    pos = as_array(ck["positions"]).astype(np.float64)
    opacity = as_array(torch.sigmoid(ck["density"]))[:, 0]
    size = np.exp(as_array(ck["scale"])).max(1)
    colour = np.clip(0.5 + SH_C0 * as_array(ck["features_albedo"]), 0, 1)
    M = gaussians_transform(a.usdz)
    pos = pos @ M[:3, :3] + M[3, :3]                              # into COLMAP's world, as the USD draws them
    cams = colmap_cameras(a.colmap)
    centres = np.array([m[:3, 3] for m in cams["poses"].values()])
    # The surface: opaque splats no bigger than the reef's own detail.
    keep = (opacity > 0.5) & (size < np.percentile(size, 90))
    surface, tint = pos[keep], colour[keep]

    # Level, along the swim, right-handed, in metres.
    centre = np.median(surface, axis=0)
    sample = surface[np.random.default_rng(0).choice(len(surface), min(300000, len(surface)), replace=False)] - centre
    _, _, vt = np.linalg.svd(sample, full_matrices=False)
    rotation = vt.copy()
    if np.median((centres - centre) @ rotation[2]) < 0:
        rotation[2] *= -1
        rotation[1] *= -1
    if np.linalg.det(rotation) < 0:
        rotation[1] *= -1
    level = (surface - centre) @ rotation.T
    above = np.median(((centres - centre) @ rotation.T)[:, 2]) - np.median(level[:, 2])
    scale = a.camera_height / max(above, 1e-9)
    xyz = level * scale
    said_scale = (f"measured: the camera {a.camera_height} m over the reef ({a.camera_height_from}), which made "
                  f"one COLMAP unit {scale:.3f} m" if a.camera_height_from else
                  f"assumed: the camera {a.camera_height} m over the reef, one COLMAP unit {scale:.3f} m")

    # The seabed: under the surface in each cell, gaps filled.
    cell = a.cell
    lo = np.percentile(xyz[:, :2], 0.5, axis=0) - 0.2
    hi = np.percentile(xyz[:, :2], 99.5, axis=0) + 0.2
    n = (np.ceil((hi - lo) / cell).astype(int) + 1)
    ij = np.clip(((xyz[:, :2] - lo) / cell).astype(int), 0, n - 1)
    key = ij[:, 1] * n[0] + ij[:, 0]
    order = np.argsort(key)
    cells, starts = np.unique(key[order], return_index=True)
    height = np.full(n[1] * n[0], np.nan)
    col = np.zeros((n[1] * n[0], 3))
    for c, s0, s1 in zip(cells, starts, list(starts[1:]) + [len(order)]):
        which = order[s0:s1]
        if len(which) >= 3:
            height[c] = np.percentile(xyz[which, 2], a.under)
            col[c] = np.median(tint[which], axis=0)
    known = ~np.isnan(height)
    seen = known.reshape(n[1], n[0])
    h = _fill(np.nan_to_num(height).reshape(n[1], n[0]), seen)
    c = _fill(col.reshape(n[1], n[0], 3), seen)
    # Smoothed by its lowest neighbour, so a spike never stands up through the reef.
    low = h.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            low = np.minimum(low, np.roll(np.roll(h, dy, 0), dx, 1))
    h = low
    np.savez(a.out / "seabed.npz", height=h, lo=lo, cell=cell, n=n, seen=seen)
    np.savez(a.out / "frame.npz", centre=centre, rotation=rotation, scale=scale)
    # The seabed grid's colours, as the first n by n vertices of a PLY (what
    # tools/video-reef reads its ground colour from).
    gx, gy = np.meshgrid(lo[0] + np.arange(n[0]) * cell, lo[1] + np.arange(n[1]) * cell)
    v = np.stack([gx.ravel(), gy.ravel(), h.ravel()], 1)
    head = ("ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            "element face 0\nproperty list uchar int vertex_indices\nend_header\n")
    vert = np.zeros(len(v), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    vert["x"], vert["y"], vert["z"] = v[:, 0], v[:, 1], v[:, 2]
    rgb = (np.clip(c.reshape(-1, 3), 0, 1) * 255).astype(np.uint8)
    vert["r"], vert["g"], vert["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    (a.out / "model.ply").write_bytes(head.encode() + vert.tobytes())
    (a.out / "patch").mkdir(exist_ok=True)
    (a.out / "patch" / "patch.json").write_text(json.dumps({
        "tool": "Gaussian splats (3DGRUT 3DGUT) trained on the video's frames and COLMAP's cameras",
        "video": json.loads(a.video), "scale": {"factor": scale, "how": "measured" if a.camera_height_from else "assumed",
                                                 "from": said_scale}}, indent=1))
    (a.out / "cameras.json").write_text(json.dumps({
        "width": cams["width"], "height": cams["height"], "fx": cams["fx"],
        "poses": {k: m.tolist() for k, m in cams["poses"].items()}}))
    print(json.dumps({"splats": int(len(pos)), "surface": int(len(surface)), "scale": round(scale, 4),
                      "seenShare": round(float(seen.mean()), 3), "grid": [int(n[0]), int(n[1])],
                      "extentM": [round(float(v), 1) for v in (hi - lo)]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
