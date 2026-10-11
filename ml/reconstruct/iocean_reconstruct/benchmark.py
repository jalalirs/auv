"""A real reef with a real answer: USGS SQUID-5 at Looe Key.

The survey photographed the reef from about 95,000 overlapping frames and
built a point cloud from all of them. Here a thin strip of those frames (one
survey line, two of its four cameras: about what one diver's pass sees) is
reconstructed on its own and fused with the coral library, and every version
is scored against the survey's own point cloud.

    prepare   pick the line's frames over the truth tile, as JPEG frames, with
              each frame's GNSS antenna position (in the survey's UTM)
    truth     (needs laspy: ~/iocean/venvs/coral) the survey's points over
              the strip, as truth.npy
    align     the reconstruction onto the survey's metres: a similarity from
              the frames to their antenna positions, refined by ICP against
              the truth points (the antenna is up to 60 cm from each camera)
    score     the reconstruction alone, the library alone and the fusion,
              against the truth over each colony found: where the strip
              captured it and where it did not
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
import re
import zipfile

import numpy as np

UTM = "EPSG:6346"      # NAD83(2011) / UTM 17N: the survey's own frame


def prepare(line_zip: pathlib.Path, locations: pathlib.Path, bounds: tuple[float, float, float, float],
            out: pathlib.Path, cameras: tuple[str, ...] = ("13", "82"), longest: int = 1600) -> dict:
    """The line's frames over `bounds` (left, bottom, right, top in UTM), from
    `cameras`, as frames/NNNNN.jpg with frames.json and gnss.json beside."""
    from PIL import Image
    from rasterio.warp import transform

    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    where = {}
    for row in csv.DictReader(locations.open()):
        where[row["ImageFile"]] = (float(row["Longitude"]), float(row["Latitude"]),
                                   float(row["Altitude (NAD83 Ellipsoid Height)"]))
    with zipfile.ZipFile(line_zip) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".tif")]
        wanted = []
        for n in names:
            base = n.rsplit("/", 1)[-1]
            cam = re.match(r"CAM(\d+)-", base)
            if not cam or cam.group(1) not in cameras or base not in where:
                continue
            wanted.append(base)
        lon, lat, alt = zip(*(where[b] for b in wanted))
        xs, ys = transform("EPSG:4326", UTM, list(lon), list(lat))
        left, bottom, right, top = bounds
        kept = [(b, x, y, z) for b, x, y, z in zip(wanted, xs, ys, alt)
                if left <= x <= right and bottom <= y <= top]
        kept.sort(key=lambda k: (k[0][6:20], k[0][:5]))         # by time, then camera
        gnss = {}
        full = {n.rsplit("/", 1)[-1]: n for n in names}
        for i, (base, x, y, z) in enumerate(kept):
            image = Image.open(io.BytesIO(archive.read(full[base])))
            if image.mode not in ("RGB", "L"):
                arr = np.asarray(image).astype(np.float64)
                arr = np.clip(arr / max(np.percentile(arr, 99.5), 1) * 255, 0, 255).astype(np.uint8)
                image = Image.fromarray(arr)
            image = image.convert("RGB")
            # SQUID-5's frames are dark (the deepest of them sit in the bottom
            # quarter of the range); each channel stretched over the range, or
            # features have nothing to land on.
            arr = np.asarray(image).astype(np.float64)
            for c in range(3):
                lo, hi = np.percentile(arr[..., c], (0.5, 99.5))
                arr[..., c] = (arr[..., c] - lo) / max(hi - lo, 1.0)
            image = Image.fromarray((np.clip(arr, 0, 1) ** (1 / 1.4) * 255).astype(np.uint8))
            image.thumbnail((longest, longest))
            name = f"{i:05d}.jpg"
            image.save(frames / name, quality=93)
            gnss[name] = {"source": base, "antenna": [x, y, z]}
    (out / "gnss.json").write_text(json.dumps(gnss, indent=1))
    said = {"videos": [str(line_zip.name)], "fromSeconds": 0.0, "everySeconds": 1.0, "frames": len(gnss),
            "cameras": list(cameras), "bounds": list(bounds), "source": "USGS SQUID-5 Looe Key 2021 (doi 10.5066/P9WSF09G)"}
    (frames / "frames.json").write_text(json.dumps(said, indent=1))
    return said


def truth(laz: pathlib.Path, run: pathlib.Path, margin: float = 2.0, most: int = 12_000_000) -> dict:
    """The survey's points over the strip (its antenna track, widened), as
    truth.npy: x, y, z in UTM metres. Points the survey trusted least (seen in
    one depth map: class 7, 'low noise') are left out."""
    import laspy

    gnss = json.loads((run / "gnss.json").read_text())
    track = np.array([g["antenna"][:2] for g in gnss.values()])
    lo, hi = track.min(0) - margin - 2.0, track.max(0) + margin + 2.0
    kept = []
    with laspy.open(laz) as reader:
        for chunk in reader.chunk_iterator(5_000_000):
            x, y, z = np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)
            inside = (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
            if "classification" in chunk.point_format.dimension_names:
                inside &= np.asarray(chunk.classification) != 7
            if inside.any():
                kept.append(np.c_[x[inside], y[inside], z[inside]])
    points = np.concatenate(kept) if kept else np.zeros((0, 3))
    if len(points) > most:
        points = points[np.random.default_rng(0).choice(len(points), most, replace=False)]
    np.save(run / "truth.npy", points.astype("float64"))
    return {"points": int(len(points)), "box": [lo.tolist(), hi.tolist()]}


def align(run: pathlib.Path) -> dict:
    """Model units to the survey's metres: a similarity from each frame's
    camera centre to its antenna position, then ICP (with scale) of the
    reconstruction's points onto the survey's."""
    import open3d as o3d

    from .prior import read_cameras, read_fused, similarity

    from .patch import frame_of

    gnss = json.loads((run / "gnss.json").read_text())
    _, frames = read_cameras(run / "colmap" / "dense" / "sparse-text")
    names = [f["name"] for f in frames if f["name"] in gnss]
    model = np.array([f["centre"] for f in frames if f["name"] in gnss])
    antenna = np.array([gnss[n]["antenna"] for n in names])
    points, _, _ = read_fused(run / "colmap" / "dense")
    survey = np.load(run / "truth.npy")
    # Up from the reef, not from the track: a survey line is straight, and a
    # line of antenna positions leaves the roll about it free. The reef's mean
    # plane, facing the cameras, is up; then heading, scale and position in
    # the plane come from the antenna, and the height from the survey's own
    # points (the antenna's heights are above the ellipsoid, the survey's
    # above its vertical datum: some twenty metres apart here).
    centre, rotation, _ = frame_of(points, np.array([f["centre"] for f in frames]))
    level = lambda p: (np.asarray(p) - centre) @ rotation.T
    cams = level(model)
    a, b = cams[:, :2], antenna[:, :2]
    ma, mb = a.mean(0), b.mean(0)
    u, d, vt = np.linalg.svd((b - mb).T @ (a - ma) / len(a))
    yaw = u @ np.diag([1.0, np.sign(np.linalg.det(u @ vt))]) @ vt
    s = float(d.sum() / ((a - ma) ** 2).sum(1).mean()) if np.linalg.det(u @ vt) > 0 else \
        float((d[0] - d[1]) / ((a - ma) ** 2).sum(1).mean())
    turn = np.eye(3)
    turn[:2, :2] = yaw
    shift = np.r_[mb - s * yaw @ ma, 0.0]
    coarse = float(np.median(np.linalg.norm(s * cams[:, :2] @ yaw.T + shift[:2] - b, axis=1)))
    pick = np.random.default_rng(0).choice(len(points), min(400_000, len(points)), replace=False)
    moved = s * level(points[pick]) @ turn.T + shift
    lift = float(np.median(survey[:, 2]) - np.median(moved[:, 2]))
    shift[2] += lift
    moved[:, 2] += lift
    # As a similarity from model units: x' = s turn rotation (x - centre) + shift.
    r = turn @ rotation
    t = shift - s * r @ centre
    pick_t = np.random.default_rng(1).choice(len(survey), min(1_500_000, len(survey)), replace=False)
    source = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(moved))
    target = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(survey[pick_t]))
    steps = []
    transform = np.eye(4)
    for reach in (0.5, 0.15, 0.05):
        fit = o3d.pipelines.registration.registration_icp(
            source, target, reach, transform,
            o3d.pipelines.registration.TransformationEstimationPointToPoint(with_scaling=True),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=60))
        transform = fit.transformation
        steps.append({"reachM": reach, "fitness": round(fit.fitness, 3), "rmseM": round(fit.inlier_rmse, 4)})
    # model -> UTM: x' = A (s R x + t) + b
    a, b = transform[:3, :3], transform[:3, 3]
    linear = a @ (s * r)
    offset = a @ t + b
    scale = float(np.cbrt(np.linalg.det(linear)))
    said = {"framesMatched": len(names), "antennaFitM": round(coarse, 3), "datumLiftM": round(lift, 3), "icp": steps,
            "metresPerUnit": scale, "linear": linear.tolist(), "offset": offset.tolist()}
    (run / "align.json").write_text(json.dumps(said, indent=1))
    (run / "scale.json").write_text(json.dumps({"measured": True, "scale": scale,
                                                "how": "the survey's GNSS and point cloud (align.json)"}, indent=1))
    return said


def score(run: pathlib.Path, near_m: float = 0.02, captured_m: float = 0.02) -> dict:
    """Each version against the survey's points over each colony found: over
    the points the strip's own reconstruction came within `captured_m` of
    (captured) and the ones it did not (missed)."""
    import open3d as o3d

    from .patch import frame_of as fit
    from .prior import HELD_EVERY, read_cameras, read_fused, read_library_ply

    told = json.loads((run / "align.json").read_text())
    linear, offset = np.array(told["linear"]), np.array(told["offset"])
    dense = run / "colmap" / "dense"
    _, frames = read_cameras(dense / "sparse-text")
    points, _, seen = read_fused(dense)
    use = set(range(len(frames))) - set(range(0, len(frames), HELD_EVERY))
    views = np.array([sum(1 for f in sv if int(f) in use) for sv in seen])
    kept = points[views >= 2]
    scale = float(json.loads((run / "scale.json").read_text())["scale"])
    centre, rotation, _ = fit(kept, np.array([f["centre"] for f in frames]))
    to_utm = lambda p: ((np.asarray(p) / scale) @ rotation + centre) @ linear.T + offset
    measured = kept @ linear.T + offset
    survey = np.load(run / "truth.npy")
    measured_tree = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(measured)))

    said = json.loads((run / "prior" / "fused.json").read_text())
    columns = {"reconstruction alone": "-raw", "library alone": "-prior", "fused": ""}
    rows = {k: {"captured": [], "missed": []} for k in columns}
    colonies = 0
    for k, c in enumerate(said["colonies"]):
        middle = to_utm(np.array([[*c["centre"], c["groundZ"]]]))[0]
        r = max(c["acrossM"]) / 2 + 0.1
        near = np.linalg.norm(survey[:, :2] - middle[:2], axis=1) < r
        truth_pts = survey[near & (survey[:, 2] > middle[2] + 0.03)]
        if len(truth_pts) < 200:
            continue
        truth_pts = truth_pts[np.random.default_rng(k).choice(len(truth_pts), min(20000, len(truth_pts)), replace=False)]
        captured = np.array([measured_tree.search_knn_vector_3d(p, 1)[2][0] < captured_m ** 2 for p in truth_pts])
        colonies += 1
        for key, suffix in columns.items():
            path = run / "prior" / f"colony-{k:03d}{suffix}.ply"
            if not path.is_file():
                continue
            v, f, _ = read_library_ply(path)
            scene = o3d.t.geometry.RaycastingScene()
            scene.add_triangles(o3d.core.Tensor(to_utm(v).astype("float32")), o3d.core.Tensor(f.astype("uint32")))
            d = scene.compute_distance(o3d.core.Tensor(truth_pts.astype("float32"))).numpy()
            rows[key]["captured"].append(d[captured])
            rows[key]["missed"].append(d[~captured])
    out = {"colonies": colonies, "align": {k: told[k] for k in ("antennaFitM", "icp", "metresPerUnit")}, "versions": {}}
    for key, parts in rows.items():
        out["versions"][key] = {}
        for part, chunks in parts.items():
            d = np.concatenate(chunks) if chunks else np.zeros(0)
            if len(d):
                out["versions"][key][part] = {"points": int(len(d)), "medianM": round(float(np.median(d)), 4),
                                              f"within{int(near_m * 100)}cm": round(float((d < near_m).mean()), 3)}
    (run / "prior" / "squid.json").write_text(json.dumps(out, indent=1))
    return out
