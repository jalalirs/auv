"""Mass against buoyancy, from the model and the parts list.

    hardware/.venv/bin/python hardware/nano/budget.py

A vehicle that is not within a few tens of grams of neutral is not a vehicle,
and the place to find that out is here rather than in the tank. Printed
parts get their mass from their volume; bought parts get the mass their
supplier states, or an estimate that says so.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out"
FRESH = 0.998    # g/cm³, the tank
PA12 = 1.01

# (name, mass g, displaced cm³, z of its centre mm, source)
BOUGHT = [
    ("3\" acrylic tube, 150 mm", 290.0, None, 0.0, "estimate from 1.19 g/cm³ × wall volume; BR lists no mass"),
    ("front cap, acrylic", 55.0, None, 0.0, "estimate"),
    ("rear cap, aluminium, 7 × M10 + penetrators", 120.0, None, 0.0, "estimate"),
    ("2 × locking flange with O-rings", 60.0, None, 0.0, "estimate"),
    ("6 × UG500", 6 * P.THRUSTER_MASS_G, 6 * 8.0, -22.0, "supplier; displacement estimated"),
    ("Raspberry Pi Zero 2 W", 11.0, 0.0, 8.0, "supplier; inside the tube"),
    ("3 × 18650 + holder", 3 * 47.0 + 25.0, 0.0, -14.0, "typical cell 47 g; inside, low"),
    ("2 × 4-in-1 ESC", 2 * 8.0, 0.0, 8.0, "typical; inside"),
    ("camera + mount", 12.0, 0.0, 0.0, "inside"),
    ("IMU, depth sensor, leak sensor, wiring", 45.0, 0.0, -5.0, "estimate; inside"),
    ("2 × light", 2 * 20.0, 2 * 7.5, -36.0, "estimate"),
    ("screws, penetrator nuts, tether plug", 40.0, 5.0, -20.0, "estimate"),
    ("2 × steel ballast bar 140 × 12 × 6", 2 * 79.0, 2 * 10.1, -56.0, "7.85 g/cm³; in the rails under the plate"),
]
PRINT_Z = {"cover": 25.0, "chassis": -30.0, "bezel": 0.0}


def compute() -> dict:
    """The rows and the totals, for the terminal and for the sheet alike."""
    parts = json.loads((OUT / "parts.json").read_text())
    rows = []
    for name, meta in parts.items():
        if "print" in meta:
            v = meta["volume_cm3"]
            rows.append((f"{name} (printed)", v * PA12, v, PRINT_Z[name], "from the model"))
    tube_outer = math.pi * (P.TUBE_OD / 20) ** 2 * (P.TUBE_LENGTH + 2 * P.CAP_REACH) / 10
    rows.append(("dry hull displacement", 0.0, tube_outer, 0.0, "tube + caps as a sealed cylinder"))
    rows += BOUGHT
    mass = sum(r[1] for r in rows)
    displaced = sum((r[2] if r[2] is not None else 0.0) for r in rows)
    buoyancy = displaced * FRESH
    cg = sum(r[1] * r[3] for r in rows) / mass
    cb = sum((r[2] or 0.0) * r[3] for r in rows) / displaced
    return {"rows": rows, "mass_g": mass, "displaced_cm3": displaced, "buoyancy_g": buoyancy,
            "net_g": buoyancy - mass, "cg_z": cg, "cb_z": cb, "righting_mm": cb - cg,
            "heave_n": 4 * P.THRUSTER_THRUST_N, "surge_n": 2 * P.THRUSTER_THRUST_N,
            "weight_n": mass / 1000 * 9.81}


def main() -> int:
    b = compute()
    rows, mass, displaced, buoyancy = b["rows"], b["mass_g"], b["displaced_cm3"], b["buoyancy_g"]
    print(f"{'part':46s} {'mass g':>8s} {'displaces cm³':>14s} {'z mm':>6s}   source")
    for name, m, v, z, src in rows:
        print(f"{name:46s} {m:8.0f} {'' if v is None else f'{v:14.0f}':>14s} {z:6.0f}   {src}")
    print("-" * 108)
    print(f"{'total':46s} {mass:8.0f} {displaced:14.0f}")
    print(f"buoyancy in the tank {buoyancy:.0f} g against {mass:.0f} g of mass: "
          f"{buoyancy - mass:+.0f} g  ({'floats' if buoyancy > mass else 'sinks'})")
    cg, cb = b["cg_z"], b["cb_z"]
    print(f"centre of gravity z {cg:+.1f} mm, centre of buoyancy z {cb:+.1f} mm, "
          f"righting arm {cb - cg:.1f} mm  (the catalogue BlueROV2 has 20)")
    heave = 4 * P.THRUSTER_THRUST_N
    surge = 2 * P.THRUSTER_THRUST_N
    print(f"thrust: heave {heave:.1f} N over {mass / 1000 * 9.81:.1f} N of weight, surge {surge:.1f} N")
    print("trim: aim for +20 to +40 g so it rises when switched off; shorten the bars to get there")
    return 0


if __name__ == "__main__":
    sys.exit(main())
