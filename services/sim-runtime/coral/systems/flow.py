"""The water the vehicle has stirred: a grid that carries the wash on after it.

Reads    the wash's jets (systems/wash.py), the place
Writes   flow: the water's own motion on a grid, which the wash then answers
Every    a twentieth of a second of simulated time

The analytic jet is where a thruster's water goes the moment it leaves the
propeller. What it does not do is linger: stop the thrusters and it is gone,
where in a tank the water the vehicle pushed goes on moving, swirls off the
glass and round the rock, and dies away over seconds. That is this.

A coarse grid over the water — five centimetres a cell in a tank — stepped by
Stam's stable fluids (1999), which is what real-time fluid has been since:

  **Driven** by the jets: each cell a jet passes through is pulled towards
  the jet's velocity there, as a body force, so the grid's water starts
  moving where the thrusters push it.
  **Carried** by itself (semi-Lagrangian advection: each cell takes the
  velocity found where its water came from a step ago), which is what makes a
  wake drift and curl.
  **Kept incompressible** (a pressure projection: the divergence solved away
  by Jacobi iteration), with the glass and the rock as walls water does not
  pass through.
  **Slowed** by the eddies it cannot resolve (a decay of a few per cent a
  second, assumed), so a stirred tank comes to rest in tens of seconds, as a
  real one does.

It is a reduced-order fluid, not a CFD solve, and says so: no turbulence model,
cells coarser than a thruster, numerical diffusion doing the work of
viscosity. It is the coupling it is for — the vehicle's water reaching the
fish, the sand and the cable after the vehicle has gone — and the place a GPU
solver (Warp) slots in when a reef wants a bigger box.

In a tank the grid is the tank's water. In open water it is a box round the
vehicle — three metres by three by two, ten-centimetre cells — that follows it,
shifted a whole cell at a time as the vehicle moves on: what it leaves behind
is let go, and what it moves into starts still. That is the water the vehicle
can have stirred in the last few seconds, which is the water that matters.
"""

from __future__ import annotations

import numpy as np

from engine import System

CELL_M = 0.05
PULL = 6.0            # how fast a cell in a jet takes up the jet's speed, 1/s
DECAY = 0.04          # what the unresolved eddies take, a share a second
JACOBI = 30
WARM = 12             # passes a step, starting from the last step's pressure
ON_WARP_FROM = 50_000  # cells: a grid this big is stepped on Warp when Warp is there


class Flow:
    def __init__(self) -> None:
        self.on = False
        self.low = np.zeros(3)
        self.cell = CELL_M
        self.shape = (0, 0, 0)
        self.u = np.zeros((0, 0, 0, 3))
        self.solid = np.zeros((0, 0, 0), dtype=bool)
        self.p = None
        self.follows = False
        self.from_ = ("derived: stable fluids (Stam 1999) on a grid, driven by the thrusters' jets; "
                      "the decay of unresolved eddies assumed")

    def set_for(self, low, high, bottoms, cell: float = CELL_M, follows: bool = False, circle=None) -> None:
        """A grid over a box of water, with the ground in it solid. `follows`:
        the box goes with the vehicle (open water). `circle`: a round tank's
        glass, (x, y, radius), outside which is solid too."""
        self.circle = None if circle is None else tuple(float(v) for v in circle)
        low, high = np.asarray(low, dtype=float), np.asarray(high, dtype=float)
        self.cell = float(cell)
        n = np.maximum(np.ceil((high - low) / self.cell).astype(int), 2)
        self.low, self.shape = low, tuple(int(k) for k in n)
        self.u = np.zeros(self.shape + (3,))
        self.bottoms, self.follows, self.surface = bottoms, bool(follows), float(high[2])
        self.p = None
        self.ground()
        self.on = True

    def ground(self) -> None:
        """Which cells are rock or sand, or above the water."""
        centres = self.centres()
        floor = self.bottoms(centres.reshape(-1, 3)).reshape(self.shape)
        self.solid = (centres[..., 2] < floor) | (centres[..., 2] > self.surface)
        circle = getattr(self, "circle", None)
        if circle is not None:
            cx, cy, r = circle
            self.solid |= np.hypot(centres[..., 0] - cx, centres[..., 1] - cy) > r

    def follow(self, at) -> None:
        """Keep the vehicle in the middle third of the box, shifting the water
        a whole number of cells: what is left behind is let go, what is moved
        into starts still."""
        middle = self.low + 0.5 * self.cell * np.array(self.shape)
        off = np.asarray(at, dtype=float) - middle
        steps = np.where(np.abs(off) > 0.17 * self.cell * np.array(self.shape),
                         np.round(off / self.cell), 0).astype(int)
        steps[2] = 0                                  # depth: the box spans the column it is in
        if not steps.any():
            return
        u = self.u
        for axis in (0, 1):
            k = int(steps[axis])
            if k == 0:
                continue
            u = np.roll(u, -k, axis=axis)
            index = [slice(None)] * 4
            index[axis] = slice(-k, None) if k > 0 else slice(None, -k)
            u[tuple(index)] = 0.0
        self.u = u
        self.low = self.low + steps * self.cell
        self.p = None
        self.ground()

    def centres(self) -> np.ndarray:
        i, j, k = (np.arange(s) for s in self.shape)
        I, J, K = np.meshgrid(i, j, k, indexing="ij")
        return self.low + (np.stack([I, J, K], axis=-1) + 0.5) * self.cell

    def at(self, points) -> np.ndarray:
        """The grid's water at each of `points`, trilinear; nothing outside it."""
        points = np.atleast_2d(np.asarray(points, dtype=float))
        out = np.zeros_like(points)
        if not self.on:
            return out
        g = (points - self.low) / self.cell - 0.5
        n = np.array(self.shape)
        inside = np.all((g >= 0.0) & (g <= n - 1.0), axis=1)
        if not inside.any():
            return out
        out[inside] = sample(self.u, g[inside])
        return out


def sample(field, g) -> np.ndarray:
    """Trilinear sample of a (nx, ny, nz, c) field at grid coordinates g (m, 3)."""
    n = np.array(field.shape[:3])
    g = np.clip(g, 0.0, n - 1.000001)
    i = np.floor(g).astype(int)
    f = g - i
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = ((f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1])
                     * (f[:, 2] if dz else 1 - f[:, 2]))
                out = out + w[:, None] * field[i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz]
    return out


def project(u, solid, cell: float, iterations: int = JACOBI, pressure=None):
    """Take the divergence out: solve for the pressure that removes it
    (Jacobi), subtract its gradient; walls and ground let nothing through."""
    u = u.copy()
    u[solid] = 0.0
    div = np.zeros(u.shape[:3])
    div[1:-1, :, :] += (u[2:, :, :, 0] - u[:-2, :, :, 0])
    div[:, 1:-1, :] += (u[:, 2:, :, 1] - u[:, :-2, :, 1])
    div[:, :, 1:-1] += (u[:, :, 2:, 2] - u[:, :, :-2, 2])
    div *= 0.5 / cell
    # The pressure's Laplacian taken as the divergence of its gradient, both
    # by central differences — the wide stencil, two cells either side — so
    # that subtracting the gradient removes exactly the divergence measured.
    # From the last step's pressure, when there is one: it barely changes in
    # a twentieth of a second, and Jacobi from a near answer needs a fraction
    # of the passes it needs from nothing.
    p = np.zeros_like(div) if pressure is None else pressure
    for _ in range(iterations):
        q = np.zeros_like(p)
        q[2:, :, :] += p[:-2, :, :]
        q[:-2, :, :] += p[2:, :, :]
        q[:, 2:, :] += p[:, :-2, :]
        q[:, :-2, :] += p[:, 2:, :]
        q[:, :, 2:] += p[:, :, :-2]
        q[:, :, :-2] += p[:, :, 2:]
        p = (q - div * 4.0 * cell * cell) / 6.0
        p[solid] = 0.0
    u[1:-1, :, :, 0] -= (p[2:, :, :] - p[:-2, :, :]) / (2.0 * cell)
    u[:, 1:-1, :, 1] -= (p[:, 2:, :] - p[:, :-2, :]) / (2.0 * cell)
    u[:, :, 1:-1, 2] -= (p[:, :, 2:] - p[:, :, :-2]) / (2.0 * cell)
    # Nothing through the walls of the box.
    u[0, :, :, 0] = u[-1, :, :, 0] = 0.0
    u[:, 0, :, 1] = u[:, -1, :, 1] = 0.0
    u[:, :, 0, 2] = u[:, :, -1, 2] = 0.0
    u[solid] = 0.0
    return u, p


class FlowSystem(System):
    name = "flow"
    reads = ("place",)
    before = ("wash", "vehicle")
    writes = ("flow",)
    every = 0.05

    def step(self, world) -> None:
        flow, wash = world.flow, world.wash
        if not flow.on:
            return
        if flow.follows:
            flow.follow(world.vehicle.position)
        # Nothing pushing and nothing moving: still water stays still, and
        # costs nothing to say so.
        if not wash.efflux.any() and not np.abs(flow.u).max() > 1e-4:
            return
        dt = self.every
        u = flow.u
        # A big grid on Warp (systems/flow_warp.py): the box's GPU, or a
        # laptop's CPU, the same arithmetic in single precision. A small one
        # stays here, in double, which is what the regression dives are held to.
        if u.shape[0] * u.shape[1] * u.shape[2] >= ON_WARP_FROM:
            from systems import flow_warp
            if flow_warp.available():
                jets = (wash.jets_at(flow.centres().reshape(-1, 3)).reshape(u.shape)
                        if wash.efflux.any() else None)
                flow.u, flow.p = flow_warp.step(u, jets, flow.solid, flow.p, flow.cell, dt,
                                                PULL, DECAY, WARM)
                return
        # Driven: towards the jets where they run.
        if wash.efflux.any():
            centres = flow.centres().reshape(-1, 3)
            jet = wash.jets_at(centres).reshape(u.shape)
            pushing = np.linalg.norm(jet, axis=-1, keepdims=True) > 1e-4
            u = u + np.where(pushing, (jet - u) * min(1.0, PULL * dt), 0.0)
        # Carried: each cell takes what was where its water came from.
        g = np.indices(flow.shape).reshape(3, -1).T.astype(float)
        back = g - u.reshape(-1, 3) * dt / flow.cell
        u = sample(u, back).reshape(u.shape)
        # Slowed, and kept incompressible.
        u *= (1.0 - DECAY * dt)
        flow.u, flow.p = project(u, flow.solid, flow.cell, iterations=WARM, pressure=flow.p)
