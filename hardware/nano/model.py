"""The nano vehicle's printed shell, as code.

    hardware/.venv/bin/python hardware/nano/model.py

Writes to hardware/out/: a STEP and an STL per printed part, an STL of the
bought parts for reference, and a PNG of the whole thing to look at.

The construction: a Titan-shaped skin, hollow and flooded, with a bore along
it that the acrylic tube drops into, two bulkheads that clamp the tube, six
thruster ducts with their own walls, split into a top and a bottom half on
the tube's axis so the tube can be lifted out.

Nothing here seals. The tube seals. The shell is shape and structure only,
which is what lets it be printed.
"""

from __future__ import annotations

import pathlib
import sys

from build123d import (Axis, Box, Cylinder, Location, Plane, RectangleRounded, Rot,
                       export_step, export_stl, fillet, loft)

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out"


def hull_form(inset: float = 0.0):
    """The Titan's shape: a loft through rounded sections along x, each
    shrunk by `inset` so the same call makes the outside and the inside."""
    sections = []
    for x, w, h, r in P.SECTIONS:
        sections.append(Plane.YZ.offset(x) * RectangleRounded(w - 2 * inset, h - 2 * inset,
                                                              max(r - inset, 1.0)))
    return loft(sections, ruled=False)


def along_x(diameter: float, length: float, at=(0.0, 0.0, 0.0)):
    """A cylinder whose axis is x, centred at `at`."""
    return Location(at) * Rot(0, 90, 0) * Cylinder(diameter / 2, length)


def along_z(diameter: float, length: float, at=(0.0, 0.0, 0.0)):
    return Location(at) * Cylinder(diameter / 2, length)


def shell():
    outer = hull_form()
    inner = hull_form(P.SKIN)
    body = outer - inner

    # Two bulkheads the tube is clamped between.
    for x in P.BULKHEAD_X:
        body += Location((x, 0, 0)) * Box(P.BULKHEAD, P.BODY_W - P.SKIN, P.BODY_H - P.SKIN)

    # Duct walls, added before the bores are cut so every duct has a wall.
    wall_d = P.DUCT_D + 2 * P.DUCT_WALL
    for _, (x, y, z) in P.VERTICAL:
        body += along_z(wall_d, P.BODY_H, (x, y, z))
    for _, (x, y, z) in P.HORIZONTAL:
        body += along_x(wall_d, P.POD_LENGTH, (x, y, z))

    # The tube's bore, right through, so the front cap is the window and the
    # rear cap's penetrators come out of the stern.
    bore = P.TUBE_OD + P.TUBE_CLEARANCE
    body -= along_x(bore, P.BODY_L + 2, (P.TUBE_X, 0, 0))
    # Front and rear openings are the bore itself; the cap flanges are what
    # sit in them, and CAP_REACH says how far they go.

    # Thruster bores.
    for _, (x, y, z) in P.VERTICAL:
        body -= along_z(P.DUCT_D, P.BODY_H + 2, (x, y, z))
    for _, (x, y, z) in P.HORIZONTAL:
        body -= along_x(P.DUCT_D, P.POD_LENGTH + 2, (x, y, z))

    return body


def halves(body):
    big = 10 * P.BODY_L
    top = body & Location((0, 0, big / 2)) * Box(big, big, big)
    bottom = body & Location((0, 0, -big / 2)) * Box(big, big, big)
    return top, bottom


def bought():
    """The parts we buy, for the picture and for checking clearances."""
    tube = along_x(P.TUBE_OD, P.TUBE_LENGTH, (P.TUBE_X, 0, 0)) \
        - along_x(P.TUBE_ID, P.TUBE_LENGTH + 2, (P.TUBE_X, 0, 0))
    caps = along_x(P.TUBE_OD, P.CAP_REACH, (P.TUBE_X + P.TUBE_LENGTH / 2 + P.CAP_REACH / 2, 0, 0)) \
        + along_x(P.TUBE_OD, P.CAP_REACH, (P.TUBE_X - P.TUBE_LENGTH / 2 - P.CAP_REACH / 2, 0, 0))
    thrusters = None
    for _, at in P.VERTICAL:
        t = along_z(P.DUCT_D - 2, 30, at)
        thrusters = t if thrusters is None else thrusters + t
    for _, at in P.HORIZONTAL:
        thrusters += along_x(P.DUCT_D - 2, 30, at)
    for y in (55.0, -55.0):   # the Titan's two lights, either side of the window
        thrusters += along_x(22.0, 14.0, (P.BODY_L / 2 - 6.0, y, 0.0))
    return tube + caps, thrusters


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    body = shell()
    top, bottom = halves(body)
    for name, part in (("shell-top", top), ("shell-bottom", bottom)):
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"))
        print(f"{name:14s} volume {part.volume / 1000:7.1f} cm³  "
              f"≈ {part.volume / 1000 * 1.01:6.0f} g in PA12")
    hull, thrusters = bought()
    export_stl(hull, str(OUT / "ref-hull.stl"))
    export_stl(thrusters, str(OUT / "ref-thrusters.stl"))
    print(f"body {P.BODY_L:.0f} × {P.BODY_W:.0f} × {P.BODY_H:.0f} mm, "
          f"tube spans x {P.TUBE_X - P.TUBE_LENGTH / 2 - P.CAP_REACH:.0f} "
          f"to {P.TUBE_X + P.TUBE_LENGTH / 2 + P.CAP_REACH:.0f} of ±{P.BODY_L / 2:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
