"""Boxfish Luna's outside, as Boxfish's own photographs show it.

    hardware/.venv/bin/python hardware/luna/shape.py

Not a moulding, an assembly, and drawn as one: a yellow pressure hull — a
cylinder lying fore and aft — with an acrylic dome on its nose over the main
camera; a black frame of two cut end plates; two yellow-and-carbon tubes along
the top and two carbon skids under it; a third float high on the port side
aft; eight ducted thrusters, one at each corner of the two end plates; a lamp
either side of the dome.

What is taken from where. The envelope, 730 × 435 × 351 mm, is published.
Everything inside it is read off five photographs on Boxfish's Luna page
(read 3 October 2026): the parts, their arrangement and their proportions to
the envelope, to a centimetre or so. The thrusters' directions are not visible
and are not published; `THRUSTERS` says what is assumed.

Writes catalog/vehicles/boxfish-luna/boxfish-luna.usd. package.py takes the
thruster layout and the lamps from here, so the drawing and the physics agree.
"""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import trimesh

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from hull_usd import Hull  # noqa: E402

ROOT = HERE.parents[1]
INTO = ROOT / "catalog/vehicles/boxfish-luna"

L, W, H = 0.730, 0.435, 0.351           # published
FRONT, BACK = L / 2, -L / 2

# The pressure hull, and the dome on its nose.
HULL_R, HULL_Z = 0.105, -0.005
HULL_FROM, HULL_TO = -0.290, 0.210
FLANGE_R, FLANGE_TO = 0.135, 0.255
DOME_R = 0.125                           # the sphere the dome is cut from
DOME_CENTRE = FRONT - DOME_R
# The frame: two end plates, front just aft of the dome's flange.
PLATE_X = (0.195, -0.300)
PLATE_T = 0.012
# The tubes: along the top edges, and the skids under.
TUBE_R, TUBE_Y, TUBE_Z = 0.022, 0.165, H / 2 - 0.025
SKID_R, SKID_Z = 0.020, -H / 2 + 0.024
# The thrusters: one at each corner of each end plate.
CORNER_Y, CORNER_Z = 0.150, 0.108
DUCT_R, DUCT_LONG = 0.050, 0.045
TOE_DEG, TILT_DEG = 45.0, 30.0
# The lamps: either side of the dome, at its middle.
LAMP_AT = (0.275, 0.170, HULL_Z)


def thrusters() -> list[dict]:
    """Eight, at the corners of the two end plates (photographed), each
    toed out 45° from fore-and-aft and tilted 30° from level towards the
    middle — an upper corner's thruster pushing out pushes down (assumed:
    Boxfish say "3D vectored" and no more). Eight corners pointed so give all
    six degrees of freedom, what each does to surge, sway, heave, roll, pitch
    and yaw a different pattern of signs. Tilted the other way, out along the
    corner, a thruster's sideways and vertical pushes very nearly cancel in
    roll, and the vehicle would have a tenth of the roll authority."""
    toe, tilt = math.radians(TOE_DEG), math.radians(TILT_DEG)
    out = []
    for end, x in (("front", PLATE_X[0]), ("rear", PLATE_X[1])):
        sx = 1.0 if end == "front" else -1.0
        for side, sy in (("starboard", 1.0), ("port", -1.0)):
            for level, sz in (("upper", 1.0), ("lower", -1.0)):
                d = np.array([sx * math.cos(tilt) * math.cos(toe), sy * math.cos(tilt) * math.sin(toe),
                              -sz * math.sin(tilt)])
                out.append({"name": f"{end}-{side}-{level}",
                            "position": [round(x, 4), round(sy * CORNER_Y, 4), round(HULL_Z + sz * CORNER_Z, 4)],
                            "direction": [round(float(c), 4) for c in d]})
    return out


def lamps() -> list[tuple]:
    x, y, z = LAMP_AT
    return [("port", [x, -y, z]), ("starboard", [x, y, z])]


# ── shapes ───────────────────────────────────────────────────────────────────

def along(mesh, start, end):
    """A mesh made along +z from 0 to its length, laid from `start` to `end`."""
    start, end = np.asarray(start, float), np.asarray(end, float)
    axis = end - start
    mesh.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], axis / np.linalg.norm(axis)))
    mesh.apply_translation(start)
    return mesh


def rod(r, start, end, sections=32):
    long = float(np.linalg.norm(np.subtract(end, start)))
    m = trimesh.creation.cylinder(radius=r, height=long, sections=sections)
    m.apply_translation([0, 0, long / 2])
    return along(m, start, end)


def ring(r_in, r_out, start, end, sections=40):
    long = float(np.linalg.norm(np.subtract(end, start)))
    m = trimesh.creation.annulus(r_min=r_in, r_max=r_out, height=long, sections=sections)
    m.apply_translation([0, 0, long / 2])
    return along(m, start, end)


def dome():
    """The acrylic dome: the front of a sphere, cut where it meets the flange."""
    s = trimesh.creation.uv_sphere(radius=DOME_R, count=[48, 48])
    s.apply_translation([DOME_CENTRE, 0, HULL_Z])
    return s.slice_plane([FLANGE_TO, 0, 0], [1, 0, 0])      # open: it sits on the flange


def plate(x):
    """An end plate: a ring round the hull and a ring round each corner duct,
    joined by the frame's edges and its mounts for the tubes and skids. Drawn
    as those parts laid over each other, which is how the plate reads."""
    a, b = [x - PLATE_T / 2, 0, 0], [x + PLATE_T / 2, 0, 0]

    def at(y, z, p):
        return [p[0], y, z]

    def bar(y0, z0, y1, z1):
        m = trimesh.creation.box(extents=[PLATE_T, abs(y1 - y0) or 0.036, abs(z1 - z0) or 0.036])
        m.apply_translation([x, (y0 + y1) / 2, (z0 + z1) / 2])
        return m

    top, bottom = HULL_Z + CORNER_Z, HULL_Z - CORNER_Z
    parts = [ring(HULL_R - 0.002, HULL_R + 0.028, at(0, HULL_Z, a), at(0, HULL_Z, b), 64)]
    parts += [ring(DUCT_R - 0.004, DUCT_R + 0.014, at(sy * CORNER_Y, HULL_Z + sz * CORNER_Z, a),
                   at(sy * CORNER_Y, HULL_Z + sz * CORNER_Z, b), 40) for sy in (1, -1) for sz in (1, -1)]
    parts += [bar(-CORNER_Y + DUCT_R, top, CORNER_Y - DUCT_R, top),           # the top edge
              bar(-CORNER_Y + DUCT_R, bottom, CORNER_Y - DUCT_R, bottom),     # the bottom edge
              bar(CORNER_Y, bottom + DUCT_R, CORNER_Y, top - DUCT_R),         # the sides
              bar(-CORNER_Y, bottom + DUCT_R, -CORNER_Y, top - DUCT_R),
              bar(0, top, 0, TUBE_Z)]                                          # up to the tubes
    for sy in (1, -1):
        parts.append(bar(sy * TUBE_Y, top, sy * TUBE_Y, TUBE_Z))              # the tubes' clamps
        parts.append(bar(sy * TUBE_Y, SKID_Z, sy * TUBE_Y, bottom))           # the skids' feet
    return trimesh.util.concatenate(parts)


def duct(unit):
    at, d = np.array(unit["position"]), np.array(unit["direction"])
    shroud = ring(DUCT_R - 0.004, DUCT_R, at - d * DUCT_LONG / 2, at + d * DUCT_LONG / 2)
    motor = rod(0.019, at - d * 0.035, at + d * 0.010, sections=24)
    return shroud, motor


def tube(y, z, parts, r):
    """A tube along x in lengths of different finish, capped black."""
    pieces = {}
    for look, x0, x1 in parts:
        pieces.setdefault(look, []).append(rod(r, [x0, y, z], [x1, y, z]))
    ends = [rod(r + 0.003, [parts[0][1], y, z], [parts[0][1] + 0.022, y, z]),
            rod(r + 0.003, [parts[-1][2] - 0.022, y, z], [parts[-1][2], y, z])]
    return pieces, ends


def build() -> Hull:
    hull = Hull("BoxfishLuna", doc="Boxfish Luna, drawn by hardware/luna/shape.py from Boxfish's photographs "
                                   "and published envelope. Origin at the centre of gravity, x forward, metres.")
    hull.look("Paint", "#f5c400", 0.28, clearcoat=1.0,
              rtx=("OmniSurface", {"diffuse_reflection_color": (0.88, 0.56, 0.0), "specular_reflection_roughness": 0.3,
                                   "specular_reflection_weight": 0.5, "coat_weight": 0.8, "coat_roughness": 0.08}))
    hull.look("Frame", "#151618", 0.5,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.012, 0.013, 0.015), "reflection_roughness_constant": 0.5}))
    hull.look("Anodised", "#202226", 0.35, metal=0.6,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.018, 0.019, 0.022), "metallic_constant": 0.6,
                               "reflection_roughness_constant": 0.32}))
    hull.look("Carbon", "#1b1c1e", 0.22, clearcoat=1.0,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.010, 0.010, 0.011), "reflection_roughness_constant": 0.18}))
    hull.look("Dome", "#e6eef2", 0.02, opacity=0.12,
              rtx=("OmniGlass", {"glass_color": (0.97, 0.99, 1.0), "glass_ior": 1.49, "thin_walled": False,
                                 "frosting_roughness": 0.0}))
    hull.look("Camera", "#0c0d0f", 0.2,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.008, 0.008, 0.01), "reflection_roughness_constant": 0.15}))
    hull.look("LampFace", "#f3d48a", 0.1, emissive="0.9, 0.75, 0.4",
              rtx=("OmniPBR", {"diffuse_color_constant": (0.9, 0.65, 0.25), "reflection_roughness_constant": 0.1}))
    hull.look("Red", "#b3201c", 0.4,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.45, 0.02, 0.015), "reflection_roughness_constant": 0.4}))

    # The pressure hull, its straps, and its rear end cap with the connectors.
    hull.add("PressureHull", rod(HULL_R, [HULL_FROM, 0, HULL_Z], [HULL_TO, 0, HULL_Z], sections=64), "Paint")
    straps = [ring(HULL_R - 0.001, HULL_R + 0.003, [x, 0, HULL_Z], [x + 0.014, 0, HULL_Z], 64) for x in (-0.06, 0.09)]
    hull.add("Straps", trimesh.util.concatenate(straps), "Frame")
    back = HULL_FROM - 0.032
    hull.add("EndCap", rod(HULL_R + 0.006, [back, 0, HULL_Z], [HULL_FROM, 0, HULL_Z], sections=64), "Anodised")
    plugs = [rod(0.008, [back - 0.022, 0.06 * math.cos(a), HULL_Z + 0.06 * math.sin(a)],
                 [back, 0.06 * math.cos(a), HULL_Z + 0.06 * math.sin(a)], 16)
             for a in np.linspace(0, 2 * math.pi, 6, endpoint=False)]
    hull.add("Connectors", trimesh.util.concatenate(plugs[:3]), "Anodised")
    hull.add("Caps", trimesh.util.concatenate(plugs[3:]), "Red")
    # The dome and its flange, and the camera behind it.
    hull.add("Flange", ring(HULL_R - 0.01, FLANGE_R, [HULL_TO, 0, HULL_Z], [FLANGE_TO, 0, HULL_Z], 64), "Anodised")
    hull.add("Dome", dome(), "Dome")
    # The camera fills the dome, as it does in the photographs: a black housing
    # most of the dome's width, the lens in its middle.
    hull.add("Camera", trimesh.util.concatenate([
        rod(FLANGE_R - 0.03, [HULL_TO, 0, HULL_Z], [FLANGE_TO + 0.01, 0, HULL_Z], 64),
        rod(0.04, [FLANGE_TO + 0.01, 0, HULL_Z], [FLANGE_TO + 0.05, 0, HULL_Z], 40)]), "Camera")
    # The frame.
    hull.add("Frame", trimesh.util.concatenate([plate(x) for x in PLATE_X]), "Frame")
    # The tubes along the top, the high float aft on the port side, the skids.
    paint, carbon, caps = [], [], []
    for y in (TUBE_Y, -TUBE_Y):
        pieces, ends = tube(y, TUBE_Z, [("Paint", BACK + 0.005, -0.12), ("Carbon", -0.12, 0.02),
                                        ("Paint", 0.02, PLATE_X[0] + 0.03)], TUBE_R)
        paint += pieces["Paint"]; carbon += pieces["Carbon"]; caps += ends
    pieces, ends = tube(-0.085, TUBE_Z + 0.002, [("Paint", BACK + 0.01, -0.17), ("Carbon", -0.17, -0.12),
                                                 ("Paint", -0.12, -0.05)], 0.020)
    paint += pieces["Paint"]; carbon += pieces["Carbon"]; caps += ends
    for y in (TUBE_Y, -TUBE_Y):
        pieces, ends = tube(y, SKID_Z, [("Carbon", BACK + 0.02, PLATE_X[0] + 0.07)], SKID_R)
        carbon += pieces["Carbon"]; caps += ends
    hull.add("Tubes", trimesh.util.concatenate(paint), "Paint")
    hull.add("CarbonTubes", trimesh.util.concatenate(carbon), "Carbon")
    hull.add("TubeEnds", trimesh.util.concatenate(caps), "Frame")
    # The thrusters' ducts and motors (the propellers are drawn turning, by
    # the runtime, at these same places: draw/propellers.py).
    shrouds, motors = zip(*(duct(u) for u in thrusters()))
    hull.add("Ducts", trimesh.util.concatenate(shrouds), "Frame")
    hull.add("Motors", trimesh.util.concatenate(motors), "Anodised")
    # The lamps, on short arms off the front plate.
    bodies, faces, arms = [], [], []
    for _, (x, y, z) in lamps():
        bodies.append(rod(0.040, [x - 0.050, y, z], [x, y, z], 32))
        face = trimesh.creation.box(extents=[0.003, 0.046, 0.046])
        face.apply_translation([x + 0.0015, y, z])
        faces.append(face)
        arms.append(rod(0.008, [PLATE_X[0], y * 0.82, z], [x - 0.04, y, z], 12))
    hull.add("Lamps", trimesh.util.concatenate(bodies + arms), "Anodised")
    hull.add("LampFaces", trimesh.util.concatenate(faces), "LampFace")
    return hull


def main() -> int:
    hull = build()
    every = trimesh.util.concatenate([m for _, m, _ in hull.meshes])
    low, high = every.bounds
    print("across", np.round(high - low, 3), "from", np.round(low, 3), "to", np.round(high, 3))
    INTO.mkdir(parents=True, exist_ok=True)
    out = hull.save(INTO / "boxfish-luna.usd")
    print(f"{out} {out.stat().st_size / 1e6:.2f} MB, {len(every.faces)} faces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
