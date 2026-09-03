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
        self.heard = {"depth": False, "imu": False, "dvl": False}

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
            estimated=True,
        )
