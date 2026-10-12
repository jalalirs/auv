"""A reef rebuilt from DeepReefMap's point cloud and the coral library.

DeepReefMap (Sauder et al. 2024, the authors of the Red Sea videos) turns a
GoPro swim into a point cloud in minutes, every point carrying a benthic class
down to the genus and an uncertainty on its depth. It covers the whole swim,
where COLMAP leaves holes, but it is soft: one camera's depth smears at the
edges, and nothing behind a colony was ever seen. A point cloud is also not a
model: nothing a renderer or a simulator can stand on.

So this rebuilds it as one:

  the seabed   a height map over the ground classes (sand, rubble, hard
               substrate), meshed and coloured from the points
  colonies     the coral points gathered colony by colony, each given the
               library colony of its own class (an Acropora gets the
               library's Acropora), sized and turned to its points
  the blend    each colony's surface pulled towards its points as far as they
               can be trusted: the gain is the library's uncertainty over the
               sum of it and the point's (DeepReefMap's own), Kalman's, so a
               confident point moves the surface and a smeared one barely does

The cloud has no scale of its own; it is given one by the camera's height over
the reef (assumed, 1.5 m, the same as every patch we have placed), and said so.

    run/                        a DeepReefMap output (iocean's copy, which keeps
      point_cloud_tsdf.csv      the cameras and holds every Nth frame back)
      poses.npy intrinsics.npy frames.json
      held.npz                  the held frames' depth, uncertainty and classes
    out/
      model.ply                 seabed and colonies, coloured
      colonies.json             each colony: class, library colony, sizes
      score.json                the held frames, against the model
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from .prior import _write_ply, read_library_ply

CAMERA_HEIGHT_M = 1.5      # assumed: the camera over the reef, as for every patch placed so far
CELL_M = 0.04              # the seabed's cells
REACH_M = 0.05             # how far a point may pull a surface
PRIOR_M = 0.03             # how far the library's surface is trusted, as one standard deviation

GROUND = {"sand", "rubble", "unknown hard substrate", "algae covered substrate", "seagrass", "dark", "transect line"}
IGNORED = {"human", "background", "fish", "transect tools", "trash", "other animal", "sea urchin", "sea cucumber",
           "clam", "anemone"}
# DeepReefMap's class, the library's kind, and the library's forms in order of preference.
CORAL = {
    "stylophora alive": ("branching", ["stylophora"]),
    "pocillopora alive": ("branching", ["pocillopora"]),
    "acropora alive": ("branching", ["acropora"]),
    "branching alive": ("branching", []), "branching dead": ("branching", []),
    "branching bleached": ("branching", []),
    "table acropora alive": ("table", []), "table acropora dead": ("table", []),
    "millepora": ("encrusting", ["millepora"]),
    "turbinaria": ("encrusting", ["plate"]),
    "massive/meandering alive": ("massive", ["porites", "favites"]),
    "massive/meandering dead": ("massive", ["porites", "favites"]),
    "massive/meandering bleached": ("massive", ["porites", "favites"]),
    "meandering alive": ("brain", ["brain", "lobophyllia"]), "meandering dead": ("brain", []),
    "meandering bleached": ("brain", []),
    "other coral alive": ("massive", []), "other coral dead": ("massive", []),
    "other coral bleached": ("massive", []),
    "sponge": ("sponge", []),
}


# ── reading ──────────────────────────────────────────────────────────────────

def read_run(run: pathlib.Path, class_to_label: dict) -> dict:
    label_to_class = {int(v): k for k, v in class_to_label.items()}
    raw = np.genfromtxt(run / "point_cloud_tsdf.csv", delimiter=",", skip_header=1,
                        usecols=(0, 1, 2, 3, 4, 5, 7, 12))
    names = np.array([label_to_class.get(int(k), "unknown") for k in raw[:, 6]])
    return {"xyz": raw[:, :3], "rgb": raw[:, 3:6] / 255.0, "label": raw[:, 6].astype(int), "class": names,
            "uncertainty": raw[:, 7],
            "poses": np.load(run / "poses.npy"), "intrinsics": np.load(run / "intrinsics.npy"),
            "frames": json.loads((run / "frames.json").read_text()), "label_to_class": label_to_class}


def level_and_scale(xyz: np.ndarray, cameras: np.ndarray, height_m: float = CAMERA_HEIGHT_M,
                    height_from: str = "") -> dict:
    """The reef's plane made the ground (z up, the cameras above it), the swim
    along x, and the units made metres by the camera's height over the reef."""
    centre = np.median(xyz, axis=0)
    sample = xyz[np.random.default_rng(0).choice(len(xyz), min(200000, len(xyz)), replace=False)] - centre
    _, _, vt = np.linalg.svd(sample, full_matrices=False)
    rotation = vt.copy()                       # rows: along, across, up
    if np.median((cameras - centre) @ rotation[2]) < 0:
        rotation[2] *= -1
        rotation[1] *= -1
    level = (xyz - centre) @ rotation.T
    above = np.median(((cameras - centre) @ rotation.T)[:, 2]) - np.median(level[:, 2])
    scale = height_m / max(above, 1e-9)
    said = (f"measured: the camera {height_m} m over the reef ({height_from}), which made one unit {scale:.2f} m"
            if height_from else
            f"assumed: the camera {height_m} m over the reef, which made one unit {scale:.2f} m")
    return {"centre": centre, "rotation": rotation, "scale": float(scale), "said": said,
            "cameraHeightM": float(height_m), "measured": bool(height_from)}


def to_model(p, frame):
    return ((np.asarray(p) - frame["centre"]) @ frame["rotation"].T) * frame["scale"]


def from_model(p, frame):
    return (np.asarray(p) / frame["scale"]) @ frame["rotation"] + frame["centre"]


# ── the seabed ───────────────────────────────────────────────────────────────

def _fill(grid: np.ndarray, known: np.ndarray, rounds: int = 400) -> np.ndarray:
    """Holes filled from their neighbours, outward, until none is left."""
    g, k = grid.copy(), known.copy()
    for _ in range(rounds):
        if k.all():
            break
        total = np.zeros_like(g)
        count = np.zeros_like(g)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            shifted = np.roll(np.roll(g * k[..., None] if g.ndim == 3 else g * k, dy, 0), dx, 1)
            kk = np.roll(np.roll(k, dy, 0), dx, 1)
            total += shifted
            count += kk[..., None] if g.ndim == 3 else kk
        fresh = ~k & ((count[..., 0] if g.ndim == 3 else count) > 0)
        g[fresh] = (total / np.maximum(count, 1))[fresh]
        k = k | fresh
    return g


def seabed_of(xyz: np.ndarray, rgb: np.ndarray, ground: np.ndarray, cell: float = CELL_M) -> dict:
    """A height map over the ground classes: the median height in each cell,
    holes filled from around them, meshed and coloured."""
    lo = np.percentile(xyz[:, :2], 0.5, axis=0) - 0.1
    hi = np.percentile(xyz[:, :2], 99.5, axis=0) + 0.1
    n = np.ceil((hi - lo) / cell).astype(int) + 1
    ij = np.clip(((xyz[:, :2] - lo) / cell).astype(int), 0, n - 1)
    key = ij[:, 1] * n[0] + ij[:, 0]
    height = np.full(n[1] * n[0], np.nan)
    colour = np.zeros((n[1] * n[0], 3))
    g = np.where(ground)[0]
    order = g[np.argsort(key[g])]
    cells, starts = np.unique(key[order], return_index=True)
    for c, a, b in zip(cells, starts, list(starts[1:]) + [len(order)]):
        which = order[a:b]
        if len(which) < 3:
            continue
        height[c] = np.median(xyz[which, 2])
        colour[c] = np.median(rgb[which], axis=0)
    # Anything seen, coral included, says where the reef is; only ground says how high its floor is.
    seen = np.zeros(n[1] * n[0], bool)
    seen[np.unique(key)] = True
    known = ~np.isnan(height)
    h = _fill(np.nan_to_num(height).reshape(n[1], n[0]), known.reshape(n[1], n[0]))
    # Smoothed over a 3 by 3 cell window, once: one camera's depth is noisy
    # cell to cell, and twice over five cells flattened the reef's ridges.
    acc = np.zeros_like(h)
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            acc += np.roll(np.roll(h, dy, 0), dx, 1)
    h = acc / 9.0
    c = _fill(colour.reshape(n[1], n[0], 3), known.reshape(n[1], n[0]))
    keep = seen.reshape(n[1], n[0])
    # Grown a little, so the floor runs under the colonies at the edge of the swim.
    for _ in range(3):
        keep = keep | np.roll(keep, 1, 0) | np.roll(keep, -1, 0) | np.roll(keep, 1, 1) | np.roll(keep, -1, 1)
    xs = lo[0] + np.arange(n[0]) * cell
    ys = lo[1] + np.arange(n[1]) * cell
    gx, gy = np.meshgrid(xs, ys)
    v = np.stack([gx.ravel(), gy.ravel(), h.ravel()], 1)
    idx = np.arange(n[0] * n[1]).reshape(n[1], n[0])
    a, b, cc, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    quads = np.stack([a.ravel(), b.ravel(), cc.ravel(), d.ravel()], 1)
    inside = keep.ravel()[quads].all(1)
    # No curtains: a cell whose corners differ by more than its own width
    # several times over is a fill across a gap, not ground.
    hz = h.ravel()[quads]
    inside &= (hz.max(1) - hz.min(1)) < 8 * cell
    q = quads[inside]
    faces = np.concatenate([q[:, [0, 1, 3]], q[:, [0, 3, 2]]])
    return {"v": v, "f": faces, "c": c.reshape(-1, 3), "lo": lo, "cell": cell, "n": n, "h": h}


def floor_at(seabed: dict, xy: np.ndarray) -> np.ndarray:
    ij = np.clip(((np.asarray(xy) - seabed["lo"]) / seabed["cell"]).astype(int), 0, seabed["n"] - 1)
    return seabed["h"][ij[..., 1], ij[..., 0]]


# ── the colonies ─────────────────────────────────────────────────────────────

def colonies_of(xyz: np.ndarray, coral: np.ndarray, kinds: np.ndarray, eps: float = 0.12, least: int = 60):
    """Coral points gathered into colonies, kind by kind, so two genera touching
    are two colonies."""
    import open3d as o3d

    out = []
    for kind in np.unique(kinds[coral]):
        which = np.where(coral & (kinds == kind))[0]
        if len(which) < least:
            continue
        cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(xyz[which]))
        labels = np.asarray(cloud.cluster_dbscan(eps=eps, min_points=12))
        for k in range(labels.max() + 1):
            members = which[labels == k]
            if len(members) >= least:
                out.append(members)
    return out


# How wide one colony of each kind gets on these reefs, at most: a patch of
# coral points wider than this is several colonies touching, not one big one.
MOST_ACROSS_M = {"branching": 0.6, "table": 1.2, "encrusting": 0.5, "massive": 1.2, "brain": 0.8, "sponge": 0.5}
# How many triangles each kind keeps when thinned: a branching colony is its
# branches and goes to crystals below a few thousand; a massive one is a dome.
TRIANGLES_OF = {"branching": 6000, "table": 6000, "encrusting": 2500, "massive": 2500, "brain": 4000, "sponge": 2500}


def pieces_of(points: np.ndarray, most: float, rng=np.random.default_rng(0)) -> list[np.ndarray]:
    """A patch cut into colony-sized pieces by k-means on the ground plane, as
    many as its footprint needs; indices into `points`."""
    area = footprint_m2(points)
    k = int(np.ceil(area / (0.6 * most * most)))
    if k <= 1:
        return [np.arange(len(points))]
    xy = points[:, :2]
    centres = xy[rng.choice(len(xy), k, replace=False)]
    for _ in range(15):
        which = np.argmin(((xy[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            if (which == j).any():
                centres[j] = xy[which == j].mean(0)
    return [np.where(which == j)[0] for j in range(k) if (which == j).sum() >= 12]


def footprint_m2(points: np.ndarray, cell: float = 0.02) -> float:
    """The ground the points cover, counted in 2 cm cells."""
    cells = np.unique(np.floor(points[:, :2] / cell).astype(np.int64), axis=0)
    return float(len(cells)) * cell * cell


def shelf_of(library: pathlib.Path, kind: str, forms: list[str]) -> list[dict]:
    told = json.loads((library / "library.json").read_text())["kinds"]
    entries = told.get(kind) or told.get("massive")
    preferred = [e for e in entries if e.get("form") in forms] if forms else []
    return preferred or entries


_THINNED: dict = {}


def thinned(path: pathlib.Path, triangles: int):
    """A library colony with at most `triangles` triangles, its colours kept;
    worked out once per file."""
    key = (str(path), triangles)
    if key not in _THINNED:
        v, f, c = read_library_ply(path)
        if triangles and len(f) > triangles:
            import open3d as o3d

            mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(v), o3d.utility.Vector3iVector(f))
            mesh.vertex_colors = o3d.utility.Vector3dVector(c)
            mesh = mesh.simplify_quadric_decimation(triangles)
            v, f, c = (np.asarray(mesh.vertices), np.asarray(mesh.triangles).astype(np.int64),
                       np.asarray(mesh.vertex_colors))
        _THINNED[key] = (v, f, c)
    return _THINNED[key]


def fit_colony(points: np.ndarray, uncertainty: np.ndarray, floor: float, shelf: list[dict],
               library: pathlib.Path, triangles: int = 0) -> dict:
    """The library colony that best fits these points, sized and turned to
    them, with a height that is the measured one and the library's weighed by
    how sure each is."""
    import open3d as o3d

    centre = np.median(points[:, :2], axis=0)
    # Across as the circle of the same footprint: a long thin patch is not a
    # colony as wide as it is long.
    across = max(2.0 * float(np.sqrt(footprint_m2(points) / np.pi)), 0.08)
    measured_h = max(float(np.percentile(points[:, 2], 95) - floor), 0.02)
    sigma_m = float(np.clip(np.median(uncertainty), 0.01, 0.3))
    best = None
    for entry in shelf:
        v0, f0, c0 = thinned(library / entry["file"], triangles)
        v0 = v0 - [v0[:, 0].mean(), v0[:, 1].mean(), v0[:, 2].min()]
        wide = max(float(np.ptp(v0[:, 0])), float(np.ptp(v0[:, 1])), 1e-6)
        prior_h = float(np.ptp(v0[:, 2])) * across / wide
        sigma_p = 0.3 * prior_h + 0.02
        height = (measured_h / sigma_m ** 2 + prior_h / sigma_p ** 2) / (1 / sigma_m ** 2 + 1 / sigma_p ** 2)
        for turn in (0.0, np.pi / 2, np.pi, 1.5 * np.pi):
            ca, sa = np.cos(turn), np.sin(turn)
            v = v0 * [across / wide, across / wide, height / max(float(np.ptp(v0[:, 2])), 1e-6)]
            v = v @ np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]]).T + [centre[0], centre[1], floor]
            scene = o3d.t.geometry.RaycastingScene()
            scene.add_triangles(o3d.core.Tensor(v.astype(np.float32)), o3d.core.Tensor(f0.astype(np.uint32)))
            miss = float(np.mean(scene.compute_distance(o3d.core.Tensor(points.astype(np.float32))).numpy()))
            if best is None or miss < best["miss"]:
                best = {"v": v, "f": f0, "c": c0, "miss": miss, "file": entry["file"], "form": entry.get("form"),
                        "turn": turn, "acrossM": across, "measuredH": measured_h, "priorH": prior_h,
                        "heightM": height, "sigmaMeasuredM": sigma_m, "sigmaPriorM": sigma_p}
    return best


def pull(fit: dict, points: np.ndarray, colours: np.ndarray, uncertainty: np.ndarray) -> dict:
    """The library surface moved towards the points that see it: each vertex by
    the gain prior^2 / (prior^2 + point^2) along its own normal, the offsets
    smoothed over the mesh, and its colour taken towards theirs by the same
    gain. Vertices no point reaches keep the library's shape and colour."""
    import open3d as o3d

    v, f = fit["v"].copy(), fit["f"]
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(v), o3d.utility.Vector3iVector(f))
    mesh.compute_vertex_normals()
    normal = np.asarray(mesh.vertex_normals)
    search = o3d.core.nns.NearestNeighborSearch(o3d.core.Tensor(points.astype(np.float32)))
    search.knn_index()
    idx, d2 = search.knn_search(o3d.core.Tensor(v.astype(np.float32)), 1)
    idx, dist = idx.numpy()[:, 0], np.sqrt(d2.numpy()[:, 0])
    near = dist < REACH_M
    sigma_pt = np.clip(uncertainty[idx], 0.005, 0.3)
    gain = np.where(near, PRIOR_M ** 2 / (PRIOR_M ** 2 + sigma_pt ** 2), 0.0)
    along = np.einsum("ij,ij->i", points[idx] - v, normal)
    offset = gain * along
    # Smoothed: neighbours averaged twice, so one smeared point is not a spike.
    for _ in range(2):
        total, count = np.zeros(len(v)), np.zeros(len(v))
        for a, b in ((0, 1), (1, 2), (2, 0)):
            np.add.at(total, f[:, a], offset[f[:, b]])
            np.add.at(count, f[:, a], 1)
        offset = 0.5 * offset + 0.5 * total / np.maximum(count, 1)
    v = v + normal * offset[:, None]
    # The whole colony tinted to what its points look like (the library's
    # pattern kept, its colour the video's), then the seen vertices taken
    # further towards the points nearest them.
    tint = np.median(colours, axis=0) / np.maximum(np.median(fit["c"], axis=0), 1e-3)
    base = np.clip(fit["c"] * (0.3 + 0.7 * tint), 0, 1)
    c = base * (1 - gain[:, None]) + colours[idx] * gain[:, None]
    return {**fit, "v": v, "c": c, "seenShare": float(near.mean()), "meanGain": float(gain[near].mean()) if near.any() else 0.0}


# ── the whole of it ──────────────────────────────────────────────────────────

def rebuild(run: pathlib.Path, library: pathlib.Path, out: pathlib.Path, class_to_label: dict, say=print,
            camera_height_m: float = CAMERA_HEIGHT_M, camera_height_from: str = "",
            colony_triangles: int = 2000, video: dict | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    told = read_run(run, class_to_label)
    cameras = told["poses"][:, :3, 3]
    frame = level_and_scale(told["xyz"], cameras, camera_height_m, camera_height_from)
    xyz = to_model(told["xyz"], frame)
    # DeepReefMap's uncertainty is in its own units, like its depths.
    uncertainty = told["uncertainty"] * frame["scale"]
    names = told["class"]
    ground = np.isin(names, list(GROUND))
    coral = np.isin(names, list(CORAL))
    say(f"  {len(xyz):,} points: {ground.mean():.0%} ground, {coral.mean():.0%} coral; {frame['said']}")
    seabed = seabed_of(xyz, told["rgb"], ground)
    kinds = np.array([CORAL.get(n, ("", []))[0] for n in names])
    groups = colonies_of(xyz, coral, kinds)
    say(f"  seabed {len(seabed['f']):,} triangles; {len(groups)} colonies")
    meshes, said = [(seabed["v"], seabed["f"], seabed["c"])], []
    cut = []
    for members in groups:
        kind = kinds[members][0]
        for piece in pieces_of(xyz[members], MOST_ACROSS_M.get(kind, 0.8)):
            cut.append(members[piece])
    say(f"  {len(groups)} coral patches cut into {len(cut)} colonies")
    for members in cut:
        values, counts = np.unique(names[members], return_counts=True)
        name = str(values[counts.argmax()])
        kind, forms = CORAL[name]
        # Seated on the low side: on a slope the median floor buries the
        # downhill edge's gap under the colony and leaves the uphill one sunk.
        floor = float(np.percentile(floor_at(seabed, xyz[members, :2]), 20))
        fit = fit_colony(xyz[members], uncertainty[members], floor, shelf_of(library, kind, forms), library,
                         triangles=TRIANGLES_OF.get(kind, colony_triangles) if colony_triangles else 0)
        fit = pull(fit, xyz[members], told["rgb"][members], uncertainty[members])
        meshes.append((fit["v"], fit["f"], fit["c"]))
        said.append({"class": name, "kind": kind, "form": fit["form"], "file": fit["file"], "points": int(len(members)),
                     "at": [round(float(x), 3) for x in np.median(xyz[members], axis=0)],
                     "acrossM": round(fit["acrossM"], 3), "measuredHeightM": round(fit["measuredH"], 3),
                     "libraryHeightM": round(fit["priorH"], 3), "heightM": round(fit["heightM"], 3),
                     "fitMissM": round(fit["miss"], 4), "seenShare": round(fit["seenShare"], 3),
                     "meanGain": round(fit["meanGain"], 3)})
    v = np.concatenate([m[0] for m in meshes])
    offsets = np.cumsum([0] + [len(m[0]) for m in meshes[:-1]])
    f = np.concatenate([m[1] + o for m, o in zip(meshes, offsets)])
    c = np.concatenate([m[2] for m in meshes])
    owner = np.concatenate([np.full(len(m[1]), k) for k, m in enumerate(meshes)])
    _write_ply(out / "model.ply", v, f, c)
    np.save(out / "owner.npy", owner)
    np.savez(out / "frame.npz", centre=frame["centre"], rotation=frame["rotation"], scale=frame["scale"])
    (out / "colonies.json").write_text(json.dumps({"frame": frame["said"], "colonies": said}, indent=1))
    # And as a patch tools/place-reconstruction can put into a place: the
    # model in its own frame (metres, z up, x along the swim).
    patch = out / "patch"
    patch.mkdir(exist_ok=True)
    _write_ply(patch / "mesh.ply", v, f, c)
    track = to_model(cameras, frame)
    (patch / "patch.json").write_text(json.dumps({
        "run": out.name,
        "tool": ("DeepReefMap (Sauder et al. 2024; code josauder/mee-deepreefmap, no licence: research use) for the "
                 "point cloud, classes and cameras; iocean-reconstruct drm for the seabed and the coral library's "
                 "colonies fitted to it"),
        "video": video or {},
        "scale": {"factor": frame["scale"], "how": "measured" if frame["measured"] else "assumed",
                  "from": frame["said"]},
        "sizeM": {"along": round(float(np.ptp(v[:, 0])), 2), "across": round(float(np.ptp(v[:, 1])), 2),
                  "relief": round(float(np.ptp(seabed["v"][:, 2])), 2)},
        "colonies": len(said), "triangles": int(len(f)),
        "track": {"lengthM": round(float(np.linalg.norm(np.diff(track, axis=0), axis=1).sum()), 1),
                  "cameraHeightM": frame["cameraHeightM"]},
    }, indent=1))
    return {"colonies": len(said), "triangles": int(len(f)), "frame": frame, "said": said}


# ── the score ────────────────────────────────────────────────────────────────

def eucm_rays(intrinsic, width: int, height: int) -> np.ndarray:
    """Each pixel's ray in the camera's frame, through DeepReefMap's camera
    model (the enhanced unified camera model, Khomutenko et al. 2016)."""
    fx, fy, cx, cy, alpha, beta = [float(x) for x in intrinsic[:6]]
    us, vs = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    mx, my = (us - cx) / fx, (vs - cy) / fy
    r2 = mx * mx + my * my
    inside = 1 - (2 * alpha - 1) * beta * r2
    mz = (1 - beta * alpha * alpha * r2) / (alpha * np.sqrt(np.maximum(inside, 0)) + (1 - alpha))
    d = np.stack([mx, my, mz], -1)
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def score(run: pathlib.Path, out: pathlib.Path, class_to_label: dict, coral_labels: set, ignored_labels: set) -> dict:
    """The model seen from each held-back frame's camera, against what
    DeepReefMap's networks said that frame shows: how much of the frame the
    model fills, how far its depth is from the frame's own, and whether coral
    is where the frame's classes say coral is. And the same for DeepReefMap's
    own cloud, which was built without these frames, as the line to beat."""
    import open3d as o3d

    held = np.load(run / "held.npz")
    poses, intrinsics = np.load(run / "poses.npy"), np.load(run / "intrinsics.npy")
    fz = np.load(out / "frame.npz")
    frame = {"centre": fz["centre"], "rotation": fz["rotation"], "scale": float(fz["scale"])}
    mesh = o3d.io.read_triangle_mesh(str(out / "model.ply"))
    v = from_model(np.asarray(mesh.vertices), frame)
    f = np.asarray(mesh.triangles)
    owner = np.load(out / "owner.npy")
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(v.astype(np.float32)), o3d.core.Tensor(f.astype(np.uint32)))
    cloud = np.genfromtxt(run / "point_cloud_tsdf.csv", delimiter=",", skip_header=1, usecols=(0, 1, 2))
    rows = []
    for k, i in enumerate(held["index"]):
        depth, unc, seg = held["depth"][k], held["uncertainty"][k], held["classes"][k]
        tall, wide = depth.shape
        rays = eucm_rays(intrinsics[i], wide, tall)
        pose = poses[i]
        d_world = rays @ pose[:3, :3].T
        origin = np.broadcast_to(pose[:3, 3], d_world.shape)
        hit = scene.cast_rays(o3d.core.Tensor(np.concatenate([origin, d_world], -1).astype(np.float32)))
        t = hit["t_hit"].numpy()
        z = t * rays[..., 2]
        which = hit["primitive_ids"].numpy()
        model_coral = np.isfinite(t) & (owner[np.clip(which, 0, len(owner) - 1)] > 0)
        wanted = (depth > 0) & ~np.isin(seg, list(ignored_labels))
        filled = wanted & np.isfinite(t)
        rel = np.abs(z[filled] - depth[filled]) / depth[filled]
        weight = 1.0 / np.maximum(unc[filled], 1e-4)
        frame_coral = np.isin(seg, list(coral_labels)) & wanted
        both = model_coral & frame_coral
        union = (model_coral & wanted) | frame_coral
        # DeepReefMap's own cloud, projected into this frame the same way.
        cam = (cloud - pose[:3, 3]) @ pose[:3, :3]
        front = cam[:, 2] > 1e-6
        cam = cam[front]
        fx, fy, cx, cy, alpha, beta = [float(x) for x in intrinsics[i][:6]]
        dd = np.sqrt(beta * (cam[:, 0] ** 2 + cam[:, 1] ** 2) + cam[:, 2] ** 2)
        den = alpha * dd + (1 - alpha) * cam[:, 2]
        u = (fx * cam[:, 0] / den + cx).astype(int)
        w_ = (fy * cam[:, 1] / den + cy).astype(int)
        ok = (u >= 0) & (u < wide) & (w_ >= 0) & (w_ < tall)
        zb = np.full((tall, wide), np.inf)
        np.minimum.at(zb, (w_[ok], u[ok]), cam[ok, 2])
        for dy in (0, 1):
            for dx in (0, 1):
                zb = np.minimum(zb, np.roll(np.roll(zb, dy, 0), dx, 1))
        cfilled = wanted & np.isfinite(zb)
        crel = np.abs(zb[cfilled] - depth[cfilled]) / depth[cfilled]
        rows.append({"frame": int(i),
                     "model": {"coverage": float(filled.sum() / max(wanted.sum(), 1)),
                               "depthRelErrorMedian": float(np.median(rel)) if rel.size else None,
                               "depthRelErrorWeighted": float(np.sum(rel * weight) / np.sum(weight)) if rel.size else None,
                               "coralIoU": float(both.sum() / max(union.sum(), 1))},
                     "cloud": {"coverage": float(cfilled.sum() / max(wanted.sum(), 1)),
                               "depthRelErrorMedian": float(np.median(crel)) if crel.size else None}})
    def mean(key, of):
        vals = [r[of][key] for r in rows if r[of][key] is not None]
        return round(float(np.mean(vals)), 4) if vals else None
    said = {"heldFrames": len(rows),
            "model": {k: mean(k, "model") for k in ("coverage", "depthRelErrorMedian", "depthRelErrorWeighted", "coralIoU")},
            "cloud": {k: mean(k, "cloud") for k in ("coverage", "depthRelErrorMedian")},
            "how": ("each held-back frame (never integrated into the cloud) seen from its own camera: coverage is the "
                    "share of its seabed and coral pixels the model fills, depth error is relative to DeepReefMap's "
                    "depth for that frame (weighted: by the inverse of its uncertainty), coral IoU is model coral "
                    "against the frame's coral classes. Self-consistency, not a truth: the frame's depth and classes "
                    "are DeepReefMap's own networks."),
            "frames": rows}
    (out / "score.json").write_text(json.dumps(said, indent=1))
    return said
