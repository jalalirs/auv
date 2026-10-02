"""Colonies drawn as what happened to them: a broken one is a stump.

Reads    coral (systems/coral.py): which colonies are broken, and where they stand

A colony the vehicle broke is drawn at half its height, cut down about its own
base, from the frame it broke in. The place names each colony's prim in its
record; one it does not name is not drawn changed, and is still broken in the
dive's result.
"""

from __future__ import annotations


def break_them(stage, coral, done: set, units_per_metre: float = 1.0) -> None:
    """Cut down every colony broken since last time, and lay on its side every
    one torn off."""
    from pxr import Gf, UsdGeom

    for i in range(len(coral)):
        torn = bool(getattr(coral, "torn_off", None) is not None and coral.torn_off[i])
        if not (coral.broken[i] or torn) or i in done:
            continue
        done.add(i)
        name = coral.prim[i] if i < len(coral.prim) else None
        if not name:
            continue
        prim = stage.GetPrimAtPath("/World/" + str(name).lstrip("/"))
        if not prim or not prim.IsValid():
            continue
        base = Gf.Vec3d(*(float(c) * units_per_metre for c in coral.at[i]))
        shape = UsdGeom.Xformable(prim)
        shape.AddTranslateOp(opSuffix="base").Set(base)
        if torn:
            # Knocked over about its base, the way it was pushed.
            shape.AddRotateXYZOp(opSuffix="torn").Set(Gf.Vec3f(0.0, 75.0, 0.0))
        else:
            shape.AddScaleOp(opSuffix="broken").Set(Gf.Vec3f(1.0, 1.0, float(coral.height[i] / coral.size[i])))
        shape.AddTranslateOp(opSuffix="base", isInverseOp=True)
