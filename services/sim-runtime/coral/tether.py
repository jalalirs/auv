"""The cable, and what it does to the vehicle on the end of it.

This is the only thing in the plan that was *wrong* rather than missing. Every
tethered dive in this record flew as though the umbilical were not there, and a
hundred metres of it streaming in a current is not a detail: an 8 mm tether has
0.8 m² of frontal area against a BlueROV2's 0.06 m², so in any current worth
worrying about the cable is the larger force by an order of magnitude. A pilot
who has flown a tethered ROV will not believe a simulator that leaves it out,
and they will be right not to.

**The model.** Quasi-static: the cable is light and slack and settles far
faster than the vehicle manoeuvres, so its shape is solved to equilibrium each
step rather than integrated. That is the standard assumption in steady-state
tether analysis and it is wrong in exactly one place — a shock load, when
somebody snatches the cable taut — which is handled separately as a limit on
reach rather than pretended about.

Three parts:

  **The shape.** Nodes along the cable, both ends pinned: the surface end at
  whatever the layout put there, the wet end at the vehicle. Each interior node
  is pushed by its own weight in water and its own drag, then the segment
  lengths are relaxed back. A few passes of that is a catenary that leans
  downstream, which is what a tether in a current looks like.

  **The pull.** With the shape known, the whole cable is in equilibrium: the
  tension at each end acts along its end segment, and the two magnitudes follow
  from the forces on everything between them. That is a three-equation,
  two-unknown least squares, which is exact when the shape has converged and
  honest about how far it has not when it has not.

  **The limit.** A vehicle cannot go further out than there is cable. When the
  straight-line distance reaches the deployed length the cable is taut, and the
  vehicle is held there the same way it is held out of a mooring block.

Drag uses only the component of the water's motion across the cable. A cable
edge-on to the flow is a cable that is not being pushed, and the cross-flow
principle — normal drag on the normal component, a much smaller tangential
term ignored — is what cable people use and what makes the shape lean rather
than balloon.
"""

from __future__ import annotations

import numpy as np

# Seawater, for the cable's own drag. The vehicle's own density is read from
# its water; the difference over the working range is under half a per cent and
# the cable's drag coefficient is not known to better than ten.
DENSITY = 1025.0

# How many pieces the cable is cut into. Twenty over a hundred metres is five
# metres a node, which resolves the lean without making the relaxation the most
# expensive thing in the step.
NODES = 20

# How many relaxation passes per solve. The shape is carried between steps, so
# each step is a few passes of correction on an already-good answer rather than
# a solve from nothing — which is what makes a quasi-static cable cheap.
PASSES = 6


class Tether:
    """A cable between something at the surface and the vehicle."""

    def __init__(self, said: dict | None = None) -> None:
        said = dict(said or {})
        # The Fathom slim tether the BlueROV2 ships with: 7.6 mm, and very
        # slightly buoyant in seawater. A working ROV tether is made near
        # neutral on purpose, because one that is not spends the dive dragging
        # the vehicle down.
        self.diameter_m = float(said.get("diameterM", 0.0076))
        self.length_m = float(said.get("lengthM", 0.0))
        # Newtons per metre, positive down. Near zero for a working tether.
        self.weight_n_per_m = float(said.get("weightNPerM", -0.02))
        # A cylinder across the flow, at the Reynolds numbers a tether sees.
        self.drag_normal = float(said.get("dragNormal", 1.2))
        self.at = np.zeros(3)          # the surface end
        self.shape: np.ndarray | None = None
        self.taut = False
        self.tension_n = 0.0
        self.struck = 0

    @property
    def out(self) -> bool:
        """Whether there is any cable in the water at all."""
        return self.length_m > 0.0

    def segment_m(self) -> float:
        return self.length_m / (NODES - 1)

    def start(self, surface_at, vehicle_at) -> None:
        """Lay the cable out, straight, between its two ends.

        Straight is wrong and it does not matter: the first solve bends it, and
        starting from a straight line rather than from nothing is what lets
        every later step be a correction rather than a solve.
        """
        self.at = np.asarray(surface_at, dtype=float)
        vehicle_at = np.asarray(vehicle_at, dtype=float)
        walk = np.linspace(0.0, 1.0, NODES)[:, None]
        self.shape = self.at[None, :] * (1 - walk) + vehicle_at[None, :] * walk

    def settle(self, vehicle_at, current, passes: int = PASSES) -> None:
        """Put the cable where the water leaves it, with both ends pinned."""
        vehicle_at = np.asarray(vehicle_at, dtype=float)
        if self.shape is None:
            self.start(self.at, vehicle_at)
        assert self.shape is not None
        self.shape[0] = self.at
        self.shape[-1] = vehicle_at
        segment = self.segment_m()
        load = self.load(current)

        for _ in range(passes):
            # Where the forces want each node to go. A displacement rather than
            # an acceleration: this is a relaxation towards equilibrium and not
            # an integration through time, and giving the cable inertia it does
            # not need is how a quasi-static solver starts ringing.
            #
            # Scaled by the segment length so that the step is a fraction of a
            # segment whatever the cable's size: the tension that will resist
            # it is not known until the shape is, and this only has to get the
            # direction right for the constraint pass to do the rest.
            step = load * (segment * 0.02)
            self.shape[1:-1] += step[1:-1]
            self.relax(segment)

        self.shape[0] = self.at
        self.shape[-1] = vehicle_at

    def load(self, current) -> np.ndarray:
        """The force on each node: its weight in water, and its drag.

        Drag on the component of the water's motion *across* the cable. A cable
        edge-on to the flow is not being pushed, and it is this that makes a
        tether lean downstream rather than balloon.
        """
        assert self.shape is not None
        current = np.asarray(current, dtype=float)
        segment = self.segment_m()
        # Which way each node's piece of cable runs.
        along = np.zeros_like(self.shape)
        along[1:-1] = self.shape[2:] - self.shape[:-2]
        along[0] = self.shape[1] - self.shape[0]
        along[-1] = self.shape[-1] - self.shape[-2]
        length = np.linalg.norm(along, axis=1, keepdims=True)
        along = np.divide(along, np.where(length < 1e-9, 1.0, length))

        flow = np.tile(current, (len(self.shape), 1))
        across = flow - along * np.sum(flow * along, axis=1, keepdims=True)
        speed = np.linalg.norm(across, axis=1, keepdims=True)
        area = self.diameter_m * segment
        drag = 0.5 * DENSITY * self.drag_normal * area * speed * across

        weight = np.zeros_like(self.shape)
        weight[:, 2] = -self.weight_n_per_m * segment
        return drag + weight

    def relax(self, segment: float) -> None:
        """Pull the nodes back to a segment apart, ends held.

        Position-based rather than elastic: a working tether stretches under a
        per cent at the loads it sees, and a stiff spring at two hundred hertz
        is a spring that explodes. What this cannot model is a shock load, and
        a shock load is the taut case, which is handled as a limit instead.
        """
        assert self.shape is not None
        for _ in range(2):
            for i in range(len(self.shape) - 1):
                a, b = self.shape[i], self.shape[i + 1]
                apart = b - a
                length = float(np.linalg.norm(apart))
                if length < 1e-9:
                    continue
                correct = (length - segment) / length * apart
                # The ends do not move; an interior node takes half each.
                first = 0.0 if i == 0 else 0.5
                second = 0.0 if i + 1 == len(self.shape) - 1 else 0.5
                share = first + second
                if share <= 0.0:
                    continue
                self.shape[i] = a + correct * (first / share)
                self.shape[i + 1] = b - correct * (second / share)

    def pull(self, current) -> np.ndarray:
        """What the cable does to the vehicle, in the world frame.

        The whole cable is in equilibrium, so the tensions at its two ends and
        everything acting on what is between them sum to nothing. Each tension
        acts along its own end segment, which leaves two unknown magnitudes and
        three equations — solved as a least squares, which is exact once the
        shape has settled and honest about how far it has not when it has not.
        """
        if self.shape is None or not self.out:
            self.tension_n = 0.0
            return np.zeros(3)
        load = self.load(current)
        # The load at the ends belongs half to the cable and half to whatever
        # it is tied to; only what the cable carries is in its own balance.
        total = load[1:-1].sum(axis=0) + 0.5 * (load[0] + load[-1])

        at_surface = self.shape[0] - self.shape[1]
        at_vehicle = self.shape[-1] - self.shape[-2]
        for one in (at_surface, at_vehicle):
            length = float(np.linalg.norm(one))
            if length < 1e-9:
                self.tension_n = 0.0
                return np.zeros(3)
            one /= length

        # T_s·û_s + T_v·û_v + Σf = 0, where each û points from the cable back
        # along its end segment towards whatever that end is tied to — which is
        # the direction that end pulls the cable, and the reverse of the
        # direction the cable pulls the vehicle.
        both = np.column_stack([at_surface, at_vehicle])
        magnitudes, *_ = np.linalg.lstsq(both, -total, rcond=None)
        tension = float(magnitudes[1])
        self.tension_n = abs(tension)
        # A cable can only pull. A negative magnitude is the solver saying the
        # shape wants to push, which a cable cannot do: it goes slack instead.
        if tension < 0.0:
            self.tension_n = 0.0
            return np.zeros(3)
        return -at_vehicle * tension

    def keep_in(self, position, was):
        """A vehicle cannot go further out than there is cable.

        The taut case, which is the one the relaxation cannot carry: put it
        back on the sphere the cable's length allows, the same way the ground
        and a mooring block put it back.
        """
        if not self.out:
            return position, False
        away = np.asarray(position, dtype=float) - self.at
        far = float(np.linalg.norm(away))
        if far <= self.length_m:
            self.taut = False
            return position, False
        # Counted on going taut rather than on every step held there. A vehicle
        # leaning on its cable for four seconds hit the end of it once, and
        # eight hundred of anything is a number nobody reads.
        if not self.taut:
            self.struck += 1
        self.taut = True
        del was
        return self.at + away / far * self.length_m, True

    def said(self) -> dict:
        deepest = None if self.shape is None else round(-float(self.shape[:, 2].min()), 2)
        return {"lengthM": round(self.length_m, 1),
                "diameterM": self.diameter_m,
                "tensionN": round(self.tension_n, 2),
                "taut": self.taut,
                "timesHeldBack": self.struck,
                "deepestM": deepest,
                "from_": [round(float(v), 1) for v in self.at]}
