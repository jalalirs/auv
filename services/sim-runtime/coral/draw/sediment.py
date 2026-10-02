"""The sand in the water, drawn where the dive says it is.

Reads    sediment (systems/sediment.py): every parcel of grains in the water

Each parcel is drawn as a fleck the colour of the bed, sand a little larger
than silt, so a cloud the thrusters raised is seen to rise, drift and fall back
— the picture of the same numbers the camera's visibility is worked out from.
"""

from __future__ import annotations

# How big a parcel is drawn, metres: not a grain's size, which is under a
# pixel, but a fleck of a cloud of them.
DRAWN_M = {0: 0.004, 1: 0.0025}
COLOUR = (0.78, 0.72, 0.6)


def draw(stage, sediment, points, units_per_metre: float = 1.0):
    """Put the parcels where they are; returns the points prim, to reuse."""
    from pxr import Gf, UsdGeom, Vt

    if points is None:
        points = UsdGeom.Points.Define(stage, "/World/Sediment")
        points.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*COLOUR)]))
    at = sediment.at * units_per_metre
    points.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in at]))
    points.GetWidthsAttr().Set(Vt.FloatArray([float(DRAWN_M.get(int(k), 0.003) * units_per_metre)
                                              for k in sediment.grain]))
    return points
