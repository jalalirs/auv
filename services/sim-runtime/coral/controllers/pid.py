"""A proportional-integral-derivative loop, with the two things that make one
usable on a vehicle: a limit on the integral, and the derivative taken on the
measured rate rather than on the error, so that moving the setpoint does not
kick the thrusters.
"""

from __future__ import annotations


class Pid:
    def __init__(self, kp: float, ki: float, kd: float, limit: float = 1.0,
                 integral_limit: float = 0.5) -> None:
        self.kp, self.ki, self.kd = kp, ki, kd
        self.limit = limit
        self.integral_limit = integral_limit
        self.integral = 0.0

    def reset(self) -> None:
        self.integral = 0.0

    def step(self, error: float, rate: float, dt: float,
             kp: float | None = None, ki: float | None = None, kd: float | None = None) -> float:
        """The output for this error and this measured rate, in [-limit, limit].

        Gains may be passed each step, so that a parameter somebody moved on a
        console takes effect at once rather than on the next dive.
        """
        kp = self.kp if kp is None else kp
        ki = self.ki if ki is None else ki
        kd = self.kd if kd is None else kd
        self.integral += error * dt
        self.integral = max(-self.integral_limit, min(self.integral_limit, self.integral))
        # The rate is the vehicle's own: positive rate reduces a positive error.
        out = kp * error + ki * self.integral - kd * rate
        # Anti-windup: an output at the stop stops accumulating.
        if abs(out) > self.limit:
            self.integral -= error * dt
            out = max(-self.limit, min(self.limit, out))
        return out
