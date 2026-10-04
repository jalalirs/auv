"""Seaglider's outside: a buoyancy glider, from its published size.

    hardware/.venv/bin/python hardware/seaglider/shape.py

1.8 m of fairing (the reference length Eriksen's wing model is written
against), wings of about a metre's span set amidships, a small rudder above
and below the tail, and the antenna mast that rises from the tail — the glider
surfaces tail-up to send its data through it. The fairing's shape is a
low-drag body of revolution, widest a third of the way back; its 0.30 m width
and the wing's planform are read off photographs, not published. The pressure
hull is inside the fairing and not drawn. Origin at the centre of gravity, the
fairing centred on it. Writes catalog/vehicles/seaglider/seaglider.usd.
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
from shape_parts import fin, lathe, placed, rod  # noqa: E402

ROOT = HERE.parents[1]
INTO = ROOT / "catalog/vehicles/seaglider"

LENGTH = 1.8                     # published reference length
WIDEST = 0.30                    # read off photographs
SPAN = 1.0                       # tip to tip, read off photographs
FRONT = LENGTH * 0.42            # the fairing sits slightly forward of the centre


def fairing_radius(s):
    """A laminar-flow body: a rounded nose, widest at a third, a long taper."""
    u = s / LENGTH
    if u <= 0.33:
        return 0.5 * WIDEST * math.sqrt(max(0.0, 1.0 - ((0.33 - u) / 0.33) ** 2))
    return 0.5 * WIDEST * (1.0 - ((u - 0.33) / 0.67) ** 1.6) ** 0.9 + 0.012 * ((u - 0.33) / 0.67)


def build() -> Hull:
    hull = Hull("Seaglider", doc="Seaglider, drawn by hardware/seaglider/shape.py from its published size. "
                                 "Origin at the centre of gravity, x forward, metres.")
    hull.look("Fairing", "#e8b200", 0.3, clearcoat=1.0,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.86, 0.55, 0.0), "reflection_roughness_constant": 0.28}))
    hull.look("Black", "#141416", 0.4,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.011, 0.011, 0.013), "reflection_roughness_constant": 0.4}))
    hull.look("White", "#e9ecef", 0.35,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.8, 0.82, 0.84), "reflection_roughness_constant": 0.35}))

    profile = [(FRONT - s, fairing_radius(s)) for s in np.linspace(0.0, LENGTH, 80)]
    profile[-1] = (profile[-1][0], 0.014)                  # the tail ends in the mast's collar
    hull.add("Fairing", lathe(profile, 72), "Fairing")
    # The wings, amidships just aft of the widest point, a little swept.
    root_x = FRONT - LENGTH * 0.40
    r_at = fairing_radius(LENGTH * 0.40)
    wings = []
    for side in (1, -1):
        w = fin(0.20, 0.11, SPAN / 2 - r_at, 0.012, sweep=0.06)
        placed(w, roll_deg=-90 * side, at=(root_x, side * r_at * 0.9, 0.0))
        wings.append(w)
    hull.add("Wings", trimesh.util.concatenate(wings), "Black")
    # The rudder: a small fin above and below the tail.
    tail_x = FRONT - LENGTH * 0.86
    r_tail = fairing_radius(LENGTH * 0.86)
    rudders = [placed(fin(0.12, 0.07, 0.10, 0.01, sweep=0.04), roll_deg=a, at=(tail_x, 0.0, 0.0)) for a in (0, 180)]
    for f, a in zip(rudders, (0, 180)):
        f.apply_translation([0.0, 0.0, r_tail * math.cos(math.radians(a))])
    hull.add("Rudder", trimesh.util.concatenate(rudders), "Black")
    # The antenna mast, from the tail, rising aft, with the antenna in its tip.
    base = np.array([FRONT - LENGTH + 0.01, 0.0, 0.0])
    up = np.array([-math.cos(math.radians(28)), 0.0, math.sin(math.radians(28))])
    tip = base + up * 0.95
    hull.add("Mast", rod(0.012, base, tip, 24), "Black")
    hull.add("Antenna", rod(0.022, tip, tip + up * 0.16, 24), "White")
    return hull


def main() -> int:
    hull = build()
    every = trimesh.util.concatenate([m for _, m, _ in hull.meshes])
    low, high = every.bounds
    print("across", np.round(high - low, 3), "from", np.round(low, 3), "to", np.round(high, 3))
    INTO.mkdir(parents=True, exist_ok=True)
    out = hull.save(INTO / "seaglider.usd")
    print(f"{out} {out.stat().st_size / 1e6:.2f} MB, {len(every.faces)} faces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
