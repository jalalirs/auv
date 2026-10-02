"""The tether, drawn where the cable's own solve says it is.

Reads    cable (systems/tether.py): its nodes; the vehicle, where it is tied on

From the rim to the point it is tied on the hull, with the lead-out the package
asks for rising straight off the crown, smoothed so a few dozen nodes read as a
cable and not a chain of sticks, and never drawn through the ground or the
glass. Nothing here moves the cable: it is drawn as it is.
"""

from __future__ import annotations

import numpy as np

# How thick the cable is drawn, at least. A five-millimetre tether is a pixel
# at three metres and reads as nothing; drawn at its own diameter and no
# thinner than this, it reads as a cable.
DRAWN_AT_LEAST_M = 0.006


class TetherDrawing:
    def __init__(self, attach, lead_out_m: float, units_per_metre: float, say) -> None:
        self.attach = np.asarray(attach, dtype=float)
        self.lead = float(lead_out_m)
        self.units = float(units_per_metre)
        self.say = say
        self.curve = None
        self.unseen = False

    def draw(self, stage, cable, vehicle, place, drawn_at) -> None:
        if cable is None or not cable.out or cable.shape is None:
            return
        try:
            from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

            shape = np.array(cable.shape, dtype=float)
            attach = self.attach
            plug = vehicle.position + vehicle.rotation @ attach
            shape[-1] = plug
            shape[0] = cable.at
            # Out of the plug the way the plug points, before the cable is free
            # to bend: drawn straight from the crown to the solve's last free
            # node, the cable cut through the lid whenever the slack lay beside
            # or below the vehicle.
            lead = self.lead
            if lead > 0.0:
                up = vehicle.rotation @ np.array([0.0, 0.0, 1.0])
                riser = plug + up * lead
                over = plug + up * (lead * 2.5)
                shape = np.vstack([shape[:-1], over, riser, plug])
            if place.seabed is not None or place.floor is not None:
                bottom = place.bottoms(shape[1:-1])
                shape[1:-1, 2] = np.maximum(shape[1:-1, 2], bottom + 0.004)
            if place.interior is not None:
                low, high = place.interior
                shape[1:-1, 0] = np.clip(shape[1:-1, 0], low[0] + 0.004, high[0] - 0.004)
                shape[1:-1, 1] = np.clip(shape[1:-1, 1], low[1] + 0.004, high[1] - 0.004)
            # Relaxed before it is drawn. The solve's nodes carry its
            # shape and its tension, and drawn as they are a slack cable came
            # out as a zig-zag of straight pieces: a cable is a curve.
            keep = 3 if lead > 0.0 else 1          # the lead-out stays straight
            for _ in range(6):
                shape[1:-keep] = 0.25 * shape[:-keep - 1] + 0.5 * shape[1:-keep] + 0.25 * shape[2:len(shape) - keep + 1]
            # A smoother line than the solve's nodes: the cable is drawn
            # through them, not as a chain of straight pieces.
            t = np.linspace(0, 1, len(shape))
            fine = np.linspace(0, 1, 6 * len(shape))
            drawn = np.stack([np.interp(fine, t, shape[:, i]) for i in range(3)], axis=1)
            points = Vt.Vec3fArray([Gf.Vec3f(*[float(v) for v in drawn_at(p)]) for p in drawn])
            if self.curve is None:
                curve = UsdGeom.BasisCurves.Define(stage, "/World/Tether")
                curve.CreateTypeAttr(UsdGeom.Tokens.linear)
                curve.CreateCurveVertexCountsAttr(Vt.IntArray([len(drawn)]))
                width = max(cable.diameter_m, DRAWN_AT_LEAST_M) * self.units
                curve.CreateWidthsAttr(Vt.FloatArray([float(width)]))
                curve.SetWidthsInterpolation(UsdGeom.Tokens.constant)
                curve.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.95, 0.45, 0.05)]))
                look = UsdShade.Material.Define(stage, "/World/Tether/Look")
                shader = UsdShade.Shader.Define(stage, "/World/Tether/Look/S")
                shader.CreateIdAttr("UsdPreviewSurface")
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.95, 0.45, 0.05))
                shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
                look.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
                UsdShade.MaterialBindingAPI.Apply(curve.GetPrim()).Bind(look)
                self.curve = curve
                self.say("tether_drawn", nodes=int(len(drawn)), widthM=round(float(width / self.units), 4),
                         from_=[round(float(v), 3) for v in shape[0]], to=[round(float(v), 3) for v in shape[-1]])
            self.curve.GetPointsAttr().Set(points)
        except Exception as bad:
            if not self.unseen:
                self.unseen = True
                self.say("tether_not_drawn", why=str(bad)[:200])
