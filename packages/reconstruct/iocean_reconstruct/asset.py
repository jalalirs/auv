"""Something that is not a reef made into an asset: a seabed survey, a
structure from a 3D model, or a pipeline from its route. Each is checked,
measured, pictured and packed for the library; laying a structure into a
place is lay.py's, a survey goes into a place build as one of its files.

    python -m iocean_reconstruct.asset '<brief>'

The brief (docs/plan/assets-contract.md; services/control-plane):

    {"kind": "bathymetry", "file": {"path": "source/<name>", "name", "format": "geotiff|xyz"},
     "datum": "MSL|LAT|...", "errorM": 0.3}
    {"kind": "structure", "type": "platform|wind-foundation|pipeline|other", "meets": "stands|drapes",
     "model": {"path": "source/<name>", "name", "format": "glb|gltf|obj", "scale": 1.0, "up": "y|z"}}
    {"kind": "structure", "type": "pipeline", "meets": "drapes",
     "route": {"points": [[lat, lon], ...], "diameterM": 0.5, "burial": 0.3}}

Inputs: /work/inputs/source/<name>, the uploaded object (none for a route).
Written: /work/outputs/asset.tar, holding

  asset.json    kind, type, meets, madeFrom, footprint, stats, preview, and
                what the next step reads: the survey's "file", the model's
                "model", the route's "route"
  preview.png   a picture for the library card
  model.usdc    a model: metres, z up, centred in x and y, its base on z = 0
  <the survey>  a survey, as it was uploaded

A survey's xyz rows are latitude, longitude, depth; depth either way up
(all of them at or below zero are heights, as a place keeps them). They are
kept as longitude, latitude, height, the order the places job reads.
Each step said as {"progress": {...}} on stdout, as the other jobs do.
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

from .job import INPUTS, OUTPUTS, SCRATCH, tell

KINDS = ("bathymetry", "structure")
TYPES = ("platform", "wind-foundation", "pipeline", "other")
MEETS = ("stands", "drapes")
# A model bigger than this is in the wrong units (millimetres, most often).
LARGEST_M = 3000.0


def metres_per_degree(lat: float) -> tuple[float, float]:
    """East and north metres in a degree at a latitude (resolve.local_of's)."""
    north = 111132.92 - 559.82 * math.cos(2 * math.radians(lat)) + 1.175 * math.cos(4 * math.radians(lat))
    east = 111412.84 * math.cos(math.radians(lat)) - 93.5 * math.cos(3 * math.radians(lat))
    return east, north


def degrees_ok(lat, lon) -> bool:
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    return bool(np.all(np.isfinite(lat)) and np.all(np.isfinite(lon)) and np.all(np.abs(lat) <= 90)
                and np.all(np.abs(lon) <= 180))


def bbox_of(lat, lon) -> list[float]:
    """[south, west, north, east], degrees."""
    return [round(float(np.min(lat)), 7), round(float(np.min(lon)), 7),
            round(float(np.max(lat)), 7), round(float(np.max(lon)), 7)]


def depth_stats(values, datum, error) -> dict:
    """A survey's depths, positive down, whichever way up they came."""
    z = np.asarray(values, float)
    z = z[np.isfinite(z)]
    if not len(z):
        raise ValueError("the survey holds no depths")
    # Heights (negative down), as a place keeps them, when none is above the
    # surface; depths otherwise.
    heights = bool(np.all(z <= 0))
    depth = -z if heights else z
    return {"shallowestM": round(float(depth.min()), 2), "deepestM": round(float(depth.max()), 2),
            "valuesAre": "heights, negative down" if heights else "depths, positive down",
            "datum": datum, "errorM": error}


# -- bathymetry ---------------------------------------------------------------------------------------

def geotiff(path: pathlib.Path) -> tuple[dict, dict, np.ndarray]:
    """bbox, stats and the depths (row 0 north) of a GeoTIFF."""
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as d:
        if d.crs is None:
            raise ValueError(f"{path.name} says nothing of where it is (no coordinate system)")
        band = d.read(1, masked=True).astype(float).filled(np.nan)
        if d.nodata is not None:
            band[band == d.nodata] = np.nan
        west, south, east, north = transform_bounds(d.crs, "EPSG:4326", *d.bounds)
        res = [abs(float(v)) for v in d.res]
        if d.crs.is_geographic:
            ex, nx = metres_per_degree((south + north) / 2)
            cell = [res[0] * ex, res[1] * nx]
        else:
            cell = res
            # A projected system in feet is said so; metres are taken as metres.
            unit = (d.crs.linear_units or "metre").lower()
            if "foot" in unit or "feet" in unit:
                cell = [c * 0.3048 for c in cell]
        crs = d.crs.to_string()
        size = [d.width, d.height]
    if not np.isfinite(band).any():
        raise ValueError(f"{path.name} holds no depths: every cell is empty")
    stats = {"cellM": [round(c, 3) for c in cell], "cells": size, "crs": crs,
             "filled": round(float(np.isfinite(band).mean()), 4)}
    return [round(south, 7), round(west, 7), round(north, 7), round(east, 7)], stats, band


def soundings(path: pathlib.Path) -> np.ndarray:
    """lat, lon, depth rows of a text file: commas, tabs or spaces, any header
    or comment lines skipped."""
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        parts = [p for p in re.split(r"[,\s;]+", line.strip()) if p]
        if len(parts) < 3:
            continue
        try:
            rows.append([float(p) for p in parts[:3]])
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"{path.name} has no rows of latitude, longitude, depth")
    return np.array(rows, float)


def bathymetry(brief: dict, out: pathlib.Path) -> dict:
    said = brief.get("file") or {}
    path = INPUTS / said.get("path", "")
    if not path.is_file():
        raise ValueError(f"the survey file {said.get('name') or said.get('path')} was not given")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", said.get("name") or path.name)
    fmt = (said.get("format") or ("geotiff" if path.suffix.lower() in (".tif", ".tiff") else "xyz")).lower()
    datum = brief.get("datum") or None
    error = brief.get("errorM")
    error = None if error is None else float(error)
    warnings = []
    if not datum:
        warnings.append("no datum was said: depths are as the file has them, against nothing named")
    if error is None:
        warnings.append("no error was said: a place build takes 0.3 m for a raster, 0.2 m for soundings")
    elif error <= 0:
        raise ValueError(f"an error of {error:g} m is not an error: say how far the survey can be wrong")
    tell("check", f"reading {name} as {'a GeoTIFF' if fmt == 'geotiff' else 'soundings'}")
    if fmt in ("geotiff", "tif", "tiff"):
        bbox, grid, band = geotiff(path)
        stats = dict(depth_stats(band, datum, error), **grid)
        z = band
        picture = lambda: preview_raster(z, out / "preview.png", bbox)  # noqa: E731
        fmt = "geotiff"
    elif fmt in ("xyz", "csv", "txt"):
        rows = soundings(path)
        lat, lon = rows[:, 0], rows[:, 1]
        if not degrees_ok(lat, lon):
            raise ValueError("the rows are not latitude, longitude, depth: a first or second column is past "
                             "90 or 180 degrees (eastings and northings are not taken yet)")
        bbox = bbox_of(lat, lon)
        ex, nx = metres_per_degree(float(lat.mean()))
        area = max((bbox[2] - bbox[0]) * nx * (bbox[3] - bbox[1]) * ex, 1.0)
        stats = dict(depth_stats(rows[:, 2], datum, error), points=int(len(rows)),
                     spacingM=round(math.sqrt(area / len(rows)), 2))
        picture = lambda: preview_points(rows, out / "preview.png")  # noqa: E731
        fmt = "xyz"
    else:
        raise ValueError(f"a survey as {fmt} is not read: a GeoTIFF or xyz/csv soundings")
    tell("check", f"{stats['shallowestM']:g} to {stats['deepestM']:g} m deep, "
                  + (f"{stats['cellM'][0]:g} m cells" if "cellM" in stats else f"{stats['points']:,} soundings"),
         **{k: stats[k] for k in ("shallowestM", "deepestM")})
    tell("preview", "a picture of the depths")
    picture()
    if fmt == "xyz":
        # The places job reads soundings as longitude, latitude, height
        # (negative down), so they are kept that way, whichever way they came.
        name = pathlib.Path(name).stem + ".xyz"
        z = rows[:, 2] if stats["valuesAre"].startswith("heights") else -rows[:, 2]
        np.savetxt(out / name, np.column_stack([rows[:, 1], rows[:, 0], z]), fmt="%.8f %.8f %.3f")
    else:
        shutil.copy(path, out / name)
    return {"kind": "bathymetry", "type": None, "meets": None, "madeFrom": "survey",
            "footprint": {"bbox": bbox}, "stats": stats, "preview": "preview.png",
            "file": {"name": name, "format": fmt}, "warnings": warnings}


def preview_raster(z: np.ndarray, to: pathlib.Path, bbox) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    step = max(1, int(max(z.shape) // 1200))
    shown = z[::step, ::step]
    depth = -shown if np.nanmax(shown) <= 0 else shown
    fig, ax = plt.subplots(figsize=(6, 6 * shown.shape[0] / max(shown.shape[1], 1) + 0.6), dpi=120)
    im = ax.imshow(depth, cmap="viridis_r", extent=[bbox[1], bbox[3], bbox[0], bbox[2]], aspect="auto")
    fig.colorbar(im, ax=ax, label="depth, m")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    fig.tight_layout()
    fig.savefig(to)
    plt.close(fig)


def preview_points(rows: np.ndarray, to: pathlib.Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    every = max(1, len(rows) // 200000)
    shown = rows[::every]
    depth = -shown[:, 2] if np.all(rows[:, 2] <= 0) else shown[:, 2]
    fig, ax = plt.subplots(figsize=(6, 6), dpi=120)
    dots = ax.scatter(shown[:, 1], shown[:, 0], c=depth, s=2, cmap="viridis_r", linewidths=0)
    fig.colorbar(dots, ax=ax, label="depth, m")
    ax.set_aspect(1 / max(math.cos(math.radians(float(rows[:, 0].mean()))), 1e-6))
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    fig.tight_layout()
    fig.savefig(to)
    plt.close(fig)


# -- a structure from a model -------------------------------------------------------------------------

def load_model(path: pathlib.Path, fmt: str | None = None):
    """Every mesh in a glb, gltf or obj as one: vertices, faces, colours (0-1)."""
    import trimesh

    loaded = trimesh.load(str(path), file_type=fmt or None, force="scene", process=False)
    meshes = [g for g in loaded.dump() if isinstance(g, trimesh.Trimesh) and len(g.faces)]
    if not meshes:
        raise ValueError(f"{path.name} holds no surfaces (no triangles)")
    colours = []
    for m in meshes:
        try:
            c = np.asarray(m.visual.to_color().vertex_colors, float)[:, :3] / 255.0
            if len(c) != len(m.vertices):
                raise ValueError
        except Exception:
            c = np.full((len(m.vertices), 3), 0.6)
        colours.append(c)
    one = trimesh.util.concatenate(meshes)
    return np.asarray(one.vertices, float), np.asarray(one.faces, np.int64), np.concatenate(colours)


def model_frame(vertices: np.ndarray, scale: float = 1.0, up: str = "z") -> np.ndarray:
    """A model in metres, z up, centred in x and y, its base on z = 0."""
    v = np.asarray(vertices, float) * float(scale)
    if up == "y":
        # glTF's way: y up and z towards the viewer; turned so y goes to z.
        v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1)
    elif up != "z":
        raise ValueError(f"up must be y or z, not {up}")
    lo, hi = v.min(0), v.max(0)
    return v - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]


def write_usd_mesh(to: pathlib.Path, points, faces, colours=None, *, doc: str = "", translate=None) -> None:
    """One triangle mesh as a USD layer: metres, z up, /Structure/Mesh, marked
    to collide for anything that reads USD physics."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, Vt

    stage = Usd.Stage.CreateNew(str(to))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdGeom.Xform.Define(stage, "/Structure")
    stage.SetDefaultPrim(root.GetPrim())
    if doc:
        stage.GetRootLayer().documentation = doc
    if translate is not None:
        root.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in translate]))
    mesh = UsdGeom.Mesh.Define(stage, "/Structure/Mesh")
    pts = np.ascontiguousarray(points, dtype=np.float32)
    mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(pts))
    tri = np.ascontiguousarray(faces, dtype=np.int32)
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(np.full(len(tri), 3, np.int32)))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(tri.reshape(-1)))
    mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
    mesh.GetDoubleSidedAttr().Set(True)
    lo, hi = pts.min(0), pts.max(0)
    mesh.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))]))
    if colours is not None:
        c = np.ascontiguousarray(colours, dtype=np.float32)
        primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3fArray,
                                                          UsdGeom.Tokens.vertex if len(c) == len(pts)
                                                          else UsdGeom.Tokens.constant)
        primvar.Set(Vt.Vec3fArray.FromNumpy(c if len(c) == len(pts) else c[:1]))
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr().Set(UsdPhysics.Tokens.none)
    stage.GetRootLayer().Save()


def read_usd_mesh(path: pathlib.Path) -> tuple[np.ndarray, np.ndarray]:
    """Every mesh in a USD layer as one, in the layer's frame, triangulated."""
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(path))
    points, faces, offset = [], [], 0
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        mesh = UsdGeom.Mesh(prim)
        world = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
        p = np.array(mesh.GetPointsAttr().Get(), float)
        p = (world @ np.c_[p, np.ones(len(p))].T)[:3].T
        counts = np.array(mesh.GetFaceVertexCountsAttr().Get(), int)
        index = np.array(mesh.GetFaceVertexIndicesAttr().Get(), int)
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        for start, n in zip(starts, counts):
            faces.extend([[index[start] + offset, index[start + k] + offset, index[start + k + 1] + offset]
                          for k in range(1, n - 1)])
        points.append(p)
        offset += len(p)
    if not points:
        raise ValueError(f"{path.name} holds no mesh")
    return np.concatenate(points), np.array(faces, np.int64).reshape(-1, 3)


def shaded(points: np.ndarray, faces: np.ndarray, colours, to: pathlib.Path, size: int = 640) -> None:
    """A model seen from above and to one side, lit from over the shoulder:
    points on its surface into a depth buffer."""
    from PIL import Image

    rng = np.random.default_rng(0)
    # Looking down 35 degrees, from the south-west.
    yaw, pitch = math.radians(-35), math.radians(-55)
    rz = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]])
    view = rx @ rz
    seen = points @ view.T
    lo, hi = seen[:, :2].min(0), seen[:, :2].max(0)
    s = (size - 40) / max(float((hi - lo).max()), 1e-9)
    a, b, c = (points[faces[:, k]] for k in range(3))
    normal = np.cross(b - a, c - a)
    area = np.linalg.norm(normal, axis=1)
    normal = normal / np.maximum(area[:, None], 1e-12)
    # Enough points on the surface to cover every pixel it shows, twice.
    n = int(np.clip(area.sum() / 2 * s * s * 2, 50_000, 3_000_000))
    pick = rng.choice(len(faces), n, p=area / area.sum()) if area.sum() > 0 else rng.integers(0, len(faces), n)
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    p = a[pick] + u[:, None] * (b[pick] - a[pick]) + v[:, None] * (c[pick] - a[pick])
    if colours is not None and len(colours) == len(points):
        col = (colours[faces[pick, 0]] * (1 - u - v)[:, None] + colours[faces[pick, 1]] * u[:, None]
               + colours[faces[pick, 2]] * v[:, None])
    else:
        col = np.full((n, 3), 0.7)
    q = p @ view.T
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    lit = np.clip(np.abs(normal[pick] @ light), 0, 1) * 0.75 + 0.25
    ij = ((q[:, :2] - lo) * s + 20).astype(int)
    ij[:, 1] = size - 1 - ij[:, 1]
    ij = np.clip(ij, 0, size - 2)
    order = np.argsort(q[:, 2])                       # the nearest the eye drawn last, so it is the one kept
    image = np.full((size, size, 3), [0.09, 0.16, 0.22])
    shade = col[order] * lit[order, None]
    for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1)):
        image[ij[order, 1] + dy, ij[order, 0] + dx] = shade
    Image.fromarray((np.clip(image, 0, 1) * 255).astype(np.uint8)).save(to)


def structure_from_model(brief: dict, out: pathlib.Path) -> dict:
    said = brief.get("model") or {}
    path = INPUTS / said.get("path", "")
    if not path.is_file():
        raise ValueError(f"the model file {said.get('name') or said.get('path')} was not given")
    fmt = (said.get("format") or path.suffix.lstrip(".")).lower()
    if fmt not in ("glb", "gltf", "obj"):
        raise ValueError(f"a model as {fmt} is not read: glb, gltf or obj")
    scale = float(said.get("scale") or 1.0)
    if scale <= 0:
        raise ValueError(f"a scale of {scale:g} is not a scale")
    up = (said.get("up") or ("y" if fmt in ("glb", "gltf") else "z")).lower()
    tell("check", f"reading {said.get('name') or path.name}")
    vertices, faces, colours = load_model(path, fmt)
    v = model_frame(vertices, scale, up)
    if not np.all(np.isfinite(v)):
        raise ValueError("the model has points that are not numbers")
    size = v.max(0) - v.min(0)
    if size.max() > LARGEST_M:
        raise ValueError(f"the model is {size.max():,.0f} m across at a scale of {scale:g}: it is in other units "
                         "(millimetres want 0.001, centimetres 0.01)")
    if size.max() < 0.01:
        raise ValueError(f"the model is {size.max() * 1000:.1f} mm across at a scale of {scale:g}: set its scale")
    warnings = []
    if size[2] < 1e-6:
        warnings.append("the model is flat: no height at all")
    tell("check", f"{len(faces):,} triangles, {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m",
         triangles=int(len(faces)), sizeM=[round(float(s), 3) for s in size])
    tell("model", "written as USD: metres, z up, its base on z = 0")
    write_usd_mesh(out / "model.usdc", v, faces, colours,
                   doc=f"{said.get('name') or path.name}: a structure, metres, z up, centred in x and y, base on z = 0")
    tell("preview", "a picture of the model")
    shaded(v, faces, colours, out / "preview.png")
    return {"kind": "structure", "type": brief.get("type") or "other", "meets": brief.get("meets") or "stands",
            "madeFrom": "model", "footprint": {"sizeM": [round(float(s), 3) for s in size]},
            "stats": {"triangles": int(len(faces)), "points": int(len(v)), "sizeM": [round(float(s), 3) for s in size],
                      "scale": scale, "up": up, "from": said.get("name") or path.name},
            "preview": "preview.png", "model": "model.usdc", "warnings": warnings}


# -- a pipeline from its route ------------------------------------------------------------------------

def route_metres(points) -> np.ndarray:
    """A route's points as metres east and north of its first."""
    p = np.asarray(points, float)
    east, north = metres_per_degree(float(p[:, 0].mean()))
    return np.stack([(p[:, 1] - p[0, 1]) * east, (p[:, 0] - p[0, 0]) * north], 1)


def structure_from_route(brief: dict, out: pathlib.Path) -> dict:
    route = brief.get("route") or {}
    points = route.get("points") or []
    try:
        p = np.asarray(points, float).reshape(-1, 2)
    except ValueError:
        raise ValueError("a route is a list of [latitude, longitude] points") from None
    if len(p) < 2:
        raise ValueError("a route needs two points at least")
    if not degrees_ok(p[:, 0], p[:, 1]):
        raise ValueError("a route point is not a latitude and longitude ([lat, lon], degrees)")
    diameter = float(route.get("diameterM") or 0)
    if not 0.01 <= diameter <= 10:
        raise ValueError(f"a pipeline {diameter:g} m across is not one: say its diameter in metres")
    burial = float(route.get("burial") or 0.0)
    if not 0 <= burial <= 1:
        raise ValueError(f"burial is the share of the diameter under the seabed, 0 to 1, not {burial:g}")
    xy = route_metres(p)
    legs = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    if np.any(legs < 1e-3):
        raise ValueError("two points of the route in a row are the same point")
    if legs.sum() > 200_000:
        raise ValueError(f"a route of {legs.sum() / 1000:.0f} km is longer than any place")
    tell("check", f"{len(p)} points, {legs.sum():,.0f} m long, {diameter:g} m across, "
                  f"{burial * 100:.0f}% buried", lengthM=round(float(legs.sum()), 1))
    tell("preview", "a picture of the route")
    preview_route(xy, diameter, out / "preview.png")
    return {"kind": "structure", "type": brief.get("type") or "pipeline", "meets": brief.get("meets") or "drapes",
            "madeFrom": "route", "footprint": {"bbox": bbox_of(p[:, 0], p[:, 1])},
            "stats": {"lengthM": round(float(legs.sum()), 1), "diameterM": diameter, "burial": burial,
                      "points": int(len(p)), "longestLegM": round(float(legs.max()), 1)},
            "preview": "preview.png",
            "route": {"points": [[float(a), float(b)] for a, b in p], "diameterM": diameter, "burial": burial},
            "warnings": []}


def preview_route(xy: np.ndarray, diameter: float, to: pathlib.Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 6), dpi=120)
    ax.set_facecolor("#16283a")
    ax.plot(xy[:, 0], xy[:, 1], color="#f2b33d", lw=3, solid_capstyle="round")
    ax.plot(xy[:, 0], xy[:, 1], "o", color="#f2b33d", ms=4)
    ax.plot(*xy[0], "o", color="#5fe08a", ms=9, label="start")
    ax.set_aspect("equal")
    span = float(max(np.ptp(xy[:, 0]), np.ptp(xy[:, 1]), 10.0))
    cx, cy = xy.min(0) + np.ptp(xy, axis=0) / 2
    ax.set_xlim(cx - span * 0.6, cx + span * 0.6)
    ax.set_ylim(cy - span * 0.6, cy + span * 0.6)
    ax.set_xlabel("metres east of the start")
    ax.set_ylabel("metres north of the start")
    ax.set_title(f"{np.linalg.norm(np.diff(xy, axis=0), axis=1).sum():,.0f} m, {diameter:g} m across")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(to)
    plt.close(fig)


# -- the whole of it ----------------------------------------------------------------------------------

def made(brief: dict, out: pathlib.Path) -> dict:
    kind = brief.get("kind")
    if kind not in KINDS:
        raise ValueError(f"an asset of kind {kind!r} is not made here: bathymetry or structure "
                         "(a reef is made from a video by iocean_reconstruct.job)")
    if kind == "bathymetry":
        return bathymetry(brief, out)
    if brief.get("type") and brief["type"] not in TYPES:
        raise ValueError(f"a structure of type {brief['type']!r}: one of {', '.join(TYPES)}")
    if brief.get("meets") and brief["meets"] not in MEETS:
        raise ValueError(f"a structure meets the seabed as {' or '.join(MEETS)}, not {brief['meets']!r}")
    if brief.get("route"):
        return structure_from_route(brief, out)
    if brief.get("model"):
        return structure_from_model(brief, out)
    raise ValueError("a structure is made from a model file or from a route")


def main(argv: list[str]) -> int:
    started = time.time()
    brief = json.loads(argv[0])
    SCRATCH.mkdir(parents=True, exist_ok=True)
    home = SCRATCH / "home"
    home.mkdir(exist_ok=True)
    os.environ.update(HOME=str(home), TMPDIR=str(SCRATCH / "tmp"), MPLCONFIGDIR=str(home / "matplotlib"),
                      MPLBACKEND="Agg")
    (SCRATCH / "tmp").mkdir(exist_ok=True)
    out = SCRATCH / "asset"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    try:
        manifest = made(brief, out)
    except Exception as failed:
        traceback.print_exc()
        tell("failed", str(failed)[:2000])
        return 1
    manifest["label"] = brief.get("label", "")
    manifest["made"] = {"tool": "iocean_reconstruct.asset", "recipe": "asset-import/v1",
                        "seconds": round(time.time() - started)}
    for warning in manifest.get("warnings") or []:
        tell("warning", warning)
    (out / "asset.json").write_text(json.dumps(manifest, indent=1))
    tell("package", "packing the asset")
    with tarfile.open(OUTPUTS / "asset.tar", "w") as archive:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                archive.add(f, arcname=str(f.relative_to(out)))
    if SCRATCH.is_relative_to(OUTPUTS) and not os.environ.get("IOCEAN_KEEP_SCRATCH"):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    kind = manifest["kind"] if manifest["kind"] == "bathymetry" else f"{manifest['type']} ({manifest['madeFrom']})"
    tell("done", f"{kind} ready", seconds=manifest["made"]["seconds"], kind=manifest["kind"],
         footprint=manifest["footprint"], stats=manifest["stats"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
