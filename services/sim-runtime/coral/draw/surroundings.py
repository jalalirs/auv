"""The seabed past the survey, drawn: what the physics already stood on.

Reads    the seabed (runner.Seabed): the survey, and round it a ship's multibeam
         where one has surveyed and GEBCO where none has (tools/surroundings)

A place's own mesh stops at its survey's square. Past it the dive's physics
had GEBCO, and the picture had nothing: a camera at the edge looked into a
void. This is one coarse mesh from the survey's inner edge out to `reach`,
heights from the same blended seabed the vehicle stands on, so where the two
overlap — the survey's outer twentieth, where it is blended into GEBCO — the
mesh lies a few centimetres under the survey's and the survey is what is seen.

Coarse on purpose: GEBCO is ~460 m a cell and multibeam ~90 m, and a mesh
finer than its data would be drawing the interpolation.
"""

from __future__ import annotations

import numpy as np

# Past the survey's edge, metres; and the most cells a side.
REACH_M = 400.0
MOST_A_SIDE = 240
# Under the survey where the two overlap, so the survey wins the depth test.
SUNK_M = 0.05
COLOUR = (0.46, 0.43, 0.37)


def mesh_of(seabed, reach_m: float = REACH_M, most: int = MOST_A_SIDE):
    """Points (n, 3) and triangles (m, 3) of the surroundings, in metres: a
    grid out to `reach_m` past the survey, with the cells wholly inside the
    survey's own unblended square left out."""
    half = 0.5 * seabed.across
    outer = half + reach_m
    n = int(min(most, max(8, np.ceil(2 * outer / max(2.0, seabed.across / 100.0)))))
    edge = np.linspace(-outer, outer, n + 1)
    x, y = np.meshgrid(edge, edge)
    z = seabed.under_many(x.ravel(), y.ravel()) - SUNK_M
    points = np.column_stack([x.ravel(), y.ravel(), z])
    # A cell is drawn unless all of it is inside the survey's own square,
    # short of the band where it is blended into what is round it.
    inner = half - 0.05 * seabed.across
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    lo_x, hi_x, lo_y, hi_y = edge[j], edge[j + 1], edge[i], edge[i + 1]
    inside = (lo_x > -inner) & (hi_x < inner) & (lo_y > -inner) & (hi_y < inner)
    i, j = i[~inside], j[~inside]
    a = i * (n + 1) + j
    b, c, d = a + 1, a + (n + 1), a + (n + 1) + 1
    faces = np.concatenate([np.column_stack([a, b, d]), np.column_stack([a, d, c])])
    return points, faces


def put_in(stage, seabed, units_per_metre: float = 1.0, path: str = "/World/Surroundings"):
    """The mesh on the stage, a plain seabed colour; returns its cell count."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    points, faces = mesh_of(seabed)
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*(float(v) * units_per_metre for v in p)) for p in points]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(faces)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([int(v) for v in faces.ravel()]))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*COLOUR)]))
    look = UsdShade.Material.Define(stage, path + "Look")
    shader = UsdShade.Shader.Define(stage, path + "Look/S")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*COLOUR))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.95)
    look.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(look)
    return len(faces) // 2
