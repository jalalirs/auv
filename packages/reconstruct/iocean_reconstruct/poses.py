"""A video's cameras from the vehicle's own navigation (docs/plan/assets-contract.md,
"Navigation poses for a video").

The poses CSV (tools/subpipe-poses writes it): image, t (s from the video's
first frame), x east, y north, z up (metres), qw qx qy qz (camera to world,
OpenCV camera: x right, y down, z along the view), altitudeM (optional). Each
frame read takes the pose nearest its time, within half a frame interval; the
cameras go to COLMAP fixed, as a text model, world to camera, and when the
altitude is known the seabed under each camera seeds points of its own.
"""

from __future__ import annotations

import csv
import pathlib

import numpy as np


def read_poses(path: pathlib.Path) -> list[dict]:
    """The CSV's rows, by time."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
            alt = r.get("altitudeM", "")
            rows.append({"image": r.get("image", ""), "t": float(r["t"]),
                         "centre": [float(r["x"]), float(r["y"]), float(r["z"])],
                         "q": [float(r["qw"]), float(r["qx"]), float(r["qy"]), float(r["qz"])],
                         "altitudeM": float(alt) if alt not in ("", "nan", "NaN") else None})
    if not rows:
        raise RuntimeError(f"the poses {path.name} hold no rows")
    rows.sort(key=lambda r: r["t"])
    return rows


def nearest_in_time(times, pose_times, interval: float) -> list[int | None]:
    """For each frame time, the index of the pose nearest it, or None when
    none is within half the interval."""
    p = np.asarray(pose_times, dtype=float)
    out = []
    for t in np.atleast_1d(np.asarray(times, dtype=float)):
        j = int(np.searchsorted(p, t))
        near = [k for k in (j - 1, j) if 0 <= k < len(p)]
        if not near:
            out.append(None)
            continue
        k = min(near, key=lambda k: abs(p[k] - t))
        out.append(k if abs(p[k] - t) <= interval / 2 + 1e-9 else None)
    return out


def rotation_of(q) -> np.ndarray:
    """The rotation a unit quaternion (w, x, y, z) stands for."""
    w, x, y, z = np.asarray(q, dtype=float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def world_to_camera(q_c2w, centre) -> tuple[list[float], list[float]]:
    """COLMAP's image pose (qw qx qy qz, tx ty tz: world to camera) from a
    camera-to-world quaternion and the camera's centre."""
    q = np.asarray(q_c2w, dtype=float)
    q = q / np.linalg.norm(q)
    r_w2c = rotation_of(q).T
    t = -r_w2c @ np.asarray(centre, dtype=float)
    qc = [q[0], -q[1], -q[2], -q[3]]
    if qc[0] < 0:
        qc = [-v for v in qc]
    return [float(v) for v in qc], [float(v) for v in t]


def intrinsics_at(camera: dict, size: tuple[int, int]) -> dict:
    """The brief's camera (at the video's resolution) at the size the frames
    are processed at: focal lengths and principal point scaled, the
    distortion unchanged (it is in normalised coordinates)."""
    need = ("width", "height", "fx", "fy", "cx", "cy")
    missing = [k for k in need if camera.get(k) in (None, "")]
    if missing:
        raise RuntimeError("a brief with poses needs the camera's calibration: " + ", ".join(missing) + " missing")
    sx, sy = size[0] / float(camera["width"]), size[1] / float(camera["height"])
    return {"model": "OPENCV", "width": int(size[0]), "height": int(size[1]),
            "fx": float(camera["fx"]) * sx, "fy": float(camera["fy"]) * sy,
            "cx": float(camera["cx"]) * sx, "cy": float(camera["cy"]) * sy,
            "k1": float(camera.get("k1") or 0), "k2": float(camera.get("k2") or 0),
            "p1": float(camera.get("p1") or 0), "p2": float(camera.get("p2") or 0)}


def params_of(k: dict) -> list[float]:
    return [k["fx"], k["fy"], k["cx"], k["cy"], k["k1"], k["k2"], k["p1"], k["p2"]]


def write_model(out: pathlib.Path, k: dict, images: list[tuple[int, str, list, list]]) -> None:
    """A COLMAP text model: one OPENCV camera, the fixed images (id, name,
    q world to camera, t), no points."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "cameras.txt").write_text(
        f"1 OPENCV {k['width']} {k['height']} " + " ".join(f"{v:.10g}" for v in params_of(k)) + "\n")
    with open(out / "images.txt", "w") as f:
        for i, name, q, t in images:
            f.write(f"{i} " + " ".join(f"{v:.12g}" for v in (*q, *t)) + f" 1 {name}\n\n")
    (out / "points3D.txt").write_text("")


def undistorted(uv: np.ndarray, k: dict, rounds: int = 20) -> np.ndarray:
    """Pixels to normalised camera coordinates, the OPENCV distortion undone
    by fixed-point iteration (as cv2.undistortPoints does)."""
    xd = (uv[:, 0] - k["cx"]) / k["fx"]
    yd = (uv[:, 1] - k["cy"]) / k["fy"]
    x, y = xd.copy(), yd.copy()
    for _ in range(rounds):
        r2 = x * x + y * y
        radial = 1 + k["k1"] * r2 + k["k2"] * r2 * r2
        dx = 2 * k["p1"] * x * y + k["p2"] * (r2 + 2 * x * x)
        dy = k["p1"] * (r2 + 2 * y * y) + 2 * k["p2"] * x * y
        x, y = (xd - dx) / radial, (yd - dy) / radial
    return np.stack([x, y], 1)


def seabed_seeds(k: dict, q_c2w, centre, altitude: float, image: np.ndarray | None,
                 grid: tuple[int, int] = (32, 18), reach: float = 4.0) -> tuple[np.ndarray, np.ndarray]:
    """Points on the seabed under one camera: rays from a grid of its pixels
    to the plane (camera z - altitude), taken as flat near the camera, those
    further than reach x altitude along the ray left out; colours from the
    frame (H x W x 3, RGB) where it is given."""
    if not altitude or altitude <= 0:                            # no bottom lock: nothing known
        return np.zeros((0, 3)), np.zeros((0, 3), np.uint8)
    w, h = k["width"], k["height"]
    us = (np.arange(grid[0]) + 0.5) * w / grid[0]
    vs = (np.arange(grid[1]) + 0.5) * h / grid[1]
    uv = np.stack(np.meshgrid(us, vs), -1).reshape(-1, 2)
    n = undistorted(uv, k)
    rays = np.column_stack([n, np.ones(len(n))]) @ rotation_of(q_c2w).T
    c = np.asarray(centre, dtype=float)
    down = rays[:, 2] < -1e-6
    s = np.full(len(rays), np.inf)
    s[down] = -altitude / rays[down, 2]
    keep = down & (s * np.linalg.norm(rays, axis=1) <= reach * altitude)
    xyz = c + s[keep, None] * rays[keep]
    if image is not None:
        ij = np.clip(uv[keep].astype(int), 0, [image.shape[1] - 1, image.shape[0] - 1])
        rgb = image[ij[:, 1], ij[:, 0], :3].astype(np.uint8)
    else:
        rgb = np.full((len(xyz), 3), 128, dtype=np.uint8)
    return xyz, rgb


def append_points(points3d: pathlib.Path, xyz: np.ndarray, rgb: np.ndarray) -> int:
    """Seed points added to a text model's points3D.txt, with no track (they
    are seen by no feature; they are where training starts)."""
    first = 1
    if points3d.is_file():
        for line in open(points3d):
            if line.strip() and not line.startswith("#"):
                first = max(first, int(line.split(None, 1)[0]) + 1)
    with open(points3d, "a") as f:
        for i, (p, c) in enumerate(zip(xyz, rgb)):
            f.write(f"{first + i} {p[0]:.5f} {p[1]:.5f} {p[2]:.5f} {int(c[0])} {int(c[1])} {int(c[2])} 0\n")
    return len(xyz)


def clahe(bgr: np.ndarray) -> np.ndarray:
    """The frame's contrast lifted: CLAHE on L of LAB, clip 4, tiles 8 x 8."""
    import cv2

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
