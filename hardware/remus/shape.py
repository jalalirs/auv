"""REMUS 100's outside, from Prestero's published hull.

    hardware/.venv/bin/python hardware/remus/shape.py

The hull is the Myring profile Prestero (2001) gives for REMUS 100: a nose
19.1 cm long with exponent 2, a 65.4 cm parallel body, and a 54.1 cm tail
closing at 25°, 19.1 cm across; it is cut where the propeller sits, which is
why it measures 1.33 m and not the profile's 1.386. Four fins at 0.638 m aft of
the centre of buoyancy, at his area. The origin is his: the centre of buoyancy,
0.611 m aft of the nose.

The finish is read off Hydroid's photographs, not published: a yellow hull,
black nose and tail cone, black fins and propeller, side-scan windows on the
flanks, a small antenna fairing on the back. Writes catalog/vehicles/remus-100/
remus-100.usd.
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
from shape_parts import box, fin, lathe, placed, rod  # noqa: E402

ROOT = HERE.parents[1]
INTO = ROOT / "catalog/vehicles/remus-100"

# Prestero's Myring parameters, metres and radians.
A, B, C, D, N, THETA = 0.191, 0.654, 0.541, 0.191, 2.0, 0.436
NOSE_X = 0.611                      # the nose, ahead of the centre of buoyancy
LENGTH = 1.33
FIN_X = -0.638                      # the fins' post
FIN_AREA = 6.65e-3                  # m², one fin
PROP_X = -0.67                      # the propeller (dynamics.json)


def radius(s):
    """The Myring radius at `s` metres aft of the nose."""
    if s <= A:
        return 0.5 * D * max(0.0, 1.0 - ((s - A) / A) ** 2) ** (1.0 / N)
    if s <= A + B:
        return 0.5 * D
    t = s - A - B
    return max(0.0, 0.5 * D - (3 * D / (2 * C ** 2) - math.tan(THETA) / C) * t ** 2
               + (D / C ** 3 - math.tan(THETA) / C ** 2) * t ** 3)


def stretch(s0, s1, n):
    """Hull profile points between s0 and s1 aft of the nose, as (x, r)."""
    return [(NOSE_X - s, radius(s)) for s in np.linspace(s0, s1, n)]


def build() -> Hull:
    hull = Hull("Remus100", doc="REMUS 100, drawn by hardware/remus/shape.py from Prestero (2001). "
                                "Origin at the centre of buoyancy, x forward, metres.")
    hull.look("Paint", "#e3a900", 0.3, clearcoat=1.0,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.85, 0.55, 0.0), "reflection_roughness_constant": 0.28}))
    hull.look("Black", "#151517", 0.45,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.012, 0.012, 0.014), "reflection_roughness_constant": 0.45}))
    hull.look("Window", "#2a2d31", 0.2,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.03, 0.033, 0.037), "reflection_roughness_constant": 0.2}))
    hull.look("Steel", "#b8bcc2", 0.25, metal=0.9,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.6, 0.62, 0.65), "metallic_constant": 0.9,
                               "reflection_roughness_constant": 0.25}))

    nose_end, tail_from = 0.12, 0.98          # where the black nose ends, the black tail begins
    hull.add("Nose", lathe(stretch(0.0, nose_end, 24) + [(NOSE_X - nose_end - 1e-4, radius(nose_end))], 64), "Black")
    hull.add("Body", lathe([(NOSE_X - nose_end, radius(nose_end))] + stretch(nose_end + 0.005, tail_from, 40), 64), "Paint")
    hull.add("Tail", lathe(stretch(tail_from, LENGTH, 30), 64), "Black")
    # Three joint bands, where the sections bolt together.
    bands = [lathe([(NOSE_X - s + 0.006, radius(s) + 0.0015), (NOSE_X - s - 0.006, radius(s) + 0.0015)], 64)
             for s in (0.32, 0.62)]
    hull.add("Bands", trimesh.util.concatenate(bands), "Black")
    # The side-scan windows, one each flank.
    windows = [box([0.30, 0.004, 0.035], [NOSE_X - 0.50, side * (0.5 * D - 0.0005), -0.01]) for side in (-1, 1)]
    hull.add("SideScan", trimesh.util.concatenate(windows), "Window")
    # Four fins, cruciform, at Prestero's area: chord 8 cm at the root, taper to 6.
    root, tip = 0.08, 0.06
    span = 2 * FIN_AREA / (root + tip)
    r_at = radius(NOSE_X - FIN_X)
    fins = [placed(fin(root, tip, span, 0.01, sweep=0.012), roll_deg=a,
                   at=(FIN_X + root / 2, 0.0, 0.0)) for a in (0, 90, 180, 270)]
    for f, a in zip(fins, (0, 90, 180, 270)):
        # Out from the hull surface, not from its axis.
        f.apply_translation([0.0, -r_at * math.sin(math.radians(a)), r_at * math.cos(math.radians(a))])
    hull.add("Fins", trimesh.util.concatenate(fins), "Black")
    # The propeller: a hub and three blades, at the package's propeller.
    hub = rod(0.018, [PROP_X - 0.03, 0, 0], [PROP_X + 0.01, 0, 0], 32)
    blades = [placed(fin(0.03, 0.022, 0.05, 0.004), roll_deg=a, yaw_deg=0, at=(PROP_X, 0.0, 0.0))
              for a in (0, 120, 240)]
    for b_, a in zip(blades, (0, 120, 240)):
        b_.apply_translation([0.0, -0.016 * math.sin(math.radians(a)), 0.016 * math.cos(math.radians(a))])
    hull.add("Propeller", trimesh.util.concatenate([hub] + blades), "Black")
    # The antenna fairing on the back, forward of the fins.
    mast = placed(fin(0.07, 0.04, 0.06, 0.016, sweep=0.02), at=(NOSE_X - 0.86, 0.0, 0.5 * D - 0.004))
    hull.add("Antenna", mast, "Paint")
    hull.add("AntennaTip", rod(0.005, [NOSE_X - 0.89, 0, 0.5 * D + 0.05], [NOSE_X - 0.89, 0, 0.5 * D + 0.075], 12), "Steel")
    return hull


def main() -> int:
    hull = build()
    every = trimesh.util.concatenate([m for _, m, _ in hull.meshes])
    low, high = every.bounds
    print("across", np.round(high - low, 3), "from", np.round(low, 3), "to", np.round(high, 3))
    INTO.mkdir(parents=True, exist_ok=True)
    out = hull.save(INTO / "remus-100.usd")
    print(f"{out} {out.stat().st_size / 1e6:.2f} MB, {len(every.faces)} faces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
