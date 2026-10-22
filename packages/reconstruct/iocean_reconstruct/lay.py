"""Reconstructions laid into a place: the place's next version, with reefs
rebuilt from video in it, drawn, stood on and dived. Any number of them, in
one job and one version.

    python -m iocean_reconstruct.lay '<brief>'

The brief (services/control-plane/internal/mapping):

    {"assets": [{"name": "red-sea-transect",       the asset's handle in the place
                 "path": "reconstruction/<id>",    where its files were staged
                 "placement": {"at": [X, Y], "headingDeg": D, "dz": Z}
                            | {"centre": true, "depthM": 8, "headingDeg": D},
                 "video": {...}}, ...],            what the place records about it
     "sink": 1.0, "clear": 1.5}                    place_in_map.py's

or, for one asset, as before: {"name", "placement", "video", "sink", "clear"}
with its files at reconstruction/.

Inputs: /work/inputs/place/ the place's version, every file at its path, and
each asset's files (reconstruction.json, parts/, surface.f32, surface.json,
path.json) under its path.

A placement is the asset's frame to the place's: the strip's centre (the mean
of its ground, as place_choose.py takes it) to "at", turned by headingDeg
about z, raised by dz. "centre" puts it in the middle of the place with its
ground's median at depthM. Each part is baked into the place's frame less a
whole-metre translate kept on the layer (NuRec keeps positions at half
precision), exported as NuRec, and laid by place_in_map.py, one asset after
another into one copy of the place. Two assets whose ground comes within a
metre of each other are said to overlap (each clears the other's colonies and
both lay their ground there); the place is still made. A dive begins where
the first asset's swim began. The package is /work/outputs/place.tar.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
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


def lay_one(asset: dict, rec: pathlib.Path, place: pathlib.Path, work: pathlib.Path, code: pathlib.Path,
            sink: float, clear: float, n: int, of: int) -> dict:
    """One asset baked and laid into `place`; what the place now holds of it."""
    name = asset["name"]
    work.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((rec / "reconstruction.json").read_text())
    placed = placement_of(asset, rec)
    P = np.array(placed["matrix"])
    # A whole-metre move kept on the layer, so the baked splats sit near the
    # origin, where half precision is fine.
    T = np.round(P[:3, 3])
    T[2] = 0.0
    tell("place", f"{name}: at ({placed['at'][0]:.0f}, {placed['at'][1]:.0f}) m, turned {placed['headingDeg']:g} "
                  f"degrees, raised {placed['dz']:+.2f} m", n=n, of=of, **{k: placed[k] for k in ("at", "headingDeg", "dz")})
    (work / "placement.json").write_text(json.dumps(placed, indent=1))

    # The swim and the bake, both through P; the bake less T.
    path = json.loads((rec / "path.json").read_text())
    frames = []
    for f in path["frames"]:
        m = P @ np.array(f["matrix"])
        frames.append({"name": f["name"], "eye": [float(v) for v in m[:3, 3]], "matrix": m.tolist()})
    (work / "align-map.json").write_text(json.dumps(dict(path, frames=frames, frame="the place's")))
    usd = np.eye(4)
    usd[:3, :3], usd[3, :3] = P[:3, :3].T, P[:3, 3] - T
    (work / "align-local.json").write_text(json.dumps(dict(path, usdMatrix=usd.tolist())))

    parts = []
    for i, piece in enumerate(manifest["pieces"]):
        baked = work / f"part-{i + 1}-baked.pt"
        tell("bake", f"{name}: part {i + 1} of {len(manifest['pieces'])} into the place's frame", n=n, of=of)
        run("bake", python("bake_splats.py", rec / piece["checkpoint"], "-", work / "align-local.json", baked,
                           work / "align-local-baked.json"))
        usdz = work / f"part-{i + 1}.usdz"
        run("bake", [sys.executable, "-m", "threedgrut.export.scripts.export_usd", "--checkpoint", baked,
                     "--output", usdz, "--format", "nurec", "--no-cameras", "--no-background", "--half",
                     "--no-transform"], cwd=code, lines=False)
        baked.unlink(missing_ok=True)
        parts.append(usdz)
    tell("lay", f"laying {name} into the place", n=n, of=of)
    video = dict(asset.get("video") or {}, reconstruction=manifest.get("name"),
                 scale=manifest.get("scale"), tape=manifest.get("tape"), cover=manifest.get("cover"))
    run("lay", python("place_in_map.py", place, name, work / "placement.json", rec, work / "align-map.json", *parts,
                      "--pieces", ",".join(f"{p['first']}:{p['last']}" for p in manifest["pieces"]),
                      # Joined to its flag: a shift west of the middle starts
                      # with a minus, which argparse otherwise reads as a flag.
                      "--translate=" + ",".join(f"{v:g}" for v in T),
                      "--sink", sink, "--clear", clear, "--video", json.dumps(video)))
    for f in parts:
        f.unlink(missing_ok=True)
    return {"name": name, "placed": placed, "start": frames[0]["eye"], "ground": footprint(rec, P, placed["dz"])}


def footprint(rec: pathlib.Path, P: np.ndarray, dz: float) -> np.ndarray:
    """Where an asset's measured ground lies in the place, a sample a metre."""
    said = json.loads((rec / "surface.json").read_text())
    grid = np.fromfile(rec / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell, (ox, oy) = float(said["cellM"]), said["origin"]
    every = max(1, int(round(1.0 / cell)))
    rr, cc = np.nonzero(np.isfinite(grid[::every, ::every]))
    local = np.stack([ox + cc * every * cell, oy + rr * every * cell, np.zeros(len(rr)), np.ones(len(rr))])
    return (P @ local)[:2].T


def overlaps(laid: list[dict], within: float = 1.0) -> list[str]:
    """Pairs of assets whose ground comes within `within` metres."""
    from scipy.spatial import cKDTree

    said = []
    for i in range(len(laid)):
        tree = cKDTree(laid[i]["ground"])
        for j in range(i + 1, len(laid)):
            d, _ = tree.query(laid[j]["ground"], distance_upper_bound=within)
            close = int(np.isfinite(d).sum())
            if close:
                said.append(f"{laid[i]['name']} and {laid[j]['name']} overlap ({close} m² of ground within {within:g} m)")
    return said


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
    base = INPUTS / "place"
    # One asset, as the brief first said it, or several.
    assets = brief.get("assets") or [{"name": brief.get("name") or "reconstruction", "path": "reconstruction",
                                      "placement": brief["placement"], "video": brief.get("video")}]
    # Each a name of its own: the place's layers and prims are named by it.
    seen: dict[str, int] = {}
    for a in assets:
        a["name"] = a.get("name") or "reconstruction"
        seen[a["name"]] = seen.get(a["name"], 0) + 1
        if seen[a["name"]] > 1:
            a["name"] = f"{a['name']}-{seen[a['name']]}"
    try:
        place = SCRATCH / "place"
        shutil.rmtree(place, ignore_errors=True)
        shutil.copytree(base, place)
        code = grut_copy()
        laid = []
        for i, asset in enumerate(assets):
            laid.append(lay_one(asset, INPUTS / (asset.get("path") or "reconstruction"), place, SCRATCH / f"asset-{i + 1}",
                                code, float(brief.get("sink", 1.0)), float(brief.get("clear", 1.5)), i + 1, len(assets)))
        crossed = overlaps(laid) if len(laid) > 1 else []
        for one in crossed:
            tell("overlap", one)
        site = json.loads((place / "site.json").read_text())
        # A dive begins over the first reef laid, where its video's swim
        # began: it is why this version exists.
        if site.get("beginAt") is not None and "beginAtBefore" not in site:
            site["beginAtBefore"] = {"at": site["beginAt"], "because": site.get("beginBecause")}
        site["beginAt"] = [round(float(v), 2) for v in laid[0]["start"]]
        site["beginBecause"] = f"where the video {laid[0]['name']} was rebuilt from began its swim"
        if crossed:
            site.setdefault("warnings", []).extend(crossed)
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
    tell("done", f"{len(laid)} asset{'s' if len(laid) != 1 else ''} laid into the place: "
                 + ", ".join(one["name"] for one in laid),
         seconds=round(time.time() - started), assets=[{"name": one["name"], **{k: one["placed"][k] for k in ("at", "headingDeg", "dz")}}
                                                       for one in laid], overlaps=crossed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
