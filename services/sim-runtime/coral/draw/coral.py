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


class Polyps:
    """A colony with its polyps out drawn softer and paler: what a reef looks
    like at night, when the polyps cover a stony colony's skeleton in a fuzz of
    tentacles, and what a closed colony looks like when something disturbed it.

    Reads    coral.polyps (systems/coral.py): the share of each colony's out

    Each named colony's material is lightened towards its own tint's pastel and
    roughened, by the share out; changed only when the share has moved."""

    MOVES = 0.03

    def __init__(self) -> None:
        self.found = None           # colony index -> [(attribute, as built, kind)]
        self.shown = {}

    def find(self, stage, coral) -> None:
        from pxr import UsdShade

        self.found = {}
        for i in range(len(coral)):
            name = coral.prim[i] if i < len(coral.prim) else None
            if not name:
                continue
            prim = stage.GetPrimAtPath("/World/" + str(name).lstrip("/"))
            if not prim or not prim.IsValid():
                continue
            material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            if not material:
                continue
            knobs = []
            for shader in material.GetPrim().GetChildren():
                for input_name, kind in (("inputs:diffuse_color_constant", "colour"),
                                         ("inputs:diffuse_reflection_color", "colour"),
                                         ("inputs:diffuseColor", "colour"),
                                         ("inputs:reflection_roughness_constant", "rough"),
                                         ("inputs:roughness", "rough")):
                    attribute = shader.GetAttribute(input_name)
                    if attribute and attribute.Get() is not None:
                        knobs.append((attribute, attribute.Get(), kind))
            if knobs:
                self.found[i] = knobs

    def show(self, stage, coral) -> None:
        from pxr import Gf

        out = getattr(coral, "polyps", None)
        if out is None or not len(out):
            return
        if self.found is None:
            self.find(stage, coral)
        for i, knobs in self.found.items():
            share = float(out[i])
            if abs(share - self.shown.get(i, -1.0)) < self.MOVES:
                continue
            self.shown[i] = share
            for attribute, built, kind in knobs:
                if kind == "colour":
                    c = [float(v) for v in built]
                    pale = [min(1.0, v * (1.0 + 0.35 * share) + 0.08 * share) for v in c]
                    attribute.Set(Gf.Vec3f(*pale))
                else:
                    attribute.Set(float(min(1.0, float(built) + 0.3 * share)))
