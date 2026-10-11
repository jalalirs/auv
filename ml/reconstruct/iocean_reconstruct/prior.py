"""A reconstruction and a coral library, fused: the library's colony as the
prior, the video's points as the measurement.

A video's reconstruction of a reef is measured where the camera looked and
wrong where it did not: the backs of colonies, the shadows between them, the
patches seen from one frame. A colony from the coral library is the opposite:
the right kind of shape everywhere and nowhere this particular colony. Fused
the way a Kalman filter fuses a prediction and a measurement, each wins where
it is the more certain: the colony is placed and sized from the points, then
its surface is pulled towards the points by a gain that is high where many
frames saw the same place and nothing where no frame did.

    python -m iocean_reconstruct.cli fuse --run redsea-single-60-180 --library /library/red-sea

Steps, each written into <run>/prior/:

  1. read the dense points and which frames saw each (COLMAP's fused.ply and
     fused.ply.vis), the undistorted cameras, and each frame's class at every
     pixel (iocean-cover label); hold back every eighth frame
  2. label each point by the frames that saw it, by vote
  3. gather the massive-coral points into colonies
  4. for each colony, the library's massive colony scaled and turned to its
     footprint and height above the ground around it (the prediction)
  5. pull each vertex along its normal towards the points near it, by the gain
     K = prior² / (prior² + measurement²) (the update); keep the posterior
     uncertainty per vertex
  6. render the held-back frames' depth from the reconstruction alone, the
     library alone and the fusion, over the massive coral those frames show,
     and score each against the frames' own depth
"""

from __future__ import annotations

import json
import pathlib
import struct
import time

import numpy as np

HELD_EVERY = 8
# A COLMAP point is triangulated from frames about two metres away; one frame
# places it to a few centimetres, n frames to that over the root of n.
MEASURED_M = 0.04
# How far a real colony's surface is from the library colony scaled to its
# footprint: lumps, a lean, a dead patch. Centimetres, not metres.
PRIOR_M = 0.08
# How near a point has to be to a vertex, across its normal, to say where
# that vertex should be.
REACH_M = 0.06

MASSIVE = ("massive", "porites", "meandering")
CLASS_SAND = 69                      # the cover model's id for sand, which synthetic/reef.py labels with
GROUND = ("sand", "rubble")


# ── reading ──────────────────────────────────────────────────────────────────

def _quaternion(qw, qx, qy, qz) -> np.ndarray:
    return np.array([[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                     [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                     [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])


def read_cameras(text: pathlib.Path) -> tuple[dict, list[dict]]:
    """The undistorted pinhole camera(s) and every frame's pose, in the order
    images.txt lists them (which is the order fused.ply.vis counts in)."""
    cams = {}
    for line in (text / "cameras.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if p[1] != "PINHOLE":
            raise ValueError(f"camera {p[0]} is {p[1]}; the dense model's cameras are undistorted pinholes")
        cams[int(p[0])] = {"w": int(p[2]), "h": int(p[3]), "fx": float(p[4]), "fy": float(p[5]),
                           "cx": float(p[6]), "cy": float(p[7])}
    frames = []
    lines = [ln for ln in (text / "images.txt").read_text().splitlines() if ln and not ln.startswith("#")]
    for line in lines[::2]:
        p = line.split()
        r = _quaternion(*(float(v) for v in p[1:5]))
        t = np.array([float(v) for v in p[5:8]])
        frames.append({"id": int(p[0]), "name": p[9], "R": r, "t": t, "camera": cams[int(p[8])],
                       "centre": -r.T @ t})
    frames.sort(key=lambda f: f["id"])
    return cams, frames


def read_fused(dense: pathlib.Path) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Points, colours and, for each point, the indices of the frames that saw it."""
    import open3d as o3d

    cloud = o3d.io.read_point_cloud(str(dense / "fused.ply"))
    points = np.asarray(cloud.points)
    colours = (np.asarray(cloud.colors) * 255).astype(np.uint8)
    raw = (dense / "fused.ply.vis").read_bytes()
    (count,) = struct.unpack_from("<Q", raw, 0)
    if count != len(points):
        raise ValueError(f"fused.ply has {len(points)} points and its visibility {count}")
    seen, at = [], 8
    whole = np.frombuffer(raw, dtype="<u4", offset=8)
    i = 0
    for _ in range(count):
        n = int(whole[i])
        seen.append(whole[i + 1:i + 1 + n])
        i += 1 + n
    return points, colours, seen


def read_depth(path: pathlib.Path) -> np.ndarray:
    """A COLMAP depth map: a text header, then the values column by column."""
    raw = path.read_bytes()
    marks, at = 0, 0
    while marks < 3:
        if raw[at:at + 1] == b"&":
            marks += 1
        at += 1
    w, h, c = (int(v) for v in raw[:at].decode().strip("&").split("&"))
    data = np.frombuffer(raw, dtype="<f4", offset=at, count=w * h * c)
    return data.reshape((w, h, c), order="F").transpose(1, 0, 2).squeeze()


def read_library_ply(path: pathlib.Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A coral library colony (tools/coral_hd write_ply): vertices, triangles, colours."""
    data = path.read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    head = data[:end].decode().split("\n")
    nv = int(next(h for h in head if h.startswith("element vertex")).split()[-1])
    nf = int(next(h for h in head if h.startswith("element face")).split()[-1])
    vert = np.frombuffer(data, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"),
                                      ("b", "u1")], count=nv, offset=end)
    face = np.frombuffer(data, dtype=[("n", "u1"), ("i", "<i4", 3)], count=nf, offset=end + vert.nbytes)
    v = np.stack([vert["x"], vert["y"], vert["z"]], 1).astype(float)
    c = np.stack([vert["r"], vert["g"], vert["b"]], 1) / 255.0
    return v, face["i"].astype(np.int64), c


# ── the patch's frame ────────────────────────────────────────────────────────

def frame_of(points: np.ndarray, centres: np.ndarray, scale: float):
    """Model units to patch metres: z up out of the reef's mean plane."""
    from .patch import frame_of as fit

    centre, rotation, _ = fit(points, centres)
    return lambda p: (np.asarray(p) - centre) @ rotation.T * scale, rotation, centre


# ── labels ───────────────────────────────────────────────────────────────────

def groups_of(id2label: dict) -> np.ndarray:
    """Class id → 1 massive coral, 2 ground, 0 anything else."""
    out = np.zeros(max(int(k) for k in id2label) + 1, np.uint8)
    for k, name in id2label.items():
        if any(w in name for w in MASSIVE):
            out[int(k)] = 1
        elif name in GROUND:
            out[int(k)] = 2
    return out


def project(frame: dict, points: np.ndarray):
    """Pixel columns, rows and depths of model points in a frame."""
    cam = (points @ frame["R"].T) + frame["t"]
    z = cam[:, 2]
    c = frame["camera"]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = c["fx"] * cam[:, 0] / z + c["cx"]
        v = c["fy"] * cam[:, 1] / z + c["cy"]
    return u, v, z


def label_points(points, seen, frames, labels: pathlib.Path, group_of: np.ndarray, use: set[int],
                 votes: int = 5) -> np.ndarray:
    """Each point's group by majority over (up to `votes` of) the frames in
    `use` that saw it: 1 massive, 2 ground, 0 other, 255 nothing to go on."""
    from PIL import Image

    tally = np.zeros((len(points), 3), np.int32)
    by_frame: dict[int, list[int]] = {}
    for i, frames_of in enumerate(seen):
        kept = [int(f) for f in frames_of if int(f) in use][:votes]
        for f in kept:
            by_frame.setdefault(f, []).append(i)
    for f, which in by_frame.items():
        frame = frames[f]
        lab = np.asarray(Image.open(labels / (pathlib.Path(frame["name"]).stem + ".png")))
        if lab.ndim == 3:                       # a rendered label: the class is the red channel
            lab = lab[..., 0]
        idx = np.asarray(which)
        u, v, z = project(frame, points[idx])
        ok = (z > 0) & (u >= 0) & (v >= 0) & (u < lab.shape[1] - 0.5) & (v < lab.shape[0] - 0.5)
        g = group_of[lab[np.round(v[ok]).astype(int), np.round(u[ok]).astype(int)]]
        np.add.at(tally, (idx[ok], g), 1)
    out = tally.argmax(1).astype(np.uint8)
    out[tally.sum(1) == 0] = 255
    return out


# ── colonies, prediction and update ──────────────────────────────────────────

def colonies_of(points: np.ndarray, eps: float = 0.06, least: int = 400) -> list[np.ndarray]:
    """Groups of massive-coral points that touch, seen from above."""
    import open3d as o3d

    flat = np.c_[points[:, :2], np.zeros(len(points))]
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(flat))
    labels = np.asarray(cloud.cluster_dbscan(eps=eps, min_points=10))
    out = []
    for k in range(labels.max() + 1):
        which = np.flatnonzero(labels == k)
        if len(which) < least:
            continue
        out += [which[part] for part in split_at_peaks(points[which]) if len(part) >= least]
    return out


def split_at_peaks(points: np.ndarray, cell_m: float = 0.02, apart_m: float = 0.15,
                   rise_m: float = 0.04) -> list[np.ndarray]:
    """Colonies that touch, seen from above, are one group to a clustering by
    distance; each is a hump of its own. The humps' tops are found on a height
    grid (a top is the highest cell within `apart_m` and stands `rise_m` over
    the lowest cell around it) and every point goes to the nearest top."""
    lo = points[:, :2].min(0)
    cells = np.floor((points[:, :2] - lo) / cell_m).astype(int)
    shape = cells.max(0) + 1
    top = np.full(shape, -np.inf)
    np.maximum.at(top, (cells[:, 0], cells[:, 1]), points[:, 2])
    r = max(1, int(round(apart_m / cell_m)))
    filled = np.where(np.isfinite(top), top, np.nan)
    peaks = []
    for i, j in zip(*np.nonzero(np.isfinite(top))):
        window = filled[max(0, i - r):i + r + 1, max(0, j - r):j + r + 1]
        if top[i, j] >= np.nanmax(window) and top[i, j] - np.nanmin(window) >= rise_m:
            if all((i - a) ** 2 + (j - b) ** 2 > r * r for a, b in peaks):
                peaks.append((i, j))
    if len(peaks) <= 1:
        return [np.arange(len(points))]
    centres = (np.array(peaks) + 0.5) * cell_m + lo
    nearest = np.argmin(((points[:, None, :2] - centres[None]) ** 2).sum(-1), axis=1)
    return [np.flatnonzero(nearest == k) for k in range(len(peaks))]


# What a massive colony's shape is, before any one is measured: how tall it
# is for how wide (Porites and the other boulder corals sit between about a
# third and four fifths), with how sure that is.
TALL_FOR_WIDE = (0.5, 0.15)
# How sure a height read off the points is: well, where the top was seen by
# many frames; hardly at all where only a side was.
HEIGHT_SEEN_M, HEIGHT_UNSEEN_M = 0.02, 0.25


def region_of(metres: np.ndarray, group: np.ndarray, colony: np.ndarray, ground_z: float,
              reach_m: float = 0.08) -> np.ndarray:
    """The colony's points: not only the ones labelled massive, which are
    often a side wall or a lit patch, but everything standing above the
    ground within `reach_m` of them, seen from above, that is not ground."""
    import open3d as o3d

    tree = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(
        o3d.utility.Vector3dVector(np.c_[metres[colony, :2], np.zeros(len(colony))])))
    lo, hi = metres[colony, :2].min(0) - reach_m, metres[colony, :2].max(0) + reach_m
    box = np.flatnonzero((metres[:, 0] > lo[0]) & (metres[:, 0] < hi[0]) & (metres[:, 1] > lo[1]) &
                         (metres[:, 1] < hi[1]) & (group != 2) & (metres[:, 2] > ground_z + 0.02))
    near = [i for i in box if tree.search_knn_vector_3d(np.r_[metres[i, :2], 0.0], 1)[2][0] < reach_m ** 2]
    return np.union1d(colony, np.asarray(near, dtype=int))


def predict(template: tuple, colony: np.ndarray, ground_z: float, views: np.ndarray | None = None,
            tall_for_wide: tuple[float, float] = TALL_FOR_WIDE) -> dict:
    """The library colony, turned and scaled to a colony: its footprint from
    the points, its height the measured one and the prior one combined by how
    sure each is (the prediction, before the surface is updated)."""
    v, f, c = template
    xy = colony[:, :2]
    middle = np.median(xy, 0)
    cov = np.cov((xy - middle).T)
    values, vectors = np.linalg.eigh(cov)
    along = vectors[:, 1]
    yaw = float(np.arctan2(along[1], along[0]))
    turn = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
    local = (xy - middle) @ turn
    a, b = (max(float(np.percentile(np.abs(local[:, k]), 95)), 0.03) for k in (0, 1))
    above = colony[:, 2] - ground_z
    measured = float(np.percentile(above, 95))
    # The top was seen when points near the measured top come from many frames.
    top = above > measured - 0.03
    seen_top = views is not None and top.sum() >= 30 and float(np.median(views[top])) >= 3
    sigma_measured = HEIGHT_SEEN_M if seen_top else HEIGHT_UNSEEN_M
    wide = a + b                                      # the mean diameter
    prior_h, sigma_prior = tall_for_wide[0] * wide, tall_for_wide[1] * wide
    w_m, w_p = 1 / sigma_measured ** 2, 1 / sigma_prior ** 2
    h = max((measured * w_m + prior_h * w_p) / (w_m + w_p), 0.02)
    sigma_h = (w_m + w_p) ** -0.5
    tv = v - [*(v[:, :2].max(0) + v[:, :2].min(0)) / 2, v[:, 2].min()]
    ta, tb = np.abs(tv[:, 0]).max(), np.abs(tv[:, 1]).max()
    th = max(tv[:, 2].max(), 1e-6)
    scaled = tv * [a / ta, b / tb, h / th]
    placed = np.c_[scaled[:, :2] @ turn.T + middle, scaled[:, 2] + ground_z]
    return {"vertices": placed, "faces": f, "colours": c, "centre": middle.tolist(), "yawDeg": round(np.degrees(yaw), 1),
            "acrossM": [round(2 * a, 3), round(2 * b, 3)], "heightM": round(h, 3), "groundZ": round(ground_z, 3),
            "height": {"measuredM": round(measured, 3), "measuredSigmaM": sigma_measured, "priorM": round(prior_h, 3),
                       "priorSigmaM": round(sigma_prior, 3), "fusedM": round(h, 3), "fusedSigmaM": round(sigma_h, 3),
                       "topSeen": bool(seen_top)}}


def best_template(shelf: list[pathlib.Path], region: np.ndarray, ground_z: float, views: np.ndarray,
                  cache: dict, most: int = 3000, seed: int = 0) -> tuple[dict, pathlib.Path, list]:
    """Of the library's colonies, the one that, placed and sized to this
    colony, lies closest to the points the video measured on it, each tried
    the way the footprint says and turned half round: which prior, before how
    much of it."""
    import open3d as o3d

    rng = np.random.default_rng(seed)
    pts = region[rng.choice(len(region), min(most, len(region)), replace=False)]
    tried = []
    best = None
    for path in shelf:
        template = cache.setdefault(path, read_library_ply(path))
        for half_turn in (False, True):
            v, f, c = template
            if half_turn:
                v = v * [-1, -1, 1]
            prediction = predict((v, f, c), region, ground_z, views)
            scene = o3d.t.geometry.RaycastingScene()
            scene.add_triangles(o3d.core.Tensor(prediction["vertices"].astype("float32")),
                                o3d.core.Tensor(prediction["faces"].astype("uint32")))
            residual = float(np.median(scene.compute_distance(o3d.core.Tensor(pts.astype("float32"))).numpy()))
            tried.append((path.name, half_turn, round(residual, 4)))
            if best is None or residual < best[0]:
                best = (residual, prediction, path)
    return best[1] | {"fitResidualM": round(best[0], 4)}, best[2], sorted(tried, key=lambda x: x[2])[:3]


def blend(prediction: dict, seen_v: np.ndarray, seen_f: np.ndarray, seen_c: np.ndarray,
          cover_m: float = 0.03, band_m: float = 0.08) -> dict:
    """The measured surface where the video saw the colony, the library's
    where it did not: the gain is one on the seen surface and nought beyond
    it. Library faces the seen surface covers go; library vertices within
    `band_m` of it are drawn onto it, fully at `cover_m`, so the two meet
    rather than overlap."""
    import open3d as o3d

    v, f, c = prediction["vertices"].copy(), prediction["faces"], prediction["colours"]
    if len(seen_f) == 0:
        return {**prediction, "gain": np.zeros(len(v)), "posteriorM": np.full(len(v), PRIOR_M),
                "measuredShare": 0.0, "meanShiftM": 0.0}
    used = np.unique(seen_f)
    tree = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(seen_v[used])))
    nearest = np.zeros(len(v), dtype=int)
    distance = np.zeros(len(v))
    for i in range(len(v)):
        _, idx, d2 = tree.search_knn_vector_3d(v[i], 1)
        nearest[i], distance[i] = used[idx[0]], np.sqrt(d2[0])
    gain = np.clip(1.0 - (distance - cover_m) / (band_m - cover_m), 0.0, 1.0)
    moved = v + gain[:, None] * (seen_v[nearest] - v)
    covered = (distance < cover_m)[f].all(1)
    kept = f[~covered]
    # One mesh: the seen surface's triangles, then the library's that remain.
    remap = -np.ones(len(seen_v), dtype=int)
    remap[used] = np.arange(len(used))
    vertices = np.concatenate([seen_v[used], moved])
    faces = np.concatenate([remap[seen_f], kept + len(used)])
    colours = np.concatenate([seen_c[used], c])
    gains = np.concatenate([np.ones(len(used)), gain])
    posterior = np.concatenate([np.full(len(used), MEASURED_M / 2), PRIOR_M * np.sqrt(1 - gain)])
    share = len(seen_f) / max(len(seen_f) + len(kept), 1)
    return {**prediction, "vertices": vertices, "faces": faces, "colours": colours, "gain": gains,
            "posteriorM": posterior, "measuredShare": round(float(share), 3),
            "meanShiftM": round(float(distance[gain > 0].mean()) if (gain > 0).any() else 0.0, 4)}


def update(prediction: dict, points: np.ndarray, colours: np.ndarray, views: np.ndarray,
           measured_m: float = MEASURED_M, prior_m: float = PRIOR_M, reach_m: float = REACH_M) -> dict:
    """Each vertex pulled along its normal towards the points near it, by the
    Kalman gain; the posterior uncertainty kept per vertex."""
    import open3d as o3d

    v, f = prediction["vertices"], prediction["faces"]
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(v), o3d.utility.Vector3iVector(f))
    mesh.compute_vertex_normals()
    n = np.asarray(mesh.vertex_normals)
    tree = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points)))
    shift = np.zeros(len(v))
    gain = np.zeros(len(v))
    colour = prediction["colours"].copy()
    sigma_point = measured_m / np.sqrt(np.maximum(views, 1))
    for i in range(len(v)):
        found, idx, _ = tree.search_radius_vector_3d(v[i], 3 * reach_m)
        if found == 0:
            continue
        idx = np.asarray(idx)
        d = (points[idx] - v[i]) @ n[i]
        across = np.linalg.norm(points[idx] - v[i] - np.outer(d, n[i]), axis=1)
        near = across < reach_m
        if not near.any():
            continue
        w = 1.0 / sigma_point[idx[near]] ** 2
        said = float((w * d[near]).sum() / w.sum())
        measured = 1.0 / np.sqrt(w.sum())
        k = prior_m ** 2 / (prior_m ** 2 + measured ** 2)
        shift[i], gain[i] = k * said, k
        if k > 0.5:
            colour[i] = (colours[idx[near]].astype(float) / 255.0).mean(0)
    # Smoothed over the surface, so one vertex does not spike where its
    # neighbours were not seen: each takes the gain-weighted mean of its ring.
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    for _ in range(4):
        num = np.zeros(len(v))
        den = np.zeros(len(v))
        for pair in (edges, edges[:, ::-1]):
            a, b = pair[:, 0], pair[:, 1]
            np.add.at(num, a, gain[b] * shift[b])
            np.add.at(den, a, gain[b])
        mixed = np.where(den > 0, num / np.maximum(den, 1e-9), 0.0)
        shift = np.where(gain > 0, 0.5 * shift + 0.5 * mixed, 0.0)
    posterior = prior_m * np.sqrt(1.0 - gain)
    return {**prediction, "vertices": v + shift[:, None] * n, "colours": colour, "gain": gain,
            "posteriorM": posterior, "measuredShare": round(float((gain > 0.5).mean()), 3),
            "meanShiftM": round(float(np.abs(shift[gain > 0]).mean()) if (gain > 0).any() else 0.0, 4)}


# ── scoring on held-back frames ──────────────────────────────────────────────

def depth_seen(meshes: list[tuple[np.ndarray, np.ndarray]], frame: dict, to_model, stride: int = 3):
    """Depth (model units) each pixel of a frame sees in these meshes, NaN where it misses."""
    import open3d as o3d

    scene = o3d.t.geometry.RaycastingScene()
    for v, f in meshes:
        scene.add_triangles(o3d.core.Tensor(to_model(v).astype("float32")), o3d.core.Tensor(f.astype("uint32")))
    c = frame["camera"]
    us, vs = np.meshgrid(np.arange(0, c["w"], stride) + 0.5, np.arange(0, c["h"], stride) + 0.5)
    dirs_cam = np.stack([(us - c["cx"]) / c["fx"], (vs - c["cy"]) / c["fy"], np.ones_like(us)], -1)
    dirs = dirs_cam @ frame["R"]                                    # camera to model: R^T d
    origins = np.broadcast_to(frame["centre"], dirs.shape)
    rays = o3d.core.Tensor(np.concatenate([origins, dirs], -1).astype("float32"))
    hit = scene.cast_rays(rays)["t_hit"].numpy()                   # along d, whose z is 1: the depth
    return np.where(np.isfinite(hit), hit, np.nan), us, vs


def standing(metres: np.ndarray, cell_m: float = 0.1, span_m: float = 1.0, above_m: float = 0.08) -> np.ndarray:
    """Which points stand above the seabed around them: the seabed taken as
    the low points (the tenth percentile of each cell, then the lowest within
    `span_m`), and a point standing when it is `above_m` over that."""
    lo = metres[:, :2].min(0)
    cells = np.floor((metres[:, :2] - lo) / cell_m).astype(int)
    shape = cells.max(0) + 1
    order = np.lexsort((metres[:, 2], cells[:, 1], cells[:, 0]))
    floor = np.full(shape, np.nan)
    keys = cells[order]
    starts = np.r_[0, np.flatnonzero((np.diff(keys, axis=0) != 0).any(1)) + 1, len(order)]
    for a, b in zip(starts[:-1], starts[1:]):
        floor[tuple(keys[a])] = metres[order[a + max(0, int((b - a) * 0.1) - 1)], 2]
    # The seabed under each cell: a plane through the low cells around it,
    # fitted, then fitted again to the cells under the first fit, so a colony
    # in the window does not lift it and a slope is not read as standing.
    r = max(1, int(round(span_m / cell_m / 2)))
    ground = np.full(shape, np.nan)
    for i in range(shape[0]):
        for j in range(shape[1]):
            a0, b0 = max(0, i - r), max(0, j - r)
            window = floor[a0:i + r + 1, b0:j + r + 1]
            ii, jj = np.nonzero(np.isfinite(window))
            if len(ii) < 4:
                if len(ii):
                    ground[i, j] = np.nanmin(window)
                continue
            zz = window[ii, jj]
            design = np.c_[ii + a0 - i, jj + b0 - j, np.ones(len(ii))]
            keep = np.ones(len(zz), bool)
            for _ in range(3):
                coef, *_ = np.linalg.lstsq(design[keep], zz[keep], rcond=None)
                below = zz <= design @ coef + 0.01
                if below.sum() < 4 or (below == keep).all():
                    break
                keep = below
            ground[i, j] = coef[2]
    return metres[:, 2] - ground[cells[:, 0], cells[:, 1]] > above_m


def fuse(run: pathlib.Path, library: pathlib.Path, out: pathlib.Path | None = None,
         by: str = "labels") -> dict:
    """The whole of it, for one run; returns what was found and scored."""
    from PIL import Image

    started = time.time()
    out = out or run / "prior"
    out.mkdir(parents=True, exist_ok=True)
    dense = run / "colmap" / "dense"
    _, frames = read_cameras(dense / "sparse-text")
    points, colours, seen = read_fused(dense)
    id2label = json.loads((run / "labels" / "classes.json").read_text())["id2label"]
    group_of = groups_of(id2label)
    held = set(range(0, len(frames), HELD_EVERY))
    use = set(range(len(frames))) - held

    # 1. What the held-back frames did not see is what the fusion measures.
    views = np.array([sum(1 for f in s if int(f) in use) for s in seen])
    keep = views >= 2
    points, colours, views = points[keep], colours[keep], views[keep]
    seen = [s for s, k in zip(seen, keep) if k]

    scale_said = json.loads((run / "scale.json").read_text()) if (run / "scale.json").is_file() else {}
    scale = float(scale_said.get("scale") or 1.0)
    to_patch, rotation, centre = frame_of(points, np.array([f["centre"] for f in frames]), scale)
    to_model = lambda p: (np.asarray(p) / scale) @ rotation + centre
    metres = to_patch(points)

    # Which frame a visibility index means is checked, not assumed: points
    # should land inside the frames that are said to have seen them.
    sample = np.random.default_rng(0).choice(len(points), min(2000, len(points)), replace=False)
    inside = []
    for i in sample:
        f = frames[int(seen[i][0])]
        u, v, z = project(f, points[i:i + 1])
        inside.append(bool(z[0] > 0 and 0 <= u[0] < f["camera"]["w"] and 0 <= v[0] < f["camera"]["h"]))
    print(json.dumps({"step": "read", "points": int(len(points)), "frames": len(frames), "held": len(held),
                      "visibilityLandsInside": round(float(np.mean(inside)), 3)}), flush=True)

    # 2. Labels by vote.
    group = label_points(points, seen, frames, run / "labels", group_of, use)
    print(json.dumps({"step": "labelled", "massive": int((group == 1).sum()), "ground": int((group == 2).sum()),
                      "other": int((group == 0).sum()), "unlabelled": int((group == 255).sum())}), flush=True)

    # 3. Colonies: the points labelled massive coral, or (by="shape", where
    # the labels cannot be trusted, as on a smoothed model's texture)
    # everything standing above the seabed that is not labelled ground.
    if by == "shape":
        group = np.where(standing(metres) & (group != 2), 1, np.where(group == 1, 0, group)).astype(np.uint8)
        print(json.dumps({"step": "standing", "points": int((group == 1).sum())}), flush=True)
    massive = np.flatnonzero(group == 1)
    ground = np.flatnonzero(group == 2)
    found = colonies_of(metres[massive])
    library_said = json.loads((library / "library.json").read_text())
    shelf = [library / e["file"] for kind in ("massive", "brain") for e in library_said["kinds"].get(kind, [])]
    templates: dict = {}

    from .patch import write_usd  # noqa: F401  (the same writer the patch uses, kept at hand)
    import open3d as o3d

    ground_tree = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(
        o3d.utility.Vector3dVector(np.c_[metres[ground, :2], np.zeros(len(ground))])))
    # The reconstruction alone, as fair as the others: its Poisson surface
    # from only the points the held-back frames did not make; and which of it
    # was seen, which is where it is within a point's spacing of a point.
    raw = _poisson(metres, colours, depth=10)
    raw_v, raw_f = np.asarray(raw.vertices), np.asarray(raw.triangles)
    raw_c = np.asarray(raw.vertex_colors)
    all_tree = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(metres)))
    print(json.dumps({"step": "surface", "vertices": int(len(raw_v)), "triangles": int(len(raw_f))}), flush=True)
    colonies, priors, posteriors, crops = [], [], [], []
    print(json.dumps({"step": "colonies", "found": len(found)}), flush=True)
    for k, which in enumerate(found):
        labelled = massive[which]
        middle = np.median(metres[labelled, :2], 0)
        n, idx, _ = ground_tree.search_radius_vector_3d(np.r_[middle, 0.0], 0.6)
        ground_z = (float(np.median(metres[ground[np.asarray(idx)], 2])) if n >= 20
                    else float(np.percentile(metres[labelled, 2], 5)))
        region = region_of(metres, group, labelled, ground_z)
        prior, chosen, runners_up = best_template(shelf, metres[region], ground_z, views[region], templates)
        # The seen part of the reconstruction over this colony.
        r = max(prior["acrossM"]) / 2 + 0.05
        inside = (np.linalg.norm(raw_v[:, :2] - prior["centre"], axis=1) < r) & (raw_v[:, 2] > ground_z + 0.01)
        seen = np.zeros(len(raw_v), bool)
        for i in np.flatnonzero(inside):
            seen[i] = all_tree.search_knn_vector_3d(raw_v[i], 1)[2][0] < 0.015 ** 2
        crop = raw_f[inside[raw_f].all(1)]
        seen_f = raw_f[seen[raw_f].all(1)]
        if len(crop):
            crops.append((raw_v, crop))
            used = np.unique(crop)
            remap = -np.ones(len(raw_v), dtype=int)
            remap[used] = np.arange(len(used))
            _write_ply(out / f"colony-{k:03d}-raw.ply", raw_v[used], remap[crop], raw_c[used])
        post = blend(prior, raw_v, seen_f, raw_c)
        priors.append((prior["vertices"], prior["faces"]))
        posteriors.append((post["vertices"], post["faces"]))
        colonies.append({k2: post[k2] for k2 in ("centre", "yawDeg", "acrossM", "heightM", "groundZ",
                                                  "measuredShare", "meanShiftM", "height")}
                        | {"points": int(len(region)), "labelled": int(len(labelled)),
                           "template": chosen.name, "fitResidualM": prior["fitResidualM"],
                           "nextBest": runners_up[1:]})
        _write_ply(out / f"colony-{k:03d}.ply", post["vertices"], post["faces"], post["colours"])
        _write_ply(out / f"colony-{k:03d}-prior.ply", prior["vertices"], prior["faces"], prior["colours"])
        np.save(out / f"colony-{k:03d}-posterior.npy", post["posteriorM"].astype("float32"))
        print(json.dumps({"step": "colony", "n": k + 1, "of": len(found), **colonies[-1]}), flush=True)

    # 6. Scored on the held-back frames, where they show massive coral.
    scores = {"raw": [], "library": [], "fused": []}
    shown = []
    for fi in sorted(held):
        frame = frames[fi]
        name = pathlib.Path(frame["name"]).stem
        truth_path = dense / "stereo" / "depth_maps" / f"{frame['name']}.geometric.bin"
        if not truth_path.is_file():
            continue
        truth = read_depth(truth_path)
        lab = np.asarray(Image.open(run / "labels" / f"{name}.png"))
        if lab.ndim == 3:
            lab = lab[..., 0]
        renders = {}
        for key, meshes in (("raw", crops), ("library", priors), ("fused", posteriors)):
            if not meshes:
                continue
            depth, us, vs = depth_seen(meshes, frame, to_model)
            renders[key] = depth
        if not renders:
            continue
        rows, cols = vs.astype(int), us.astype(int)
        t = truth[rows, cols]
        m = (group_of[lab[rows, cols]] == 1) & (t > 0)
        # The same pixels for all three: where every one of them sees coral.
        common = m.copy()
        for d in renders.values():
            common &= np.isfinite(d)
        for key, d in renders.items():
            if common.sum() < 50:
                continue
            err = np.abs(d[common] - t[common]) * scale
            scores[key].append({"frame": name, "pixels": int(common.sum()), "medianM": float(np.median(err)),
                                "coverage": float(np.isfinite(d[m]).mean()) if m.any() else 0.0})
        if common.sum() >= 50:
            shown.append((fi, int(common.sum())))

    summary = {k: ({"frames": len(v), "medianErrorM": round(float(np.median([s["medianM"] for s in v])), 4),
                    "meanCoverage": round(float(np.mean([s["coverage"] for s in v])), 3)} if v else None)
               for k, v in scores.items()}
    said = {"run": run.name, "frames": len(frames), "heldBack": len(held), "points": int(len(points)),
            "massivePoints": int(len(massive)), "groundPoints": int(len(ground)), "colonies": colonies,
            "scores": summary, "perFrame": scores, "best": sorted(shown, key=lambda s: -s[1])[:3],
            "settings": {"measuredM": MEASURED_M, "priorM": PRIOR_M, "reachM": REACH_M, "heldEvery": HELD_EVERY},
            "seconds": round(time.time() - started)}
    (out / "fused.json").write_text(json.dumps(said, indent=1))
    return said


def _poisson(points: np.ndarray, colours: np.ndarray, depth: int = 10):
    import open3d as o3d

    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.colors = o3d.utility.Vector3dVector(colours / 255.0)
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.05, max_nn=30))
    cloud.orient_normals_to_align_with_direction(np.array([0.0, 0.0, 1.0]))
    mesh, density = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(cloud, depth=depth)
    density = np.asarray(density)
    mesh.remove_vertices_by_mask(density < np.quantile(density, 0.05))
    return mesh


def _write_ply(path: pathlib.Path, v: np.ndarray, f: np.ndarray, c: np.ndarray) -> None:
    head = ("ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n")
    vert = np.zeros(len(v), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    vert["x"], vert["y"], vert["z"] = v[:, 0], v[:, 1], v[:, 2]
    rgb = (np.clip(c, 0, 1) * 255).astype(np.uint8)
    vert["r"], vert["g"], vert["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    face = np.zeros(len(f), dtype=[("n", "u1"), ("i", "<i4", 3)])
    face["n"], face["i"] = 3, f
    path.write_bytes(head.encode() + vert.tobytes() + face.tobytes())


# ── a picture of it ──────────────────────────────────────────────────────────

def _colour_seen(meshes: list[tuple[np.ndarray, np.ndarray, np.ndarray]], frame: dict, to_model, stride: int = 1):
    """What each pixel of a frame sees in these coloured meshes: colour, and
    whether it hit anything."""
    import open3d as o3d

    scene = o3d.t.geometry.RaycastingScene()
    tables = []
    for v, f, c in meshes:
        scene.add_triangles(o3d.core.Tensor(to_model(v).astype("float32")), o3d.core.Tensor(f.astype("uint32")))
        tables.append((f, c))
    cam = frame["camera"]
    us, vs = np.meshgrid(np.arange(0, cam["w"], stride) + 0.5, np.arange(0, cam["h"], stride) + 0.5)
    dirs = np.stack([(us - cam["cx"]) / cam["fx"], (vs - cam["cy"]) / cam["fy"], np.ones_like(us)], -1) @ frame["R"]
    rays = o3d.core.Tensor(np.concatenate([np.broadcast_to(frame["centre"], dirs.shape), dirs], -1).astype("float32"))
    hit = scene.cast_rays(rays)
    geometry, prim = hit["geometry_ids"].numpy(), hit["primitive_ids"].numpy()
    uv = hit["primitive_uvs"].numpy()
    out = np.zeros(us.shape + (3,))
    seen = np.isfinite(hit["t_hit"].numpy())
    for g, (f, c) in enumerate(tables):
        at = seen & (geometry == g)
        tri = f[prim[at]]
        w = np.stack([1 - uv[at, 0] - uv[at, 1], uv[at, 0], uv[at, 1]], -1)
        out[at] = (c[tri] * w[..., None]).sum(1)
    return out, seen


def picture(run: pathlib.Path, frame_index: int, out: pathlib.Path) -> None:
    """A held-back frame beside the reconstruction alone, the library alone and
    the fusion, rendered from where that frame was taken."""
    from PIL import Image, ImageDraw

    dense = run / "colmap" / "dense"
    _, frames = read_cameras(dense / "sparse-text")
    points, colours, seen = read_fused(dense)
    use = set(range(len(frames))) - set(range(0, len(frames), HELD_EVERY))
    views = np.array([sum(1 for f in s if int(f) in use) for s in seen])
    keep = views >= 2
    points, colours = points[keep], colours[keep]
    scale = float(json.loads((run / "scale.json").read_text()).get("scale") or 1.0)
    to_patch, rotation, centre = frame_of(points, np.array([f["centre"] for f in frames]), scale)
    to_model = lambda p: (np.asarray(p) / scale) @ rotation + centre
    metres = to_patch(points)
    said = json.loads((run / "prior" / "fused.json").read_text())
    raw = _poisson(metres, colours, depth=10)
    raw_v, raw_f = np.asarray(raw.vertices), np.asarray(raw.triangles)
    raw_c = np.asarray(raw.vertex_colors)
    versions = {"reconstruction alone": [], "library alone": [], "fused": []}
    for k, c in enumerate(said["colonies"]):
        r = max(c["acrossM"]) / 2 + 0.05
        inside = np.linalg.norm(raw_v[:, :2] - c["centre"], axis=1) < r
        tri = raw_f[inside[raw_f].all(1)]
        if len(tri):
            versions["reconstruction alone"].append((raw_v, tri, raw_c))
        versions["library alone"].append(read_library_ply(run / "prior" / f"colony-{k:03d}-prior.ply"))
        versions["fused"].append(read_library_ply(run / "prior" / f"colony-{k:03d}.ply"))
    frame = frames[frame_index]
    photo = np.asarray(Image.open(dense / "images" / frame["name"]).convert("RGB")).astype(float) / 255.0
    panels = [("held-back photo", photo)]
    for name, meshes in versions.items():
        colour, hit = _colour_seen(meshes, frame, to_model)
        panel = photo * 0.35
        panel[hit] = colour[hit]
        panels.append((name, panel))
    h, w = photo.shape[:2]
    sheet = Image.new("RGB", (w * 2 + 10, h * 2 + 70), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (name, panel) in enumerate(panels):
        x, y = (i % 2) * (w + 10), (i // 2) * (h + 35) + 30
        sheet.paste(Image.fromarray((np.clip(panel, 0, 1) * 255).astype(np.uint8)), (x, y))
        draw.text((x + 6, y - 22), name, fill="black")
    sheet.save(out)


# ── scored against a scene whose 3D is known ─────────────────────────────────

def similarity(source: np.ndarray, target: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Scale, rotation and shift taking source points onto target (Umeyama)."""
    ms, mt = source.mean(0), target.mean(0)
    a, b = source - ms, target - mt
    u, d, vt = np.linalg.svd(b.T @ a / len(source))
    flip = np.eye(3)
    if np.linalg.det(u @ vt) < 0:
        flip[2, 2] = -1
    rotation = u @ flip @ vt
    scale = float(np.trace(np.diag(d) @ flip) / (a ** 2).sum(1).mean())
    return scale, rotation, mt - scale * rotation @ ms


def read_truth(path: pathlib.Path):
    data = path.read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    head = data[:end].decode().split("\n")
    nv = int(next(h for h in head if h.startswith("element vertex")).split()[-1])
    nf = int(next(h for h in head if h.startswith("element face")).split()[-1])
    vert = np.frombuffer(data, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("class", "u1"), ("colony", "<i4")],
                         count=nv, offset=end)
    face = np.frombuffer(data, dtype=[("n", "u1"), ("i", "<i4", 3)], count=nf, offset=end + vert.nbytes)
    return (np.stack([vert["x"], vert["y"], vert["z"]], 1).astype(float), face["i"].astype(np.int64),
            vert["class"].copy(), vert["colony"].copy())


def against_truth(run: pathlib.Path, near_m: float = 0.02) -> dict:
    """The reconstruction alone, the library alone and the fusion, against the
    scene they were filmed from: over the parts of each colony some frame saw,
    and over the parts no frame did."""
    import open3d as o3d

    told = json.loads((run / "cameras.json").read_text())
    truth_centres = {c["name"]: np.array(c["centre"]) for c in told["frames"]}
    _, frames = read_cameras(run / "colmap" / "dense" / "sparse-text")
    names = [f["name"] for f in frames if f["name"] in truth_centres]
    model_centres = np.array([f["centre"] for f in frames if f["name"] in truth_centres])
    s, rot, shift = similarity(model_centres, np.array([truth_centres[n] for n in names]))
    aligned = (s * model_centres @ rot.T + shift)
    residual = float(np.median(np.linalg.norm(aligned - np.array([truth_centres[n] for n in names]), axis=1)))

    # Patch metres to model units to the scene's metres.
    dense = run / "colmap" / "dense"
    points, colours, seen = read_fused(dense)
    use = set(range(len(frames))) - set(range(0, len(frames), HELD_EVERY))
    views = np.array([sum(1 for f in sv if int(f) in use) for sv in seen])
    points = points[views >= 2]
    scale = float(json.loads((run / "scale.json").read_text()).get("scale") or 1.0)
    from .patch import frame_of as fit
    centre, rotation, _ = fit(points, np.array([f["centre"] for f in frames]))
    to_truth = lambda p: s * (((np.asarray(p) / scale) @ rotation + centre) @ rot.T) + shift

    tv, tf, tclass, tcolony = read_truth(run / "truth.ply")
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(tv.astype("float32")), o3d.core.Tensor(tf.astype("uint32")))
    # What can be known at all: a colony's surface that faces out, not its
    # base resting on the sand or the underside of an overhang.
    sand_faces = tf[(tclass[tf] == CLASS_SAND).all(1)]
    sand = o3d.t.geometry.RaycastingScene()
    sand.add_triangles(o3d.core.Tensor(tv.astype("float32")), o3d.core.Tensor(sand_faces.astype("uint32")))
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(tv), o3d.utility.Vector3iVector(tf))
    mesh.compute_vertex_normals()
    normal_z = np.asarray(mesh.vertex_normals)[:, 2]
    candidates = np.flatnonzero(tcolony >= 0)[::3]
    down = np.c_[tv[candidates, :2], np.full(len(candidates), 10.0), np.zeros((len(candidates), 2)),
                 -np.ones(len(candidates))]
    ground_under = 10.0 - sand.cast_rays(o3d.core.Tensor(down.astype("float32")))["t_hit"].numpy()
    knowable = (tv[candidates, 2] > ground_under + 0.03) & (normal_z[candidates] > -0.2)
    # Which colonies were found: a true colony is matched by a found one
    # whose centre stands within its footprint.
    said = json.loads((run / "prior" / "fused.json").read_text())
    found_at = np.array([to_truth(np.array([[*c["centre"], c["groundZ"]]]))[0, :2] for c in said["colonies"]]) \
        if said["colonies"] else np.zeros((0, 2))
    matched = set()
    for c in told["colonies"]:
        k = c["id"]
        here = tv[tcolony == k]
        radius = max(float(np.abs(here[:, :2] - [c["x"], c["y"]]).max()), 0.15)
        if len(found_at) and np.min(np.linalg.norm(found_at - [c["x"], c["y"]], axis=1)) < radius:
            matched.add(k)
    sample = candidates[knowable & np.isin(tcolony[candidates], list(matched))]
    pts = tv[sample]
    # Which of it a frame saw: unoccluded from its centre, in front of it and
    # inside its picture.
    seen_by = np.zeros(len(sample), bool)
    w, h, focal = told["width"], told["height"], told["focalPx"]
    for c in told["frames"]:
        m = np.array(c["world_from_camera"])
        cam = (pts - m[:3, 3]) @ m[:3, :3]                  # Blender camera: -z forward, +y up
        z = -cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = focal * cam[:, 0] / z + w / 2
            v = -focal * cam[:, 1] / z + h / 2
        inside = (z > 0.1) & (u >= 0) & (u < w) & (v >= 0) & (v < h)
        if not inside.any():
            continue
        origin = np.asarray(c["centre"])
        d = pts[inside] - origin
        dist = np.linalg.norm(d, axis=1)
        rays = o3d.core.Tensor(np.c_[np.broadcast_to(origin, d.shape), d / dist[:, None]].astype("float32"))
        hit = scene.cast_rays(rays)["t_hit"].numpy()
        seen_by[np.flatnonzero(inside)[np.abs(hit - dist) < 0.01]] = True

    out = {"cameraFitResidualM": round(residual, 4), "scaleModelToMetres": round(s, 5),
           "trueColonies": len(told["colonies"]), "found": len(said["colonies"]), "matched": len(matched),
           "matchedKinds": sorted(c["kind"] for c in told["colonies"] if c["id"] in matched),
           "missedKinds": sorted(c["kind"] for c in told["colonies"] if c["id"] not in matched),
           "scoredVertices": int(len(sample)), "knowableShare": round(float(knowable.mean()), 3),
           "seenShare": round(float(seen_by.mean()), 3), "versions": {}}
    for key, suffix in (("reconstruction alone", "-raw"), ("library alone", "-prior"), ("fused", "")):
        version = o3d.t.geometry.RaycastingScene()
        added = 0
        for k in range(len(said["colonies"])):
            path = run / "prior" / f"colony-{k:03d}{suffix}.ply"
            if not path.is_file():
                continue
            v, f, _ = read_library_ply(path)
            version.add_triangles(o3d.core.Tensor(to_truth(v).astype("float32")),
                                  o3d.core.Tensor(f.astype("uint32")))
            added += 1
        if not added:
            continue
        distance = version.compute_distance(o3d.core.Tensor(pts.astype("float32"))).numpy()
        row = {}
        for part, mask in (("seen", seen_by), ("hidden", ~seen_by)):
            if mask.any():
                row[part] = {"medianM": round(float(np.median(distance[mask])), 4),
                             f"within{int(near_m * 100)}cm": round(float((distance[mask] < near_m).mean()), 3)}
        out["versions"][key] = row
    (run / "prior" / "truth.json").write_text(json.dumps(out, indent=1))
    return out


def against_mesh(run: pathlib.Path, near_m: float = 0.02) -> dict:
    """The three versions against a real reef's mesh (truth.obj, rendered by
    synthetic/from_model.py), over each colony found: the true surface within
    its footprint and above the ground around it, split by whether the
    rendered camera path could see it."""
    import open3d as o3d

    told = json.loads((run / "cameras.json").read_text())
    truth_centres = {c["name"]: np.array(c["centre"]) for c in told["frames"]}
    _, frames = read_cameras(run / "colmap" / "dense" / "sparse-text")
    names = [f["name"] for f in frames if f["name"] in truth_centres]
    model_centres = np.array([f["centre"] for f in frames if f["name"] in truth_centres])
    s, rot, shift = similarity(model_centres, np.array([truth_centres[n] for n in names]))
    residual = float(np.median(np.linalg.norm(s * model_centres @ rot.T + shift
                                              - np.array([truth_centres[n] for n in names]), axis=1)))
    dense = run / "colmap" / "dense"
    points, _, seen = read_fused(dense)
    use = set(range(len(frames))) - set(range(0, len(frames), HELD_EVERY))
    views = np.array([sum(1 for f in sv if int(f) in use) for sv in seen])
    points = points[views >= 2]
    scale = float(json.loads((run / "scale.json").read_text()).get("scale") or 1.0)
    from .patch import frame_of as fit
    centre, rotation, _ = fit(points, np.array([f["centre"] for f in frames]))
    to_truth = lambda p: s * (((np.asarray(p) / scale) @ rotation + centre) @ rot.T) + shift

    mesh = o3d.io.read_triangle_mesh(str(run / "truth.obj"))
    mesh.compute_vertex_normals()
    tv, tf = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    normal_z = np.asarray(mesh.vertex_normals)[:, 2]
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(tv.astype("float32")), o3d.core.Tensor(tf.astype("uint32")))

    said = json.loads((run / "prior" / "fused.json").read_text())
    picked = []
    for k, c in enumerate(said["colonies"]):
        middle = to_truth(np.array([[*c["centre"], c["groundZ"]]]))[0]
        r = max(c["acrossM"]) / 2 + 0.1
        near = np.flatnonzero(np.linalg.norm(tv[:, :2] - middle[:2], axis=1) < r)
        ring = np.flatnonzero((np.linalg.norm(tv[:, :2] - middle[:2], axis=1) > r) &
                              (np.linalg.norm(tv[:, :2] - middle[:2], axis=1) < r + 0.4))
        ground = float(np.percentile(tv[ring, 2], 30)) if len(ring) > 50 else middle[2]
        picked.append(near[(tv[near, 2] > ground + 0.03) & (normal_z[near] > -0.2)])
    sample = np.unique(np.concatenate(picked)) if picked else np.zeros(0, int)
    sample = sample[::max(1, len(sample) // 60000)]
    pts = tv[sample]
    seen_by = np.zeros(len(sample), bool)
    w, h, focal = told["width"], told["height"], told["focalPx"]
    for c in told["frames"]:
        m = np.array(c["world_from_camera"])
        cam = (pts - m[:3, 3]) @ m[:3, :3]
        z = -cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = focal * cam[:, 0] / z + w / 2
            v = -focal * cam[:, 1] / z + h / 2
        inside = (z > 0.1) & (u >= 0) & (u < w) & (v >= 0) & (v < h)
        if not inside.any():
            continue
        origin = np.asarray(c["centre"])
        d = pts[inside] - origin
        dist = np.linalg.norm(d, axis=1)
        rays = o3d.core.Tensor(np.c_[np.broadcast_to(origin, d.shape), d / dist[:, None]].astype("float32"))
        hit = scene.cast_rays(rays)["t_hit"].numpy()
        seen_by[np.flatnonzero(inside)[np.abs(hit - dist) < 0.01]] = True

    out = {"cameraFitResidualM": round(residual, 4), "colonies": len(said["colonies"]),
           "scoredVertices": int(len(sample)), "seenShare": round(float(seen_by.mean()), 3) if len(sample) else None,
           "versions": {}}
    for key, suffix in (("reconstruction alone", "-raw"), ("library alone", "-prior"), ("fused", "")):
        version = o3d.t.geometry.RaycastingScene()
        added = 0
        for k in range(len(said["colonies"])):
            path = run / "prior" / f"colony-{k:03d}{suffix}.ply"
            if not path.is_file():
                continue
            v, f, _ = read_library_ply(path)
            version.add_triangles(o3d.core.Tensor(to_truth(v).astype("float32")),
                                  o3d.core.Tensor(f.astype("uint32")))
            added += 1
        if not added or not len(sample):
            continue
        distance = version.compute_distance(o3d.core.Tensor(pts.astype("float32"))).numpy()
        row = {}
        for part, mask in (("seen", seen_by), ("hidden", ~seen_by)):
            if mask.any():
                row[part] = {"points": int(mask.sum()), "medianM": round(float(np.median(distance[mask])), 4),
                             f"within{int(near_m * 100)}cm": round(float((distance[mask] < near_m).mean()), 3)}
        out["versions"][key] = row
    (run / "prior" / "mesh.json").write_text(json.dumps(out, indent=1))
    return out
