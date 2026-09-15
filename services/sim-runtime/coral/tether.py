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

import cable

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

    def start(self, surface_at, vehicle_at, current=None) -> None:
        """Lay the cable out between its two ends, with its slack in it."""
        self.at = np.asarray(surface_at, dtype=float)
        self.shape = cable.lay_out(self.at, vehicle_at, self.length_m, NODES, current)

    def settle(self, vehicle_at, current, passes: int = PASSES) -> None:
        """Put the cable where the water leaves it, with both ends pinned.

        A solve from nothing sweeps the length constraint along the whole
        chain; the per-step correction to an already-settled shape does not
        need to and cannot afford to at two hundred hertz.
        """
        vehicle_at = np.asarray(vehicle_at, dtype=float)
        cold = self.shape is None or passes > PASSES
        if self.shape is None:
            self.start(self.at, vehicle_at, current)
        assert self.shape is not None
        cable.settle(self.shape, self.at, vehicle_at, self.length_m, current,
                     self.diameter_m, self.weight_n_per_m, passes, self.drag_normal,
                     sweeps=(NODES - 1) if cold else None)

    def load(self, current) -> np.ndarray:
        assert self.shape is not None
        return cable.load_on(self.shape, current, self.segment_m(),
                             self.diameter_m, self.weight_n_per_m, self.drag_normal)

    def pull(self, current) -> np.ndarray:
        """What the cable does to the vehicle, in the world frame.

        From the tension in every segment rather than from the two ends — see
        `cable.tension_along`, which says why the cheaper way is wrong.
        """
        if self.shape is None or not self.out:
            self.tension_n = 0.0
            return np.zeros(3)
        tensions, along = cable.tension_along(self.shape, self.load(current))
        if tensions is None:
            self.tension_n = 0.0
            return np.zeros(3)
        # A cable can only pull. A negative answer is the solve saying this
        # segment wants to push, which means it has gone slack there.
        tension = float(max(0.0, tensions[-1]))
        self.tension_n = tension
        # It pulls the vehicle back along the segment it is tied by.
        return -along[-1] * tension

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
