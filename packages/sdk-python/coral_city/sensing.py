"""From what the sensors say to what the controller is handed.

A vehicle does not know where it is. It knows the pressure at its depth
sensor, the attitude and rates its IMU reports, and the velocity over the
ground its DVL measures — and everything else is worked out. This is where it
is worked out, once, for the dive and the tank alike, so that a controller
tried in the tank with `sensed=True` is seeing exactly what it will see on
the vehicle: dead-reckoned position from the DVL rotated by the attitude,
depth from pressure, and nothing it would not have.
"""

from __future__ import annotations

import numpy as np

from .controller import Observation

SURFACE_PRESSURE_PA = 101325.0
GRAVITY = 9.80665


def rotation_of(w: float, x: float, y: float, z: float) -> np.ndarray:
    """A body-to-world rotation matrix from a unit quaternion."""
    n = (w * w + x * x + y * y + z * z) ** 0.5
    if n < 1e-12:
        return np.eye(3)
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


class Navigator:
    """Keeps the vehicle's estimate of itself up to date as readings arrive."""

    def __init__(self, density: float = 1025.0) -> None:
        self.density = density
        self.depth = 0.0
        self.rotation = np.eye(3)
        self.rates = np.zeros(3)
        self.velocity = np.zeros(3)       # body u v w
        self.xy = np.zeros(2)             # dead-reckoned, from where it started
        self._last_t: float | None = None
        self.heard = {"depth": False, "imu": False, "dvl": False, "sonar": False}
        # The last fan, and its nearest return. None until one arrives, which is
        # the honest answer for a vehicle that carries no sonar as well as one
        # whose first sweep has not come back yet.
        self.fan: dict | None = None
        self.nearest: dict | None = None

    def pressure(self, pascals: float) -> None:
        self.depth = max(0.0, (float(pascals) - SURFACE_PRESSURE_PA) / (self.density * GRAVITY))
        self.heard["depth"] = True

    def imu(self, quaternion_wxyz, rates) -> None:
        w, x, y, z = (float(v) for v in quaternion_wxyz)
        if abs(w) + abs(x) + abs(y) + abs(z) > 1e-9:
            self.rotation = rotation_of(w, x, y, z)
        self.rates = np.asarray(rates, dtype=float)
        self.heard["imu"] = True

    def dvl(self, velocity_body) -> None:
        self.velocity = np.asarray(velocity_body, dtype=float)
        self.heard["dvl"] = True

    @property
    def ready(self) -> bool:
        return self.heard["depth"] and self.heard["imu"]

    def sonar_fan(self, bearings, ranges) -> None:
        """One sweep of a forward-looking sonar, as the vehicle publishes it.

        Kept until the next one, because a fan arrives a few times a second and a
        controller is asked twenty times a second: the alternative is a controller
        that sees the water empty on nineteen ticks out of twenty.

        `LaserScan` says "nothing there" with infinity. The interface says it with
        NaN, because a range that is not a number is easier to be wrong about
        loudly than one that is ten thousand metres.
        """
        import math

        kept, nearest, beam = [], None, None
        for i, one in enumerate(ranges):
            value = float(one)
            if not math.isfinite(value):
                kept.append(float("nan"))
                continue
            kept.append(value)
            if nearest is None or value < nearest:
                nearest, beam = value, i
        # Lists, not whatever arrived: the interface says a fan is two lists of
        # numbers, and a controller that got arrays from one path and lists from
        # another would be written against whichever it was tried on first.
        self.fan = {"bearingsRad": [float(b) for b in bearings], "rangesM": kept}
        self.nearest = (None if nearest is None else
                        {"rangeM": nearest, "bearingRad": float(bearings[beam]),
                         "beam": int(beam)})
        self.heard["sonar"] = True

    def observation(self, t: float) -> Observation:
        """Advance the dead reckoning to t and hand back what is known."""
        if self._last_t is not None and self.heard["dvl"]:
            dt = max(0.0, t - self._last_t)
            self.xy += (self.rotation @ self.velocity)[:2] * dt
        self._last_t = t
        return Observation(
            t=t,
            position=np.array([self.xy[0], self.xy[1], -self.depth]),
            velocity=np.concatenate([self.velocity, self.rates]),
            rotation=self.rotation.copy(),
            floor=None,
            on_the_bottom=False,
            # What the sonar last saw. The vehicle publishes `/sonar/scan` and
            # the catalogue declares it; until 27 September 2026 nothing here
            # listened, so `seen` and `sonar` were always None for a deployed
            # controller and an obstacle-avoiding one was impossible to write
            # against this interface — while the runtime's own `wary` had both.
            seen=self.nearest,
            sonar=self.fan,
            estimated=True,
        )
