"""The EdgeTech 2300's outside, at its datasheet's size.

    hardware/.venv/bin/python hardware/towfish/shape.py

205.9 × 81.7 × 50.8 cm, and 76.3 cm tall over the rear fins: published. A
towbody that is wide and flat rather than a torpedo — a rounded shell, yellow
over a grey belly, its nose and tail drawn in; the side-scan transducers along
each lower flank; the sub-bottom array across the belly; the two tail fins that
point it into the flow; and the stainless tow bail on its back, which is where
the cable takes it. Proportions inside the envelope are read off EdgeTech's
photographs and are not published. Origin at the body's centre, x forward,
metres. Writes catalog/vehicles/edgetech-2300/edgetech-2300.usd.
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
from shape_parts import box, fin, loft, placed, rod, rounded_outline  # noqa: E402

ROOT = HERE.parents[1]
INTO = ROOT / "catalog/vehicles/edgetech-2300"

L, W, H = 2.059, 0.817, 0.508          # published
FINS_H = 0.763                         # published, with the rear fins
R = 0.17                               # the shell's corner radius, read off photographs
NOSE, TAIL = 0.30, 0.22                # how much of each end is drawn in


def half(outline, upper):
    """The upper or lower half of a closed (y, z) outline, closed along z = 0."""
    keep = [(y, z) for y, z in outline if (z >= 0) == upper]
    keep.sort(key=lambda p: -p[0] if upper else p[0])
    w = max(abs(y) for y, _ in outline)
    return [(w if upper else -w, 0.0)] + keep + [(-w if upper else w, 0.0)]


def shell(upper):
    """One half of the body: the parallel middle and the drawn-in ends, lofted."""
    def outline_at(scale_w, scale_h):
        return half(rounded_outline(W * scale_w, H * scale_h, R * min(scale_w, scale_h), 10), upper)
    sections = []
    for t in np.linspace(0.0, 1.0, 10):                      # the tail, aft end first
        k = 0.55 + 0.45 * math.sin(t * math.pi / 2)
        sections.append((-L / 2 + t * TAIL, outline_at(k, 0.6 + 0.4 * k)))
    sections.append((L / 2 - NOSE, outline_at(1.0, 1.0)))
    for t in np.linspace(0.0, 1.0, 14)[1:]:                  # the nose
        k = math.sqrt(max(1e-4, 1.0 - t ** 2))
        sections.append((L / 2 - NOSE + t * NOSE, outline_at(0.25 + 0.75 * k, 0.3 + 0.7 * k)))
    n = min(len(o) for _, o in sections)
    return loft([(x, o[:n]) for x, o in sections])


def build() -> Hull:
    hull = Hull("EdgeTech2300", doc="EdgeTech 2300, drawn by hardware/towfish/shape.py at its published size. "
                                    "Origin at the body's centre, x forward, metres.")
    hull.look("Paint", "#e8a600", 0.3, clearcoat=1.0,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.86, 0.5, 0.0), "reflection_roughness_constant": 0.3}))
    hull.look("Belly", "#8d9196", 0.45,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.25, 0.26, 0.28), "reflection_roughness_constant": 0.45}))
    hull.look("Transducer", "#18191b", 0.3,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.014, 0.014, 0.016), "reflection_roughness_constant": 0.3}))
    hull.look("Stainless", "#c4c8cd", 0.22, metal=0.95,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.66, 0.68, 0.7), "metallic_constant": 0.95,
                               "reflection_roughness_constant": 0.22}))

    hull.add("Shell", shell(True), "Paint")
    hull.add("Belly", shell(False), "Belly")
    # The side-scan transducers: long dark strips low on each flank.
    strips = [box([1.15, 0.03, 0.07], [0.05, s * (W / 2 - 0.004), -0.10]) for s in (1, -1)]
    hull.add("SideScan", trimesh.util.concatenate(strips), "Transducer")
    # The sub-bottom array across the belly.
    hull.add("SubBottom", box([0.60, 0.52, 0.025], [0.05, 0.0, -H / 2 + 0.002]), "Transducer")
    # Two tail fins on the back, raising it to its published 76.3 cm.
    fin_h = FINS_H - H
    fins = [placed(fin(0.42, 0.26, fin_h + 0.04, 0.025, sweep=0.12), at=(-L / 2 + 0.52, s * 0.27, H / 2 - 0.04))
            for s in (1, -1)]
    hull.add("Fins", trimesh.util.concatenate(fins), "Paint")
    # The tow bail: a stainless arch on the back, ahead of the middle.
    bx, top = 0.22, H / 2
    bail = [rod(0.016, [bx, s * 0.12, top - 0.01], [bx, s * 0.12, top + 0.20], 20) for s in (1, -1)]
    bail.append(rod(0.016, [bx, -0.12, top + 0.20], [bx, 0.12, top + 0.20], 20))
    bail.append(box([0.12, 0.30, 0.03], [bx, 0.0, top + 0.005]))
    hull.add("TowBail", trimesh.util.concatenate(bail), "Stainless")
    return hull


def main() -> int:
    hull = build()
    every = trimesh.util.concatenate([m for _, m, _ in hull.meshes])
    low, high = every.bounds
    print("across", np.round(high - low, 3), "from", np.round(low, 3), "to", np.round(high, 3))
    (INTO / "edgetech-2300.usda").unlink(missing_ok=True)       # the block drawing it replaces
    out = hull.save(INTO / "edgetech-2300.usd")
    print(f"{out} {out.stat().st_size / 1e6:.2f} MB, {len(every.faces)} faces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
