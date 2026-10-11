"""How the dive was flown, as opposed to whether it did the job.

Two controllers can both score 1 on a transect: one flies it on a quarter of
its thrust, level, never more than a few centimetres off the line; the other
saturates its thrusters, rolls fifteen degrees in every correction and wanders
a metre and a half either side. The score cannot tell them apart and a
customer choosing between them wants nothing else.

So every task keeps this beside its score, once a step, on simulated time:

  effort     the thrusters' mean and peak command, as a share of full, and the
             share of the time any of them was flat out
  attitude   how far it rolled and pitched: typically (root mean square) and
             at worst
  off line   for a task that runs along a line (a transect, a section, a
             pipeline at its offset): how long it was more than a metre off,
             and how far off at worst and on average, counted from when it
             first came onto the line, because getting to a line drawn
             somewhere else is not being off it

Everything here is worked out from the simulator's own state, so it is
derived, never measured.
"""

from __future__ import annotations

import numpy as np

# How far off a line counts as off it. A survey camera at two metres sees
# about three across, so a metre either way is where the swath stops
# overlapping the line it was meant to cover.
OFF_LINE_M = 1.0
# A command this close to full is a thruster with nothing left.
FLAT_OUT = 0.98


def distance_to(line: np.ndarray, at) -> float:
    """How far a point is from a polyline, in the horizontal."""
    p = np.asarray(at, dtype=float)[:2]
    line = np.asarray(line, dtype=float)[:, :2]
    if len(line) == 1:
        return float(np.hypot(*(p - line[0])))
    a, b = line[:-1], line[1:]
    ab = b - a
    length2 = np.maximum((ab ** 2).sum(axis=1), 1e-12)
    along = np.clip(((p - a) * ab).sum(axis=1) / length2, 0.0, 1.0)
    nearest = a + ab * along[:, None]
    return float(np.min(np.hypot(*(p - nearest).T)))


class Ride:
    """Effort, attitude and line-keeping, summed over a task's steps."""

    def __init__(self) -> None:
        self.last_t: float | None = None
        self.seconds = 0.0
        self.effort_s = 0.0
        self.peak = 0.0
        self.flat_out_s = 0.0
        self.roll2_s = self.pitch2_s = 0.0
        self.attitude_s = 0.0
        self.worst_roll = self.worst_pitch = 0.0
        self.line_s = 0.0
        self.off_s = 0.0
        self.off_sum_s = 0.0
        self.worst_off = 0.0
        self.joined = False

    def step(self, t: float, position, commands, attitude=None, line=None) -> None:
        """One step: `attitude` is (roll, pitch) in radians, `line` is
        (points, offset) for a task flown along one, else None."""
        dt = 0.0 if self.last_t is None else max(0.0, float(t) - self.last_t)
        self.last_t = float(t)
        if dt <= 0.0:
            return
        self.seconds += dt
        pushed = np.abs(np.asarray(commands, dtype=float))
        if pushed.size:
            self.effort_s += float(pushed.mean()) * dt
            self.peak = max(self.peak, float(pushed.max()))
            if float(pushed.max()) >= FLAT_OUT:
                self.flat_out_s += dt
        if attitude is not None:
            roll, pitch = (float(np.degrees(v)) for v in attitude)
            self.roll2_s += roll * roll * dt
            self.pitch2_s += pitch * pitch * dt
            self.attitude_s += dt
            self.worst_roll = max(self.worst_roll, abs(roll))
            self.worst_pitch = max(self.worst_pitch, abs(pitch))
        if line is not None:
            points, offset = line
            if points is not None and len(points):
                off = abs(distance_to(points, position) - float(offset))
                self.joined = self.joined or off <= OFF_LINE_M
                if not self.joined:
                    return
                self.line_s += dt
                self.off_sum_s += off * dt
                self.worst_off = max(self.worst_off, off)
                if off > OFF_LINE_M:
                    self.off_s += dt

    def said(self) -> dict:
        seconds = max(self.seconds, 1e-9)
        out = {
            "effort": {"meanShare": round(self.effort_s / seconds, 3),
                       "peakShare": round(min(1.0, self.peak), 3),
                       "flatOutShare": round(self.flat_out_s / seconds, 3)},
            "seconds": round(self.seconds, 1),
        }
        if self.attitude_s > 0:
            out["rollDeg"] = {"typical": round(float(np.sqrt(self.roll2_s / self.attitude_s)), 2),
                              "worst": round(self.worst_roll, 2)}
            out["pitchDeg"] = {"typical": round(float(np.sqrt(self.pitch2_s / self.attitude_s)), 2),
                               "worst": round(self.worst_pitch, 2)}
        if self.line_s > 0:
            out["offLine"] = {"thresholdM": OFF_LINE_M,
                              "secondsOnTheLine": round(self.line_s, 1),
                              "secondsOff": round(self.off_s, 1),
                              "worstM": round(self.worst_off, 2),
                              "meanM": round(self.off_sum_s / self.line_s, 2)}
        return out
