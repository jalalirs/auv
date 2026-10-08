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


def _patch(cfg, a) -> int:
    from .patch import make

    run = config.run_dir(a.name)
    about = {**_about(cfg, a.name), "video": json.loads((run / "frames" / "frames.json").read_text())}
    said = make(run / "colmap" / "dense", run / "colmap" / "sparse-text", run / "patch", cfg, about)
    print(json.dumps({k: said[k] for k in ("frames", "sizeM", "seenM2", "track", "scale")}, indent=1))
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
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    return {"video": _video, "patch": _patch}[a.command](cfg, a)


if __name__ == "__main__":
    sys.exit(main())
