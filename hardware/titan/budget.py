"""Mass against buoyancy for the mini ROV.

    hardware/.venv/bin/python hardware/rov/budget.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "titan"
FRESH = 0.998
PETG = 1.27

# (name, mass g, displaced cm³, z of centre, source)
BOUGHT = [
    ("LeMotech box 158 × 89 × 58 with lid", 220.0, P.BOX_L * P.BOX_W * P.BOX_H / 1000, 0.0, "mass estimated from 2.5 mm ABS; displacement is the sealed outside"),
    ("6 × thruster", 6 * P.THRUSTER_MASS_G, 6 * P.THRUSTER_DISPLACED_CM3, -5.0, "class estimate; MEASURE"),
    ("Pi, PCA9685, BNO055, buck, 6 ESC, wiring", 190.0, 0.0, 0.0, "inside"),
    ("camera", 12.0, 0.0, P.WINDOW_Z, "inside"),
    ("window, bezel screws, 2 glands", 40.0, 6.0, 0.0, "estimate"),
    # Six thrusters and 700 g of nylon make this one heavier than the box
    # alone; the steel bars stay out and the rails wait for a lighter build.
    ("trim: wheel weights on the plate", 120.0, 15.0, P.PLATE_Z - P.PLATE_T - 2.0, "5 g strips, as many as the bucket says"),
    ("straps, screws, tether stub", 40.0, 10.0, 0.0, "estimate"),
]
PRINT_Z = {"cover": 18.0, "chassis": -28.0, "bezel": P.WINDOW_Z, "pods": -10.0, "tray": -10.0}


def compute():
    parts = json.loads((OUT / "parts.json").read_text())
    rows = [(f"{k} (printed)", v["volume_cm3"] * PETG, v["volume_cm3"], PRINT_Z[k], "from the model")
            for k, v in parts.items() if "print" in v]
    rows += BOUGHT
    if "ref-foam" in parts:
        v = parts["ref-foam"]["volume_cm3"]
        rows.append(("closed-cell foam, tail and nose", v * P.FOAM_DENSITY * 1000 / 1000, v, 4.0, "volume from the model, 30 g/L"))
    mass = sum(r[1] for r in rows)
    disp = sum(r[2] for r in rows)
    buoy = disp * FRESH
    cg = sum(r[1] * r[3] for r in rows) / mass
    cb = sum(r[2] * r[3] for r in rows) / disp
    return {"rows": rows, "mass_g": mass, "displaced_cm3": disp, "buoyancy_g": buoy, "net_g": buoy - mass,
            "cg_z": cg, "cb_z": cb, "righting_mm": cb - cg,
            "heave_n": 4 * P.THRUSTER_THRUST_N, "surge_n": 2 * P.THRUSTER_THRUST_N, "weight_n": mass / 1000 * 9.81}


def main() -> int:
    b = compute()
    print(f"{'part':44s} {'g':>7s} {'cm³':>7s} {'z':>6s}  source")
    for n, m, v, z, s in b["rows"]:
        print(f"{n:44s} {m:7.0f} {v:7.0f} {z:6.0f}  {s}")
    print("-" * 96)
    print(f"{'total':44s} {b['mass_g']:7.0f} {b['displaced_cm3']:7.0f}")
    print(f"buoyancy {b['buoyancy_g']:.0f} g against {b['mass_g']:.0f} g: {b['net_g']:+.0f} g in fresh water")
    print(f"CG z {b['cg_z']:+.1f}, CB z {b['cb_z']:+.1f}, righting arm {b['righting_mm']:.1f} mm")
    print(f"heave {b['heave_n']:.0f} N, surge {b['surge_n']:.0f} N, weight {b['weight_n']:.1f} N")
    return 0


if __name__ == "__main__":
    sys.exit(main())
