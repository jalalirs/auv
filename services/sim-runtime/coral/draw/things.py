"""What somebody laid out, drawn where the world says it is.

Reads    the world (world.py): its things, after the seabed and the water have
         settled them

A layout was physics only: the vehicle struck a nursery frame and the sonar
heard it, and a film showed open sand. This draws them, plainly. Something
standing as a cylinder of its own size; a line or a pipeline as a tube along
its own curve, so a pipeline is seen resting on the high ground and bridging
the hollows exactly where the physics put it. Nothing here moves them.
"""

from __future__ import annotations

import math

import numpy as np

COLOURS = {
    "pipeline": (0.78, 0.52, 0.18),      # coated line pipe
    "mooring-line": (0.85, 0.80, 0.30),
    "nursery-frame": (0.55, 0.57, 0.60),
    "transponder": (0.95, 0.75, 0.10),
    "marker-post": (0.95, 0.45, 0.15),
    "mooring-block": (0.50, 0.50, 0.48),
}
PLAIN = (0.6, 0.6, 0.6)
SIDES = 12


def tube(curve, radius: float):
    """Points and quads of a tube of `radius` along `curve` (n, 3)."""
    curve = np.asarray(curve, dtype=float)
    n = len(curve)
    ahead = np.gradient(curve, axis=0)
    ahead /= np.maximum(np.linalg.norm(ahead, axis=1, keepdims=True), 1e-9)
    up = np.tile([0.0, 0.0, 1.0], (n, 1))
    up[np.abs(ahead[:, 2]) > 0.9] = [1.0, 0.0, 0.0]
    side = np.cross(ahead, up)
    side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-9)
    over = np.cross(side, ahead)
    angles = np.linspace(0.0, 2 * math.pi, SIDES, endpoint=False)
    ring = (np.cos(angles)[None, :, None] * side[:, None, :]
            + np.sin(angles)[None, :, None] * over[:, None, :]) * radius
    points = (curve[:, None, :] + ring).reshape(-1, 3)
    quads = []
    for i in range(n - 1):
        for k in range(SIDES):
            a, b = i * SIDES + k, i * SIDES + (k + 1) % SIDES
            quads.append([a, b, b + SIDES, a + SIDES])
    return points, np.array(quads, dtype=int)


def _material(stage, path, colour):
    from pxr import Gf, Sdf, UsdShade

    look = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + "/S")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*colour))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.7)
    look.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return look


def put_in(stage, world, units_per_metre: float = 1.0, root: str = "/World/Laid") -> int:
    """Every thing in the world, drawn; returns how many."""
    from pxr import Gf, UsdGeom, UsdShade, Vt

    from world import Spanning, Standing

    u = float(units_per_metre)
    UsdGeom.Xform.Define(stage, root)
    drawn = 0
    for k, thing in enumerate(world.things):
        colour = COLOURS.get(thing.kind, PLAIN)
        path = f"{root}/T{k}"
        if isinstance(thing, Spanning) and len(thing.curve) >= 2:
            points, quads = tube(thing.curve, max(0.01, float(thing.radius)))
            mesh = UsdGeom.Mesh.Define(stage, path)
            mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*(float(v) * u for v in p)) for p in points]))
            mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4] * len(quads)))
            mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([int(v) for v in quads.ravel()]))
            mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
            prim = mesh
        elif isinstance(thing, Standing):
            cylinder = UsdGeom.Cylinder.Define(stage, path)
            cylinder.CreateRadiusAttr(float(thing.radius) * u)
            cylinder.CreateHeightAttr(float(thing.height) * u)
            cylinder.CreateAxisAttr("Z")
            middle = (thing.low + thing.high) / 2.0
            UsdGeom.XformCommonAPI(cylinder).SetTranslate(
                Gf.Vec3d(float(thing.at[0]) * u, float(thing.at[1]) * u, float(middle) * u))
            prim = cylinder
        else:
            continue
        prim.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*colour)]))
        UsdShade.MaterialBindingAPI.Apply(prim.GetPrim()).Bind(_material(stage, path + "Look", colour))
        drawn += 1
    return drawn
