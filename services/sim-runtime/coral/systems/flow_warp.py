"""The water grid's step on the GPU: systems/flow.py's arithmetic as Warp kernels.

The same stable-fluids step — driven towards the jets, carried by itself,
slowed, kept incompressible by the wide-stencil Jacobi projection — written as
Warp kernels, so that it runs on the box's GPU (Isaac Sim carries Warp 1.13 as
an extension) and on a laptop's CPU (warp-lang). flow.py's numpy is the
reference and stays; this is used when Warp is there and says so, and the two
are held to each other by test_flow_warp.py.

The grid's state stays numpy, owned by `Flow`: each step copies it to the
device, steps it, and copies it back. A twentieth of a second of a 256,000-cell
grid is three megabytes each way, which a GPU does not notice, and nothing else
in the engine has to know where the arithmetic was done.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np


def _warp():
    """Warp, wherever it is: installed, or Isaac Sim's own extension."""
    try:
        import warp as wp
        return wp
    except ImportError:
        pass
    for root in (pathlib.Path("/isaac-sim/extscache"),):
        for found in sorted(root.glob("omni.warp.core-*")) if root.exists() else []:
            sys.path.insert(0, str(found))
            try:
                import warp as wp
                return wp
            except ImportError:
                sys.path.remove(str(found))
    return None


wp = _warp()
KERNELS = None


def available() -> bool:
    return wp is not None


def device() -> str:
    if wp is None:
        return "none"
    wp.init()
    return "cuda:0" if wp.get_cuda_device_count() > 0 else "cpu"


def _kernels():
    global KERNELS
    if KERNELS is not None:
        return KERNELS

    @wp.func
    def trilinear(u: wp.array3d(dtype=wp.vec3), g: wp.vec3, nx: int, ny: int, nz: int):
        # The cell clamped as an index, not as a coordinate: n - 1.000001 is
        # n - 1 in single precision, and the corner past it was read off the
        # end of the array (a NaN, now and then).
        x = wp.clamp(g[0], 0.0, float(nx - 1))
        y = wp.clamp(g[1], 0.0, float(ny - 1))
        z = wp.clamp(g[2], 0.0, float(nz - 1))
        i = wp.min(int(wp.floor(x)), nx - 2)
        j = wp.min(int(wp.floor(y)), ny - 2)
        k = wp.min(int(wp.floor(z)), nz - 2)
        fx = x - float(i)
        fy = y - float(j)
        fz = z - float(k)
        out = wp.vec3(0.0, 0.0, 0.0)
        for dx in range(2):
            for dy in range(2):
                for dz in range(2):
                    w = (fx if dx == 1 else 1.0 - fx) * (fy if dy == 1 else 1.0 - fy) * (fz if dz == 1 else 1.0 - fz)
                    out = out + w * u[i + dx, j + dy, k + dz]
        return out

    @wp.kernel
    def pulled(u: wp.array3d(dtype=wp.vec3), jet: wp.array3d(dtype=wp.vec3),
               out: wp.array3d(dtype=wp.vec3), pull: float):
        i, j, k = wp.tid()
        here = u[i, j, k]
        push = jet[i, j, k]
        if wp.length(push) > 1.0e-4:
            here = here + (push - here) * pull
        out[i, j, k] = here

    @wp.kernel
    def carried(u: wp.array3d(dtype=wp.vec3), out: wp.array3d(dtype=wp.vec3), dt: float, cell: float, keep: float):
        i, j, k = wp.tid()
        back = wp.vec3(float(i), float(j), float(k)) - u[i, j, k] * (dt / cell)
        out[i, j, k] = trilinear(u, back, u.shape[0], u.shape[1], u.shape[2]) * keep

    @wp.kernel
    def walled(u: wp.array3d(dtype=wp.vec3), solid: wp.array3d(dtype=wp.int32)):
        i, j, k = wp.tid()
        if solid[i, j, k] != 0:
            u[i, j, k] = wp.vec3(0.0, 0.0, 0.0)

    @wp.kernel
    def divergence(u: wp.array3d(dtype=wp.vec3), div: wp.array3d(dtype=float), cell: float):
        i, j, k = wp.tid()
        nx = u.shape[0]
        ny = u.shape[1]
        nz = u.shape[2]
        d = float(0.0)
        if i > 0 and i < nx - 1:
            d += u[i + 1, j, k][0] - u[i - 1, j, k][0]
        if j > 0 and j < ny - 1:
            d += u[i, j + 1, k][1] - u[i, j - 1, k][1]
        if k > 0 and k < nz - 1:
            d += u[i, j, k + 1][2] - u[i, j, k - 1][2]
        div[i, j, k] = d * 0.5 / cell

    @wp.kernel
    def jacobi(p: wp.array3d(dtype=float), div: wp.array3d(dtype=float), solid: wp.array3d(dtype=wp.int32),
               out: wp.array3d(dtype=float), cell: float):
        i, j, k = wp.tid()
        nx = p.shape[0]
        ny = p.shape[1]
        nz = p.shape[2]
        q = float(0.0)
        if i >= 2:
            q += p[i - 2, j, k]
        if i < nx - 2:
            q += p[i + 2, j, k]
        if j >= 2:
            q += p[i, j - 2, k]
        if j < ny - 2:
            q += p[i, j + 2, k]
        if k >= 2:
            q += p[i, j, k - 2]
        if k < nz - 2:
            q += p[i, j, k + 2]
        value = (q - div[i, j, k] * 4.0 * cell * cell) / 6.0
        if solid[i, j, k] != 0:
            value = 0.0
        out[i, j, k] = value

    @wp.kernel
    def subtract(u: wp.array3d(dtype=wp.vec3), p: wp.array3d(dtype=float), solid: wp.array3d(dtype=wp.int32),
                 cell: float):
        i, j, k = wp.tid()
        nx = u.shape[0]
        ny = u.shape[1]
        nz = u.shape[2]
        v = u[i, j, k]
        gx = float(0.0)
        gy = float(0.0)
        gz = float(0.0)
        if i > 0 and i < nx - 1:
            gx = (p[i + 1, j, k] - p[i - 1, j, k]) / (2.0 * cell)
        if j > 0 and j < ny - 1:
            gy = (p[i, j + 1, k] - p[i, j - 1, k]) / (2.0 * cell)
        if k > 0 and k < nz - 1:
            gz = (p[i, j, k + 1] - p[i, j, k - 1]) / (2.0 * cell)
        v = wp.vec3(v[0] - gx, v[1] - gy, v[2] - gz)
        if i == 0 or i == nx - 1:
            v = wp.vec3(0.0, v[1], v[2])
        if j == 0 or j == ny - 1:
            v = wp.vec3(v[0], 0.0, v[2])
        if k == 0 or k == nz - 1:
            v = wp.vec3(v[0], v[1], 0.0)
        if solid[i, j, k] != 0:
            v = wp.vec3(0.0, 0.0, 0.0)
        u[i, j, k] = v

    KERNELS = dict(pulled=pulled, carried=carried, walled=walled, divergence=divergence,
                   jacobi=jacobi, subtract=subtract)
    return KERNELS


def step(u: np.ndarray, jets: np.ndarray | None, solid: np.ndarray, pressure, cell: float, dt: float,
         pull: float, decay: float, passes: int, where: str | None = None):
    """flow.py's FlowSystem.step after its early returns: driven, carried,
    slowed, projected. Returns (u, p) as numpy."""
    k = _kernels()
    where = where or device()
    shape = u.shape[:3]
    # Copied, not aliased: on the CPU Warp will wrap a numpy buffer in place, and
    # these are temporaries that Python frees under the kernel (it read as NaN,
    # one run in six).
    dev = lambda a, dtype: wp.array(np.ascontiguousarray(a), dtype=dtype, device=where, copy=True)  # noqa: E731
    U = dev(u.astype(np.float32), wp.vec3)
    S = dev(solid.astype(np.int32), wp.int32)
    A = wp.zeros(shape, dtype=wp.vec3, device=where)
    if jets is not None:
        J = dev(jets.astype(np.float32), wp.vec3)
        wp.launch(k["pulled"], dim=shape, inputs=[U, J, A, float(min(1.0, pull * dt))], device=where)
        U, A = A, U
    wp.launch(k["carried"], dim=shape, inputs=[U, A, float(dt), float(cell), float(1.0 - decay * dt)], device=where)
    U = A
    wp.launch(k["walled"], dim=shape, inputs=[U, S], device=where)
    D = wp.zeros(shape, dtype=float, device=where)
    wp.launch(k["divergence"], dim=shape, inputs=[U, D, float(cell)], device=where)
    P = dev((np.zeros(shape) if pressure is None else pressure).astype(np.float32), float)
    Q = wp.zeros(shape, dtype=float, device=where)
    for _ in range(passes):
        wp.launch(k["jacobi"], dim=shape, inputs=[P, D, S, Q, float(cell)], device=where)
        P, Q = Q, P
    wp.launch(k["subtract"], dim=shape, inputs=[U, P, S, float(cell)], device=where)
    return U.numpy().astype(float), P.numpy().astype(float)
