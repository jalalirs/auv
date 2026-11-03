"""Colonies drawn as what happened to them: a broken one is a stump.

Reads    coral (systems/coral.py): which colonies are broken, and where they stand;
         the place's reef as its world edited it (systems/coral.as_edited)

A colony the vehicle broke is drawn at half its height, cut down about its own
base, from the frame it broke in. The place names each colony's prim in its
record; one it does not name is not drawn changed, and is still broken in the
dive's result.
"""

from __future__ import annotations

import numpy as np


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
        # About its drawn geometry's own base, which an edited colony has
        # where it was built, not where the world moved it to.
        stands = coral.at[i] if coral.drawn_at is None else coral.drawn_at[i]
        base = Gf.Vec3d(*(float(c) * units_per_metre for c in stands))
        shape = UsdGeom.Xformable(prim)
        shape.AddTranslateOp(opSuffix="base").Set(base)
        if torn:
            # Knocked over about its base, the way it was pushed.
            shape.AddRotateXYZOp(opSuffix="torn").Set(Gf.Vec3f(0.0, 75.0, 0.0))
        else:
            shape.AddScaleOp(opSuffix="broken").Set(Gf.Vec3f(1.0, 1.0, float(coral.height[i] / coral.size[i])))
        shape.AddTranslateOp(opSuffix="base", isInverseOp=True)


def as_edited(stage, coral, rows: list, not_drawn: list, units_per_metre: float = 1.0) -> dict:
    """Draw the colonies where the world put them.

    Each built colony's geometry was written where it was built, so a moved
    one is taken back to its own base, sized, turned (headingDeg is clockwise
    from north; USD turns anticlockwise) and stood at its new base. A new one
    is a reference to the built colony it copies, moved the same way. A
    colony the world hid or no longer lists is deactivated: not drawn, and
    nothing to collide with. Done once, before the dive starts."""
    from pxr import Gf, Usd, UsdGeom

    moved = copied = gone = 0
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    work = []
    # Copies first, so each references its colony as built, then the moves.
    for i, row in sorted(enumerate(rows), key=lambda r: not r[1].get("copyOf")):
        name, was = row.get("prim"), row.get("builtAt")
        if not name or not was or i >= len(coral):
            continue
        path = "/World/" + str(name).lstrip("/")
        if row.get("copyOf"):
            prim = stage.DefinePrim(path)
            prim.GetReferences().AddInternalReference("/World/" + str(row["copyOf"]).lstrip("/"))
            prim.SetActive(True)
            UsdGeom.Imageable(prim).GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
            copied += 1
        else:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
        grown = float(row.get("sizeM", 0.1)) / max(1e-6, float(row.get("builtSizeM") or row.get("sizeM", 0.1)))
        turn = float(row.get("headingDeg", 0.0))
        now = np.asarray(coral.at[i], dtype=float) * units_per_metre
        then = np.asarray(coral.drawn_at[i] if coral.drawn_at is not None else coral.at[i], dtype=float) * units_per_metre
        stays = float(np.linalg.norm(now[:2] - then[:2])) < 1e-6
        if not row.get("copyOf") and abs(grown - 1.0) < 1e-6 and abs(turn) < 1e-6 and stays:
            continue
        # The pivot is the colony's drawn base, which is not always the
        # heightfield's: a colony built on a rock stands on the rock.
        base = bounds.ComputeWorldBound(prim).ComputeAlignedRange()
        if row.get("copyOf") and not base.IsEmpty():
            # A copy carries its colony's own transform but not its parent's.
            built = bounds.ComputeWorldBound(stage.GetPrimAtPath("/World/" + str(row["copyOf"]).lstrip("/"))).ComputeAlignedRange()
            if not built.IsEmpty():
                then[:2] += np.array(base.GetMin())[:2] - np.array(built.GetMin())[:2]
        if not base.IsEmpty():
            then[2] = base.GetMin()[2]
        if stays:
            now[2] = then[2]
        edit = Gf.Matrix4d().SetTranslate(Gf.Vec3d(*(-then))) \
            * Gf.Matrix4d().SetScale(Gf.Vec3d(grown, grown, grown)) \
            * Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), -turn)) \
            * Gf.Matrix4d().SetTranslate(Gf.Vec3d(*now))
        work.append((prim, edit, bool(row.get("copyOf"))))
    # Measured, then written: the edit is in the world's frame, whatever
    # transform the colony or its parent already carries.
    worlds = [UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()) for prim, _, _ in work]
    for (prim, edit, copy), world in zip(work, worlds):
        parent = UsdGeom.Xformable(prim.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default()) \
            if prim.GetParent().IsA(UsdGeom.Xformable) else Gf.Matrix4d(1.0)
        shape = UsdGeom.Xformable(prim)
        shape.ClearXformOpOrder()
        shape.AddTransformOp(opSuffix="world").Set(world * edit * parent.GetInverse())
        moved += 0 if copy else 1
    for name in not_drawn:
        prim = stage.GetPrimAtPath("/World/" + str(name).lstrip("/"))
        if prim and prim.IsValid():
            prim.SetActive(False)
            gone += 1
    return {"moved": moved, "copied": copied, "notDrawn": gone}


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
