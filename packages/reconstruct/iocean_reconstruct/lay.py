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
with its files at reconstruction/. A structure (asset.py's) is an entry with
"kind": "structure", and needs no search before it:

    {"name", "path": "asset/<id>", "kind": "structure", "meets": "stands",
     "placement": {"lat", "lon", "headingDeg"}}    a model stood on the seabed there
    {"name", "path": "asset/<id>", "kind": "structure", "meets": "drapes"}
                                                   a route laid along the seabed
                                                   (a model that drapes is given a
                                                   placement and follows the seabed)

its files (asset.json, model.usdc) under its path.

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

A structure goes in the way the runtime already takes a reef: its mesh a layer
in layers.reconstructions ("kind": "structure", drawn at
/World/Reconstructions/<name>), its top a height grid in surfaces, which the
seabed reads for physics, altitude and sonar, so a vehicle rests on it and is
stopped by it. A grid has no underside: what is under a deck is solid. Each is
recorded in site.json structures[]. A model stands with its base on the
seabed at its lat/lon, turned headingDeg about z as a reef's placement is; a
pipeline is a tube of diameterM along its route, every ring on the seabed
under it less burial x diameter, its top a strip of grid along each leg. The
place's own colonies within half a metre of either are taken off.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import shutil
import sys
import tarfile
import time
import traceback

import numpy as np

from .asset import read_usd_mesh, write_usd_mesh
from .job import INPUTS, OUTPUTS, SCRATCH, grut_copy, python, run, tell, whole_of
from .resolve import local_of

# How far a structure clears the place's colonies, and the sides of a tube.
STRUCTURE_CLEAR_M = 0.5
RING = 16
# A strip's sand, for the place's ground round it: its splats within
# SAND_BAND_M of its edge and SAND_OVER_M of its ground (the pipe or the reef
# is in the middle and stands up). The place's colour goes to it under the
# strip and back to its own over GROUND_FALLOFF_M.
SAND_BAND_M = 3.0
SAND_OVER_M = 0.5
GROUND_FALLOFF_M = 15.0
SH_C0 = 0.28209479177387814


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
    blend_ground(place, name, rec, P, [rec / piece["checkpoint"] for piece in manifest["pieces"]], n=n, of=of)
    return {"name": name, "placed": placed, "start": frames[0]["eye"], "ground": footprint(rec, P, placed["dz"])}


# -- the place's ground coloured to a strip ---------------------------------------------------------

def strip_colour(rec: pathlib.Path, checkpoints: list[pathlib.Path]) -> dict | None:
    """A strip's sand as its own splats have it: their base colour (the SH's
    DC term), opacity-weighted, over the band SAND_BAND_M in from its edge and
    within SAND_OVER_M of its ground. The parts are in the strip's own frame,
    as its surface is."""
    import torch
    from scipy import ndimage

    said = json.loads((rec / "surface.json").read_text())
    grid = np.fromfile(rec / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell, (ox, oy) = float(said["cellM"]), said["origin"]
    whole = whole_of(np.isfinite(grid), cell)
    band = whole & (ndimage.distance_transform_edt(np.pad(whole, 1))[1:-1, 1:-1] * cell <= SAND_BAND_M)
    total, weight, count = np.zeros(3), 0.0, 0
    for path in checkpoints:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        pos = ck["positions"].detach().double().numpy()
        alpha = torch.sigmoid(ck["density"].detach().double()).numpy().reshape(len(pos), -1)[:, 0]
        colour = np.clip(0.5 + SH_C0 * ck["features_albedo"].detach().double().numpy()[:, :3], 0.0, 1.0)
        del ck
        u = np.round((pos[:, 0] - ox) / cell).astype(int)
        v = np.round((pos[:, 1] - oy) / cell).astype(int)
        ok = (u >= 0) & (u < said["columns"]) & (v >= 0) & (v < said["rows"])
        sel = ok.copy()
        with np.errstate(invalid="ignore"):
            sel[ok] = band[v[ok], u[ok]] & (np.abs(pos[ok, 2] - grid[v[ok], u[ok]]) <= SAND_OVER_M)
        total += (alpha[sel, None] * colour[sel]).sum(0)
        weight += float(alpha[sel].sum())
        count += int(sel.sum())
    if weight <= 0:
        return None
    return {"colour": [float(c) for c in total / weight], "splats": count}


def ground_blend(rgb: np.ndarray, across: float, P: np.ndarray, whole: np.ndarray, cell: float, origin,
                 colour, falloff: float = GROUND_FALLOFF_M) -> tuple[np.ndarray, dict]:
    """The place's colour map (rows north to south, columns west to east, laid
    nought-to-one over `across` metres as make-site lays it) taken to `colour`
    over a strip's footprint (`whole`, its own grid, put in the place by P),
    and back to its own over `falloff` metres outside it, smoothstep on the
    distance. Only a window round the strip is touched."""
    from scipy import ndimage

    h, w = rgb.shape[:2]
    ox, oy = origin
    rr, cc = np.nonzero(whole)
    if not len(rr):
        return rgb, {"texels": 0}
    own = np.c_[ox + cc * cell, oy + rr * cell]
    xy = own @ P[:2, :2].T + P[:2, 3]                               # the strip's cells, in the place
    lo, hi = xy.min(0) - falloff - cell, xy.max(0) + falloff + cell
    c0, c1 = (np.clip(np.round((np.array([lo[0], hi[0]]) / across + 0.5) * w - 0.5), 0, w - 1)).astype(int)
    r0, r1 = (np.clip(np.round((0.5 - np.array([hi[1], lo[1]]) / across) * h - 0.5), 0, h - 1)).astype(int)
    C, R = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
    X, Y = ((C + 0.5) / w - 0.5) * across, (0.5 - (R + 0.5) / h) * across
    # A texel is under the strip if its centre is, or any of the strip's cells
    # is in it (a strip finer than the map's texels has no texel centre in it).
    back = (np.stack([X.ravel(), Y.ravel()], 1) - P[:2, 3]) @ P[:2, :2]
    u = np.round((back[:, 0] - ox) / cell).astype(int)
    v = np.round((back[:, 1] - oy) / cell).astype(int)
    ok = (u >= 0) & (u < whole.shape[1]) & (v >= 0) & (v < whole.shape[0])
    under = np.zeros(len(u), dtype=bool)
    under[ok] = whole[v[ok], u[ok]]
    under = under.reshape(C.shape)
    tc = np.round((xy[:, 0] / across + 0.5) * w - 0.5).astype(int) - c0
    tr = np.round((0.5 - xy[:, 1] / across) * h - 0.5).astype(int) - r0
    ok = (tc >= 0) & (tc < C.shape[1]) & (tr >= 0) & (tr < C.shape[0])
    under[tr[ok], tc[ok]] = True
    if not under.any():
        return rgb, {"texels": 0}
    d = ndimage.distance_transform_edt(~under, sampling=(across / h, across / w))
    t = np.clip(d / max(falloff, 1e-6), 0.0, 1.0)
    weight = 1.0 - t * t * (3.0 - 2.0 * t)
    out = rgb.astype(float).copy()
    window = out[r0:r1 + 1, c0:c1 + 1]
    before = window[under].mean(0)
    out[r0:r1 + 1, c0:c1 + 1] = window * (1.0 - weight[..., None]) + np.asarray(colour, float) * weight[..., None]
    return out, {"texels": int((weight > 0).sum()), "texelsUnder": int(under.sum()),
                 "before": [float(c) for c in before]}


def blend_ground(place: pathlib.Path, name: str, rec: pathlib.Path, P: np.ndarray, checkpoints: list[pathlib.Path],
                 colour=None, n: int = 1, of: int = 1) -> dict | None:
    """The place's ground colour (textures/site_colour.jpg, which make-site
    writes for a place with a ground) taken to a strip's sand under it and
    round it, so the strip is not a carpet of another colour on the floor;
    recorded on the strip in site.json. `colour` given, its splats are not
    read (tests). A place painted some other way is left as it is."""
    site_path = place / "site.json"
    site = json.loads(site_path.read_text())
    texture = place / "textures" / "site_colour.jpg"
    if site.get("ground") is None or not texture.is_file():
        tell("ground", f"{name}: the place has no colour map of its own; its ground is left as it is", n=n, of=of)
        return None
    from PIL import Image

    said = json.loads((rec / "surface.json").read_text())
    grid = np.fromfile(rec / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell = float(said["cellM"])
    splats = None
    if colour is None:
        found = strip_colour(rec, checkpoints)
        if not found:
            tell("ground", f"{name}: no splats by the strip's edge to take a colour from; the ground is left",
                 n=n, of=of)
            return None
        colour, splats = found["colour"], found["splats"]
    rgb = np.asarray(Image.open(texture).convert("RGB"), dtype=float) / 255.0
    out, how = ground_blend(rgb, float(site["from"]["acrossMetres"]), P, whole_of(np.isfinite(grid), cell), cell,
                            said["origin"], colour)
    if not how["texels"]:
        return None
    Image.fromarray(np.clip(np.round(out * 255), 0, 255).astype("uint8")).save(texture, quality=95)
    record = {"colour": [round(float(c), 4) for c in colour], "falloffM": GROUND_FALLOFF_M,
              "texture": "textures/site_colour.jpg", "placeColourBefore": [round(c, 4) for c in how["before"]],
              "texels": how["texels"], "texelsUnder": how["texelsUnder"], "splats": splats,
              "kind": "derived",
              "from": (f"derived: from the asset's splats, their base colour opacity-weighted within {SAND_BAND_M:g} m "
                       f"of the strip's edge and {SAND_OVER_M:g} m of its ground; the place's colour taken to it "
                       f"under the strip and back to its own over {GROUND_FALLOFF_M:g} m (smoothstep)")}
    for entry in site.get("reconstructions") or []:
        if entry.get("name") == name:
            entry["groundColour"] = record
    site_path.write_text(json.dumps(site, indent=1))
    tell("ground", f"{name}: the place's ground taken to the strip's sand under it and over {GROUND_FALLOFF_M:g} m "
                   "round it", n=n, of=of, colour=record["colour"])
    return record


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


# -- structures -------------------------------------------------------------------------------------

def seabed_of(place: pathlib.Path, site: dict):
    """The bottom under many points as the runtime reads it (its Seabed): the
    place's heightfield, bilinear and clamped at its edge, with every ground
    laid over it (surfaces: a reef's, a structure's) faded in over its feather."""
    hf = site["mesh"]["heightfield"]
    h = np.fromfile(place / hf["file"], dtype="<f4").reshape(hf["rows"], hf["columns"]).astype(float)
    across = float(site["from"]["acrossMetres"])
    rows, cols = h.shape
    laid = []
    for said in site.get("surfaces") or []:
        try:
            g = np.fromfile(place / said["file"], dtype="<f4").reshape(said["rows"], said["columns"]).astype(float)
        except (OSError, ValueError, KeyError):
            continue
        laid.append((g, said["origin"], math.radians(float(said.get("headingDeg", 0.0))), float(said["cellM"]),
                     max(float(said.get("featherM", 1.0)), 1e-6)))

    def bilinear(g, u, v):
        r_, c_ = g.shape
        uu, vv = np.clip(u, 0.0, c_ - 1.0001), np.clip(v, 0.0, r_ - 1.0001)
        c, r = uu.astype(int), vv.astype(int)
        fu, fv = uu - c, vv - r
        corners = np.stack([g[r, c], g[r, c + 1], g[r + 1, c], g[r + 1, c + 1]])
        weights = np.stack([(1 - fu) * (1 - fv), fu * (1 - fv), (1 - fu) * fv, fu * fv])
        known = np.isfinite(corners)
        total = np.where(known, weights, 0.0).sum(0)
        z = (np.where(known, corners, 0.0) * weights).sum(0) / np.maximum(total, 1e-12)
        return np.where(total > 0, z, np.nan), total

    def under(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        out, _ = bilinear(h, (x / across + 0.5) * (cols - 1), (y / across + 0.5) * (rows - 1))
        for g, (ox, oy), a, cell, feather in laid:
            dx, dy = x - ox, y - oy
            u = (math.cos(a) * dx + math.sin(a) * dy) / cell
            v = (-math.sin(a) * dx + math.cos(a) * dy) / cell
            r_, c_ = g.shape
            inside = (u >= 0) & (u <= c_ - 1) & (v >= 0) & (v <= r_ - 1)
            z, total = bilinear(g, u, v)
            edge = np.minimum.reduce([u, v, c_ - 1 - u, r_ - 1 - v]) * cell
            w = np.where(inside & np.isfinite(z), np.clip(edge / feather, 0, 1) * np.clip(total, 0, 1), 0.0)
            out = w * np.nan_to_num(z) + (1 - w) * out
        return out
    return under


def inside_place(site: dict, xy, what: str) -> None:
    half = float(site["from"]["acrossMetres"]) / 2
    worst = float(np.abs(np.atleast_2d(np.asarray(xy, float))).max())
    if worst > half:
        raise ValueError(f"{what} is outside the place: {worst:,.0f} m from its centre, which is {half:,.0f} m "
                         "from its edge")


def stand_at(site: dict, placement: dict, under) -> dict:
    """Where a model stands: its lat/lon in the place's metres, its base on
    the seabed there, turned headingDeg about z."""
    x, y = local_of(site, float(placement["lat"]), float(placement["lon"]))
    z = float(under(np.array([x]), np.array([y]))[0])
    heading = float(placement.get("headingDeg") or 0.0)
    t = math.radians(heading)
    m = np.eye(4)
    m[:3, :3] = [[math.cos(t), -math.sin(t), 0], [math.sin(t), math.cos(t), 0], [0, 0, 1]]
    m[:3, 3] = [x, y, z]
    return {"at": [float(x), float(y)], "headingDeg": heading, "baseZ": z, "matrix": m.tolist()}


def along_route(xy: np.ndarray, step: float) -> np.ndarray:
    """A route's points every `step` metres or less, its corners kept."""
    out = []
    for a, b in zip(xy[:-1], xy[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
        out.append(a + (np.arange(n) / n)[:, None] * (b - a))
    return np.concatenate(out + [xy[-1:]])


def tube(xy, diameter: float, burial: float, under, step: float | None = None,
         ring: int = RING) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A pipeline along a route on the seabed: its centre every `step` metres,
    on the bottom under it less burial x diameter, plus its radius. The tube's
    vertices, its triangles (capped at both ends) and the centre line."""
    r = diameter / 2
    pts = along_route(np.asarray(xy, float), step or float(np.clip(diameter, 0.1, 1.0)))
    centre = np.c_[pts, under(pts[:, 0], pts[:, 1]) - burial * diameter + r]
    t = np.gradient(centre, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    side = np.cross(t, [0.0, 0.0, 1.0])
    side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-12)
    up = np.cross(side, t)
    a = 2 * math.pi * np.arange(ring) / ring
    verts = (centre[:, None, :] + r * (np.cos(a)[None, :, None] * side[:, None, :]
                                       + np.sin(a)[None, :, None] * up[:, None, :])).reshape(-1, 3)
    n = len(centre)
    k, j = np.meshgrid(np.arange(n - 1), np.arange(ring), indexing="ij")
    p0, p1 = k * ring + j, k * ring + (j + 1) % ring
    q0, q1 = p0 + ring, p1 + ring
    faces = np.concatenate([np.stack([p0, p1, q1], -1).reshape(-1, 3), np.stack([p0, q1, q0], -1).reshape(-1, 3)])
    first, last = len(verts), len(verts) + 1
    verts = np.vstack([verts, centre[0], centre[-1]])
    jj = np.arange(ring)
    caps = np.concatenate([np.stack([np.full(ring, first), (jj + 1) % ring, jj], -1),
                           np.stack([np.full(ring, last), (n - 1) * ring + jj, (n - 1) * ring + (jj + 1) % ring], -1)])
    # Wound so each triangle faces out of the pipe: the other way the renderer
    # saw the inside of every face and drew the pipe black.
    return verts, np.concatenate([faces, caps])[:, ::-1].astype(np.int64), centre


def pipe_tops(xy, centre: np.ndarray, diameter: float, under, longest: float = 200.0) -> list[dict]:
    """A pipeline's top as height grids, one strip along each leg (a long leg
    in pieces of `longest` metres), rounded past each end so a corner is
    whole: the tube's crown where it is above the seabed, the seabed where it
    is buried, nothing off it."""
    xy = np.asarray(xy, float)
    r = diameter / 2
    cell = float(np.clip(diameter / 6, 0.03, 0.25))
    half = r + 3 * cell
    grids = []
    for a, b in zip(xy[:-1], xy[1:]):
        length = float(np.linalg.norm(b - a))
        d = (b - a) / length
        perp = np.array([-d[1], d[0]])
        heading = math.degrees(math.atan2(d[1], d[0]))
        # The centre's height along this leg, by distance from its start.
        s_c, t_c = (centre[:, :2] - a) @ d, (centre[:, :2] - a) @ perp
        on = (np.abs(t_c) < 1e-6) & (s_c >= -1e-6) & (s_c <= length + 1e-6)
        order = np.argsort(s_c[on])
        s_on, z_on = s_c[on][order], centre[on, 2][order]
        start = 0.0
        while start < length - 1e-9:
            end = min(length, start + longest)
            s0, s1 = start - half, end + half
            cols = int(math.ceil((s1 - s0) / cell)) + 1
            rows = int(math.ceil(2 * half / cell)) + 1
            S, T = np.meshgrid(s0 + np.arange(cols) * cell, -half + np.arange(rows) * cell)
            along = np.clip(S, 0.0, length)
            dist = np.hypot(T, S - along)
            cz = np.interp(along, s_on, z_on)
            X, Y = a[0] + S * d[0] + T * perp[0], a[1] + S * d[1] + T * perp[1]
            ground = under(X.ravel(), Y.ravel()).reshape(X.shape)
            top = np.where(dist < r, cz + np.sqrt(np.maximum(r * r - dist * dist, 0.0)), np.nan)
            corner = a + s0 * d - half * perp
            grids.append({"grid": np.where(np.isfinite(top), np.maximum(top, ground), np.nan).astype("<f4"),
                          "origin": [float(corner[0]), float(corner[1])], "headingDeg": heading, "cellM": cell})
            start = end
    return grids


def model_top(points: np.ndarray, faces: np.ndarray, cell: float | None = None) -> dict:
    """A model's top as a height grid, north up: the highest of its surface
    over each cell, nothing where it is not. Points sampled over every
    triangle, eight a cell, so walls count; widened a cell, so it is never
    thinner than it is."""
    from scipy import ndimage

    lo, hi = points[:, :2].min(0), points[:, :2].max(0)
    cell = cell or float(np.clip((hi - lo).max() / 300, 0.05, 1.0))
    origin = lo - 2 * cell
    cols, rows = (np.ceil((hi - lo) / cell).astype(int) + 5)
    a, b, c = (points[faces[:, k]] for k in range(3))
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    n = np.clip(np.ceil(area / (cell * cell / 8)).astype(int), 1, None)
    if n.sum() > 6_000_000:
        n = np.clip((n * 6_000_000 / n.sum()).astype(int), 1, None)
    pick = np.repeat(np.arange(len(faces)), n)
    rng = np.random.default_rng(0)
    u, v = rng.random(len(pick)), rng.random(len(pick))
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    p = np.vstack([a[pick] + u[:, None] * (b[pick] - a[pick]) + v[:, None] * (c[pick] - a[pick]), points])
    ij = np.clip(np.floor((p[:, :2] - origin) / cell + 0.5).astype(int), 0, [cols - 1, rows - 1])
    top = np.full((rows, cols), -np.inf)
    np.maximum.at(top, (ij[:, 1], ij[:, 0]), p[:, 2])
    top = ndimage.maximum_filter(top, size=3)
    return {"grid": np.where(np.isfinite(top), top, np.nan).astype("<f4"),
            "origin": [float(origin[0]), float(origin[1])], "headingDeg": 0.0, "cellM": cell}


def cells_of(top: dict) -> np.ndarray:
    """Where a height grid says something, in the place: each cell's centre."""
    rr, cc = np.nonzero(np.isfinite(top["grid"]))
    a = math.radians(top["headingDeg"])
    u, v = cc * top["cellM"], rr * top["cellM"]
    return np.c_[top["origin"][0] + math.cos(a) * u - math.sin(a) * v,
                 top["origin"][1] + math.sin(a) * u + math.cos(a) * v]


def clear_colonies(place: pathlib.Path, site: dict, xy: np.ndarray, within: float) -> int:
    """The place's own colonies within `within` metres of `xy` taken off."""
    coral_file = (site.get("layers") or {}).get("coral")
    if not coral_file or not (place / coral_file).exists() or not len(xy):
        return 0
    from pxr import Usd, UsdGeom
    from scipy.spatial import cKDTree

    tree = cKDTree(xy)
    removed = 0
    stage = Usd.Stage.Open(str(place / coral_file))
    for prim in stage.Traverse():
        if prim.GetTypeName() != "PointInstancer":
            continue
        pos = np.array(UsdGeom.PointInstancer(prim).GetPositionsAttr().Get() or [], dtype=float)
        if not len(pos):
            continue
        d, _ = tree.query(pos[:, :2], distance_upper_bound=within)
        keep = ~np.isfinite(d)
        if keep.all():
            continue
        kept = np.flatnonzero(keep)
        for attr in prim.GetAttributes():
            value = attr.Get()
            try:
                length = len(value)
            except TypeError:
                continue
            if length != len(pos) or attr.GetName() in ("invisibleIds", "inactiveIds"):
                continue
            attr.Set(type(value)([value[int(i)] for i in kept]))
        removed += int((~keep).sum())
    stage.GetRootLayer().Save()
    return removed


# What a structure is made of, as it looks a few years on the seabed: a
# platform's or a foundation's steel painted and fouled, a pipeline's concrete
# weight coat. Chosen, not measured.
SURFACES = {
    "platform": {"colour": (0.30, 0.31, 0.29), "roughness": 0.6, "metallic": 0.35},
    "wind-foundation": {"colour": (0.33, 0.35, 0.30), "roughness": 0.6, "metallic": 0.3},
    "pipeline": {"colour": (0.46, 0.44, 0.40), "roughness": 0.95, "metallic": 0.0},
    "other": {"colour": (0.40, 0.40, 0.40), "roughness": 0.8, "metallic": 0.1},
}


def surface_of(kind: str | None) -> dict:
    return SURFACES.get(kind or "other", SURFACES["other"])


STANDING = '''#usda 1.0
(
    doc = "{name}: a structure ({kind}) standing on this place's seabed. Metres, Z up."
    defaultPrim = "Structure"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "Structure" (
    prepend references = @model.usdc@
    prepend apiSchemas = ["MaterialBindingAPI"]
)
{{
    double3 xformOp:translate = ({x!r}, {y!r}, {z!r})
    float xformOp:rotateZ = {heading!r}
    uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateZ"]
    rel material:binding = </Structure/Looks/Surface>

    def Scope "Looks"
    {{
        def Material "Surface"
        {{
            token outputs:surface.connect = </Structure/Looks/Surface/Shader.outputs:surface>

            def Shader "Shader"
            {{
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = ({r!r}, {g!r}, {b!r})
                float inputs:roughness = {roughness!r}
                float inputs:metallic = {metallic!r}
                token outputs:surface
            }}
        }}
    }}
}}
'''


def lay_structure(asset: dict, src: pathlib.Path, place: pathlib.Path, n: int, of: int) -> dict:
    """A structure laid into `place`: drawn, stood on, recorded; what the
    place now holds of it."""
    name = asset["name"]
    made = json.loads((src / "asset.json").read_text())
    if made.get("kind") != "structure":
        raise ValueError(f"{name} is a {made.get('kind')}, not a structure")
    meets = asset.get("meets") or made.get("meets") or "stands"
    site_path = place / "site.json"
    site = json.loads(site_path.read_text())
    under = seabed_of(place, site)
    into = place / "structures" / name
    shutil.rmtree(into, ignore_errors=True)
    into.mkdir(parents=True)
    warnings = []
    record = {"name": name, "type": made.get("type"), "meets": meets, "madeFrom": made.get("madeFrom"),
              "asset": asset.get("path")}
    if made.get("route"):
        route = made["route"]
        diameter, burial = float(route["diameterM"]), float(route.get("burial") or 0.0)
        xy = np.array([local_of(site, float(lat), float(lon)) for lat, lon in route["points"]])
        inside_place(site, xy, f"{name}'s route")
        tell("place", f"{name}: {len(xy)} points, {made['stats']['lengthM']:,.0f} m of pipe {diameter:g} m across "
                      f"on the seabed, {burial * 100:.0f}% buried", n=n, of=of)
        verts, faces, centre = tube(xy, diameter, burial, under)
        tops = pipe_tops(xy, centre, diameter, under)
        shift = np.round(centre.mean(0))
        write_usd_mesh(into / "structure.usdc", verts - shift, faces, np.full((1, 3), [0.45, 0.42, 0.38]),
                       doc=f"{name}: a pipeline {diameter:g} m across along its route on this place's seabed, "
                           f"{burial * 100:.0f}% buried. Metres, Z up.", translate=shift,
                       surface=surface_of("pipeline"))
        layer = f"structures/{name}/structure.usdc"
        start = [float(centre[0, 0]), float(centre[0, 1]), float(centre[0, 2] + diameter / 2 + 2.0)]
        placed = {"at": [float(v) for v in xy[0]], "headingDeg": 0.0, "dz": 0.0}
        record.update(route={"points": route["points"], "lengthM": made["stats"].get("lengthM"),
                             "local": [[round(float(a), 2), round(float(b), 2)] for a, b in xy],
                             "diameterM": diameter, "burial": burial},
                      triangles=int(len(faces)))
    else:
        if not asset.get("placement"):
            raise ValueError(f"{name} is a model: it needs a placement {{lat, lon, headingDeg}}")
        at = stand_at(site, asset["placement"], under)
        inside_place(site, at["at"], name)
        M = np.array(at["matrix"])
        model = src / (made.get("model") or "model.usdc")
        local, faces = read_usd_mesh(model)
        world = (M @ np.c_[local, np.ones(len(local))].T)[:3].T
        ground = under(world[:, 0], world[:, 1])
        spread = float(ground.max() - ground.min())
        if meets == "drapes":
            # Each vertex follows the seabed under it, as the base does at the middle.
            world[:, 2] += ground - at["baseZ"]
            shift = np.round(world.mean(0))
            write_usd_mesh(into / "structure.usdc", world - shift, faces, None, translate=shift,
                           doc=f"{name}: a structure following this place's seabed. Metres, Z up.",
                           surface=surface_of(made.get("type")))
            layer = f"structures/{name}/structure.usdc"
        else:
            if spread > 0.5:
                warnings.append(f"{name} stands where the seabed under it varies {spread:.1f} m: its base is at "
                                "the seabed at its middle, so some of it is buried or off the bottom")
            shutil.copy(model, into / "model.usdc")
            x, y, z = (float(v) for v in M[:3, 3])
            look = surface_of(made.get("type"))
            r, g, b = look["colour"]
            (into / "structure.usda").write_text(STANDING.format(name=name, kind=made.get("type") or "other",
                                                                 x=x, y=y, z=z, heading=at["headingDeg"],
                                                                 r=r, g=g, b=b, roughness=look["roughness"],
                                                                 metallic=look["metallic"]))
            layer = f"structures/{name}/structure.usda"
        tell("place", f"{name}: at ({at['at'][0]:.0f}, {at['at'][1]:.0f}) m, turned {at['headingDeg']:g} degrees, "
                      f"its base at {at['baseZ']:.1f} m", n=n, of=of, at=at["at"], headingDeg=at["headingDeg"])
        tops = [model_top(world, faces)]
        reach = float((world[:, :2].max(0) - world[:, :2].min(0)).max()) / 2 + 5.0
        start = [at["at"][0], at["at"][1] - reach, 0.0]
        start[2] = float(under(np.array([start[0]]), np.array([start[1]]))[0] + 2.0)
        placed = {"at": at["at"], "headingDeg": at["headingDeg"], "dz": at["baseZ"]}
        record.update(placement=dict(asset["placement"], at=[round(v, 2) for v in at["at"]],
                                     baseZ=round(at["baseZ"], 2)),
                      seabedUnderM=[round(float(ground.min()), 2), round(float(ground.max()), 2)],
                      triangles=int(len(faces)))

    # Its top in the ground the runtime reads; the place's colonies off it.
    surfaces = []
    for k, top in enumerate(tops):
        file = f"structures/{name}/surface-{k + 1}.f32"
        top["grid"].tofile(place / file)
        rows, cols = top["grid"].shape
        surfaces.append({"name": f"{name}/{k + 1}", "file": file, "rows": int(rows), "columns": int(cols),
                         "cellM": top["cellM"], "origin": top["origin"], "headingDeg": top["headingDeg"],
                         "featherM": top["cellM"], "from": f"the top of {name}, a structure"})
    footprint = np.concatenate([cells_of(top) for top in tops])
    removed = clear_colonies(place, site, footprint, STRUCTURE_CLEAR_M)
    layers = site.setdefault("layers", {})
    layers["reconstructions"] = [r for r in layers.get("reconstructions") or [] if r.get("name") != name]
    layers["reconstructions"].append({"name": name, "file": layer, "kind": "structure"})
    site["surfaces"] = [s for s in site.get("surfaces") or []
                        if s.get("name") != name and not str(s.get("name", "")).startswith(f"{name}/")] + surfaces
    record.update(file=layer, drawn=f"/World/Reconstructions/{re.sub(r'[^A-Za-z0-9_]', '_', name)}",
                  surfaces=[s["name"] for s in surfaces], coloniesRemoved=removed,
                  collides="as ground: its top is in surfaces, which the seabed reads (a grid has no underside)")
    site["structures"] = [r for r in site.get("structures") or [] if r.get("name") != name] + [record]
    if warnings:
        site.setdefault("warnings", []).extend(warnings)
    site_path.write_text(json.dumps(site, indent=1))
    for one in warnings:
        tell("warning", one)
    # Its ground about a sample a metre, for overlaps.
    every = max(1, int(round(1.0 / min(t["cellM"] for t in tops))) ** 2)
    return {"name": name, "placed": placed, "start": start, "ground": footprint[::every], "structure": True}


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
        code = None
        laid = []
        for i, asset in enumerate(assets):
            src = INPUTS / (asset.get("path") or "reconstruction")
            if asset.get("kind") == "structure":
                laid.append(lay_structure(asset, src, place, i + 1, len(assets)))
                continue
            code = code or grut_copy()
            laid.append(lay_one(asset, src, place, SCRATCH / f"asset-{i + 1}", code, float(brief.get("sink", 1.0)),
                                float(brief.get("clear", 1.5)), i + 1, len(assets)))
        crossed = overlaps(laid) if len(laid) > 1 else []
        for one in crossed:
            tell("overlap", one)
        site = json.loads((place / "site.json").read_text())
        # A dive begins over the first reef laid, where its video's swim
        # began: it is why this version exists.
        if site.get("beginAt") is not None and "beginAtBefore" not in site:
            site["beginAtBefore"] = {"at": site["beginAt"], "because": site.get("beginBecause")}
        site["beginAt"] = [round(float(v), 2) for v in laid[0]["start"]]
        site["beginBecause"] = (f"beside {laid[0]['name']}, the structure laid in" if laid[0].get("structure") else
                                f"where the video {laid[0]['name']} was rebuilt from began its swim")
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
