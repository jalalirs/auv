"""iocean-reconstruct: a reef patch in 3D from a dive video.

    iocean-reconstruct video --video FILE[,FILE] --name NAME [--from S] [--to S]
                                    frames, COLMAP, then the patch -> runs/<name>/
    iocean-reconstruct patch --name NAME
                                    the patch again from a finished COLMAP run

Data under IOCEAN_ML_DATA (see config.py); videos are read from wherever they are
given, in the container /videos for the cover project's raw ones.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

from . import config


def _about(cfg: dict, name: str) -> dict:
    return {"run": name, "config": cfg["name"], "commit": os.environ.get("GIT_COMMIT", "unknown"),
            "tool": "COLMAP (BSD-3-Clause): SIFT, sequential matching, incremental mapping, patch-match stereo, "
                    + ("Poisson" if cfg["dense"]["mesher"] == "poisson" else "Delaunay") + " meshing",
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _video(cfg, a) -> int:
    from .colmap import reconstruct
    from .frames import extract
    from .patch import make

    run = config.run_dir(a.name)
    frames = run / "frames"
    if not (frames / "frames.json").exists():
        said = extract([pathlib.Path(p) for p in a.video.split(",")], frames, cfg["frames"]["every"], a.start, a.end,
                       cfg["frames"]["longest_side"])
        print(json.dumps(said), flush=True)
    done = reconstruct(frames, run / "colmap", cfg)
    print(json.dumps(done), flush=True)
    about = {**_about(cfg, a.name), "video": json.loads((frames / "frames.json").read_text()), "colmap": done}
    said = make(run / "colmap" / "dense", run / "colmap" / "sparse-text", run / "patch", cfg, about)
    print(json.dumps({k: said[k] for k in ("frames", "sizeM", "seenM2", "track", "scale")}, indent=1))
    return 0


def _scale(cfg, a) -> int:
    from .scale import measure

    run = config.run_dir(a.name)
    video = json.loads((run / "frames" / "frames.json").read_text())
    said = measure(pathlib.Path(a.video or video["videos"][0]), run / "colmap" / "sparse-text",
                   float(video["fromSeconds"]), float(video["everySeconds"]))
    (run / "scale.json").write_text(json.dumps(said, indent=1) + "\n")
    print(json.dumps(said, indent=1))
    return 0


def _patch(cfg, a) -> int:
    from .patch import make

    run = config.run_dir(a.name)
    about = {**_about(cfg, a.name), "video": json.loads((run / "frames" / "frames.json").read_text())}
    if (run / "scale.json").exists():
        about["measuredScale"] = json.loads((run / "scale.json").read_text())
    said = make(run / "colmap" / "dense", run / "colmap" / "sparse-text", run / "patch", cfg, about)
    print(json.dumps({k: said[k] for k in ("frames", "sizeM", "seenM2", "track", "scale")}, indent=1))
    return 0


def _fuse(cfg, a) -> int:
    from .prior import fuse

    if a.picture is not None:
        from .prior import picture

        target = config.run_dir(a.name) / "prior" / f"compare-{a.picture:03d}.jpg"
        picture(config.run_dir(a.name), a.picture, target)
        print(json.dumps({"picture": str(target)}))
        return 0
    said = fuse(config.run_dir(a.name), pathlib.Path(a.library))
    if a.truth:
        from .prior import against_truth

        print(json.dumps(against_truth(config.run_dir(a.name)), indent=1))
    print(json.dumps({k: said[k] for k in ("points", "massivePoints", "groundPoints", "scores", "best", "seconds")}
                     | {"colonies": len(said["colonies"])}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="iocean-reconstruct", description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="default.yaml")
    sub = ap.add_subparsers(dest="command", required=True)
    v = sub.add_parser("video")
    v.add_argument("--video", required=True, help="one file, or several a transect was cut into, comma separated")
    v.add_argument("--name", required=True)
    v.add_argument("--from", dest="start", type=float, default=0.0, help="seconds")
    v.add_argument("--to", dest="end", type=float, help="seconds")
    p = sub.add_parser("patch")
    p.add_argument("--name", required=True)
    m = sub.add_parser("scale", help="measure the scale from the video's own motion sensor")
    m.add_argument("--name", required=True)
    m.add_argument("--video", help="the video, where frames.json's path is not the one mounted here")
    fu = sub.add_parser("fuse", help="the coral library as the prior, the video's points as the measurement")
    fu.add_argument("--name", required=True)
    fu.add_argument("--library", required=True, help="a coral library folder (library.json and its colonies)")
    fu.add_argument("--picture", type=int, help="only draw held-back frame N beside the three versions")
    fu.add_argument("--truth", action="store_true", help="also score against truth.ply (a synthetic run)")
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    return {"video": _video, "patch": _patch, "scale": _scale, "fuse": _fuse}[a.command](cfg, a)


if __name__ == "__main__":
    sys.exit(main())
