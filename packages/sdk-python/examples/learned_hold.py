"""A linear station-holding policy, with weights that are learned.

What it sees: where it is relative to where it began, in its own frame; how
deep it is relative to where it began; how far its heading has swung; and its
velocities. What it asks: a wrench, as the weights say. The hand-written hold
is a special case of this — a diagonal-ish matrix — which is why its gains
are the seed the learner starts from.
"""

from __future__ import annotations

import math

import numpy as np

from coral_city import Command, Controller, Observation

FEATURES = ("ahead", "starboard", "deep", "turned", "u", "v", "w", "r", "one")

# Filled in by the learner when it writes learned_hold.py.
WEIGHTS: list[list[float]] | None = [[12.23307, 5.32318, 8.3952, -12.81387, -24.3001, 10.21627, -6.18556, 1.50034, -2.01517], [-8.65263, 7.42852, 8.96194, -6.36309, -5.64825, -83.5581, -20.70417, 4.2645, -1.23552], [-7.08609, -3.22941, 13.82673, -12.14305, 10.94911, 2.45701, -33.10821, 6.74046, 8.64437], [0.02469, -0.9984, -3.74653, -1.61526, 8.58795, -9.51242, 7.52068, 5.75602, -8.91053], [-16.39563, -17.85875, 13.5569, -14.47387, 4.49409, 0.70935, 22.39908, -10.10954, -10.49021], [8.13545, -3.28269, 1.69768, 3.82284, -2.07819, -28.99984, -4.70963, -3.29767, -1.90917]]


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def features(seen: Observation, station: np.ndarray, depth: float, heading: float) -> np.ndarray:
    off_world = np.array([station[0] - seen.position[0], station[1] - seen.position[1], 0.0])
    off_body = seen.rotation.T @ off_world
    return np.array([
        off_body[0], off_body[1],
        seen.depth - depth,
        wrap(heading - seen.heading),
        seen.velocity[0], seen.velocity[1], seen.velocity[2], seen.velocity[5],
        1.0,
    ])


class LinearHold(Controller):
    name = "learned-hold"
    says = "A linear policy whose weights were learned in the tank, in a current."
    vehicle = "bluerov2"
    commands = "wrench"
    needs = ("dvl",)

    def __init__(self, weights: np.ndarray | None = None) -> None:
        super().__init__()
        self.weights = np.array(WEIGHTS if weights is None and WEIGHTS is not None else
                                (weights if weights is not None else self.seed_weights()), dtype=float)
        self.station = None
        self.depth = 0.0
        self.heading = 0.0
        self.declare("gain", 1.0, 0.0, 2.0, "", "a single scale on everything the policy asks")

    @classmethod
    def with_weights(cls, weights: np.ndarray) -> "LinearHold":
        return cls(weights=weights)

    @classmethod
    def seed_weights(cls) -> np.ndarray:
        # Rows: surge sway heave roll pitch yaw. Columns: FEATURES.
        w = np.zeros((6, len(FEATURES)))
        w[0, 0], w[0, 4] = 17.0 * 0.4, -17.0 * 1.3          # surge on ahead, against u
        w[1, 1], w[1, 5] = 24.2 * 0.4, -24.2 * 1.3          # sway on starboard, against v
        w[2, 2], w[2, 6], w[2, 8] = 26.0 * 0.5, -26.0 * 1.4, 1.66   # heave on deep, against w, trim
        w[5, 3], w[5, 7] = 0.28 * 2.0, -0.28 * 2.8          # yaw on turned, against r
        return w

    def engage(self, seen: Observation) -> None:
        self.station = seen.position[:2].copy()
        self.depth = seen.depth
        self.heading = seen.heading

    def observe(self, seen: Observation) -> Command:
        if self.station is None:
            self.engage(seen)
        x = features(seen, self.station, self.depth, self.heading)
        wrench = self["gain"] * (self.weights @ x)
        most = self.described.most
        wrench = np.clip(wrench, -most, most)
        wrench[3] = 0.0
        wrench[4] = 0.0
        return Command(wrench=wrench)

    def status(self) -> dict:
        return {"learned": WEIGHTS is not None}
