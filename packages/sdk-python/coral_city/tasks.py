"""What a controller is scored on in the tank.

A task watches the dive and says, at the end, how well it went as a number in
[0, 1], and along the way what each step was worth — which is the reward a
learner trains on. The platform's tasks will be these same shapes evaluated by
the runtime; until then the tank's scores are the ones there are.
"""

from __future__ import annotations

import math

import numpy as np

from .controller import Observation


class Task:
    name = "task"

    def start(self, seen: Observation) -> None:
        """The dive has begun; here is where the vehicle is."""

    def step(self, seen: Observation, dt: float) -> float:
        """What this step was worth."""
        return 0.0

    def score(self) -> float:
        """How the dive went, in [0, 1]."""
        return 0.0

    def describe(self) -> dict:
        return {"name": self.name}


class HoldStation(Task):
    """Stay where the dive began: within a radius, at a depth, on a heading."""

    name = "hold-station"

    def __init__(self, radius_m: float = 0.25, depth_tolerance_m: float = 0.10,
                 heading_tolerance_deg: float = 10.0) -> None:
        self.radius = radius_m
        self.depth_tolerance = depth_tolerance_m
        self.heading_tolerance = math.radians(heading_tolerance_deg)
        self.station = None
        self.within = 0.0
        self.total = 0.0

    def start(self, seen: Observation) -> None:
        self.station = (seen.position[:2].copy(), seen.depth, seen.heading)

    def step(self, seen: Observation, dt: float) -> float:
        xy, depth, heading = self.station
        off = float(np.hypot(*(seen.position[:2] - xy)))
        turned = abs((seen.heading - heading + math.pi) % (2 * math.pi) - math.pi)
        there = (off <= self.radius and abs(seen.depth - depth) <= self.depth_tolerance
                 and turned <= self.heading_tolerance)
        self.total += dt
        if there:
            self.within += dt
        # Dense enough to learn from: closer is better, there is best.
        return 1.0 if there else -min(1.0, off + abs(seen.depth - depth))

    def score(self) -> float:
        return 0.0 if self.total == 0 else self.within / self.total

    def describe(self) -> dict:
        return {"name": self.name, "radiusM": self.radius, "depthToleranceM": self.depth_tolerance,
                "score": round(self.score(), 3)}


class ReachDepth(Task):
    """Get to a depth and stay there; scored on the last part of the dive."""

    name = "reach-depth"

    def __init__(self, depth_m: float, tolerance_m: float = 0.10, judged_fraction: float = 0.25) -> None:
        self.depth = depth_m
        self.tolerance = tolerance_m
        self.judged_fraction = judged_fraction
        self.errors: list[tuple[float, float]] = []

    def step(self, seen: Observation, dt: float) -> float:
        error = abs(seen.depth - self.depth)
        self.errors.append((dt, error))
        return -error

    def score(self) -> float:
        if not self.errors:
            return 0.0
        tail = self.errors[int(len(self.errors) * (1 - self.judged_fraction)):]
        within = sum(dt for dt, error in tail if error <= self.tolerance)
        total = sum(dt for dt, _ in tail)
        return 0.0 if total == 0 else within / total

    def describe(self) -> dict:
        return {"name": self.name, "depthM": self.depth, "toleranceM": self.tolerance,
                "score": round(self.score(), 3)}


TASKS = {"hold": HoldStation, "hold-station": HoldStation, "reach-depth": ReachDepth}
