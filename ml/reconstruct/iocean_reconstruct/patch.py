"""The reconstruction as a reef patch: upright, at a scale, in its own metres.

COLMAP's model has no up and no scale. Up is the reef's mean plane: the
smallest axis of the dense points, turned to face the cameras. Along is the
largest axis, which on a transect is the direction the diver swam. The scale
is set so the cameras' median height above that plane is `camera_height_m`:
an assumption, said as one in patch.json, until the patch is matched to
something measured (a tape length, a GPS track, the place's own seabed).

Written into patch/:

    mesh.ply, mesh.usda   the surface, coloured per vertex, metres, z up,
                          x along the transect, origin at the patch's middle
    dem.npy, ortho.png    the surface seen from above at `cell_m`: height
                          (NaN where nothing was seen) and colour
    preview.png           the orthophoto beside the relief, to look at
    patch.json            size, scale and how it was set, frames used
"""

from __future__ import annotations

import json
import pathlib

import numpy as np


def frame_of(points: np.ndarray, cameras: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Centre, rotation (rows: along, across, up) and the cameras' heights
    above the points' mean plane, in the model's own units."""
    centre = points.mean(0)
    values, vectors = np.linalg.eigh(np.cov((points - centre).T))
    up, along = vectors[:, 0], vectors[:, 2]
    if np.dot(cameras.mean(0) - centre, up) < 0:
        up = -up
    across = np.cross(up, along)
    rotation = np.stack([along, across, up])
    heights = (cameras - centre) @ up
    return centre, rotation, heights


def rasterise(points: np.ndarray, colours: np.ndarray, cell_m: float):
    """Points in patch metres onto a grid from above: the highest point's
    height and colour in each cell, NaN where none landed."""
    lo = points[:, :2].min(0)
    shape = (np.ceil((points[:, :2].max(0) - lo) / cell_m).astype(int) + 1)[::-1]
    col = ((points[:, 0] - lo[0]) / cell_m).astype(int)
    row = ((points[:, 1] - lo[1]) / cell_m).astype(int)
    order = np.argsort(points[:, 2])                       # highest last, so it wins
    height = np.full(shape, np.nan, np.float32)
    rgb = np.zeros(tuple(shape) + (3,), np.uint8)
    height[row[order], col[order]] = points[order, 2]
    rgb[row[order], col[order]] = colours[order]
    return height[::-1], rgb[::-1], lo                      # north (+y) up, as a picture


def make(dense: pathlib.Path, text: pathlib.Path, out: pathlib.Path, cfg: dict, about: dict) -> dict:
    import open3d as o3d
    from PIL import Image

    from .colmap import cameras as read_cameras

    out.mkdir(parents=True, exist_ok=True)
    cloud = o3d.io.read_point_cloud(str(dense / "fused.ply"))
    points = np.asarray(cloud.points)
    colours = (np.asarray(cloud.colors) * 255).astype(np.uint8)
    cams = read_cameras(text)
    centres = np.array([c for _, c in cams])
    centre, rotation, heights = frame_of(points, centres)
    scale = float(cfg["scale"]["camera_height_m"]) / float(np.median(heights))

    def to_patch(p):
        return (np.asarray(p) - centre) @ rotation.T * scale

    pts = to_patch(points)
    mesh = o3d.io.read_triangle_mesh(str(dense / "meshed.ply"))
    mesh.vertices = o3d.utility.Vector3dVector(to_patch(mesh.vertices))
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(str(out / "mesh.ply"), mesh)
    write_usd(out / "mesh.usda", np.asarray(mesh.vertices), np.asarray(mesh.triangles),
              np.asarray(mesh.vertex_colors) if mesh.has_vertex_colors() else None)

    cell = float(cfg.get("patch", {}).get("cell_m", 0.01))
    height, rgb, lo = rasterise(pts, colours, cell)
    np.save(out / "dem.npy", height)
    Image.fromarray(rgb).save(out / "ortho.png")
    preview(height, rgb, out / "preview.png")

    seen = np.isfinite(height)
    cam_patch = to_patch(centres)
    said = {
        **about,
        "frames": {"registered": len(cams)},
        "sizeM": {"along": round(float(np.ptp(pts[:, 0])), 2), "across": round(float(np.ptp(pts[:, 1])), 2),
                  "relief": round(float(np.nanpercentile(height, 99) - np.nanpercentile(height, 1)), 2)},
        "seenM2": round(float(seen.sum()) * cell * cell, 1),
        "points": int(len(pts)), "meshTriangles": int(len(mesh.triangles)),
        "cellM": cell, "demOrigin": [round(float(lo[0]), 3), round(float(lo[1]), 3)],
        "track": {"lengthM": round(float(np.linalg.norm(np.diff(cam_patch[:, :2], axis=0), axis=1).sum()), 1),
                  "cameraHeightM": round(float(np.median(cam_patch[:, 2] - 0)), 2)},
        "scale": {"factor": scale, "how": cfg["scale"]["how"],
                  "from": f"the cameras' median height above the reef's mean plane, set to "
                          f"{cfg['scale']['camera_height_m']} m: how high a diver swims a transect video; "
                          "not measured"},
        "frame": "metres, z up (the reef's mean plane), x along the transect, origin at the patch's middle",
        "placed": None,
    }
    (out / "patch.json").write_text(json.dumps(said, indent=1) + "\n")
    return said


def write_usd(path: pathlib.Path, vertices: np.ndarray, triangles: np.ndarray, colours=None) -> None:
    from pxr import Gf, Usd, UsdGeom, Vt

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Patch")
    stage.SetDefaultPrim(root.GetPrim())
    mesh = UsdGeom.Mesh.Define(stage, "/Patch/Reef")
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, v)) for v in vertices]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(triangles)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(triangles.astype(int).ravel().tolist()))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    if colours is not None and len(colours):
        colour = mesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex)
        colour.Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, c)) for c in colours]))
    stage.Save()


def preview(height: np.ndarray, rgb: np.ndarray, path: pathlib.Path) -> None:
    """The orthophoto, and the relief lit from the north-west, side by side."""
    from PIL import Image

    h = np.where(np.isfinite(height), height, np.nanmin(height) if np.isfinite(height).any() else 0)
    gy, gx = np.gradient(h)
    shade = np.clip(0.6 - (gx - gy) * 8.0, 0, 1)
    relief = (shade * 255).astype(np.uint8)
    relief[~np.isfinite(height)] = 0
    both = np.concatenate([rgb, np.repeat(relief[..., None], 3, -1)], 1)
    img = Image.fromarray(both)
    img.thumbnail((2400, 2400))
    img.save(path)
