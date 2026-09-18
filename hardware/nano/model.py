"""The nano vehicle, as code.

    hardware/.venv/bin/python hardware/nano/model.py

Writes to hardware/out/: a STEP and an STL per printed part, an STL per
bought part for the pictures and the clearance checks, parts.json saying
which is which and what colour, and a GLB of the whole thing.

The construction, read off the Titan: an orange capsule over the acrylic
tube, split on the tube's axis so the top lifts off; a black chassis that is
the lower half of the capsule, a base plate, four arms out to the vertical
thruster pods on the wings, and two struts back to the horizontal pods on the
stern corners; a bezel round the window; two lights on the nose.

Nothing printed seals. The tube seals. The prints are shape and structure,
which is what lets them be printed.
"""

from __future__ import annotations

import json
import pathlib
import sys

from build123d import (Axis, Box, Cylinder, Location, RectangleRounded, Rot, SlotOverall,
                       export_step, export_stl, extrude, fillet)

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out"

# What each part is made of and the colour it is drawn in. MJF PA12 comes
# out grey or black; the orange is a dye or a coat of paint, and the record
# should say so rather than let a picture promise a colour a printer cannot.
PARTS: dict[str, dict] = {}


def along_x(d: float, length: float, at=(0.0, 0.0, 0.0)):
    return Location(at) * Rot(0, 90, 0) * Cylinder(d / 2, length)


def along_z(d: float, length: float, at=(0.0, 0.0, 0.0)):
    return Location(at) * Cylinder(d / 2, length)


def stadium(length: float, width: float, z0: float, z1: float, x: float = 0.0):
    """A stadium in plan, extruded from z0 to z1."""
    return Location((x, 0, z0)) * extrude(SlotOverall(length, width), z1 - z0)


def rounded(length: float, width: float, r: float, z0: float, z1: float, x: float = 0.0):
    """A rounded rectangle in plan, extruded from z0 to z1."""
    return Location((x, 0, z0)) * extrude(RectangleRounded(length, width, r), z1 - z0)


def capsule_shell(top: bool):
    """Half of the capsule: a stadium shell with a domed crown, above the
    parting line for the cover and below it for the chassis' cradle."""
    h = P.CAPSULE_H / 2
    s = P.CAPSULE_SKIN
    sign = 1.0 if top else -1.0
    outer = rounded(P.CAPSULE_L, P.CAPSULE_W, P.CAPSULE_CORNER_R, 0.0, sign * h, P.CAPSULE_X)
    crown = outer.faces().sort_by(Axis.Z)[-1 if top else 0]
    outer = fillet(crown.edges(), P.CAPSULE_CROWN_R)
    inner = rounded(P.CAPSULE_L - 2 * s, P.CAPSULE_W - 2 * s, P.CAPSULE_CORNER_R - s,
                    -sign * 1.0, sign * (h - s), P.CAPSULE_X)
    crown = inner.faces().sort_by(Axis.Z)[-1 if top else 0]
    inner = fillet(crown.edges(), P.CAPSULE_CROWN_R - s)
    shell = outer - inner
    # The tube's bore, from the stern to just short of the nose, so the
    # capsule touches the tube only at the cradle ribs and the stern is open
    # for the rear cap's penetrators. The nose wall stays, and the window is
    # cut through it.
    bore_end = P.TUBE_FRONT + 1.0
    shell -= along_x(P.TUBE_OD + P.TUBE_CLEARANCE, 400.0, (bore_end - 200.0, 0, 0))
    shell -= along_x(P.WINDOW_D, 40.0, (P.TUBE_FRONT + 10.0, 0, 0))
    return shell, inner


def cradle_ribs(top: bool, inside):
    """Two ribs that hold the tube on its diameter, one each side of centre,
    clipped to the inside of the capsule so they never show through the crown."""
    sign = 1.0 if top else -1.0
    ribs = None
    for x in (P.TUBE_X - 45.0, P.TUBE_X + 45.0):
        rib = Location((x, 0, sign * P.CAPSULE_H / 4)) * Box(6.0, P.CAPSULE_W, P.CAPSULE_H / 2)
        rib -= along_x(P.TUBE_OD + P.TUBE_CLEARANCE, 10, (x, 0, 0))
        ribs = rib if ribs is None else ribs + rib
    return ribs & inside


def bosses(top: bool):
    sign = 1.0 if top else -1.0
    out = None
    for x, y in P.BOSSES:
        boss = along_z(P.BOSS_D, P.BOSS_H, (x, y, sign * P.BOSS_H / 2))
        boss -= along_z(P.SCREW_D, P.BOSS_H + 2, (x, y, sign * P.BOSS_H / 2))
        out = boss if out is None else out + boss
    return out


def pod(at, vertical: bool):
    """A duct ring with a spoked hub for the motor at one end."""
    x, y, z = at
    if vertical:
        ring = along_z(P.POD_OD, P.POD_LENGTH, at) - along_z(P.DUCT_D, P.POD_LENGTH + 2, at)
        hub_z = z + P.POD_LENGTH / 2 - P.HUB_T / 2
        hub = along_z(P.HUB_D, P.HUB_T, (x, y, hub_z))
        for i in range(P.SPOKES):
            hub += Location((x, y, hub_z)) * Rot(0, 0, 120 * i) * Location((P.DUCT_D / 4, 0, 0)) \
                * Box(P.DUCT_D / 2 + 1, P.SPOKE_W, P.HUB_T)
        # Slots for the motor screws: any pattern 12–19 mm across.
        for i in range(4):
            hub -= Location((x, y, hub_z)) * Rot(0, 0, 90 * i) * Location((7.75, 0, 0)) \
                * Box(3.5, 2.6, P.HUB_T + 2)
        return ring + hub
    ring = along_x(P.POD_OD, P.POD_LENGTH, at) - along_x(P.DUCT_D, P.POD_LENGTH + 2, at)
    hub_x = x + P.POD_LENGTH / 2 - P.HUB_T / 2
    hub = along_x(P.HUB_D, P.HUB_T, (hub_x, y, z))
    for i in range(P.SPOKES):
        hub += Location((hub_x, y, z)) * Rot(120 * i, 0, 0) * Location((0, P.DUCT_D / 4, 0)) \
            * Box(P.HUB_T, P.DUCT_D / 2 + 1, P.SPOKE_W)
    for i in range(4):
        hub -= Location((hub_x, y, z)) * Rot(90 * i, 0, 0) * Location((0, 7.75, 0)) \
            * Box(P.HUB_T + 2, 3.5, 2.6)
    return ring + hub


def cover():
    shell, inside = capsule_shell(top=True)
    part = shell + cradle_ribs(top=True, inside=inside) + bosses(top=True)
    # Vents along the crown.
    for x in P.VENTS_X:
        part -= along_z(P.VENT_D, 30.0, (x, 0, P.CAPSULE_H / 2))
    # The tether eye: a lug on the crown with a hole across it.
    ex, ey = P.TETHER_EYE
    lug = Location((ex, ey, P.CAPSULE_H / 2 + 3.0)) * Box(16.0, 6.0, 12.0)
    lug = fillet(lug.edges().filter_by(Axis.Y), 2.5)
    lug -= Location((ex, ey, P.CAPSULE_H / 2 + 5.0)) * Rot(90, 0, 0) * Cylinder(3.0, 10.0)
    part += lug
    PARTS["cover"] = {"print": "MJF PA12, dyed or painted orange", "colour": "#f26a1b"}
    return part


def chassis():
    shell, inside = capsule_shell(top=False)
    part = shell + cradle_ribs(top=False, inside=inside) + bosses(top=False)
    # The base plate.
    z0, z1 = P.PLATE_Z
    plate = stadium(P.PLATE_L, P.PLATE_W, z0, z1, P.PLATE_X)
    # Lightened: a big window under the tube, leaving a rim and a spine.
    plate -= stadium(P.PLATE_L - 60, P.PLATE_W - 50, z0 - 1, z1 + 1, P.PLATE_X)
    plate += Location((P.PLATE_X, 0, (z0 + z1) / 2)) * Box(P.PLATE_L - 40, 16.0, z1 - z0)
    part += plate
    # Arms to the vertical pods, and the pods.
    for _, (x, y, z) in P.VERTICAL:
        reach = abs(y) - P.PLATE_W / 2 + 12.0
        arm = Location((x, (abs(y) - reach / 2 + 2.0) * (1 if y > 0 else -1), (z0 + z1) / 2)) \
            * Box(P.ARM_W, reach + 4.0, z1 - z0)
        part += arm
        part += pod((x, y, z), vertical=True)
    # Struts to the horizontal pods, and the pods.
    for _, (x, y, z) in P.HORIZONTAL:
        strut = Location((x + P.POD_LENGTH / 2 - 8.0, y * 0.72, (z0 + z1) / 2 + 3.0)) \
            * Box(28.0, abs(y) * 0.5, (z1 - z0) + 6.0)
        part += strut
        part += pod((x, y, z), vertical=False)
    # Ballast rails under the plate: a channel each side, open at the stern,
    # that a steel bar slides into and a screw through the plate retains.
    bl, bw, bh = P.BALLAST_BAR
    for y in (P.BALLAST_Y, -P.BALLAST_Y):
        rail = Location((P.BALLAST_X, y, z0 - bh / 2 - 1.0)) * Box(bl + 6.0, bw + 6.0, bh + 2.0)
        rail -= Location((P.BALLAST_X - 3.0, y, z0 - bh / 2 - 1.0)) * Box(bl + 6.0, bw + 0.4, bh + 0.4)
        part += rail
    # Light brackets.
    for x, y, z in P.LIGHTS:
        part += Location((x - 4.0, y, (z1 + z) / 2)) * Box(16.0, 14.0, z - z1 + 2.0)
    # The bores, cut last so nothing bridges a duct.
    for _, at in P.VERTICAL:
        part -= along_z(P.DUCT_D, P.POD_LENGTH + 2, at) - hub_keep(at, True)
    for _, at in P.HORIZONTAL:
        part -= along_x(P.DUCT_D, P.POD_LENGTH + 2, at) - hub_keep(at, False)
    PARTS["chassis"] = {"print": "MJF PA12, black", "colour": "#1e1e1e"}
    return part


def hub_keep(at, vertical: bool):
    """The slab at the hub's end of a duct that the bore must not remove."""
    x, y, z = at
    if vertical:
        return along_z(P.DUCT_D + 2, P.HUB_T + 0.01, (x, y, z + P.POD_LENGTH / 2 - P.HUB_T / 2))
    return along_x(P.DUCT_D + 2, P.HUB_T + 0.01, (x + P.POD_LENGTH / 2 - P.HUB_T / 2, y, z))


def bezel():
    nose = P.CAPSULE_X + P.CAPSULE_L / 2
    part = along_x(P.BEZEL_OD, P.BEZEL_T, (nose + P.BEZEL_T / 2, 0, 0)) \
        - along_x(P.WINDOW_D - 8.0, P.BEZEL_T + 2, (nose + P.BEZEL_T / 2, 0, 0))
    PARTS["bezel"] = {"print": "MJF PA12, black", "colour": "#1e1e1e"}
    return part


def bought():
    """The parts we buy, for the pictures and the clearance checks."""
    parts = {}
    tube = along_x(P.TUBE_OD, P.TUBE_LENGTH, (P.TUBE_X, 0, 0)) \
        - along_x(P.TUBE_ID, P.TUBE_LENGTH + 2, (P.TUBE_X, 0, 0))
    parts["ref-tube"] = (tube, {"buy": "Blue Robotics 3\" locking tube, 150 mm", "colour": "#a8d4f0", "alpha": 0.45})
    front = along_x(P.TUBE_OD, P.CAP_REACH, (P.TUBE_FRONT - P.CAP_REACH / 2, 0, 0))
    parts["ref-front-cap"] = (front, {"buy": "3\" acrylic end cap, blank", "colour": "#cfe8f7", "alpha": 0.5})
    rear = along_x(P.TUBE_OD, P.CAP_REACH, (P.TUBE_REAR + P.CAP_REACH / 2, 0, 0))
    for i in range(6):
        import math
        a = math.radians(60 * i)
        rear += along_x(10.0, 12.0, (P.TUBE_REAR - 6.0, 26.0 * math.cos(a), 26.0 * math.sin(a)))
    rear += along_x(10.0, 12.0, (P.TUBE_REAR - 6.0, 0, 0))
    parts["ref-rear-cap"] = (rear, {"buy": "3\" aluminium end cap, 7 × M10", "colour": "#9a9a9a"})
    thrusters = None
    for _, (x, y, z) in P.VERTICAL:
        top = z + P.POD_LENGTH / 2 - P.HUB_T
        motor = along_z(P.THRUSTER_MOTOR_D, 30.0, (x, y, top - 15.0))
        prop = along_z(P.THRUSTER_PROP_D, 8.0, (x, y, top - 36.0))
        thrusters = motor + prop if thrusters is None else thrusters + motor + prop
    for _, (x, y, z) in P.HORIZONTAL:
        end = x + P.POD_LENGTH / 2 - P.HUB_T
        thrusters += along_x(P.THRUSTER_MOTOR_D, 30.0, (end - 15.0, y, z))
        thrusters += along_x(P.THRUSTER_PROP_D, 8.0, (end - 36.0, y, z))
    parts["ref-thrusters"] = (thrusters, {"buy": "6 × ApisQueen UG500", "colour": "#3a3a3a"})
    lights = None
    for x, y, z in P.LIGHTS:
        light = along_x(P.LIGHT_D, P.LIGHT_L, (x, y, z))
        lights = light if lights is None else lights + light
    parts["ref-lights"] = (lights, {"buy": "2 × small LED light in a 20 mm can", "colour": "#e8e8e8"})
    # Inside the tube: a camera, a computer, a battery, the ESCs. Drawn so the
    # fit is a picture and not a promise.
    camera = along_x(24.0, 20.0, (P.TUBE_FRONT - P.CAP_REACH - 10.0, 0, 0))
    parts["ref-camera"] = (camera, {"buy": "Raspberry Pi camera in a 24 mm mount", "colour": "#222222"})
    pi = Location((P.TUBE_X + 15.0, 0, 8.0)) * Box(65.0, 30.0, 6.0)
    parts["ref-computer"] = (pi, {"buy": "Raspberry Pi Zero 2 W", "colour": "#2e7d32"})
    battery = Location((P.TUBE_X + 10.0, 0, -14.0)) * Box(66.0, 56.0, 19.0)
    parts["ref-battery"] = (battery, {"buy": "3 × 18650 in a holder, 3S", "colour": "#1565c0"})
    escs = Location((P.TUBE_X - 40.0, 0, 8.0)) * Box(32.0, 32.0, 8.0)
    parts["ref-escs"] = (escs, {"buy": "2 × 4-in-1 20 A drone ESC, stacked", "colour": "#6d4c41"})
    return parts


def glb() -> None:
    """One coloured GLB of everything, for a viewer that is not a plot."""
    import trimesh

    scene = trimesh.Scene()
    for name, meta in PARTS.items():
        mesh = trimesh.load(OUT / f"{name}.stl", force="mesh")
        rgb = [int(meta["colour"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        alpha = int(255 * meta.get("alpha", 1.0))
        mesh.visual.face_colors = rgb + [alpha]
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    scene.export(OUT / "nano.glb")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    printed = {"cover": cover(), "chassis": chassis(), "bezel": bezel()}
    for name, part in printed.items():
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"))
        PARTS[name]["volume_cm3"] = round(part.volume / 1000, 1)
        PARTS[name]["mass_g"] = round(part.volume / 1000 * 1.01)
        bb = part.bounding_box()
        PARTS[name]["bbox_mm"] = [round(v, 1) for v in (bb.size.X, bb.size.Y, bb.size.Z)]
        print(f"{name:10s} {PARTS[name]['volume_cm3']:7.1f} cm³ ≈ {PARTS[name]['mass_g']:4d} g   "
              f"{PARTS[name]['bbox_mm']}")
    for name, (part, meta) in bought().items():
        export_stl(part, str(OUT / f"{name}.stl"))
        meta["volume_cm3"] = round(part.volume / 1000, 1)
        PARTS[name] = meta
    (OUT / "parts.json").write_text(json.dumps(PARTS, indent=2))
    glb()
    print(f"overall {P.OVERALL_L:.0f} × {P.OVERALL_W:.0f} × {P.OVERALL_H:.0f} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
