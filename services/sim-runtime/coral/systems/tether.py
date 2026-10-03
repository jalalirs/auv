"""The tether as a cable: weight, drag, inertia and contact — and when it holds the vehicle.

Reads    the vehicle, the water, the wash, the place, the clock
Writes   cable: where the cable is, what it pulls on the vehicle with, and
         whether it has fouled

The cable is a chain of masses (lumped-mass, as MoorDyn and Stonefish do),
cut into a few centimetres a node in a tank and a few metres on a reef:

  **Forces.** Each node carries its weight in water — near nothing for a
  tether, which is made near-neutral on purpose — and drag on the water moving
  past it: normal drag on the part across the cable and a small tangential one
  along it (Morison, the cross-flow principle cable people use). The water is
  the dive's: the current, and the vehicle's own wash, so a thruster blowing
  across the cable pushes it. Out of the water a node simply falls.
  **Inextensible, not stiff.** Segments may go slack but not stretch: each
  step the nodes are moved back to at most a segment apart (position-based
  dynamics), the dry end fixed at the rim and the wet end on the vehicle.
  **Contact.** A node never goes into the ground, the rock or the glass: it is
  put back out of it, and a node touching something is held by friction. That
  is what lets a cable catch on a pillar, and stay caught.
  **Tension.** The force it took to keep each segment from stretching — the
  constraint's multiplier, in extended position-based dynamics (XPBD), with
  the compliance of the cable's axial stiffness. At the vehicle's end it pulls
  the vehicle back along the last segment, at the point it is tied on, so a
  cable caught on a rock behind the vehicle holds it back and pitches it.

**When the dive fails.** Three ways, after the tether-entanglement literature
(Rajan et al. 2016; REACT, Amer et al. 2026; Battocletti et al. 2024):

  wrapped   the tightest path the cable could be pulled into, keeping its
            turns round what it is wrapped on, is longer than the cable: it
            cannot be pulled straight to reach (REACT's test)
  held      caught on something and pulling against the thrusters — tension
            above a share of what they can push, with the cable in contact,
            for seconds on end
  parted    tension past the breaking load

How many times it has gone round each rock (its winding number) is reported
with the dive, and does not fail one on its own.

Assumed, and said: the axial stiffness and breaking load when the package does
not state them; a drag coefficient of 1.2 across and 0.01 along; added mass as
the water the cable displaces. Measured data to check it against exists — a
BlueROV2's tether motion-captured in a tank with the drum's tension recorded
(Scientific Data, 2025) — and is the first thing to fit.
"""

from __future__ import annotations

import math

import numpy as np

from engine import System

DENSITY = 1025.0
DRAG_NORMAL = 1.2
DRAG_ALONG = 0.01
FRICTION = 0.6              # what a node touching something keeps of its sliding, per step: none of it
GRAVITY = 9.80665


class Umbilical:
    """A cable from the rim to the vehicle, moving."""

    def __init__(self, said: dict | None = None) -> None:
        said = dict(said or {})
        self.diameter_m = float(said.get("diameterM", 0.0076))
        self.length_m = float(said.get("lengthM", 0.0))
        self.weight_n_per_m = float(said.get("weightNPerM", -0.02))      # in water, positive down
        area = math.pi * (0.5 * self.diameter_m) ** 2
        # Its own mass, when the package does not say: a cable is mostly
        # plastic and copper, a little denser than the water it displaces.
        self.mass_per_m = float(said.get("massKgPerM", 1150.0 * area))
        self.drag_normal = float(said.get("dragNormal", DRAG_NORMAL))
        self.stiffness_n = float(said.get("axialStiffnessN", 20000.0))
        self.breaking_n = float(said.get("breakingN", 1500.0))
        self.from_ = str(said.get("_", ""))
        self.at = np.zeros(3)
        self.shape: np.ndarray | None = None
        self.velocity: np.ndarray | None = None
        self.touching: np.ndarray | None = None
        self.force = np.zeros(3)           # on the vehicle, world frame
        self.tension_n = 0.0
        self.most_tension_n = 0.0
        self.path_m = 0.0                  # the length of the path it takes now
        self.taut_path_m = 0.0             # the tightest it could be pulled, keeping its turns
        self.winding: dict[str, float] = {}
        self.verdict: str | None = None
        self.why = ""
        self.held_for_s = 0.0
        # Kept for the drawing and for the old reach limit (systems/contact.py).
        self.taut = False
        self.struck = 0

    # How much stretch the solver may leave in a cable it has not converged,
    # as a share of its length. Below this, tension is the solver's force.
    SOLVER_SLACK = 0.005

    @property
    def out(self) -> bool:
        return self.length_m > 0.0

    def nodes(self) -> int:
        """Enough to wrap round a hand-sized rock in a tank; a few metres a
        node on a reef."""
        return int(np.clip(round(self.length_m / 0.045), 20, 60))

    def segment_m(self) -> float:
        return self.length_m / (len(self.shape) - 1) if self.shape is not None else self.length_m

    def start(self, surface_at, vehicle_at) -> None:
        """Laid out between its ends with its slack hanging, at rest."""
        self.at = np.asarray(surface_at, dtype=float)
        n = self.nodes()
        a, b = self.at, np.asarray(vehicle_at, dtype=float)
        t = np.linspace(0.0, 1.0, n)[:, None]
        straight = a + (b - a) * t
        span = float(np.linalg.norm(b - a))
        slack = max(0.0, self.length_m - span)
        # The slack as a sag (or a rise, for a floating cable) in the middle.
        sag = 0.35 * slack * np.sin(np.pi * t[:, 0]) * (1.0 if self.weight_n_per_m >= 0 else -1.0)
        straight[:, 2] -= sag
        self.shape = straight
        self.velocity = np.zeros_like(straight)
        self.touching = np.zeros(n, dtype=bool)

    # ── the step ─────────────────────────────────────────────────────────────

    def step(self, dt: float, end, flow, place, level, sweeps: int = 8) -> None:
        """Move the cable on by dt, the wet end at `end`. `flow(points)` is the
        water's velocity at each node; `place` stops it; `level` is the surface."""
        x, v = self.shape, self.velocity
        n = len(x)
        seg = self.length_m / (n - 1)
        x[0] = self.at
        x[-1] = np.asarray(end, dtype=float)
        free = slice(1, n - 1)
        r = 0.5 * self.diameter_m
        mass = self.mass_per_m * seg
        added = DENSITY * math.pi * r * r * seg
        wet = x[free, 2] < (0.0 if level is None else level)

        # Along the cable at each node, for which part of the water is across it.
        along = np.zeros_like(x)
        along[1:-1] = x[2:] - x[:-2]
        along /= np.maximum(np.linalg.norm(along, axis=1, keepdims=True), 1e-9)
        u = flow(x[free]) - v[free]
        ua = np.sum(u * along[free], axis=1, keepdims=True) * along[free]
        un = u - ua
        # Drag, taken implicitly: it can slow a node to the water's speed and
        # no further, however large the step — a light cable in a fast jet is
        # otherwise a cable that rings.
        cn = 0.5 * DENSITY * self.drag_normal * self.diameter_m * seg * np.linalg.norm(un, axis=1, keepdims=True)
        ca = 0.5 * DENSITY * DRAG_ALONG * math.pi * self.diameter_m * seg * np.linalg.norm(ua, axis=1, keepdims=True)
        m = np.where(wet[:, None], mass + added, mass)
        kn, ka = cn * dt / m, ca * dt / m
        dv = np.where(wet[:, None], un * kn / (1.0 + kn) + ua * ka / (1.0 + ka), 0.0)
        down = np.where(wet, self.weight_n_per_m * seg / (mass + added), GRAVITY)
        dv[:, 2] -= down * dt
        v[free] += dv
        was = x.copy()
        x[free] += v[free] * dt

        # Never longer than a segment between nodes, free to go slack, and
        # never in anything: the two in turn, a few times, because each undoes
        # a little of the other where a cable is pressed round a rock. The ends
        # do not move for it: one is on the rim, the other on the vehicle.
        w = [0.0] + [1.0 / float(mi) for mi in m[:, 0]] + [0.0]
        compliance = seg / max(self.stiffness_n, 1.0) / (dt * dt)
        lam = [0.0] * (n - 1)
        for _ in range(4):
            self.hold_together(x, seg, max(2, sweeps // 4), w, compliance, lam)
            self.keep_out(x, place, r)
            # A cable that floats lies on the surface, it does not leave it:
            # the surface holds it up the way the bottom holds a heavy one.
            if level is not None and self.weight_n_per_m < 0.0:
                x[1:-1, 2] = np.minimum(x[1:-1, 2], level - r)
        self.velocity = (x - was) / dt
        self.velocity[0] = 0.0
        # Friction: a node pressed against something does not slide freely.
        if self.touching.any():
            self.velocity[self.touching] *= (1.0 - FRICTION)

        # What it pulls the vehicle with: what it took to hold the last
        # segment to its length, along it.
        self.path_m = float(np.linalg.norm(np.diff(x, axis=0), axis=1).sum())
        tensions = -np.asarray(lam) / (dt * dt)
        tension = float(tensions[-1])
        # A few passes a step cannot converge a cable stretched hard — one
        # wrapped on a rock and pulled on — and under-converged XPBD is soft.
        # Past what the solver leaves (half a per cent), the stretch the path
        # shows is real and pulls at the cable's own stiffness.
        strain = (self.path_m - self.length_m) / max(self.length_m, 1e-6)
        tension = max(tension, self.stiffness_n * max(0.0, strain - self.SOLVER_SLACK))
        last = x[-2] - x[-1]
        last /= max(float(np.linalg.norm(last)), 1e-9)
        self.tension_n = tension
        self.most_tension_n = max(self.most_tension_n, float(tensions.max()), tension)
        self.force = last * tension

    @staticmethod
    def hold_together(x, seg: float, sweeps: int, w, compliance: float, lam) -> None:
        """Pull nodes back to at most a segment apart, ends held — XPBD, so
        that what it took to hold them is a force and not a guess.

        Each segment is a one-sided constraint, C = length − segment: it may
        go slack, not stretch, with the compliance of the cable's axial
        stiffness. `lam` carries each segment's multiplier through the passes
        of a step, never positive (a cable only pulls); −lam/dt² is the
        tension in that segment. Swept forward and back, so a correction at
        either end reaches the other."""
        nodes = x.tolist()
        last = len(nodes) - 1
        for sweep in range(sweeps):
            order = range(last) if sweep % 2 == 0 else range(last - 1, -1, -1)
            for i in order:
                wa, wb = w[i], w[i + 1]
                if wa + wb <= 0.0:
                    continue
                a, b = nodes[i], nodes[i + 1]
                dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                if length < 1e-12:
                    continue
                was = lam[i]
                now = min(0.0, was + (seg - length - compliance * was) / (wa + wb + compliance))
                change = now - was
                if change == 0.0:
                    continue
                lam[i] = now
                ux, uy, uz = dx / length, dy / length, dz / length
                a[0] -= ux * change * wa
                a[1] -= uy * change * wa
                a[2] -= uz * change * wa
                b[0] += ux * change * wb
                b[1] += uy * change * wb
                b[2] += uz * change * wb
        x[:] = nodes

    def keep_out(self, x, place, r: float) -> None:
        """Out of the ground, the rock and the glass. A node in rock that is
        a wall goes out sideways, not up it: a cable against a pillar is
        against its side, and is caught on it."""
        n = len(x)
        touching = np.zeros(n, dtype=bool)
        inner = x[1:-1]
        bottom = place.bottoms(inner)
        into = inner[:, 2] < bottom + r
        if into.any():
            idx = np.flatnonzero(into)
            facing = place.facing(inner[idx])
            gentle = (facing[:, 2] > 0.6) | (inner[idx, 2] < bottom[idx] - 0.5)
            lift = idx[gentle]
            inner[lift, 2] = bottom[lift] + r
            wall = idx[~gentle]
            if len(wall):
                side = facing[~gentle, :2]
                side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-9)
                for _ in range(12):
                    still_in = place.bottoms(inner[wall]) >= inner[wall, 2] - r
                    if not still_in.any():
                        break
                    inner[wall[still_in], :2] += side[still_in] * (2.0 * r)
            touching[1:-1][idx] = True
        if place.interior is not None:
            from systems.glass import held_in
            held, over, _ = held_in(inner, place.interior, r)
            touching[1:-1] |= over
            inner[:, :2] = held
        x[1:-1] = inner
        self.touching = touching

    # ── fouled ───────────────────────────────────────────────────────────────

    def tightest(self, place, iterations: int = 150) -> float:
        """The length of the tightest path the cable could be pulled into
        without passing through anything: every other node moved towards the
        line between its neighbours, unless that would put it or the segments
        either side of it in rock. In open water that is the straight line
        between the ends; wound round a pillar it goes round the pillar
        (REACT's taut-tether test)."""
        x = self.shape.copy()
        r = 0.5 * self.diameter_m

        def clear(points):
            return place.bottoms(points) < points[:, 2] - r

        # A node moves at most this far a pass, and a segment is checked
        # along its length, so neither can hop across something thin.
        most = 0.01
        along = np.linspace(0.2, 0.8, 4)[:, None, None]
        for it in range(iterations):
            k = np.arange(1 + it % 2, len(x) - 1, 2)
            if not len(k):
                continue
            step = 0.7 * (0.5 * (x[k - 1] + x[k + 1]) - x[k])
            far = np.linalg.norm(step, axis=1, keepdims=True)
            moved = x[k] + step * np.minimum(1.0, most / np.maximum(far, 1e-12))
            ok = clear(moved)
            for end in (x[k - 1], x[k + 1]):
                samples = (end[None] + along * (moved - end)[None]).reshape(-1, 3)
                ok &= clear(samples).reshape(len(along), -1).all(axis=0)
            x[k[ok]] = moved[ok]
        return float(np.linalg.norm(np.diff(x, axis=0), axis=1).sum())

    def wound(self, rocks) -> dict:
        """How many times the cable goes round each rock, signed: the angle
        it sweeps about the rock's middle, in turns, end to end."""
        out = {}
        xy = self.shape[:, :2]
        for name, centre in rocks.items():
            d = xy - np.asarray(centre, dtype=float)[None, :2]
            a = np.arctan2(d[:, 1], d[:, 0])
            step = (np.diff(a) + np.pi) % (2 * np.pi) - np.pi
            out[name] = round(float(step.sum() / (2 * np.pi)), 2)
        return out

    def keep_in(self, position, was):
        """The old reach limit: no further from the rim, in a straight line,
        than there is cable. Asks only; the vehicle counts what it hits."""
        if not self.out:
            return position, False
        away = np.asarray(position, dtype=float) - self.at
        far = float(np.linalg.norm(away))
        if far <= self.length_m:
            return position, False
        del was
        return self.at + away / far * self.length_m, True

    def said(self) -> dict:
        deepest = None if self.shape is None else round(-float(self.shape[:, 2].min()), 3)
        return {"lengthM": round(self.length_m, 2), "diameterM": self.diameter_m,
                "tensionN": round(self.tension_n, 2), "mostTensionN": round(self.most_tension_n, 2),
                "pathM": round(self.path_m, 3), "tightestM": round(self.taut_path_m, 3),
                "touching": int(self.touching.sum()) if self.touching is not None else 0,
                "winding": self.winding, "fouled": self.verdict, "why": self.why,
                "deepestM": deepest, "from_": [round(float(c), 2) for c in self.at],
                "model": "lumped-mass, position-based, with contact (systems/tether.py)"}


class TetherSystem(System):
    """Moves the cable each tick and decides whether it has fouled."""

    name = "cable"
    reads = ("vehicle", "water", "wash", "flow", "place", "clock", "ship")
    writes = ("cable",)

    # How often it asks whether the cable has fouled. The tightest-path test
    # is the dear one, and a cable does not wrap a rock in a quarter second.
    JUDGED_EVERY_S = 0.25
    # Held: pulling against the thrusters with this share of what they can
    # push, while caught on something, for this long.
    HELD_SHARE = 0.6
    HELD_FOR_S = 3.0

    def __init__(self, dt: float, attach, can_push_n: float, rocks: dict, say) -> None:
        self.dt = float(dt)
        self.attach = np.asarray(attach, dtype=float)
        self.can_push_n = float(can_push_n)
        self.rocks = rocks
        self.say = say
        self.judged_at = -1e9

    def end_of(self, v):
        return v.position + v.rotation @ self.attach

    def step(self, world) -> None:
        cable = world.cable
        if cable is None or not cable.out or cable.shape is None:
            return
        v, water, wash = world.vehicle, world.water, world.wash
        now = world.clock.simulated
        # Towed: the dry end is the ship's stern, wherever she has got to.
        if world.ship.towing:
            cable.at = world.ship.at.copy()

        def flow(points):
            return water.flow_at(points, now) + wash.at(points)

        cable.step(self.dt, self.end_of(v), flow, world.place, water.level)
        if now - self.judged_at >= self.JUDGED_EVERY_S:
            self.judge(cable, world.place, now - max(self.judged_at, now - self.JUDGED_EVERY_S))
            self.judged_at = now

    def judge(self, cable, place, since: float) -> None:
        if cable.verdict is not None:
            return
        cable.winding = cable.wound(self.rocks)
        caught = bool(cable.touching.any())
        cable.taut_path_m = cable.tightest(place) if caught else float(
            np.linalg.norm(cable.shape[-1] - cable.shape[0]))
        if cable.tension_n > cable.breaking_n:
            self.foul(cable, "parted", f"tension {cable.tension_n:.0f} N past its breaking load "
                                       f"of {cable.breaking_n:.0f} N")
            return
        straight = float(np.linalg.norm(cable.shape[-1] - cable.shape[0]))
        # Wrapped: what it is caught on makes the tightest path longer than the
        # cable — not merely a vehicle at the end of a straight one.
        if caught and cable.taut_path_m > cable.length_m and \
                cable.taut_path_m > straight + 0.05 * cable.length_m:
            self.foul(cable, "wrapped", f"wrapped on something: the tightest it could be pulled is "
                                        f"{cable.taut_path_m:.2f} m against {cable.length_m:.2f} m paid out")
            return
        if caught and cable.tension_n > self.HELD_SHARE * self.can_push_n:
            cable.held_for_s += since
            if cable.held_for_s >= self.HELD_FOR_S:
                self.foul(cable, "held", f"caught and pulling {cable.tension_n:.1f} N against thrusters "
                                         f"that push {self.can_push_n:.1f} N, for {cable.held_for_s:.1f} s")
        else:
            cable.held_for_s = 0.0

    def foul(self, cable, verdict: str, why: str) -> None:
        cable.verdict, cable.why = verdict, why
        self.say("tether_fouled", fouled=verdict, why=why, winding=cable.winding,
                 touching=int(cable.touching.sum()), tensionN=round(cable.tension_n, 2))
