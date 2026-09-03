"""Station-keeping: the controller every dive begins under.

A real ROV is trimmed a little buoyant and holds its depth on the thrusters; a
simulated one that starts by sinking is not a simulation of anything. So a
dive opens with this engaged at the vehicle's starting pose — depth, heading and
position — and it keeps the vehicle there until something else asks for it.

It is built from three autopilots that are useful on their own: depth, heading
and horizontal position. Manual flying borrows the first two, so that a person
pushing ahead does not also have to fight to stay level, which is how a real
ROV with an autopilot feels.

Every loop works in accelerations — metres per second squared per metre of
error, radians per second squared per radian — and the vehicle's own effective
mass turns those into newtons. So the gains mean the same thing on an
eleven-kilogram vehicle and a hundred-kilogram one: kp 0.5 is a loop with a
natural period of nine seconds on both, and kd 1.4 damps it critically on both.

The one thing the loops do not have to discover is the trim. A vehicle that is
a newton or two heavy would otherwise sink until the integrator caught up, on
every engagement, so the net buoyancy the model declares is fed forward as a
starting point and the integrator only corrects what the model got wrong.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Command, Controller, Observation
from .pid import Pid


def wrap(angle: float) -> float:
    """An angle into (-pi, pi]."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


class Autopilots:
    """The three loops, sharing one set of declared parameters."""

    def __init__(self, owner: Controller, mass: np.ndarray, capability: np.ndarray,
                 trim_n: float) -> None:
        d = owner.declare
        # Depth: the slowest axis, with the most drag and the most added mass,
        # and on a frame whose vertical thrusters sit ahead of the centre of
        # gravity every newton of heave also pitches the hull — so it is asked
        # for gently.
        d("depthKp", 0.5, 0.0, 4.0, "1/s²", "heave per metre of depth error")
        d("depthKd", 1.4, 0.0, 6.0, "1/s", "heave against vertical speed")
        d("depthKi", 0.08, 0.0, 1.0, "1/s³", "slow correction for a trim the model has wrong")
        d("trimN", trim_n, -50.0, 50.0, "N", "the steady heave that makes the vehicle neutral; the model's own by default")
        d("headingKp", 2.0, 0.0, 10.0, "1/s²", "yaw per radian of heading error")
        d("headingKd", 2.8, 0.0, 10.0, "1/s", "yaw against turn rate")
        d("positionKp", 0.4, 0.0, 3.0, "1/s²", "surge and sway per metre off station")
        d("positionKd", 1.3, 0.0, 6.0, "1/s", "surge and sway against speed")
        d("positionKi", 0.05, 0.0, 1.0, "1/s³", "slow correction for a steady push")
        d("deadbandM", 0.02, 0.0, 0.5, "m", "closer than this counts as there")
        self.owner = owner
        self.mass = np.asarray(mass, dtype=float)
        self.depth = Pid(0.5, 0.08, 1.4)
        self.heading = Pid(2.0, 0.0, 2.8)
        self.surge = Pid(0.4, 0.05, 1.3)
        self.sway = Pid(0.4, 0.05, 1.3)
        self.limit(capability)

    def limit(self, authority: np.ndarray) -> None:
        """How much force each axis may actually use.

        Not always the thrusters' full capability: the helm keeps a vehicle
        from leaning over, and what is left after that is what these loops
        may spend. Each is limited to the acceleration its axis can produce,
        so the integrator stops winding the moment the axis is at the stop
        rather than storing up a correction the thrusters cannot deliver.
        """
        self.capability = np.asarray(authority, dtype=float)
        most = np.divide(self.capability, self.mass, out=np.zeros(6), where=self.mass > 0)
        for loop, axis, ki in ((self.depth, 2, 0.08), (self.heading, 5, 1e-9),
                               (self.surge, 0, 0.05), (self.sway, 1, 0.05)):
            loop.limit = float(most[axis])
            # The integral alone may reach the stop, and no further.
            loop.integral_limit = float(most[axis]) / ki
            loop.integral = max(-loop.integral_limit, min(loop.integral_limit, loop.integral))

    def reset(self) -> None:
        for loop in (self.depth, self.heading, self.surge, self.sway):
            loop.reset()

    def hold_depth(self, seen: Observation, target: float, dt: float) -> float:
        """Heave, in newtons, that holds a depth. Positive is up."""
        o = self.owner
        # Error in z: target depth deeper than now means go down, i.e. negative heave.
        error = seen.depth - target
        if abs(error) < o["deadbandM"]:
            error = 0.0
        # The rate the loop damps is the one that closes the error: a positive
        # error is too deep, and rising — positive body w — closes it.
        wanted = self.depth.step(error, float(seen.velocity[2]), dt,
                                 kp=o["depthKp"], ki=o["depthKi"], kd=o["depthKd"])
        return self._newtons(2, wanted) + o["trimN"]

    def hold_heading(self, seen: Observation, target: float, dt: float) -> float:
        """Yaw, in newton-metres, that holds a heading."""
        o = self.owner
        error = wrap(target - seen.heading)
        wanted = self.heading.step(error, float(seen.velocity[5]), dt,
                                   kp=o["headingKp"], ki=0.0, kd=o["headingKd"])
        return self._newtons(5, wanted)

    def hold_position(self, seen: Observation, target: np.ndarray, dt: float) -> tuple[float, float]:
        """Surge and sway, in newtons, that hold a horizontal position."""
        o = self.owner
        error_world = np.array([target[0] - seen.position[0], target[1] - seen.position[1], 0.0])
        error_body = seen.rotation.T @ error_world
        if np.hypot(error_body[0], error_body[1]) < o["deadbandM"]:
            error_body[:] = 0.0
        surge = self.surge.step(float(error_body[0]), float(seen.velocity[0]), dt,
                                kp=o["positionKp"], ki=o["positionKi"], kd=o["positionKd"])
        sway = self.sway.step(float(error_body[1]), float(seen.velocity[1]), dt,
                              kp=o["positionKp"], ki=o["positionKi"], kd=o["positionKd"])
        return self._newtons(0, surge), self._newtons(1, sway)

    def _newtons(self, axis: int, acceleration: float) -> float:
        """An acceleration on one axis, as the force this hull needs for it."""
        most = float(self.capability[axis])
        return float(np.clip(acceleration * self.mass[axis], -most, most))


class HoldController(Controller):
    """Keep the vehicle where it was put."""

    name = "hold"
    kind = "builtin"
    says = "Holds depth, heading and position where the vehicle was left."

    def __init__(self, capability: np.ndarray, mass: np.ndarray, trim_n: float, dt: float) -> None:
        super().__init__()
        self.capability = capability
        self.dt = dt
        self.pilots = Autopilots(self, mass, capability, trim_n)
        self.target_depth = 0.0
        self.target_heading = 0.0
        self.target_position = np.zeros(2)
        self.last_error = 0.0

    def engage(self, seen: Observation) -> None:
        """Hold here: wherever the vehicle is at this instant."""
        self.target_depth = seen.depth
        self.target_heading = seen.heading
        self.target_position = seen.position[:2].copy()
        self.pilots.reset()

    def limit(self, authority: np.ndarray) -> None:
        self.capability = np.asarray(authority, dtype=float)
        self.pilots.limit(authority)

    def hold_at(self, depth: float | None = None, heading: float | None = None,
                position=None) -> None:
        """A different station, asked for from outside."""
        if depth is not None:
            self.target_depth = float(depth)
        if heading is not None:
            self.target_heading = wrap(float(heading))
        if position is not None:
            self.target_position = np.array(position[:2], dtype=float)

    def observe(self, seen: Observation) -> Command:
        heave = self.pilots.hold_depth(seen, self.target_depth, self.dt)
        yaw = self.pilots.hold_heading(seen, self.target_heading, self.dt)
        surge, sway = self.pilots.hold_position(seen, self.target_position, self.dt)
        wrench = np.array([surge, sway, heave, 0.0, 0.0, yaw])
        self.last_error = float(np.hypot(*(self.target_position - seen.position[:2])))
        return Command(wrench=np.clip(wrench, -self.capability, self.capability))

    def status(self) -> dict:
        return {"targetDepthM": round(self.target_depth, 3),
                "targetHeadingDeg": round(math.degrees(self.target_heading), 1),
                "targetPosition": [round(float(v), 3) for v in self.target_position],
                "offStationM": round(self.last_error, 3)}
