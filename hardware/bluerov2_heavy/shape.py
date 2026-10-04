"""BlueROV2 Heavy's outside: the frame drawn round where its thrusters are.

    hardware/.venv/bin/python hardware/bluerov2_heavy/shape.py

An open frame of two cut side panels and cross members, the 4-inch
electronics tube with its dome and camera up the middle, the 3-inch battery
tube under it, buoyancy blocks on top, four lamps at the front, and eight T200
thrusters: four vectored horizontals and, the heavy kit, four verticals on arms
outboard of the panels. The frame is the standard BlueROV2's published
457 × 254 mm side; every thruster is drawn exactly where the package's
dynamics.json puts it, so the drawing, the propellers the runtime turns and
the physics agree. Origin at the centre of gravity, x forward, metres.
Writes catalog/vehicles/bluerov2-heavy/bluerov2-heavy.usd.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import trimesh

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from hull_usd import Hull  # noqa: E402
from shape_parts import box, ring, rod  # noqa: E402

ROOT = HERE.parents[1]
INTO = ROOT / "catalog/vehicles/bluerov2-heavy"

L, H = 0.457, 0.254               # the frame's published length and height
PANEL_Y, PANEL_T, BAR = 0.150, 0.012, 0.028
DUCT_R, DUCT_LONG = 0.050, 0.060


def flat(mesh):
    """Faces shaded flat: a cut plate, not a tube."""
    mesh.unmerge_vertices()
    return mesh


def thrusters() -> list[dict]:
    return json.loads((INTO / "dynamics.json").read_text())["thrusters"]["units"]


def panel(y):
    """A side panel as its outline and ribs: what reads as the cut-out plate."""
    x0, x1, z0, z1 = -L / 2, L / 2, -H / 2, H / 2
    parts = [box([L, PANEL_T, BAR], [0, y, z1 - BAR / 2]),
             box([L, PANEL_T, BAR], [0, y, z0 + BAR / 2]),
             box([BAR, PANEL_T, H], [x1 - BAR / 2, y, 0]),
             box([BAR, PANEL_T, H], [x0 + BAR / 2, y, 0]),
             box([BAR, PANEL_T, H], [0.0, y, 0])]
    return trimesh.util.concatenate(parts)


def t200(unit):
    at, d = np.array(unit["position"], float), np.array(unit["direction"], float)
    shroud = ring(DUCT_R - 0.004, DUCT_R, at - d * DUCT_LONG / 2, at + d * DUCT_LONG / 2, 40)
    motor = rod(0.022, at - d * 0.04, at + d * 0.012, 24)
    return shroud, motor


def build() -> Hull:
    hull = Hull("BlueROV2Heavy", doc="BlueROV2 Heavy, drawn by hardware/bluerov2_heavy/shape.py round its "
                                     "package's thrusters. Origin at the centre of gravity, x forward, metres.")
    hull.look("Frame", "#16171a", 0.55,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.013, 0.014, 0.016), "reflection_roughness_constant": 0.55}))
    hull.look("Foam", "#1f2a3a", 0.8,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.02, 0.03, 0.05), "reflection_roughness_constant": 0.8}))
    hull.look("Acrylic", "#dfe9ee", 0.03, opacity=0.18,
              rtx=("OmniGlass", {"glass_color": (0.96, 0.98, 1.0), "glass_ior": 1.49, "thin_walled": True}))
    hull.look("Aluminium", "#a9adb3", 0.3, metal=0.9,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.55, 0.57, 0.6), "metallic_constant": 0.9,
                               "reflection_roughness_constant": 0.3}))
    hull.look("Board", "#1d5c3a", 0.5,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.03, 0.15, 0.07), "reflection_roughness_constant": 0.5}))
    hull.look("Thruster", "#202226", 0.35,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.02, 0.021, 0.024), "reflection_roughness_constant": 0.35}))
    hull.look("LampFace", "#f4f1e6", 0.1, emissive="0.9, 0.88, 0.8",
              rtx=("OmniPBR", {"diffuse_color_constant": (0.9, 0.88, 0.8), "reflection_roughness_constant": 0.1}))

    # The frame: two side panels and the cross members between them.
    hull.add("Panels", flat(trimesh.util.concatenate([panel(PANEL_Y), panel(-PANEL_Y)])), "Frame")
    cross = [box([BAR, 2 * PANEL_Y, BAR * 0.8], [x, 0, z]) for x in (L / 2 - 0.05, -L / 2 + 0.05)
             for z in (H / 2 - BAR / 2, -H / 2 + BAR / 2)]
    hull.add("CrossMembers", flat(trimesh.util.concatenate(cross)), "Frame")
    # The electronics tube, its end caps, the dome and the camera behind it.
    ez, er = 0.012, 0.057
    hull.add("Enclosure", rod(er, [-0.16, 0, ez], [0.13, 0, ez], 64), "Acrylic")
    hull.add("Electronics", flat(box([0.22, 0.07, 0.012], [-0.02, 0, ez])), "Board")
    hull.add("EndCaps", trimesh.util.concatenate([
        rod(er + 0.006, [-0.19, 0, ez], [-0.16, 0, ez], 64),
        rod(er + 0.006, [0.13, 0, ez], [0.15, 0, ez], 64)]), "Aluminium")
    dome = trimesh.creation.uv_sphere(radius=er, count=[40, 40])
    dome.apply_translation([0.15, 0, ez])
    hull.add("Dome", dome.slice_plane([0.15, 0, 0], [1, 0, 0]), "Acrylic")
    hull.add("Camera", rod(0.02, [0.14, 0, ez], [0.175, 0, ez], 32), "Thruster")
    # The battery tube under it.
    hull.add("Battery", rod(0.044, [-0.14, 0, -0.075], [0.11, 0, -0.075], 48), "Aluminium")
    # Buoyancy on top, between the thrusters.
    foam = [box([0.20, 0.085, 0.045], [0.0, side * 0.075, H / 2 - 0.0225]) for side in (1, -1)]
    hull.add("Foam", flat(trimesh.util.concatenate(foam)), "Foam")
    # The eight thrusters, where the package says, and the verticals' arms.
    shrouds, motors = zip(*(t200(u) for u in thrusters()))
    hull.add("Ducts", trimesh.util.concatenate(shrouds), "Thruster")
    hull.add("Motors", trimesh.util.concatenate(motors), "Thruster")
    arms = []
    for u in thrusters():
        x, y, z = u["position"]
        if abs(u["direction"][2]) > 0.9:          # a vertical: out on an arm from its panel
            arms.append(box([0.03, abs(y) - PANEL_Y + 0.006, 0.012], [x, np.sign(y) * (PANEL_Y + abs(y)) / 2, z]))
    hull.add("Arms", flat(trimesh.util.concatenate(arms)), "Frame")
    # Four lamps at the front, two each side of the dome.
    lamps, faces = [], []
    for y in (0.095, -0.095):
        for z in (0.03, -0.05):
            lamps.append(rod(0.016, [L / 2 - 0.05, y, z], [L / 2 - 0.005, y, z], 24))
            faces.append(rod(0.013, [L / 2 - 0.005, y, z], [L / 2 - 0.002, y, z], 24))
    hull.add("Lamps", trimesh.util.concatenate(lamps), "Aluminium")
    hull.add("LampFaces", trimesh.util.concatenate(faces), "LampFace")
    return hull


def main() -> int:
    hull = build()
    every = trimesh.util.concatenate([m for _, m, _ in hull.meshes])
    low, high = every.bounds
    print("across", np.round(high - low, 3), "from", np.round(low, 3), "to", np.round(high, 3))
    out = hull.save(INTO / "bluerov2-heavy.usd")
    print(f"{out} {out.stat().st_size / 1e6:.2f} MB, {len(every.faces)} faces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
