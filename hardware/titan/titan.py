"""The mini Titan, as code.

    hardware/.venv/bin/python hardware/titan/titan.py

Writes to hardware/out/titan/: a STEP and an STL per printed part, an STL
per bought part for the pictures, parts.json, and titan.json for the sheet.

Printed: the cover (orange, the upper half of the capsule), the chassis
(black: the lower half of the capsule, the base plate, four arms to the
vertical pods, two struts to the stern pods, ballast rails), the nose bezel,
and the tray inside the box. Bought: the box, six thrusters, the window, two
glands, the boards, two steel bars.

Nothing printed seals. The box seals on its lid gasket; the window on an
O-ring and silicone; the tether on two glands. The capsule floods.
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

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "titan"
PARTS: dict[str, dict] = {}


def along_x(d, length, at=(0.0, 0.0, 0.0)):
    return Location(at) * Rot(0, 90, 0) * Cylinder(d / 2, length)


def along_z(d, length, at=(0.0, 0.0, 0.0)):
    return Location(at) * Cylinder(d / 2, length)


def rounded(length, width, r, z0, z1, x=0.0, y=0.0):
    return Location((x, y, z0)) * extrude(RectangleRounded(length, width, r), z1 - z0)


def capsule_half(top: bool):
    """Half the capsule: a rounded-rectangle shell with a domed crown."""
    h = P.CAPSULE_H / 2
    s = P.SKIN
    sign = 1.0 if top else -1.0
    r = P.CAPSULE_CROWN_R if top else P.BELLY_R
    outer = rounded(P.CAPSULE_L, P.CAPSULE_W, P.CAPSULE_CORNER_R, 0.0, sign * h, P.CAPSULE_X)
    crown = outer.faces().sort_by(Axis.Z)[-1 if top else 0]
    outer = fillet(crown.edges(), r)
    inner = rounded(P.CAPSULE_L - 2 * s, P.CAPSULE_W - 2 * s, P.CAPSULE_CORNER_R - s, -sign * 1.0, sign * (h - s), P.CAPSULE_X)
    crown = inner.faces().sort_by(Axis.Z)[-1 if top else 0]
    inner = fillet(crown.edges(), r - s)
    shell = outer - inner
    # The nose opening for the window, and a drain slot low in the stern.
    nose_x = P.CAPSULE_X + P.CAPSULE_L / 2
    shell -= along_x(P.NOSE_OPENING_D, 40.0, (nose_x, 0, P.WINDOW_Z))
    if not top:
        sw, sh = P.STERN_OPENING
        shell -= Location((P.CAPSULE_X - P.CAPSULE_L / 2, 0, -h + 12.0)) * Box(30.0, sw, sh)
    return shell, inner


def bosses(top: bool):
    sign = 1.0 if top else -1.0
    out = None
    for x, y in P.BOSSES:
        b = along_z(P.BOSS_OD, 12.0, (x, y, sign * 6.0))
        b -= along_z(P.SCREW_D, 14.0, (x, y, sign * 6.0))
        out = b if out is None else out + b
    return out


def tab_y(at):
    """Where the joint's plane sits: just inboard of the pod ring."""
    x, y, z = at
    side = 1.0 if y > 0 else -1.0
    return side, y - side * (P.POD_OD / 2)


def tab(at, chassis_side: bool):
    """One of the two mating tabs, a plate in the xz plane with four M3."""
    x, y, z = at
    side, yj = tab_y(at)
    yc = yj - side * P.TAB_T / 2 if chassis_side else yj + side * P.TAB_T / 2
    plate = Location((x, yc, z)) * Box(P.TAB_W, P.TAB_T, P.TAB_H)
    for sx in (1.0, -1.0):
        for sz in (1.0, -1.0):
            plate -= Location((x + sx * P.TAB_HOLES / 2, yc, z + sz * P.TAB_HOLES / 2)) * Rot(90, 0, 0) * Cylinder(1.6, P.TAB_T + 2)
    return plate


def pod(at, vertical: bool):
    """A duct ring with a split band, two ears, and its half of the joint.
    Printed last, after the duct is measured; everything else is printed
    before."""
    x, y, z = at
    side, yj = tab_y(at)
    if vertical:
        ring = along_z(P.POD_OD, P.POD_LENGTH, at) - along_z(P.DUCT_OD, P.POD_LENGTH + 2, at)
        ring -= Location((x, y + side * (P.DUCT_OD / 2 + P.POD_WALL / 2), z)) * Box(2.0, P.POD_WALL + 2, P.POD_LENGTH + 2)
        ears = Location((x, y + side * (P.DUCT_OD / 2 + P.POD_WALL + 3.0), z)) * Box(14.0, 6.0, P.BAND_W)
        ears -= along_x(3.2, 16.0, (x, y + side * (P.DUCT_OD / 2 + P.POD_WALL + 3.0), z))
    else:
        ring = along_x(P.POD_OD, P.POD_LENGTH, at) - along_x(P.DUCT_OD, P.POD_LENGTH + 2, at)
        ring -= Location((x, y, z - (P.DUCT_OD / 2 + P.POD_WALL / 2))) * Box(P.POD_LENGTH + 2, 2.0, P.POD_WALL + 2)
        ears = Location((x, y, z - (P.DUCT_OD / 2 + P.POD_WALL + 3.0))) * Box(P.BAND_W, 14.0, 6.0)
        ears -= along_z(3.2, 16.0, (x, y, z - (P.DUCT_OD / 2 + P.POD_WALL + 3.0)))
    # A short bridge from the ring's inboard face to the tab.
    bridge = Location((x, yj + side * 2.0, z)) * Box(P.TAB_W - 6.0, 6.0, P.TAB_H - 6.0)
    return ring + ears + bridge + tab(at, chassis_side=False)


def cover():
    shell, inside = capsule_half(top=True)
    part = shell + bosses(top=True)
    for x, y in P.VENTS:
        part -= along_z(P.VENT_D, 40.0, (x, y, P.CAPSULE_H / 2))
    # The connector dome: a rounded collar on the crown over the gland.
    top_z = P.CAPSULE_H / 2
    dome = along_z(P.PORT_DOME_D, P.PORT_DOME_H + 12.0, (P.PORT_X, 0, top_z - 6.0 + (P.PORT_DOME_H + 12.0) / 2 - 6.0))
    dome = fillet(dome.faces().sort_by(Axis.Z)[-1].edges(), 8.0)
    dome -= along_z(P.PORT_DOME_D - 8.0, P.PORT_DOME_H + 12.0, (P.PORT_X, 0, top_z - 8.0 + (P.PORT_DOME_H + 12.0) / 2 - 6.0))
    dome -= along_z(P.PORT_HOLE_D, 60.0, (P.PORT_X, 0, top_z))
    part += dome
    PARTS["cover"] = {"print": "JLC3DP, MJF PA12, dyed orange if offered, else grey and painted. Order on day one", "colour": "#f26a1b"}
    return part


def chassis():
    shell, inside = capsule_half(top=False)
    part = shell + bosses(top=False)
    # The base plate under the capsule, lightened to a rim and a spine.
    z0, z1 = P.PLATE_Z - P.PLATE_T, P.PLATE_Z
    plate = rounded(P.CAPSULE_L - 16.0, P.PLATE_W, P.CAPSULE_CORNER_R, z0, z1, P.CAPSULE_X)
    plate -= rounded(P.CAPSULE_L - 80.0, P.PLATE_W - 30.0, 8.0, z0 - 1, z1 + 1, P.CAPSULE_X + 10.0)
    plate += Location((P.CAPSULE_X, 0, (z0 + z1) / 2)) * Box(P.CAPSULE_L - 30.0, 18.0, P.PLATE_T)
    part += plate
    # Arms out to the vertical pods, and the pods.
    for name, at, axis in P.THRUSTERS:
        x, y, z = at
        if axis[2] == 1.0:
            side = 1.0 if y > 0 else -1.0
            y_in = side * (P.PLATE_W / 2 - 4.0)
            _, yj = tab_y(at)
            arm = Location((x, (y_in + yj) / 2, z)) * Box(P.ARM_W, abs(yj - y_in), P.ARM_T)
            riser = Location((x, y_in, (z1 + z) / 2)) * Box(P.ARM_W, 8.0, abs(z - z1) + P.ARM_T)
            part += arm + riser + tab(at, chassis_side=True)
        else:
            side = 1.0 if y > 0 else -1.0
            _, yj = tab_y(at)
            ys = yj - side * (P.TAB_T + P.ARM_W / 2)
            # A strut back from under the tail to the pod's tab, and a drop.
            x_in = P.TAIL_X + 24.0
            strut = Location(((x_in + x) / 2, ys, z0 - P.ARM_T / 2)) * Box(abs(x - x_in) + P.TAB_W / 2, P.ARM_W, P.ARM_T)
            drop = Location((x, ys, (z0 - P.ARM_T + z) / 2)) * Box(P.TAB_W - 10.0, P.ARM_W - 8.0, abs(z - z0) + P.ARM_T)
            part += strut + drop + tab(at, chassis_side=True)
    # Two cradle ribs inside the lower capsule that the standing box sits in.
    for x in (P.BOX_X - 60.0, P.BOX_X + 60.0):
        rib = Location((x, 0, -P.CAPSULE_H / 4)) * Box(6.0, P.CAPSULE_W, P.CAPSULE_H / 2)
        rib -= Location((x, 0, 0)) * Box(8.0, P.BOX_W + 1.0, P.BOX_H + 1.0)
        part += rib & inside
    PARTS["chassis"] = {"print": "JLC3DP, MJF PA12 black. Order on day one: nothing on it depends on a measurement", "colour": "#1e1e1e"}
    return part


def pods():
    out = None
    for name, at, axis in P.THRUSTERS:
        p = pod(at, vertical=axis[2] == 1.0)
        out = p if out is None else out + p
    PARTS["pods"] = {"print": "6 rings, PETG at Sketchat after the duct is measured; one STEP, print six", "colour": "#2b2f33"}
    return out


def bezel():
    x = P.BOX_X + P.BOX_L / 2
    part = along_x(P.BEZEL_OD, P.BEZEL_T, (x + P.BEZEL_T / 2, 0, P.WINDOW_Z))
    part -= along_x(P.WINDOW_D + 0.4, 3.2, (x + 1.6, 0, P.WINDOW_Z))
    part -= along_x(P.WINDOW_D - 6.0, P.BEZEL_T + 2, (x + P.BEZEL_T / 2, 0, P.WINDOW_Z))
    for i in range(4):
        a = math.radians(45 + 90 * i)
        part -= along_x(3.2, P.BEZEL_T + 2, (x + P.BEZEL_T / 2, P.BEZEL_SCREWS_R * math.cos(a), P.WINDOW_Z + P.BEZEL_SCREWS_R * math.sin(a)))
    PARTS["bezel"] = {"print": "JLC3DP, MJF PA12 black, with the cover and chassis", "colour": "#111111"}
    return part


def tray():
    """Two flat decks: ESCs and the converter on the lower, the small boards
    on the upper, joined by four standoffs. One printed part."""
    def deck(z_top):
        d = Location((P.BOX_X, 0, z_top - P.TRAY_T / 2)) * Box(P.TRAY_L, P.TRAY_W, P.TRAY_T)
        nx, ny = int(P.TRAY_L // P.TRAY_GRID), int(P.TRAY_W // P.TRAY_GRID)
        for i in range(1, nx):
            for j in range(1, ny):
                d -= along_z(2.6, P.TRAY_T + 2, (P.BOX_X - P.TRAY_L / 2 + i * P.TRAY_GRID, -P.TRAY_W / 2 + j * P.TRAY_GRID, z_top - P.TRAY_T / 2))
        return d
    lower = deck(P.TRAY_Z)
    upper = deck(P.DECK_Z)
    # The upper deck stops short of the converter at the stern.
    upper -= Location((P.BOX_X - 48.0, 0, P.DECK_Z)) * Box(46.0, P.TRAY_W + 2, P.TRAY_T + 2)
    part = lower + upper
    for sx in (1.0, -1.0):
        for sy in (1.0, -1.0):
            x = P.BOX_X + (58.0 if sx > 0 else -20.0)
            part += along_z(5.0, P.DECK_Z - P.TRAY_T - P.TRAY_Z, (x, sy * (P.TRAY_W / 2 - 5.0), (P.TRAY_Z + P.DECK_Z - P.TRAY_T) / 2))
            part += along_z(5.0, P.TRAY_Z - P.TRAY_T - P.FLOOR_Z, (P.BOX_X + sx * (P.TRAY_L / 2 - 5.0), sy * (P.TRAY_W / 2 - 5.0), (P.FLOOR_Z + P.TRAY_Z - P.TRAY_T) / 2))
    cx, cy, cz, cw, ch, ct = P.CAMERA
    px = cx - ct / 2 - 1.5
    post = Location((px, 0, (P.TRAY_Z + cz + 14.0) / 2)) * Box(3.0, 30.0, cz + 14.0 - P.TRAY_Z)
    for sy in (1.0, -1.0):
        for sz in (1.0, -1.0):
            post -= along_x(2.2, 6.0, (px, sy * 10.5, cz + sz * 6.25))
    post -= along_x(12.0, 6.0, (px, 0, cz))
    part += post
    PARTS["tray"] = {"print": "PETG at Sketchat after the box is measured; two decks on standoffs", "colour": "#c9c9c9"}
    return part


def bought():
    parts = {}
    body = Location((P.BOX_X, 0, (-P.BOX_H / 2 + P.LID_Z) / 2)) * Box(P.BOX_L, P.BOX_W, P.LID_Z + P.BOX_H / 2)
    body -= Location((P.BOX_X, 0, (P.FLOOR_Z + P.LID_Z + 1) / 2)) * Box(P.INSIDE_L, P.INSIDE_W, P.LID_Z + 1 - P.FLOOR_Z)
    body -= along_x(P.WINDOW_BORE, 10.0, (P.BOX_X + P.BOX_L / 2, 0, P.WINDOW_Z))
    parts["ref-box"] = (body, {"buy": "LeMotech ABS box 158 × 89 × 58 (6.2 × 3.5 × 2.3 in), IP65, lying flat inside the capsule", "colour": "#2a2a2a"})
    lid = Location((P.BOX_X, 0, (P.LID_Z + P.BOX_H / 2) / 2)) * Box(P.BOX_L, P.BOX_W, P.LID_T)
    lid -= along_z(P.GLAND_HOLE_D, 10.0, (P.PORT_X, 0, P.BOX_H / 2))
    parts["ref-lid"] = (lid, {"buy": "its clear lid, up, with the PG9 through it", "colour": "#a8d4f0", "alpha": 0.4})
    thr = None
    for name, at, axis in P.THRUSTERS:
        x, y, z = at
        if axis[2] == 1.0:
            t = along_z(P.DUCT_OD, P.DUCT_LENGTH, at) - along_z(P.DUCT_OD - 6.0, P.DUCT_LENGTH + 2, at) + along_z(30.0, 40.0, at)
            for i in range(3):
                t += Location(at) * Rot(0, 0, 120 * i) * Location((P.DUCT_OD / 4 - 2, 0, 0)) * Box(P.DUCT_OD / 2 - 2, 4.0, 6.0)
        else:
            t = along_x(P.DUCT_OD, P.DUCT_LENGTH, at) - along_x(P.DUCT_OD - 6.0, P.DUCT_LENGTH + 2, at) + along_x(30.0, 40.0, at)
            for i in range(3):
                t += Location(at) * Rot(120 * i, 0, 0) * Location((0, P.DUCT_OD / 4 - 2, 0)) * Box(6.0, P.DUCT_OD / 2 - 2, 4.0)
        thr = t if thr is None else thr + t
    parts["ref-thrusters"] = (thr, {"buy": "6 × Cryfokt 2838 500 KV, 60 mm duct; duct size is a guess until measured", "colour": "#3a3f44"})
    window = along_x(P.WINDOW_D, P.WINDOW_T, (P.BOX_X + P.BOX_L / 2 + 1.6, 0, P.WINDOW_Z))
    parts["ref-window"] = (window, {"buy": "30 × 3 mm cast acrylic disc, SACO", "colour": "#cfe8f7", "alpha": 0.5})
    gz = P.BOX_H / 2
    gland = along_z(19.0, 12.0, (P.PORT_X, 0, gz + 6.0)) + along_z(6.5, 90.0, (P.PORT_X, 0, gz + 50.0))
    parts["ref-glands"] = (gland, {"buy": "1 × PG9 gland in the box's top wall; the tether is the round Cat6, owned", "colour": "#111111"})
    boards = None
    for name, x, y, z, length, width, height in P.BOARDS:
        b = Location((x, y, z + height / 2)) * Box(length, width, height)
        boards = b if boards is None else boards + b
    parts["ref-boards"] = (boards, {"buy": "Pi, PCA9685, BNO055, buck, 6 ESCs, terminals", "colour": "#2e7d32"})
    cx, cy, cz, cw, ch, ct = P.CAMERA
    parts["ref-camera"] = (Location((cx, cy, cz)) * Box(ct, cw, ch) + along_x(9.0, 6.0, (cx + ct / 2 + 3.0, cy, cz)),
                           {"buy": "Camera Module 3 Wide, owned", "colour": "#222222"})
    foam = None
    for x0, x1 in (P.FOAM_TAIL, P.FOAM_NOSE):
        f = Location(((x0 + x1) / 2, 0, 0)) * Box(x1 - x0, P.CAPSULE_W - 2 * P.SKIN - 4.0, P.CAPSULE_H - 2 * P.SKIN - 6.0)
        foam = f if foam is None else foam + f
    foam -= along_x(P.NOSE_OPENING_D + 4.0, 80.0, (P.BOX_X + P.BOX_L / 2 + 20.0, 0, P.WINDOW_Z))
    x0, x1 = P.FOAM_OVER
    for zc in (P.BOX_H / 2 + 1.0 + P.FOAM_SHEET / 2, -(P.BOX_H / 2 + 1.0 + P.FOAM_SHEET / 2)):
        foam += Location(((x0 + x1) / 2, 0, zc)) * Box(x1 - x0, P.BOX_W - 6.0, P.FOAM_SHEET)
    foam -= along_z(P.PORT_DOME_D, 60.0, (P.PORT_X, 0, P.BOX_H / 2 + 10.0))
    # Clip the foam to the capsule's true inside, crown fillets included. A
    # plain rounded box left the foam poking through the curved top corners.
    _, inner_top = capsule_half(top=True)
    _, inner_bottom = capsule_half(top=False)
    foam = foam & (inner_top + inner_bottom)
    parts["ref-foam"] = (foam, {"buy": "closed-cell foam, cut from a pool noodle, in the tail and nose voids", "colour": "#e9e4d3"})
    return parts


def geometry(parts):
    import base64
    import numpy as np
    import trimesh
    out = []
    for name, meta in parts.items():
        mesh = trimesh.load(OUT / f"{name}.stl", force="mesh")
        # The sheet must stay under 16 MB. Smooth parts decimate well. The
        # tray's grid of seven hundred holes does not, and nobody orbits a
        # sheet to count them, so it is drawn as its plain plate.
        if name == "tray":
            lo, hi = mesh.bounds
            mesh = trimesh.creation.box(extents=hi - lo, transform=trimesh.transformations.translation_matrix((lo + hi) / 2))
        elif len(mesh.faces) > 15000:
            mesh = mesh.simplify_quadric_decimation(face_count=15000)
        tris = mesh.vertices[mesh.faces].astype(np.float32).reshape(-1)
        out.append({"name": name, "colour": meta["colour"], "alpha": meta.get("alpha", 1.0),
                    "triangles": int(len(mesh.faces)), "positions": base64.b64encode(tris.tobytes()).decode("ascii")})
    (OUT / "titan.json").write_text(json.dumps(out))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    printed = {"cover": cover(), "chassis": chassis(), "bezel": bezel(), "pods": pods(), "tray": tray()}
    for name, part in printed.items():
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"))
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
