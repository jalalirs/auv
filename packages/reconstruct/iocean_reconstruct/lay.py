"""A reconstruction laid into a place: the place's next version, with the reef
rebuilt from a video in it, drawn, stood on and dived.

    python -m iocean_reconstruct.lay '<brief>'

The brief (services/control-plane/internal/mapping):

    {"name": "red-sea-transect",                  the reconstruction's handle in the place
     "placement": {"at": [X, Y], "headingDeg": D, "dz": Z}
                | {"centre": true, "depthM": 8, "headingDeg": D},
     "video": {...},                              what the place records about the video
     "sink": 1.0, "clear": 1.5}                   place_in_map.py's

Inputs: /work/inputs/place/ the place's version, every file at its path, and
/work/inputs/reconstruction/ the reconstruction's (reconstruction.json,
parts/, surface.f32, surface.json, path.json).

The placement is the reconstruction's frame to the place's: the strip's centre
(the mean of its ground, as place_choose.py takes it) to "at", turned by
headingDeg about z, raised by dz. "centre" puts it in the middle of the place
with its ground's median at depthM. Each part is baked into the place's frame
less a whole-metre translate kept on the layer (NuRec keeps positions at half
precision), exported as NuRec, and the place written by place_in_map.py; the
package is /work/outputs/place.tar.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tarfile
import time
import traceback

import numpy as np

from .job import INPUTS, OUTPUTS, SCRATCH, grut_copy, python, run, tell


def placement_of(brief: dict, surface_dir) -> dict:
    said = json.loads((surface_dir / "surface.json").read_text())
    grid = np.fromfile(surface_dir / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell, (ox, oy) = float(said["cellM"]), said["origin"]
    rr, cc = np.nonzero(np.isfinite(grid))
    every = max(1, len(rr) // 200000)
    xs, ys = ox + cc[::every] * cell, oy + rr[::every] * cell
    cx, cy = float(xs.mean()), float(ys.mean())
    asked = brief["placement"]
    heading = float(asked.get("headingDeg", 0.0))
    if asked.get("centre"):
        at = [0.0, 0.0]
        dz = -abs(float(asked.get("depthM", 8.0))) - float(np.nanmedian(grid))
    else:
        at, dz = [float(v) for v in asked["at"]], float(asked["dz"])
    t = math.radians(heading)
    c, s = math.cos(t), math.sin(t)
    m = np.eye(4)
    m[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    m[:3, 3] = [at[0] - (c * cx - s * cy), at[1] - (s * cx + c * cy), dz]
    return {"headingDeg": heading, "at": at, "dz": dz, "centre": [cx, cy], "matrix": m.tolist(),
            "fit": asked.get("fit")}


def main(argv: list[str]) -> int:
    started = time.time()
    brief = json.loads(argv[0])
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "logs").mkdir(exist_ok=True)
    home = SCRATCH / "home"
    home.mkdir(exist_ok=True)
    os.environ.update(HOME=str(home), TMPDIR=str(SCRATCH / "tmp"),
                      TORCH_EXTENSIONS_DIR=str(SCRATCH / "torch-extensions"))
    (SCRATCH / "tmp").mkdir(exist_ok=True)
    rec, base = INPUTS / "reconstruction", INPUTS / "place"
    name = brief.get("name") or "reconstruction"
    try:
        manifest = json.loads((rec / "reconstruction.json").read_text())
        placed = placement_of(brief, rec)
        P = np.array(placed["matrix"])
        # A whole-metre move kept on the layer, so the baked splats sit near
        # the origin, where half precision is fine.
        T = np.round(P[:3, 3])
        T[2] = 0.0
        tell("place", f"the reef at ({placed['at'][0]:.0f}, {placed['at'][1]:.0f}) m, turned {placed['headingDeg']:g} "
                      f"degrees, raised {placed['dz']:+.2f} m", **{k: placed[k] for k in ("at", "headingDeg", "dz")})
        place = SCRATCH / "place"
        shutil.rmtree(place, ignore_errors=True)
        shutil.copytree(base, place)
        (SCRATCH / "placement.json").write_text(json.dumps(placed, indent=1))

        # The swim and the bake, both through P; the bake less T.
        path = json.loads((rec / "path.json").read_text())
        frames = []
        for f in path["frames"]:
            m = P @ np.array(f["matrix"])
            frames.append({"name": f["name"], "eye": [float(v) for v in m[:3, 3]], "matrix": m.tolist()})
        (SCRATCH / "align-map.json").write_text(json.dumps(dict(path, frames=frames, frame="the place's")))
        usd = np.eye(4)
        usd[:3, :3], usd[3, :3] = P[:3, :3].T, P[:3, 3] - T
        (SCRATCH / "align-local.json").write_text(json.dumps(dict(path, usdMatrix=usd.tolist())))

        code = grut_copy()
        parts = []
        for i, piece in enumerate(manifest["pieces"]):
            baked = SCRATCH / f"part-{i + 1}-baked.pt"
            tell("bake", f"part {i + 1} into the place's frame", n=i + 1, of=len(manifest["pieces"]))
            run("bake", python("bake_splats.py", rec / piece["checkpoint"], "-", SCRATCH / "align-local.json", baked,
                               SCRATCH / "align-local-baked.json"))
            usdz = SCRATCH / f"part-{i + 1}.usdz"
            run("bake", [sys.executable, "-m", "threedgrut.export.scripts.export_usd", "--checkpoint", baked,
                         "--output", usdz, "--format", "nurec", "--no-cameras", "--no-background", "--half",
                         "--no-transform"], cwd=code, lines=False)
            baked.unlink(missing_ok=True)
            parts.append(usdz)
        tell("lay", "laying the reef into the place")
        video = dict(brief.get("video") or {}, reconstruction=manifest.get("name"),
                     scale=manifest.get("scale"), tape=manifest.get("tape"), cover=manifest.get("cover"))
        laid = run("lay", python("place_in_map.py", place, name, SCRATCH / "placement.json", rec,
                                 SCRATCH / "align-map.json", *parts,
                                 "--pieces", ",".join(f"{p['first']}:{p['last']}" for p in manifest["pieces"]),
                                 "--translate", ",".join(f"{v:g}" for v in T),
                                 "--sink", brief.get("sink", 1.0), "--clear", brief.get("clear", 1.5),
                                 "--video", json.dumps(video)))
        site = json.loads((place / "site.json").read_text())
        # A dive begins over the reef rebuilt, where the video's swim began:
        # it is why this version exists.
        if site.get("beginAt") is not None:
            site["beginAtBefore"] = {"at": site["beginAt"], "because": site.get("beginBecause")}
        site["beginAt"] = [round(float(v), 2) for v in frames[0]["eye"]]
        site["beginBecause"] = f"where the video {name} was rebuilt from began its swim"
    except Exception as failed:
        traceback.print_exc()
        tell("failed", str(failed)[:2000])
        return 1
    (place / "site.json").write_text(json.dumps(site, indent=1))
    tell("package", "packing the place")
    with tarfile.open(OUTPUTS / "place.tar", "w") as archive:
        for f in sorted(place.rglob("*")):
            if f.is_file():
                archive.add(f, arcname=str(f.relative_to(place)))
    if SCRATCH.is_relative_to(OUTPUTS) and not os.environ.get("IOCEAN_KEEP_SCRATCH"):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    tell("done", f"{name} laid into the place", seconds=round(time.time() - started),
         **{k: placed[k] for k in ("at", "headingDeg", "dz")})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
