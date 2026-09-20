"""The mini ROV, as code.

    hardware/.venv/bin/python hardware/rov/rov.py

Writes to hardware/out/rov/: a STEP and an STL per printed part, an STL per
bought part for the pictures, parts.json, and rov.json for the design sheet.

Printed: the cradle (floor frame, two cheeks, two stern arms, four thruster
saddles, ballast channels, strap slots), the bezel that holds the window,
and the tray inside the box. Bought: the box, four thrusters, the window,
two glands, the boards, two steel bars.

Nothing printed seals. The box seals on its own lid gasket; the window on
an O-ring and silicone; the tether on two glands.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

from build123d import (Axis, Box, Cylinder, Location, Plane, RectangleRounded, Rot,
                       export_step, export_stl, extrude, fillet)

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "rov"
PARTS: dict[str, dict] = {}


def along_x(d, length, at=(0.0, 0.0, 0.0)):
    return Location(at) * Rot(0, 90, 0) * Cylinder(d / 2, length)


def along_z(d, length, at=(0.0, 0.0, 0.0)):
    return Location(at) * Cylinder(d / 2, length)


def rounded_plate(length, width, r, z0, z1, x=0.0, y=0.0):
    return Location((x, y, z0)) * extrude(RectangleRounded(length, width, r), z1 - z0)


def saddle(at, axis):
    """A band clamp around a duct: a ring of BAND_W with a split and two
    screw ears, plus a foot that joins it to the cradle."""
    x, y, z = at
    od = P.DUCT_OD + 2 * P.BAND_T
    if axis == "z":
        ring = along_z(od, P.BAND_W, at) - along_z(P.DUCT_OD, P.BAND_W + 2, at)
        # Split on the outboard side, with two ears for an M3.
        side = 1.0 if y > 0 else -1.0
        ring -= Location((x, y + side * (P.DUCT_OD / 2 + P.BAND_T / 2), z)) * Box(2.0, P.BAND_T + 2, P.BAND_W + 2)
        ears = Location((x, y + side * (P.DUCT_OD / 2 + P.BAND_T + 3.0), z)) * Box(14.0, 6.0, P.BAND_W)
        ears -= along_x(3.2, 16.0, (x, y + side * (P.DUCT_OD / 2 + P.BAND_T + 3.0), z))
        return ring + ears
    ring = along_x(od, P.BAND_W, at) - along_x(P.DUCT_OD, P.BAND_W + 2, at)
    ring -= Location((x, y, z - (P.DUCT_OD / 2 + P.BAND_T / 2))) * Box(P.BAND_W + 2, 2.0, P.BAND_T + 2)
    ears = Location((x, y, z - (P.DUCT_OD / 2 + P.BAND_T + 3.0))) * Box(P.BAND_W, 14.0, 6.0)
    ears -= along_z(3.2, 16.0, (x, y, z - (P.DUCT_OD / 2 + P.BAND_T + 3.0)))
    return ring + ears


def cradle():
    z0 = P.CRADLE_FLOOR_Z
    z1 = z0 + P.CRADLE_T
    # The floor: a rim, a spine and two cross bars.
    floor = rounded_plate(P.CRADLE_L, P.CRADLE_W, P.BOX_R + P.CHEEK_T, z0, z1)
    floor -= rounded_plate(P.CRADLE_L - 2 * P.FLOOR_RIM, P.CRADLE_W - 2 * P.FLOOR_RIM, 4.0, z0 - 1, z1 + 1)
    floor += Location((0, 0, (z0 + z1) / 2)) * Box(P.CRADLE_L - 8.0, P.SPINE_W, P.CRADLE_T)
    for x in P.STRAP_SLOTS_X:
        floor += Location((x, 0, (z0 + z1) / 2)) * Box(P.SPINE_W, P.CRADLE_W - 8.0, P.CRADLE_T)
    part = floor
    # Two cheeks along the long sides, up to CHEEK_H, with strap slots.
    for side in (1.0, -1.0):
        y = side * (P.CRADLE_W / 2 - P.CHEEK_T / 2)
        cheek = Location((0, y, z1 + P.CHEEK_H / 2)) * Box(P.CRADLE_L, P.CHEEK_T, P.CHEEK_H)
        for x in P.STRAP_SLOTS_X:
            cheek -= Location((x, y, z1 + P.CHEEK_H - 8.0)) * Box(P.STRAP_W, P.CHEEK_T + 2, P.STRAP_T + 1.0)
        part += cheek
    # Low end walls at nose and stern so the box cannot slide out.
    for x in (P.CRADLE_L / 2 - P.CHEEK_T / 2, -(P.CRADLE_L / 2 - P.CHEEK_T / 2)):
        wall = Location((x, 0, z1 + 10.0)) * Box(P.CHEEK_T, P.CRADLE_W, 20.0)
        # Keep the rear wall clear of the glands and the front clear of the window.
        wall -= Location((x, 0, z1 + 10.0)) * Box(P.CHEEK_T + 2, P.CRADLE_W - 40.0, 22.0)
        part += wall
    # Vertical thruster saddles: a foot from the cheek out to the ring.
    for name, at, axis in P.THRUSTERS:
        x, y, z = at
        if axis[2] == 1.0:
            side = 1.0 if y > 0 else -1.0
            reach = abs(y) - P.DUCT_OD / 2 - P.BAND_T - (P.CRADLE_W / 2)
            foot = Location((x, side * (P.CRADLE_W / 2 + reach / 2), z)) * Box(P.BAND_W + 20.0, reach + 2.0, P.BAND_W)
            part += foot + saddle(at, "z")
        else:
            # An arm back from the cheek's rear end to the stern saddle.
            side = 1.0 if y > 0 else -1.0
            cheek_y = side * (P.CRADLE_W / 2 - P.CHEEK_T / 2)
            x0 = -P.CRADLE_L / 2
            arm = Location(((x0 + x) / 2, (cheek_y + y) / 2, (z1 + 15.0 + z) / 2)) \
                * Box(abs(x - x0) + P.BAND_W, P.ARM_W, P.ARM_T)
            # A gusset down to the saddle's ears.
            part += arm + saddle(at, "x")
    # Ballast channels under the floor, open at the stern.
    bl, bw, bh = P.BALLAST_BAR
    for side in (1.0, -1.0):
        y = side * P.BALLAST_Y
        ch = Location((0, y, z0 - bh / 2 - 1.0)) * Box(bl + 6.0, bw + 6.0, bh + 2.0)
        ch -= Location((-3.0, y, z0 - bh / 2 - 1.0)) * Box(bl + 6.0, bw + 0.4, bh + 0.4)
        part += ch
    PARTS["cradle"] = {"print": "PETG at Sketchat, in two halves split at x = 0 if the bed is under 300 mm", "colour": "#1e1e1e"}
    return part


def bezel():
    x = P.BOX_L / 2
    part = along_x(P.BEZEL_OD, P.BEZEL_T, (x + P.BEZEL_T / 2, 0, P.WINDOW_Z))
    part -= along_x(P.WINDOW_D + 0.4, 3.2, (x + 1.6, 0, P.WINDOW_Z))           # the disc's pocket
    part -= along_x(P.WINDOW_D - 6.0, P.BEZEL_T + 2, (x + P.BEZEL_T / 2, 0, P.WINDOW_Z))
    for i in range(4):
        a = math.radians(45 + 90 * i)
        part -= along_x(3.2, P.BEZEL_T + 2, (x + P.BEZEL_T / 2, P.BEZEL_SCREWS_R * math.cos(a), P.WINDOW_Z + P.BEZEL_SCREWS_R * math.sin(a)))
    PARTS["bezel"] = {"print": "PETG; four M3 through the box wall, silicone under it", "colour": "#f26a1b"}
    return part


def tray():
    part = Location((0, 0, P.TRAY_Z - P.TRAY_T / 2)) * Box(P.TRAY_L, P.TRAY_W, P.TRAY_T)
    nx, ny = int(P.TRAY_L // P.TRAY_GRID), int(P.TRAY_W // P.TRAY_GRID)
    for i in range(1, nx):
        for j in range(1, ny):
            x = -P.TRAY_L / 2 + i * P.TRAY_GRID
            y = -P.TRAY_W / 2 + j * P.TRAY_GRID
            part -= along_z(2.6, P.TRAY_T + 2, (x, y, P.TRAY_Z - P.TRAY_T / 2))
    # Four feet, and the camera post at the front.
    for sx in (1.0, -1.0):
        for sy in (1.0, -1.0):
            part += along_z(6.0, P.TRAY_Z - P.TRAY_T - P.FLOOR_Z, (sx * (P.TRAY_L / 2 - 6.0), sy * (P.TRAY_W / 2 - 6.0), (P.FLOOR_Z + P.TRAY_Z - P.TRAY_T) / 2))
    cx, cy, cz, cw, ch, ct = P.CAMERA
    px = cx - ct / 2 - 1.5
    post = Location((px, 0, (P.TRAY_Z + cz + 14.0) / 2)) * Box(3.0, 30.0, cz + 14.0 - P.TRAY_Z)
    for sy in (1.0, -1.0):
        for sz in (1.0, -1.0):
            post -= along_x(2.2, 6.0, (px, sy * 10.5, cz + sz * 6.25))
    post -= along_x(12.0, 6.0, (px, 0, cz))
    part += post
    PARTS["tray"] = {"print": "PETG; a grid of M2.5 holes, boards screw or tie down", "colour": "#c9c9c9"}
    return part


def bought():
    parts = {}
    body = rounded_plate(P.BOX_L, P.BOX_W, P.BOX_R, -P.BOX_H / 2, P.LID_Z)
    body -= rounded_plate(P.INSIDE_L, P.INSIDE_W, P.BOX_R - P.BOX_WALL, P.FLOOR_Z, P.LID_Z + 1)
    for sx in (1.0, -1.0):
        for sy in (1.0, -1.0):
            body += along_z(P.BOSS_D, P.INSIDE_H, (sx * (P.INSIDE_L / 2 - P.BOSS_INSET), sy * (P.INSIDE_W / 2 - P.BOSS_INSET), P.FLOOR_Z + P.INSIDE_H / 2))
    body -= along_x(P.WINDOW_BORE, 10.0, (P.BOX_L / 2, 0, P.WINDOW_Z))
    for x, y, z in P.GLANDS:
        body -= along_x(P.GLAND_HOLE_D, 10.0, (x, y, z))
    parts["ref-box"] = (body, {"buy": "LeMotech ABS box 200 × 120 × 75, IP65", "colour": "#2a2a2a"})
    lid = rounded_plate(P.BOX_L, P.BOX_W, P.BOX_R, P.LID_Z, P.BOX_H / 2)
    parts["ref-lid"] = (lid, {"buy": "its clear polycarbonate lid", "colour": "#a8d4f0", "alpha": 0.35})
    thr = None
    for name, at, axis in P.THRUSTERS:
        x, y, z = at
        if axis[2] == 1.0:
            duct = along_z(P.DUCT_OD, P.DUCT_LENGTH, at) - along_z(P.DUCT_OD - 6.0, P.DUCT_LENGTH + 2, at)
            motor = along_z(30.0, 40.0, at)
            for i in range(3):
                motor += Location(at) * Rot(0, 0, 120 * i) * Location((P.DUCT_OD / 4 - 2, 0, 0)) * Box(P.DUCT_OD / 2 - 2, 4.0, 6.0)
        else:
            duct = along_x(P.DUCT_OD, P.DUCT_LENGTH, at) - along_x(P.DUCT_OD - 6.0, P.DUCT_LENGTH + 2, at)
            motor = along_x(30.0, 40.0, at)
            for i in range(3):
                motor += Location(at) * Rot(120 * i, 0, 0) * Location((0, P.DUCT_OD / 4 - 2, 0)) * Box(6.0, P.DUCT_OD / 2 - 2, 4.0)
        t = duct + motor
        thr = t if thr is None else thr + t
    parts["ref-thrusters"] = (thr, {"buy": "4 × Cryfokt 2838 500 KV, 60 mm duct; duct size is a guess until measured", "colour": "#3a3f44"})
    window = along_x(P.WINDOW_D, P.WINDOW_T, (P.BOX_L / 2 + 1.6, 0, P.WINDOW_Z))
    parts["ref-window"] = (window, {"buy": "30 × 3 mm cast acrylic disc, SACO", "colour": "#cfe8f7", "alpha": 0.5})
    glands = None
    for x, y, z in P.GLANDS:
        g = along_x(15.0, 14.0, (x - 7.0, y, z)) + along_x(6.0, 40.0, (x - 30.0, y, z))
        glands = g if glands is None else glands + g
    parts["ref-glands"] = (glands, {"buy": "2 × PG7, owned", "colour": "#111111"})
    boards = None
    for name, x, y, z, length, width, height in P.BOARDS:
        b = Location((x, y, z + height / 2)) * Box(length, width, height)
        boards = b if boards is None else boards + b
    parts["ref-boards"] = (boards, {"buy": "Pi, PCA9685, BNO055, buck, 4 ESCs, terminals", "colour": "#2e7d32"})
    cx, cy, cz, cw, ch, ct = P.CAMERA
    cam = Location((cx, cy, cz)) * Box(ct, cw, ch) + along_x(9.0, 6.0, (cx + ct / 2 + 3.0, cy, cz))
    parts["ref-camera"] = (cam, {"buy": "Camera Module 3 Wide, owned", "colour": "#222222"})
    bl, bw, bh = P.BALLAST_BAR
    bars = None
    for side in (1.0, -1.0):
        b = Location((0, side * P.BALLAST_Y, P.CRADLE_FLOOR_Z - bh / 2 - 1.0)) * Box(bl, bw, bh)
        bars = b if bars is None else bars + b
    parts["ref-ballast"] = (bars, {"buy": "2 × mild steel 150 × 20 × 8, any metal shop", "colour": "#6d6d6d"})
    return parts


def geometry(parts):
    import base64
    import numpy as np
    import trimesh
    out = []
    for name, meta in parts.items():
        # The sheet's geometry file must stay under 16 MB. A coarse STL is
        # written beside the fine one for parts with many small features,
        # because a grid of holes does not decimate.
        coarse = OUT / f"{name}.sheet.stl"
        mesh = trimesh.load(coarse if coarse.exists() else OUT / f"{name}.stl", force="mesh")
        tris = mesh.vertices[mesh.faces].astype(np.float32).reshape(-1)
        out.append({"name": name, "colour": meta["colour"], "alpha": meta.get("alpha", 1.0),
                    "triangles": int(len(mesh.faces)), "positions": base64.b64encode(tris.tobytes()).decode("ascii")})
    (OUT / "rov.json").write_text(json.dumps(out))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    printed = {"cradle": cradle(), "bezel": bezel(), "tray": tray()}
    for name, part in printed.items():
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"))
        export_stl(part, str(OUT / f"{name}.sheet.stl"), tolerance=0.4, angular_tolerance=0.8)
        PARTS[name]["volume_cm3"] = round(part.volume / 1000, 1)
        PARTS[name]["mass_g"] = round(part.volume / 1000 * 1.27)
        bb = part.bounding_box()
        PARTS[name]["bbox_mm"] = [round(v, 1) for v in (bb.size.X, bb.size.Y, bb.size.Z)]
        print(f"{name:8s} {PARTS[name]['volume_cm3']:7.1f} cm³ ≈ {PARTS[name]['mass_g']:4d} g PETG  {PARTS[name]['bbox_mm']}")
    for name, (part, meta) in bought().items():
        export_stl(part, str(OUT / f"{name}.stl"))
        meta["volume_cm3"] = round(part.volume / 1000, 1)
        PARTS[name] = meta
    (OUT / "parts.json").write_text(json.dumps(PARTS, indent=2))
    geometry(PARTS)
    print(f"overall {P.OVERALL_L:.0f} × {P.OVERALL_W:.0f} × {P.OVERALL_H:.0f} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
