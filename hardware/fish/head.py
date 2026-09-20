"""The fish's head, as code.

    hardware/.venv/bin/python hardware/fish/head.py

Writes to hardware/out/fish/: a STEP and an STL per printed part, an STL per
bought part for the pictures, parts.json saying which is which, and the
geometry the design sheet loads.

The construction: one sealed shell, printed as a single piece, closed at the
nose by an acrylic window and open at the rear. A drive plate closes the
rear on a face O-ring; it carries the motor on its dry side, a lip seal in
its thickness, and the crank on its wet side. Behind it a flooded tail bay
carries the cable guides and takes OpenFish's tail. The electronics ride a
tray that slides in from the rear before the plate goes on.

Nothing printed seals against water on its own: the shell is coated inside
with epoxy after printing, the plate seals on an O-ring, the shaft on a lip
seal, the window on an O-ring, the tether on two glands.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

from build123d import (Axis, Box, Cylinder, Location, Plane, RectangleRounded, Rot,
                       export_step, export_stl, extrude, fillet, loft)

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "fish"
REF = pathlib.Path(__file__).resolve().parents[1] / "reference" / "openfish"
PARTS: dict[str, dict] = {}


# ── primitives ───────────────────────────────────────────────────────────────

def along_x(d: float, length: float, at=(0.0, 0.0, 0.0)):
    return Location(at) * Rot(0, 90, 0) * Cylinder(d / 2, length)


def along_z(d: float, length: float, at=(0.0, 0.0, 0.0)):
    return Location(at) * Cylinder(d / 2, length)


def section(x: float, w: float, h: float, r: float):
    return Plane.YZ.offset(x) * RectangleRounded(w, h, r)


def hull(stations, inset: float = 0.0):
    """A loft through rounded sections along x, each shrunk by `inset`."""
    return loft([section(x, w - 2 * inset, h - 2 * inset, max(r - inset, 1.0))
                 for x, w, h, r in stations], ruled=False)


def slab(x0: float, x1: float, w: float, h: float, r: float, inset: float = 0.0):
    """A rounded-rectangle prism from x0 to x1."""
    return Plane.YZ.offset(x0) * extrude(RectangleRounded(w - 2 * inset, h - 2 * inset, max(r - inset, 1.0)), x1 - x0)


# ── printed parts ────────────────────────────────────────────────────────────

def shell():
    outer = hull(P.STATIONS)
    inner_stations = [(x, w, h, r) for x, w, h, r in P.STATIONS]
    inner_stations[-1] = (P.NOSE_X - P.NOSE_WALL, *P.STATIONS[-1][1:])
    inner = hull(inner_stations, P.SKIN)
    # The cavity runs from a little behind the bulkhead plane (so the loft
    # cuts cleanly through the rear face) to the nose wall.
    inner = inner - Location((-5.0, 0, 0)) * Box(10.0, 200.0, 200.0)
    body = outer - inner
    # The rear collar, outside the skin, with the screw holes.
    collar = slab(0.0, P.COLLAR_T, P.COLLAR_W, P.COLLAR_H, P.COLLAR_R)
    collar -= slab(-1.0, P.COLLAR_T + 1.0, *P.STATIONS[0][1:], P.SKIN)
    body += collar
    for y, z in P.COLLAR_SCREWS:
        body -= along_x(P.COLLAR_SCREW_D, P.COLLAR_T + 2.0, (P.COLLAR_T / 2, y, z))
    # The window: a pocket for the disc and the bore through the nose wall.
    body -= along_x(P.WINDOW_D + 0.4, P.WINDOW_T + 0.2, (P.NOSE_X - P.WINDOW_T / 2 + 0.1, 0, P.WINDOW_Z))
    body -= along_x(P.WINDOW_BORE, P.NOSE_WALL * 3, (P.NOSE_X - P.NOSE_WALL, 0, P.WINDOW_Z))
    for i in range(4):
        a = math.radians(45 + 90 * i)
        body -= along_x(1.6, 8.0, (P.NOSE_X - 3.0, P.BEZEL_SCREWS_R * math.cos(a), P.WINDOW_Z + P.BEZEL_SCREWS_R * math.sin(a)))
    # Two gland bosses on the crown, and their holes.
    for x, y in P.GLANDS:
        top = crown_z(x)
        body += along_z(P.GLAND_BOSS_D, P.GLAND_BOSS_H + 6.0, (x, y, top - 3.0 + (P.GLAND_BOSS_H + 6.0) / 2 - 3.0))
        body -= along_z(P.GLAND_HOLE_D, 40.0, (x, y, top))
    # Tray rails: two ledges along the floor the tray's edges ride on.
    for side in (1.0, -1.0):
        rail = Location(((P.TRAY_X[0] + P.TRAY_X[1]) / 2, side * (P.TRAY_W / 2 + P.RAIL_W / 2 + 0.3), P.TRAY_Z - P.TRAY_T - 1.5)) \
            * Box(P.TRAY_X[1] - P.TRAY_X[0], P.RAIL_W, 3.0)
        body += rail & inner_envelope()
    PARTS["shell"] = {"print": "PETG at Sketchat, then MJF PA12; epoxy-coat the inside", "colour": "#2b6e8f"}
    return body


def inner_envelope():
    """The cavity as a solid, for clipping things that must stay inside it."""
    stations = [(x, w, h, r) for x, w, h, r in P.STATIONS]
    stations[-1] = (P.NOSE_X - P.NOSE_WALL, *P.STATIONS[-1][1:])
    return hull(stations, P.SKIN + 0.2)


def crown_z(x: float) -> float:
    """The shell's top at station x, by linear interpolation between stations."""
    for (x0, _, h0, _), (x1, _, h1, _) in zip(P.STATIONS, P.STATIONS[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return (h0 + t * (h1 - h0)) / 2
    return P.STATIONS[0][2] / 2


def plate():
    part = slab(-P.PLATE_T, 0.0, P.COLLAR_W, P.COLLAR_H, P.COLLAR_R)
    for y, z in P.COLLAR_SCREWS:
        part -= along_x(P.COLLAR_SCREW_D, P.PLATE_T + 2.0, (-P.PLATE_T / 2, y, z))
    # The face O-ring groove on the dry face, a ring around the opening.
    groove_r = P.ORING_MEAN / 2
    ring = along_x(P.ORING_MEAN + P.ORING_SECTION + 0.6, 1.5, (-0.75, 0, 0)) \
        - along_x(P.ORING_MEAN - P.ORING_SECTION - 0.6, 2.0, (-0.75, 0, 0))
    part -= ring
    # The motor face: two M3 holes and a clearance for the gearbox boss.
    for s in (1.0, -1.0):
        part -= along_x(3.2, P.PLATE_T + 2.0, (-P.PLATE_T / 2, s * P.MOTOR_HOLES / 2, P.MOTOR_AXIS_Z))
    part -= along_x(P.MOTOR_BOSS_D + 0.4, 2.0, (-0.5, 0, P.MOTOR_AXIS_Z))
    # The shaft bore, and the lip-seal pocket from the wet side.
    part -= along_x(P.SHAFT_D + 0.6, P.PLATE_T + 2.0, (-P.PLATE_T / 2, 0, P.MOTOR_AXIS_Z))
    part -= along_x(P.SEAL_OD + 0.1, P.SEAL_T + 0.2, (-P.PLATE_T + P.SEAL_T / 2, 0, P.MOTOR_AXIS_Z))
    PARTS["drive-plate"] = {"print": "MJF PA12 or machined Delrin; the seal pocket wants a smooth bore", "colour": "#1e1e1e"}
    return part


def crank():
    x = P.CRANK_X
    part = along_x(P.CRANK_D, P.CRANK_T, (x, 0, P.MOTOR_AXIS_Z))
    part -= along_x(P.SHAFT_D + 0.1, P.CRANK_T + 2.0, (x, 0, P.MOTOR_AXIS_Z))
    # The D: a flat left in the bore.
    part += Location((x, 0, P.MOTOR_AXIS_Z + P.SHAFT_D / 2 - 0.25)) * Box(P.CRANK_T, P.SHAFT_D, 0.5)
    # A grub screw from the rim to the flat.
    part -= Location((x, 0, P.MOTOR_AXIS_Z + P.CRANK_D / 4 + 1.0)) * Cylinder(P.GRUB_M / 2 - 0.2, P.CRANK_D / 2)
    for r in P.CRANK_RADII:
        part -= along_x(2.5, P.CRANK_T + 2.0, (x, r, P.MOTOR_AXIS_Z))
    PARTS["crank"] = {"print": "MJF PA12; tap the pin holes M3", "colour": "#f26a1b"}
    return part


def bay():
    outer = hull(P.BAY_STATIONS)
    inner = hull(P.BAY_STATIONS, P.SKIN)
    part = outer - inner
    # The front flange that bolts to the collar through the plate.
    flange = slab(-P.COLLAR_T - P.PLATE_T, -P.PLATE_T, P.COLLAR_W, P.COLLAR_H, P.COLLAR_R)
    flange -= slab(-P.COLLAR_T - P.PLATE_T - 1.0, -P.PLATE_T + 1.0, *P.BAY_STATIONS[0][1:], P.SKIN)
    part += flange
    for y, z in P.COLLAR_SCREWS:
        part -= along_x(P.COLLAR_SCREW_D, P.COLLAR_T + P.PLATE_T + 2.0, (-(P.COLLAR_T + P.PLATE_T) / 2 - P.PLATE_T / 2, y, z))
    # The cable guide wall, with its two holes on the tail's midline.
    guide = slab(P.GUIDE_X - 2.0, P.GUIDE_X + 2.0, *P.BAY_STATIONS[0][1:], P.SKIN - 0.5)
    guide -= along_x(P.CRANK_D + 6.0, 6.0, (P.GUIDE_X, 0, P.MOTOR_AXIS_Z))  # clear the crank's sweep
    part += guide
    for s in (1.0, -1.0):
        part -= along_x(P.CABLE_HOLE_D, 8.0, (P.GUIDE_X, s * P.CABLE_Y, P.CABLE_Z))
    # Flooding: the bay fills through the rear and two vents high and low.
    for z in (28.0, -28.0):
        part -= along_z(6.0, 20.0, (-20.0, 0, z))
    # The rear face: a ring the first rib bolts to, with OpenFish's two M3.
    rear = slab(-P.BAY_LENGTH, -P.BAY_LENGTH + 4.0, *P.BAY_STATIONS[1][1:])
    rear -= slab(-P.BAY_LENGTH - 1.0, -P.BAY_LENGTH + 5.0, *P.BAY_STATIONS[1][1:], 8.0)
    part += rear
    for s in (1.0, -1.0):
        part -= along_x(2.6, 6.0, (-P.BAY_LENGTH + 2.0, s * P.RIB_SCREWS_Y, P.RIB_SCREWS_Z))
    PARTS["tail-bay"] = {"print": "PETG or MJF PA12; it floods, nothing to seal", "colour": "#3a3f44"}
    return part


def tray():
    x0, x1 = P.TRAY_X
    part = Location(((x0 + x1) / 2, 0, P.TRAY_Z - P.TRAY_T / 2)) * Box(x1 - x0, P.TRAY_W, P.TRAY_T)
    # Clip the tray to the cavity's taper toward the nose.
    part = part & inner_envelope()
    nx = int((x1 - x0) // P.TRAY_GRID)
    ny = int(P.TRAY_W // P.TRAY_GRID)
    for i in range(1, nx):
        for j in range(ny):
            y = -P.TRAY_W / 2 + P.TRAY_GRID / 2 + j * P.TRAY_GRID
            part -= along_z(2.6, P.TRAY_T + 2.0, (x0 + i * P.TRAY_GRID, y, P.TRAY_Z - P.TRAY_T / 2))
    # The camera bracket: a post up from the tray's front edge, an arm
    # forward along the crown of the cavity, and a plate hanging from the
    # arm's end carrying the Module 3's 21 × 12.5 hole pattern.
    cx, cy, cz, cw, ch, ct = P.CAMERA
    px, az = P.CAMERA_POST_X, P.CAMERA_ARM_Z
    post = Location((px, 0, (P.TRAY_Z + az) / 2)) * Box(4.0, 12.0, az - P.TRAY_Z)
    arm = Location(((px + cx - 4.0) / 2, 0, az)) * Box(cx - 4.0 - px + 4.0, 10.0, 4.0)
    plate_x = cx - ct / 2 - 1.0
    hang = Location((plate_x, 0, (az + cz - 13.0) / 2)) * Box(2.0, 30.0, az - (cz - 13.0))
    for sy in (1.0, -1.0):
        for sz in (1.0, -1.0):
            hang -= along_x(2.2, 6.0, (plate_x, sy * 10.5, cz + sz * 6.25))
    hang -= along_x(12.0, 6.0, (plate_x, 0, cz))
    part += (post + arm + hang) & inner_envelope()
    PARTS["tray"] = {"print": "PETG; a grid of M2.5 holes, everything screws or ties down", "colour": "#c9c9c9"}
    return part


def bezel():
    part = along_x(P.BEZEL_OD, P.BEZEL_T, (P.NOSE_X + P.BEZEL_T / 2, 0, P.WINDOW_Z))
    part -= along_x(P.WINDOW_D - 4.0, P.BEZEL_T + 2.0, (P.NOSE_X + P.BEZEL_T / 2, 0, P.WINDOW_Z))
    for i in range(4):
        a = math.radians(45 + 90 * i)
        part -= along_x(2.2, P.BEZEL_T + 2.0, (P.NOSE_X + P.BEZEL_T / 2, P.BEZEL_SCREWS_R * math.cos(a), P.WINDOW_Z + P.BEZEL_SCREWS_R * math.sin(a)))
    PARTS["bezel"] = {"print": "MJF PA12, black", "colour": "#1e1e1e"}
    return part


# ── bought parts, drawn for the picture and the clearances ───────────────────

def bought():
    parts = {}
    motor = along_x(P.MOTOR_D, P.MOTOR_LENGTH, (P.MOTOR_LENGTH / 2, 0, P.MOTOR_AXIS_Z))
    motor += along_x(P.SHAFT_D, P.SHAFT_LENGTH + P.PLATE_T, (-(P.SHAFT_LENGTH + P.PLATE_T) / 2 + 0.01, 0, P.MOTOR_AXIS_Z))
    parts["ref-motor"] = (motor, {"buy": "JGA25-370 12 V 500 rpm, Amazon.sa", "colour": "#8a8f94"})
    seal = along_x(P.SEAL_OD, P.SEAL_T, (-P.PLATE_T + P.SEAL_T / 2, 0, P.MOTOR_AXIS_Z)) \
        - along_x(P.SHAFT_D, P.SEAL_T + 2.0, (-P.PLATE_T + P.SEAL_T / 2, 0, P.MOTOR_AXIS_Z))
    parts["ref-seal"] = (seal, {"buy": "4 × 10 × 4 NBR lip seal, AliExpress", "colour": "#7a2e2e"})
    window = along_x(P.WINDOW_D, P.WINDOW_T, (P.NOSE_X - P.WINDOW_T / 2, 0, P.WINDOW_Z))
    parts["ref-window"] = (window, {"buy": "30 mm × 3 mm cast acrylic disc, SACO or laser-cut", "colour": "#a8d4f0", "alpha": 0.5})
    boards = None
    for name, x, y, z, length, width, height in P.BOARDS:
        b = Location((x + length / 2, y, z + height / 2)) * Box(length, width, height)
        boards = b if boards is None else boards + b
    parts["ref-boards"] = (boards, {"buy": "buck, BNO055, BTS7960, Pi Zero 2 W, as ordered", "colour": "#2e7d32"})
    cx, cy, cz, cw, ch, ct = P.CAMERA
    cam = Location((cx, cy, cz)) * Box(ct, cw, ch)
    cam += along_x(9.0, 6.0, (cx + ct / 2 + 3.0, cy, cz))
    parts["ref-camera"] = (cam, {"buy": "Camera Module 3 Wide", "colour": "#222222"})
    glands = None
    for x, y in P.GLANDS:
        top = crown_z(x) + P.GLAND_BOSS_H
        g = along_z(15.0, 12.0, (x, y, top + 6.0))
        g += along_z(6.0, 30.0, (x, y, top + 27.0))
        glands = g if glands is None else glands + g
    parts["ref-glands"] = (glands, {"buy": "2 × PG7 gland; Cat6 and the power pair", "colour": "#111111"})
    cables = None
    for s in (1.0, -1.0):
        c = along_x(1.0, 120.0, (P.GUIDE_X - 55.0, s * P.CABLE_Y, P.CABLE_Z))
        cables = c if cables is None else cables + c
    parts["ref-cables"] = (cables, {"buy": "0.5 mm 7-strand steel wire, as ordered", "colour": "#f26a1b"})
    # OpenFish's ribs, from their STLs, stood along the tail at a guessed pitch.
    try:
        import trimesh
        from build123d import import_stl
        ribs = None
        pitch = 30.0
        for i, n in enumerate((6, 7, 8, 9)):
            m = trimesh.load(REF / f"Part_{n}.STL", force="mesh")
            lo, hi = m.bounds
            centre = (lo + hi) / 2
            # Their ribs lie in the xy plane, thickness along z; stand them in yz.
            m.apply_translation(-centre)
            m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(90), [0, 1, 0]))
            m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(90), [1, 0, 0]))
            m.apply_translation([-P.BAY_LENGTH - 5.0 - i * pitch, 0, 0])
            tmp = OUT / f"_rib{n}.stl"
            OUT.mkdir(parents=True, exist_ok=True)
            m.export(tmp)
            solid = import_stl(str(tmp))
            ribs = solid if ribs is None else ribs + solid
        parts["ref-ribs"] = (ribs, {"buy": "OpenFish ribs 6-9, printed from their STLs; pitch here is a guess", "colour": "#d9d9d9"})
    except Exception as e:  # the picture is worse without them and no worse than before
        print("ribs not placed:", e)
    return parts


# ── output ───────────────────────────────────────────────────────────────────

def geometry(parts: dict) -> None:
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
                    "triangles": int(len(mesh.faces)),
                    "positions": base64.b64encode(tris.tobytes()).decode("ascii")})
    (OUT / "head.json").write_text(json.dumps(out))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    printed = {"shell": shell(), "drive-plate": plate(), "crank": crank(),
               "tail-bay": bay(), "tray": tray(), "bezel": bezel()}
    for name, part in printed.items():
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"))
        export_stl(part, str(OUT / f"{name}.sheet.stl"), tolerance=0.4, angular_tolerance=0.8)
        PARTS[name]["volume_cm3"] = round(part.volume / 1000, 1)
        PARTS[name]["mass_g"] = round(part.volume / 1000 * 1.27)   # PETG
        bb = part.bounding_box()
        PARTS[name]["bbox_mm"] = [round(v, 1) for v in (bb.size.X, bb.size.Y, bb.size.Z)]
        print(f"{name:12s} {PARTS[name]['volume_cm3']:7.1f} cm³ ≈ {PARTS[name]['mass_g']:4d} g PETG  {PARTS[name]['bbox_mm']}")
    for name, (part, meta) in bought().items():
        export_stl(part, str(OUT / f"{name}.stl"))
        meta["volume_cm3"] = round(part.volume / 1000, 1)
        PARTS[name] = meta
    (OUT / "parts.json").write_text(json.dumps(PARTS, indent=2))
    geometry(PARTS)
    print(f"head: nose to first rib {P.HEAD_LENGTH:.0f} mm, widest {max(s[1] for s in P.STATIONS):.0f} × {max(s[2] for s in P.STATIONS):.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
