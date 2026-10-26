"""A reef rebuilt from a dive video laid into one of our places.

    python place_in_map.py PLACE NAME PLACEMENT SURFACE_DIR ALIGN_MAP PART.usdz [PART.usdz ...]
        --pieces 1:260,261:500,501:756 [--sink 1.0] [--clear 1.5] [--video '{...}']

PLACEMENT is place_choose.py's (the strip's frame to the place's); the parts
are NuRec splats already baked into the place's frame through it
(bake_splats.py with ALIGN_MAP, whose frames are the swim in the place).
Into PLACE, which is changed (work on a copy):

  reconstructions/NAME/   the parts, splats.usda referencing them, and
                          surface.f32: the ground the splats stand on, lifted
                          by the placement's dz
  site.json               layers.reconstructions (drawn at
                          /World/Reconstructions/NAME), surfaces (the ground,
                          read by the seabed for physics, altitude and fish),
                          reconstructions[] (provenance and its pieces, each
                          with its stretch of the swim, drawn one at a time)
  seabed.usda             the drawn ground lowered under the strip, to --sink
                          metres below the reef's own ground, so it does not
                          stand through the splats; physics is the surface's
  (the reconstruction is drawn at /World/Reconstructions/<NAME with every
  character not a letter, digit or _ made _>)
  coral.usda              the place's own colonies taken off the strip and
                          --clear metres round it

Run inside iocean/3dgrut (pxr).
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import shutil

import numpy as np
from pxr import Sdf, Usd, UsdGeom, Vt
from scipy import ndimage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("place", type=pathlib.Path)
    ap.add_argument("name")
    ap.add_argument("placement", type=pathlib.Path)
    ap.add_argument("surface", type=pathlib.Path)
    ap.add_argument("align", type=pathlib.Path)
    ap.add_argument("parts", nargs="+", type=pathlib.Path)
    ap.add_argument("--pieces", required=True)
    ap.add_argument("--sink", type=float, default=1.0)
    ap.add_argument("--keep-edge", type=float, default=0.0,
                    help="metres: the ground is lowered only under the strip this far in from its edge "
                         "(a strip whose edge fades shows a lowered rim through it)")
    ap.add_argument("--clear", type=float, default=1.5)
    ap.add_argument("--video", default="{}")
    ap.add_argument("--translate", default="",
                    help="X,Y,Z put on the reef's layer: the parts were baked near the origin with this "
                         "taken off, because NuRec keeps positions at half precision (0.5 m steps at 550 m)")
    a = ap.parse_args()
    ranges = [tuple(int(v) for v in r.split(":")) for r in a.pieces.split(",")]
    if len(ranges) != len(a.parts):
        raise SystemExit(f"{len(a.parts)} parts but {len(ranges)} piece ranges")

    placed = json.loads(a.placement.read_text())
    P = np.array(placed["matrix"])
    heading, dz = float(placed["headingDeg"]), float(placed["dz"])
    said = json.loads((a.surface / "surface.json").read_text())
    grid = np.fromfile(a.surface / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell = float(said["cellM"])
    ox, oy = said["origin"]

    # The parts and their layer.
    into = a.place / "reconstructions" / a.name
    into.mkdir(parents=True, exist_ok=True)
    names = []
    for i, part in enumerate(a.parts):
        shutil.copy(part, into / f"splats-{i}.usdz")
        names.append(f"splats-{i}.usdz")
    move = ""
    if a.translate:
        tx, ty, tz = (float(v) for v in a.translate.split(","))
        move = f'''
    double3 xformOp:translate = ({tx}, {ty}, {tz})
    uniform token[] xformOpOrder = ["xformOp:translate"]
'''
    parts = "".join(f'''
    def Xform "Part{i}" (
        prepend references = @{n}@
    )
    {{
    }}
''' for i, n in enumerate(names))
    (into / "splats.usda").write_text(f'''#usda 1.0
(
    doc = "{a.name}: a reef rebuilt from a dive video (3DGRUT splats, NuRec, in pieces drawn one at a time), baked into this place's frame. Metres, Z up."
    defaultPrim = "Reef"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "Reef"
{{{move}{parts}}}
''')

    # Its ground, in the place: the grid's corner through the placement.
    lifted = (grid + dz).astype("<f4")
    lifted.tofile(into / "surface.f32")
    corner = P @ np.array([ox, oy, 0.0, 1.0])
    surface = {"name": a.name, "file": f"reconstructions/{a.name}/surface.f32", "rows": int(said["rows"]),
               "columns": int(said["columns"]), "cellM": cell, "origin": [float(corner[0]), float(corner[1])],
               "headingDeg": heading, "featherM": 1.0, "from": said.get("from", "")}

    # Where the strip is, in the place: every measured cell's centre.
    rr, cc = np.nonzero(np.isfinite(grid))
    local = np.stack([ox + cc * cell, oy + rr * cell, np.zeros(len(rr)), np.ones(len(rr))])
    xy = (P @ local)[:2].T
    zt = lifted[rr, cc].astype(float)

    # The swim, in the place, cut into each piece's stretch.
    told = json.loads(a.align.read_text())
    frames = sorted(told["frames"], key=lambda f: f["name"])
    prim = re.sub(r"[^A-Za-z0-9_]", "_", a.name)            # what the runtime names it
    pieces = [{"prim": f"/World/Reconstructions/{prim}/Part{i}", "frames": [lo, hi],
               "path": [[round(float(v), 3) for v in f["eye"]] for f in frames[lo - 1:hi:2]]}
              for i, (lo, hi) in enumerate(ranges)]

    site_path = a.place / "site.json"
    site = json.loads(site_path.read_text())
    layers = site.setdefault("layers", {})
    layers["reconstructions"] = [r for r in layers.get("reconstructions") or [] if r.get("name") != a.name]
    layers["reconstructions"].append({"name": a.name, "file": f"reconstructions/{a.name}/splats.usda"})
    site["surfaces"] = [s for s in site.get("surfaces") or [] if s.get("name") != a.name] + [surface]
    site["reconstructions"] = [r for r in site.get("reconstructions") or [] if r.get("name") != a.name] + [{
        "name": a.name, "kind": "splats", "video": json.loads(a.video),
        "placement": {"at": placed["at"], "headingDeg": heading, "dzM": dz, "fit": placed.get("fit")},
        "pieces": pieces,
        "drawn": "the piece whose stretch of the swim is nearest the camera, one at a time",
        "light": "carried: the splats hold the video's own water; the place's water is on top of it",
    }]

    # The drawn ground lowered under the strip: under its solid core only, when
    # its edge fades (--keep-edge), or the lowered ground shows through the
    # fade as a dark rim along both sides.
    stage = Usd.Stage.Open(str(a.place / layers.get("terrain", "seabed.usda")))
    lowered = 0
    from scipy.spatial import cKDTree
    under, under_z = xy, zt
    if a.keep_edge > 0:
        from scipy import ndimage
        whole = ndimage.binary_fill_holes(np.isfinite(grid))
        inside_m = ndimage.distance_transform_edt(np.pad(whole, 1))[1:-1, 1:-1] * cell
        core = inside_m[rr, cc] >= a.keep_edge
        if core.any():
            under, under_z = xy[core], zt[core]
    tree = cKDTree(under)
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        mesh = UsdGeom.Mesh(prim)
        world = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
        pts = np.array(mesh.GetPointsAttr().Get(), dtype=float)
        wp = (world @ np.c_[pts, np.ones(len(pts))].T)[:3].T
        # A vertex anywhere near the strip, within a cell of the mesh, goes under it.
        spacing = float(np.median(np.abs(np.diff(np.unique(np.round(wp[:, 0], 2)))))) if len(wp) > 2 else 5.0
        # Under a core (--keep-edge) only the vertices over it, half a mesh
        # cell either way; otherwise the reach carried the lowering back out
        # to the edge it was kept off.
        reach = 0.5 * spacing if a.keep_edge > 0 else max(spacing, 2.0) + 1.0
        d, j = tree.query(wp[:, :2], distance_upper_bound=reach)
        hit = np.isfinite(d)
        if not hit.any():
            continue
        floor = np.full(len(wp), np.inf)
        floor[hit] = under_z[j[hit]] - a.sink
        # The lowest of the strip near each vertex, not the one cell nearest it.
        for k in np.where(hit)[0]:
            near = tree.query_ball_point(wp[k, :2], reach if a.keep_edge > 0 else max(spacing, 2.0))
            if near:
                floor[k] = min(floor[k], float(under_z[near].min()) - a.sink)
        new = np.minimum(wp[:, 2], floor)
        changed = new < wp[:, 2] - 1e-6
        if changed.any():
            inv = np.linalg.inv(world)
            wp[:, 2] = new
            back = (inv @ np.c_[wp, np.ones(len(wp))].T)[:3].T
            mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(back.astype(np.float32)))
            lowered += int(changed.sum())
    stage.GetRootLayer().Save()

    # The place's own colonies off the strip.
    removed = 0
    coral_file = layers.get("coral")
    if coral_file and (a.place / coral_file).exists():
        cstage = Usd.Stage.Open(str(a.place / coral_file))
        for prim in cstage.Traverse():
            if prim.GetTypeName() != "PointInstancer":
                continue
            inst = UsdGeom.PointInstancer(prim)
            pos = np.array(inst.GetPositionsAttr().Get() or [], dtype=float)
            if not len(pos):
                continue
            d, _ = tree.query(pos[:, :2], distance_upper_bound=a.clear)
            keep = ~np.isfinite(d)
            if keep.all():
                continue
            n = len(pos)
            kept = np.flatnonzero(keep)
            for attr in prim.GetAttributes():
                value = attr.Get()
                try:
                    length = len(value)
                except TypeError:
                    continue
                if length != n or attr.GetName() in ("invisibleIds", "inactiveIds"):
                    continue
                attr.Set(type(value)([value[int(i)] for i in kept]))
            removed += int((~keep).sum())
        cstage.GetRootLayer().Save()

    site_path.write_text(json.dumps(site, indent=1))
    print(json.dumps({"reconstruction": a.name, "parts": len(names), "surfaceCells": int(len(xy)),
                      "groundVerticesLowered": lowered, "coloniesRemoved": removed,
                      "at": placed["at"], "headingDeg": heading, "dzM": round(dz, 2)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
