"""COLMAP, step by step, each step's output kept and its log beside it.

    features   SIFT on every frame, one camera for the whole video
    match      each frame against its neighbours (a video is a sequence)
    map        structure from motion: camera poses and sparse points
    dense      undistort, patch-match stereo, fuse: a dense coloured point cloud
    mesh       a surface through the dense points

A step whose output exists is not run again, so a run that stopped resumes.
"""

from __future__ import annotations

import pathlib
import subprocess
import time


def _run(args: list[str], log: pathlib.Path) -> float:
    t0 = time.time()
    with open(log, "w") as out:
        out.write(" ".join(args) + "\n\n")
        out.flush()
        done = subprocess.run(args, stdout=out, stderr=subprocess.STDOUT)
    if done.returncode != 0:
        tail = log.read_text().splitlines()[-15:]
        raise RuntimeError(f"{args[1]} failed (exit {done.returncode}); the end of {log}:\n" + "\n".join(tail))
    return round(time.time() - t0, 1)


def sparse_model(work: pathlib.Path) -> pathlib.Path | None:
    """The largest model the mapper made, by how many frames it placed."""
    models = sorted((work / "sparse").glob("*/images.bin"))
    if not models:
        return None
    return max((m.parent for m in models), key=lambda m: (m / "images.bin").stat().st_size)


def reconstruct(frames: pathlib.Path, work: pathlib.Path, cfg: dict) -> dict:
    c, d = cfg["colmap"], cfg["dense"]
    work.mkdir(parents=True, exist_ok=True)
    logs = work / "logs"
    logs.mkdir(exist_ok=True)
    db = work / "database.db"
    seconds = {}
    if not (work / "features.done").exists():
        seconds["features"] = _run(["colmap", "feature_extractor", "--database_path", str(db),
                                    "--image_path", str(frames),
                                    "--ImageReader.camera_model", c["camera_model"],
                                    "--ImageReader.single_camera", "1" if c["single_camera"] else "0",
                                    "--FeatureExtraction.use_gpu", "1", "--FeatureExtraction.gpu_index", c["gpu"]],
                                   logs / "features.log")
        (work / "features.done").touch()
    if not (work / "match.done").exists():
        seconds["match"] = _run(["colmap", "sequential_matcher", "--database_path", str(db),
                                 "--SequentialMatching.overlap", str(c["sequential_overlap"]),
                                 "--FeatureMatching.use_gpu", "1", "--FeatureMatching.gpu_index", c["gpu"]],
                                logs / "match.log")
        (work / "match.done").touch()
    if sparse_model(work) is None:
        (work / "sparse").mkdir(exist_ok=True)
        seconds["map"] = _run(["colmap", "mapper", "--database_path", str(db), "--image_path", str(frames),
                               "--output_path", str(work / "sparse")], logs / "map.log")
    model = sparse_model(work)
    if model is None:
        raise RuntimeError("the mapper placed no frames: the video may be too blurred, too dark or too fast")
    dense = work / "dense"
    if not (dense / "fused.ply").exists():
        seconds["undistort"] = _run(["colmap", "image_undistorter", "--image_path", str(frames),
                                     "--input_path", str(model), "--output_path", str(dense),
                                     "--max_image_size", str(d["max_image_size"])], logs / "undistort.log")
        seconds["stereo"] = _run(["colmap", "patch_match_stereo", "--workspace_path", str(dense),
                                  "--PatchMatchStereo.geom_consistency", "true",
                                  "--PatchMatchStereo.gpu_index", c["gpu"]], logs / "stereo.log")
        seconds["fuse"] = _run(["colmap", "stereo_fusion", "--workspace_path", str(dense),
                                "--output_path", str(dense / "fused.ply")], logs / "fuse.log")
    if not (dense / "meshed.ply").exists():
        if d["mesher"] == "poisson":
            seconds["mesh"] = _run(["colmap", "poisson_mesher", "--input_path", str(dense / "fused.ply"),
                                    "--output_path", str(dense / "meshed.ply"),
                                    "--PoissonMeshing.depth", str(d["poisson_depth"]),
                                    "--PoissonMeshing.trim", str(d["trim"])], logs / "mesh.log")
        else:
            seconds["mesh"] = _run(["colmap", "delaunay_mesher", "--input_path", str(dense),
                                    "--output_path", str(dense / "meshed.ply")], logs / "mesh.log")
    # The sparse model as text too, for reading the camera positions without COLMAP.
    text = work / "sparse-text"
    if not (text / "images.txt").exists():
        text.mkdir(exist_ok=True)
        _run(["colmap", "model_converter", "--input_path", str(model), "--output_path", str(text),
              "--output_type", "TXT"], logs / "convert.log")
    return {"model": str(model), "seconds": seconds}


def cameras(text: pathlib.Path):
    """Each registered frame's name and camera centre, from images.txt."""
    import numpy as np

    out = []
    lines = [ln for ln in (text / "images.txt").read_text().splitlines() if ln and not ln.startswith("#")]
    for line in lines[::2]:
        p = line.split()
        qw, qx, qy, qz, tx, ty, tz = (float(v) for v in p[1:8])
        r = np.array([[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                      [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                      [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])
        out.append((p[9], -r.T @ np.array([tx, ty, tz])))
    return out
