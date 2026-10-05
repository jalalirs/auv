"""A numerical tow tank: a hull held in a current, and the force the water puts on it.

    # on a machine with the hull's mesh (trimesh): the hull as cells, flow along +x
    hardware/.venv/bin/python hardware/tow_tank.py voxels <hull.usd> <out.npz> --axis surge --cells 96
    # on a GPU, with Warp (the runtime image has it): the drag
    python tow_tank.py run <hull.npz | sphere:48 | cube:32> --re 50000

Nobody has towed mini-hoot. What can be done instead is solve the water round
it, which is a lattice-Boltzmann solver here: D3Q19, a Smagorinsky large-eddy
model for the turbulence the grid cannot resolve (Hou, Sterling, Chen & Doolen
1996), the hull as cells the water bounces off half way between, and the force
on it as the momentum the water hands it at each of those bounces (Ladd 1994),
BGK collision. A regularised collision (Latt & Chopard 2006) is there too; it
is stabler and put a sphere 30 % over its measured drag, so it is not the default.
The tank is periodic across, the water comes in at a set speed upstream and
leaves downstream, and the hull is a few per cent of the cross-section so the
walls do not crowd it.

It is worth exactly as much as it reproduces. So it is run first on shapes
whose drag was measured — a cube face-on (Hoerner: 1.05) and a sphere
(Hoerner, Achenbach: 0.47 subcritical) — and on the BlueROV2 Heavy, against
the drag Li et al. (2020) measured on load cells; only then on a hull nobody
has measured.

Forces come back as a drag coefficient on the hull's own frontal area, which
is what carries over from the lattice to the sea at the same Reynolds number
(and, past separation at sharp edges, at others).
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np

# D3Q19: rest, the six faces, the twelve edges.
C = np.array([[0, 0, 0],
              [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1],
              [1, 1, 0], [-1, -1, 0], [1, -1, 0], [-1, 1, 0],
              [1, 0, 1], [-1, 0, -1], [1, 0, -1], [-1, 0, 1],
              [0, 1, 1], [0, -1, -1], [0, 1, -1], [0, -1, 1]], dtype=np.int32)
W = np.array([1 / 3] + [1 / 18] * 6 + [1 / 36] * 12, dtype=np.float32)
OPP = np.array([0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17], dtype=np.int32)

AXES = {"surge": 0, "sway": 1, "heave": 2}
# How much the tank's crowding raises a drag coefficient, per unit of blockage
# and of the coefficient itself (Maskell's form, Cd_u = Cd (1 + theta Cd s)).
# Not Maskell's 2.5, which is for a closed wind tunnel: this tank is periodic
# across, and the same cube towed at 4.0 % and 1.5 % blockage (1.235, 1.203)
# gives theta 0.9 for it.
MASKELL = 0.9


# ── the hull as cells ────────────────────────────────────────────────────────

def voxels(hull: str, out: str, axis: str, cells: int) -> None:
    """The hull turned so the water meets it along +x, as solid cells."""
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import hull_coefficients
    import trimesh
    from scipy import ndimage

    vertices, faces = hull_coefficients.load(hull)
    k = AXES[axis]
    order = [k] + [a for a in range(3) if a != k]
    vertices = vertices[:, order]
    length = float(np.max(vertices.max(0) - vertices.min(0)))
    pitch = length / cells
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    grid = mesh.voxelized(pitch).matrix
    # Solid inside each closed part; an open frame's gaps stay water, because
    # only what is enclosed on every side is filled.
    solid = ndimage.binary_fill_holes(grid)
    np.savez_compressed(out, solid=solid, pitchM=pitch, axis=axis, hull=str(hull))
    frontal = int(solid.any(axis=0).sum())
    print(f"{hull}: {solid.shape} cells of {pitch * 1000:.1f} mm along {axis}; "
          f"{int(solid.sum()):,} solid, frontal {frontal:,} cells ({frontal * pitch * pitch:.4f} m²)")


def shape(said: str) -> tuple[np.ndarray, float]:
    """A test body: sphere:<diameter> or cube:<side>, in cells."""
    kind, size = said.split(":")
    n = int(size)
    if kind == "cube":
        return np.ones((n, n, n), dtype=bool), 1.0
    r = n / 2.0
    g = np.indices((n, n, n)).astype(float) + 0.5 - r
    return (g ** 2).sum(0) <= r * r, 1.0


# ── the water ────────────────────────────────────────────────────────────────

def run(body: str, re: float, u: float, blockage: float, flows: float, measure: float, smag: float,
        regularised: bool = False, down: float = 4.0) -> dict:
    sys.path.insert(0, "/w")
    try:
        import warp as wp
    except ImportError:
        import glob
        sys.path[:0] = glob.glob("/isaac-sim/extscache/omni.warp.core*")
        import warp as wp
    wp.init()

    if ":" in body and not body.endswith(".npz"):
        solid, pitch = shape(body)
        about = {"body": body}
    else:
        saved = np.load(body)
        solid, pitch = saved["solid"], float(saved["pitchM"])
        about = {"body": str(saved["hull"]), "axis": str(saved["axis"]), "pitchM": pitch}
    bx, by, bz = solid.shape
    frontal = int(solid.any(axis=0).sum())
    length = float(max(bx, by, bz))
    # The tank: a few hull lengths each way, and wide enough that the hull is
    # `blockage` of its cross-section.
    side = int(math.ceil(math.sqrt(frontal / blockage)))
    side = max(side, max(by, bz) + 16)
    ny = nz = side + (side % 2)
    up, behind = int(1.5 * length), int(down * length)
    nx = up + bx + behind
    mask = np.zeros((nx, ny, nz), dtype=np.int32)
    y0, z0 = (ny - by) // 2, (nz - bz) // 2
    mask[up:up + bx, y0:y0 + by, z0:z0 + bz] = solid
    reference = length
    nu = u * reference / re
    tau0 = 0.5 + 3.0 * nu
    print(f"tank {nx}×{ny}×{nz} = {nx * ny * nz / 1e6:.1f} M cells; body {bx}×{by}×{bz}, frontal {frontal} cells "
          f"({frontal / (ny * nz):.1%} of the section); Re {re:.0f}, u {u}, tau {tau0:.6f}", flush=True)

    c = wp.array(C, dtype=wp.int32)
    w = wp.array(W, dtype=wp.float32)
    opp = wp.array(OPP, dtype=wp.int32)
    solid_d = wp.array(mask, dtype=wp.int32)
    feq0 = np.zeros((19, nx, ny, nz), dtype=np.float32)
    for q in range(19):
        cu = 3.0 * C[q, 0] * u
        feq0[q] = W[q] * (1.0 + cu + 0.5 * cu * cu - 1.5 * u * u)
    f_a = wp.array(feq0, dtype=wp.float32)
    f_b = wp.zeros_like(f_a)
    # The force, summed into many slots and those summed at the end: one total
    # that every cell beside the hull adds to each step is a queue at one
    # address, and on the Heavy it made the measured flow-through thirty
    # times slower than the rest.
    slots = 4096
    force = wp.zeros(slots, dtype=wp.vec3)
    vec19 = wp.types.vector(length=19, dtype=wp.float32)

    @wp.kernel
    def step(f_in: wp.array4d(dtype=wp.float32), f_out: wp.array4d(dtype=wp.float32),
             solid: wp.array3d(dtype=wp.int32), c: wp.array2d(dtype=wp.int32),
             w: wp.array(dtype=wp.float32), opp: wp.array(dtype=wp.int32),
             nx: int, ny: int, nz: int, u_in: float, tau0: float, smag: float,
             force: wp.array(dtype=wp.vec3), measuring: int, regularised: int, slots: int):
        i, j, k = wp.tid()
        if solid[i, j, k] != 0:
            return
        f = vec19()
        push = wp.vec3(0.0, 0.0, 0.0)
        for q in range(19):
            si = i - c[q, 0]
            sj = (j - c[q, 1] + ny) % ny
            sk = (k - c[q, 2] + nz) % nz
            if si < 0:
                cu = 3.0 * float(c[q, 0]) * u_in
                f[q] = w[q] * (1.0 + cu + 0.5 * cu * cu - 1.5 * u_in * u_in)
            elif si >= nx:
                f[q] = f_in[q, i, j, k]
            elif solid[si, sj, sk] != 0:
                # Bounced back half way: what left this cell towards the hull
                # last step comes back, and the hull took twice its momentum.
                o = opp[q]
                f[q] = f_in[o, i, j, k]
                back = 2.0 * f_in[o, i, j, k]
                push = push + wp.vec3(float(c[o, 0]) * back, float(c[o, 1]) * back, float(c[o, 2]) * back)
            else:
                f[q] = f_in[q, si, sj, sk]
        # Only a cell beside the hull has anything to add; every cell adding
        # its zero to the one total made the measured flow-through four times
        # slower than the rest.
        if measuring != 0 and (push[0] != 0.0 or push[1] != 0.0 or push[2] != 0.0):
            wp.atomic_add(force, (i * 31 + j * 17 + k * 7) % slots, push)
        rho = float(0.0)
        ux = float(0.0)
        uy = float(0.0)
        uz = float(0.0)
        for q in range(19):
            rho += f[q]
            ux += f[q] * float(c[q, 0])
            uy += f[q] * float(c[q, 1])
            uz += f[q] * float(c[q, 2])
        ux /= rho
        uy /= rho
        uz /= rho
        if i == 0:
            rho = 1.0
            ux = u_in
            uy = 0.0
            uz = 0.0
        uu = ux * ux + uy * uy + uz * uz
        # The stress the grid does not resolve, and the eddy viscosity for it.
        pxx = float(0.0)
        pyy = float(0.0)
        pzz = float(0.0)
        pxy = float(0.0)
        pxz = float(0.0)
        pyz = float(0.0)
        feq = vec19()
        for q in range(19):
            cx = float(c[q, 0])
            cy = float(c[q, 1])
            cz = float(c[q, 2])
            cu = 3.0 * (cx * ux + cy * uy + cz * uz)
            feq[q] = w[q] * rho * (1.0 + cu + 0.5 * cu * cu - 1.5 * uu)
            d = f[q] - feq[q]
            pxx += cx * cx * d
            pyy += cy * cy * d
            pzz += cz * cz * d
            pxy += cx * cy * d
            pxz += cx * cz * d
            pyz += cy * cz * d
        pi = wp.sqrt(pxx * pxx + pyy * pyy + pzz * pzz + 2.0 * (pxy * pxy + pxz * pxz + pyz * pyz))
        tau = 0.5 * (tau0 + wp.sqrt(tau0 * tau0 + 18.0 * smag * smag * pi / rho))
        # Regularised (Latt & Chopard 2006): what relaxes is only the part of
        # the populations' departure from equilibrium that is a stress. The
        # rest — ghost moments a BGK step carries along — is what blew up at a
        # thruster duct's lip when the viscosity was this small.
        keep = 1.0 - 1.0 / tau
        for q in range(19):
            if i == 0:
                f_out[q, i, j, k] = feq[q]
            elif regularised == 0:
                f_out[q, i, j, k] = f[q] - (f[q] - feq[q]) / tau
            else:
                cx = float(c[q, 0])
                cy = float(c[q, 1])
                cz = float(c[q, 2])
                stress = ((cx * cx - 1.0 / 3.0) * pxx + (cy * cy - 1.0 / 3.0) * pyy + (cz * cz - 1.0 / 3.0) * pzz
                          + 2.0 * (cx * cy * pxy + cx * cz * pxz + cy * cz * pyz))
                f_out[q, i, j, k] = feq[q] + keep * 4.5 * w[q] * stress

    steps_per_flow = int(nx / u)
    total = int(flows * steps_per_flow)
    measured_from = int(total - measure * steps_per_flow)
    began = time.perf_counter()
    for n in range(total):
        measuring = 1 if n >= measured_from else 0
        wp.launch(step, dim=(nx, ny, nz), inputs=[f_a, f_b, solid_d, c, w, opp, nx, ny, nz, u, tau0, smag,
                                                  force, measuring, 1 if regularised else 0, slots])
        f_a, f_b = f_b, f_a
        if n % 2000 == 0:
            wp.synchronize()
            # A run that has gone unstable says so and stops, rather than
            # spending the rest of its hour averaging NaN.
            probe = f_a[0, nx - 2].numpy()
            if not np.all(np.isfinite(probe)):
                print(json.dumps({**about, "unstable": True, "atStep": n}), flush=True)
                return {"unstable": True}
            if n > 0:
                rate = n * nx * ny * nz / (time.perf_counter() - began) / 1e9
                print(f"  step {n:,} of {total:,} ({rate:.2f} G cell-updates a second)", flush=True)
    wp.synchronize()
    pushed = force.numpy().astype(np.float64).sum(axis=0) / max(1, total - measured_from)
    cd = float(pushed[0]) / (0.5 * u * u * frontal)
    # The tank's neighbours crowd the flow past the hull and raise its drag;
    # taken back out in Maskell's (1963) form, with the tank's own theta.
    share = frontal / (ny * nz)
    corrected = cd / (1.0 + MASKELL * cd * share)
    out = {**about, "cells": [nx, ny, nz], "bodyCells": [bx, by, bz], "frontalCells": frontal,
           "blockage": round(frontal / (ny * nz), 4), "reynolds": re, "latticeSpeed": u, "tau0": tau0,
           "smagorinsky": smag, "collision": "regularised" if regularised else "BGK", "flowThroughs": flows, "measuredOver": measure,
           "dragCoefficient": round(cd, 4),
           "dragCoefficientCorrected": round(corrected, 4),
           "correctedBy": f"Maskell's form, theta {MASKELL} (this tank's, from a cube at two blockages), for {share:.1%} of the section",
           "sideCoefficients": [round(float(pushed[1]) / (0.5 * u * u * frontal), 4),
                                round(float(pushed[2]) / (0.5 * u * u * frontal), 4)],
           "seconds": round(time.perf_counter() - began, 1)}
    if "pitchM" in about:
        area = frontal * about["pitchM"] ** 2
        out["frontalM2"] = round(area, 5)
        out["quadraticNPerMs2"] = round(0.5 * 1025.0 * corrected * area, 3)
    print(json.dumps(out), flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="what", required=True)
    v = sub.add_parser("voxels")
    v.add_argument("hull")
    v.add_argument("out")
    v.add_argument("--axis", choices=list(AXES), default="surge")
    v.add_argument("--cells", type=int, default=96)
    r = sub.add_parser("run")
    r.add_argument("body")
    r.add_argument("--re", type=float, default=5e4)
    r.add_argument("--u", type=float, default=0.05)
    r.add_argument("--blockage", type=float, default=0.04)
    r.add_argument("--flows", type=float, default=3.0, help="flow-throughs of the tank to run")
    r.add_argument("--measure", type=float, default=1.0, help="of which, flow-throughs averaged at the end")
    r.add_argument("--smagorinsky", type=float, default=0.17)
    r.add_argument("--down", type=float, default=4.0,
                   help="hull lengths of tank behind it; fewer fits a finer hull in less memory")
    r.add_argument("--regularised", action="store_true",
                   help="Latt & Chopard's collision: stabler, but it put a sphere 30 % over its measured drag")
    a = ap.parse_args()
    if a.what == "voxels":
        voxels(a.hull, a.out, a.axis, a.cells)
    else:
        run(a.body, a.re, a.u, a.blockage, a.flows, a.measure, a.smagorinsky, a.regularised, a.down)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
