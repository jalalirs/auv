"""A vehicle's added mass and drag, worked out from its own hull.

    hardware/.venv/bin/python hardware/hull_coefficients.py <hull.usd> [--dynamics dynamics.json]

Every vehicle on the platform flies Fossen's model — rigid body, added mass,
linear and quadratic drag on each axis — and until now the coefficients were
the BlueROV2's, scaled to each vehicle by its volume and frontal area. The
shape of the hull did not enter. This works them out from the hull itself, by
the standard engineering estimates a naval architect uses before a tow tank:

  **Quadratic drag**, each translation: ½ ρ C_D A, A the hull's silhouette
  seen along that axis (holes in an open frame are not area), C_D a bluff
  body's from its length along the flow over its width (Hoerner, Fluid-Dynamic
  Drag, 1965, ch. 3: 1.15 at l/d ½, falling to 0.85 at 2 and back up to 1.0 by
  8 as skin friction grows).
  **Quadratic drag**, each rotation: the same drag on every element of the two
  silhouettes the rotation sweeps, each moving at ω r and pushing back with
  lever r, so ½ ρ C_D ∫ |r|³ dA.
  **Added mass**, every axis: that of the ellipsoid with the hull's extents
  (Lamb 1932; Imlay 1961 for the rotations), scaled by how solid the hull's
  silhouette is — an open frame pushes less water than the box around it.
  **Linear drag** is not derived: it comes from laminar friction and small
  separated flows no silhouette shows. It is left as the package has it.

All of it is a first estimate, and says so ("derived" against "assumed"); a
tow test, CFD or system identification is what replaces it.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

import numpy as np
from scipy import integrate, ndimage

RHO = 1025.0
CELL_M = 0.002

# Hoerner's bluff body: C_D against length along the flow over width.
L_OVER_D = np.array([0.0, 0.5, 1.0, 2.0, 4.0, 8.0])
CD_BLUFF = np.array([1.17, 1.15, 0.90, 0.85, 0.87, 1.00])


# ── the hull ─────────────────────────────────────────────────────────────────

def load(path) -> tuple[np.ndarray, np.ndarray]:
    """Every mesh in a USD file, in metres, Z up, in the root's frame."""
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(path))
    scale = UsdGeom.GetStageMetersPerUnit(stage) or 1.0
    y_up = UsdGeom.GetStageUpAxis(stage) == "Y"
    cache = UsdGeom.XformCache()
    points, faces, base = [], [], 0
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        p = np.asarray(mesh.GetPointsAttr().Get() or [], dtype=float)
        counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get() or [], dtype=int)
        index = np.asarray(mesh.GetFaceVertexIndicesAttr().Get() or [], dtype=int)
        if not len(p) or not len(counts):
            continue
        m = np.asarray(cache.GetLocalToWorldTransform(prim), dtype=float)
        p = np.c_[p, np.ones(len(p))] @ m
        p = p[:, :3] * scale
        # Fans: every polygon as triangles from its first corner.
        starts = np.r_[0, np.cumsum(counts)[:-1]]
        tris = [np.c_[index[starts[counts > k - 1]], index[starts[counts > k - 1] + k - 1],
                      index[starts[counts > k - 1] + k]]
                for k in range(2, counts.max())]
        f = np.vstack([t for t in tris if len(t)])
        points.append(p)
        faces.append(f + base)
        base += len(p)
    v = np.vstack(points)
    if y_up:
        v = v[:, [0, 2, 1]] * np.array([1.0, -1.0, 1.0])
    return v, np.vstack(faces)


def silhouette(v, f, axis: int, cell: float = CELL_M):
    """The hull seen along `axis`: a raster of what is solid, and where its
    cells are (the two other coordinates, metres)."""
    a, b = [k for k in range(3) if k != axis]
    tri = v[f][:, :, [a, b]]
    low = v[:, [a, b]].min(axis=0) - 2 * cell
    n = np.ceil((v[:, [a, b]].max(axis=0) + 2 * cell - low) / cell).astype(int)
    grid = np.zeros(n, dtype=bool)
    # Each triangle splatted by points spread over it, as many as its
    # projected size needs to leave no cell inside it empty.
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    span = np.maximum(np.linalg.norm(e1, axis=1), np.linalg.norm(e2, axis=1))
    steps = np.clip(np.ceil(span / (0.5 * cell)).astype(int), 1, 200)
    for k in np.unique(steps):
        these = np.flatnonzero(steps == k)
        s, t = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = (s + t) <= k
        s, t = s[keep] / k, t[keep] / k
        pts = (tri[these, 0][:, None, :] + s[None, :, None] * e1[these][:, None, :]
               + t[None, :, None] * e2[these][:, None, :]).reshape(-1, 2)
        ij = np.floor((pts - low) / cell).astype(int)
        grid[ij[:, 0], ij[:, 1]] = True
    grid = ndimage.binary_closing(grid, iterations=1)
    centres = [low[0] + (np.arange(n[0]) + 0.5) * cell, low[1] + (np.arange(n[1]) + 0.5) * cell]
    return grid, centres


# ── the estimates ────────────────────────────────────────────────────────────

def bluff_cd(length_m: float, area_m2: float) -> float:
    width = math.sqrt(4.0 * area_m2 / math.pi)
    return float(np.interp(length_m / max(width, 1e-9), L_OVER_D, CD_BLUFF))


def ellipsoid_added_mass(a: float, b: float, c: float, rho: float = RHO) -> np.ndarray:
    """The six diagonal added masses of a solid ellipsoid, semi-axes a, b, c
    along x, y, z (Lamb; the rotations as Imlay 1961 gives them)."""
    def g(p, q, r):
        f = lambda s: 1.0 / ((p * p + s) * math.sqrt((a * a + s) * (b * b + s) * (c * c + s)))
        return a * b * c * integrate.quad(f, 0.0, np.inf, limit=200)[0]

    al, be, ga = g(a, b, c), g(b, a, c), g(c, a, b)
    volume = 4.0 / 3.0 * math.pi * a * b * c
    m = rho * volume
    out = [m * al / (2.0 - al), m * be / (2.0 - be), m * ga / (2.0 - ga)]
    for (p, q, ap, aq) in ((b, c, be, ga), (c, a, ga, al), (a, b, al, be)):
        top = (p * p - q * q) ** 2 * (aq - ap)
        bottom = 2.0 * (p * p - q * q) + (p * p + q * q) * (ap - aq)
        out.append(m / 5.0 * top / bottom if abs(bottom) > 1e-12 else 0.0)
    return np.array(out)


def coefficients(v, f, centre=None, cell: float = CELL_M, rho: float = RHO) -> dict:
    """Added mass and quadratic drag, every axis, from the hull's mesh."""
    centre = (np.asarray(centre, dtype=float) if centre is not None
              else 0.5 * (v.min(axis=0) + v.max(axis=0)))
    extent = v.max(axis=0) - v.min(axis=0)
    seen, areas, cds = {}, [], []
    for axis in range(3):
        grid, (ca, cb) = silhouette(v, f, axis, cell)
        seen[axis] = (grid, ca, cb)
        area = float(grid.sum()) * cell * cell
        cd = bluff_cd(float(extent[axis]), area)
        areas.append(area)
        cds.append(cd)
    quadratic = [0.5 * rho * cd * a for cd, a in zip(cds, areas)]
    # Rotations: the two silhouettes each sweeps, every element at its lever.
    others = {0: (1, 2), 1: (2, 0), 2: (0, 1)}
    for axis in range(3):
        total = 0.0
        for sweeping in others[axis]:
            grid, ca, cb = seen[sweeping]
            plane = [k for k in range(3) if k != sweeping]
            lever_axis = [k for k in range(3) if k not in (axis, sweeping)][0]
            coord = ca if plane[0] == lever_axis else cb
            r = np.abs(coord - centre[lever_axis])
            arm = r[:, None] if plane[0] == lever_axis else r[None, :]
            total += float((grid * arm ** 3).sum()) * cell * cell * cds[sweeping]
        quadratic.append(0.5 * rho * total)
    # Added mass: the ellipsoid of the hull's extents, as solid as its
    # silhouettes are (the mean of the three, against the ellipses they sit in).
    a, b, c = 0.5 * extent
    ellipses = [math.pi * b * c, math.pi * a * c, math.pi * a * b]
    solid = float(np.clip(np.mean([ar / el for ar, el in zip(areas, ellipses)]), 0.0, 1.0))
    added = ellipsoid_added_mass(a, b, c, rho) * solid
    return {"extentM": [round(float(e), 4) for e in extent],
            "silhouetteM2": [round(x, 4) for x in areas],
            "dragCoefficient": [round(x, 3) for x in cds],
            "solidity": round(solid, 3),
            "addedMass": [round(float(x), 3) for x in added],
            "quadraticDamping": [round(float(x), 3) for x in quadratic]}


# Which of these a package takes, and why the rest it does not. Checked
# against the BlueROV2 (docs/results/hull-coefficients-2026-10-03.md): surge
# drag within about 15 % of what Li et al. (2020) measured in a current tank;
# sway and heave about half of their CFD, so a lower bound for an open frame;
# the rotations five to twenty times under both references — not taken.
TAKEN = "translational quadratic drag"


def drag_for(hull, centre=None, rho: float = RHO):
    """What a package takes from its hull: the quadratic drag in surge, sway
    and heave, N/(m/s)^2, and a note saying where it came from. None when the
    hull is not there to read."""
    hull = pathlib.Path(hull)
    if not hull.exists():
        return None
    v, f = load(hull)
    got = coefficients(v, f, centre=centre, rho=rho)
    note = ("Surge, sway and heave derived from the hull (hardware/hull_coefficients.py): its silhouette on each axis, "
            f"{got['silhouetteM2']} m^2, by Hoerner's bluff-body drag coefficients {got['dragCoefficient']}; checked against "
            "the BlueROV2 (docs/results/hull-coefficients-2026-10-03.md). Roll, pitch and yaw are the BlueROV2's scaled "
            "(assumed): estimated from a hull they come out five to twenty times under what was measured.")
    return got["quadraticDamping"][:3], note


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("hull")
    ap.add_argument("--dynamics", help="a package's dynamics.json, to compare with what it carries")
    ap.add_argument("--cell", type=float, default=CELL_M)
    args = ap.parse_args(argv)
    v, f = load(args.hull)
    centre = None
    if args.dynamics:
        doc = json.loads(pathlib.Path(args.dynamics).read_text())
        centre = doc.get("centreOfGravityM")
    got = coefficients(v, f, centre=centre, cell=args.cell)
    print(json.dumps(got, indent=1))
    if args.dynamics:
        names = ["surge", "sway", "heave", "roll", "pitch", "yaw"]
        carried_am = np.abs(doc["addedMass"]["diagonal"])
        carried_q = np.abs(doc["quadraticDamping"]["diagonal"])
        print(f"{'':6} {'added mass':>22} {'quadratic drag':>24}")
        print(f"{'':6} {'carried':>10} {'hull':>10} {'carried':>12} {'hull':>10}")
        for k, n in enumerate(names):
            print(f"{n:6} {carried_am[k]:10.3f} {got['addedMass'][k]:10.3f} {carried_q[k]:12.3f} "
                  f"{got['quadraticDamping'][k]:10.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
