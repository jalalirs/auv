"""Where the vehicle thinks it is, which is not where it is.

This is the thing that makes an underwater task a task. There is no GPS below
the surface — radio does not travel in seawater — so a vehicle in the water
does not know where it is. It knows how fast it is going over the ground,
because a Doppler velocity log pings the bottom and measures the shift; it
knows which way it is pointing, because a compass says so, badly; and it knows
how deep it is, because pressure is depth. It adds those up. That is dead
reckoning, and it drifts.

Everything the platform gave a controller before this was the simulator's own
truth, which no vehicle has ever had. A "reach a point" flown on truth is a
straight line and a solved problem. Flown on dead reckoning it is the real
one: your estimate says you are there, and you are four metres away, and the
only thing that can tell you so is a fix from outside.

What a fix is, and where it comes from:

  Dead reckoning     DVL bottom-track velocity, heading, depth, integrated.
                     Always available while the bottom is in range. Drifts at
                     roughly one to three per cent of distance travelled, and
                     the compass is what dominates it: two degrees of heading
                     bias is three and a half metres of cross-track error over
                     a hundred metres, and no amount of good velocity fixes it.

  LBL                Transponders on the seabed, surveyed in beforehand. The
                     vehicle ranges to three or more and solves for position:
                     a metre or better, every few seconds, inside the array
                     and nowhere else. It is accurate and it is furniture —
                     somebody has to lay it and survey it.

  USBL               One transceiver on a ship or a buoy measures range and
                     bearing to the vehicle at once. Error is a share of slant
                     range — half a per cent is a good system — so it is metres
                     at depth and it needs a surface asset overhead.

  GNSS               At the surface, and only there.

  A beacon           A single transponder on a dock: range and bearing to that
                     one thing. It says nothing about where you are and
                     everything about where the dock is, which is what the
                     last five metres of a docking needs — dead reckoning is
                     out by more than the cradle is wide.

The vehicle carries what its package says it carries. The water carries what
the conditions say is deployed in it. A dive with neither is a dive on dead
reckoning, which is most of them, and which is why an AUV surfaces to fix.

Every error here is drawn once from the dive's own seed and then held, so the
same dive drifts the same way twice — a navigation error that changed between
two runs of one seed would make every comparison meaningless.
"""

from __future__ import annotations

import math

import numpy as np


def turn_of(angle: float) -> np.ndarray:
    """A rotation about the world's vertical, for a heading error."""
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


class Navigation:
    """A vehicle's own idea of where it is."""

    def __init__(self, suite: dict | None = None, aiding: dict | None = None,
                 began_at=None, seed: int = 0) -> None:
        suite = suite or {}
        self.has_dvl = bool(suite.get("dvl", True))
        # Water Linked's A50 reaches fifty metres and reads to about one per
        # cent; the numbers a package states are the ones used.
        self.dvl_range = tuple(suite.get("dvlRangeM", (0.05, 50.0)))
        self.dvl_scale_error = float(suite.get("dvlScaleError", 0.01))
        self.dvl_noise = float(suite.get("dvlNoiseMs", 0.002))
        self.heading_accuracy = math.radians(float(suite.get("headingAccuracyDeg", 2.0)))
        self.depth_noise = float(suite.get("depthNoiseM", 0.02))

        # What is deployed in this water, if anything.
        self.aiding = dict(aiding or {})
        self.kind = str(self.aiding.get("kind", "none"))
        self.every = float(self.aiding.get("everyS", 3.0))
        self.fix_accuracy = float(self.aiding.get("accuracyM", 1.0))
        self.slant_share = float(self.aiding.get("accuracyPercent", 0.5)) / 100.0
        self.reach = float(self.aiding.get("rangeM", 300.0))
        self.at = None if self.aiding.get("at") is None else np.array(self.aiding["at"], dtype=float)
        self.surface_fix_at = float(self.aiding.get("surfaceFixDepthM", 0.5))
        # How much of a fix to believe. A fix is not the truth either: it has
        # its own error, and steering at every one of them makes a vehicle
        # chase the noise — which is why station-keeping on raw USBL is worse
        # than station-keeping on dead reckoning, and why every real vehicle
        # runs a filter. This is the simplest honest one: dead reckoning
        # carries the position between fixes, and a fix pulls it a share of
        # the way rather than teleporting it.
        self.trust = float(self.aiding.get("trust", 0.25))

        # Drawn once, held for the dive: this vehicle's compass is wrong by
        # this much today, and its log reads this much fast or slow.
        draw = np.random.RandomState(seed % (2 ** 32))
        self.heading_bias = float(draw.normal(0.0, self.heading_accuracy))
        self.scale = 1.0 + float(draw.normal(0.0, self.dvl_scale_error))
        # And how wrong its guess at its own speed is when it has no bottom to
        # measure against. This is a bias and not a jitter: a vehicle inferring
        # its speed from thrust and drag is wrong in one direction all day,
        # which is exactly why the error grows instead of averaging out.
        # Between a tenth and a third out, one way or the other. Never nearly
        # right: a vehicle with no log is not a vehicle with a slightly worse
        # log, and a draw that came out near zero would say it was.
        self.blind_scale = 1.0 + float(draw.choice([-1.0, 1.0])) * float(draw.uniform(0.1, 0.32))
        self._noise = draw

        self.believed = np.array(began_at if began_at is not None else [0.0, 0.0, 0.0], dtype=float)
        self.bottom_lock = True
        self.fixes = 0
        self.last_fix_t: float | None = None
        self.last_fix_from = "the position it was put in at"
        self.travelled = 0.0

    # ── what it does every step ──────────────────────────────────────────────

    def step(self, t: float, position, velocity, rotation, floor, dt: float) -> None:
        """Integrate what the instruments say, and take a fix if one is going.

        `position`, `velocity` and `rotation` are the truth; nothing outside
        this class is allowed to see them, and what it does with them is
        exactly what an instrument would do: measure them badly.
        """
        altitude = None if floor is None else float(position[2]) - float(floor)
        self.bottom_lock = bool(self.has_dvl and altitude is not None
                                and self.dvl_range[0] <= altitude <= self.dvl_range[1])

        # Heading, as the compass has it: out by a bias it keeps all dive, and
        # by a little noise besides.
        measured = self.believed_rotation(rotation)

        # Velocity over the ground. With bottom lock it is the log's; without
        # it, the vehicle is reduced to what it can infer from its own motion
        # through the water, which is much worse — a fifth of the speed lost
        # or gained, and no way to know which.
        through = np.asarray(velocity[:3], dtype=float)
        if self.bottom_lock:
            read = through * self.scale + self._noise.normal(0.0, self.dvl_noise, 3)
        else:
            read = through * self.blind_scale + self._noise.normal(0.0, self.dvl_noise * 5.0, 3)

        self.believed[:2] += (measured @ read)[:2] * dt
        self.travelled += float(np.linalg.norm(np.asarray(velocity[:3]))) * dt
        # Depth is not dead reckoned. Pressure is depth, to a centimetre or so,
        # for as long as the vehicle is in the water — which is why an AUV's
        # error is a horizontal error and never a vertical one.
        self.believed[2] = float(position[2]) + float(self._noise.normal(0.0, self.depth_noise))

        self.maybe_fix(t, position)

    def maybe_fix(self, t: float, position) -> None:
        """A fix from outside, if there is anything out there to give one."""
        depth = float(-position[2])
        if depth <= self.surface_fix_at and self.kind in ("gnss", "usbl", "lbl", "none"):
            # At the surface there is sky. Every AUV that can afford the time
            # comes up for this, and it is the only thing that resets the drift
            # to nothing.
            if self.kind == "none" and not self.aiding.get("gnss", True):
                return
            # At the surface there is nothing better to be had, so the fix is
            # taken whole rather than blended: that is the reset an AUV
            # surfaces for.
            self._take(t, position, 2.5, "a satellite fix at the surface", trust=1.0)
            return
        if self.kind == "none" or (self.last_fix_t is not None and t - self.last_fix_t < self.every):
            return
        if self.kind == "lbl":
            # Inside the array or nothing: ranging to transponders you cannot
            # hear is not a degraded fix, it is no fix.
            if self.at is not None and float(np.linalg.norm(self.at[:2] - position[:2])) > self.reach:
                return
            self._take(t, position, self.fix_accuracy, "an LBL fix from the array")
        elif self.kind == "beacon":
            # A transponder on the dock. It gives the range and bearing to
            # that one thing and nothing about the world, so what it corrects
            # is the vehicle's idea of where it is *relative to the dock* —
            # which, since the dock's position is known, is a position.
            if self.at is None:
                return
            away = float(np.linalg.norm(self.at - np.asarray(position, dtype=float)))
            if away > self.reach:
                return
            # Close in it is very good and far out it is nothing, which is what
            # a short-baseline homing transponder actually is.
            self._take(t, position, max(0.05, self.fix_accuracy * max(0.2, away / 10.0)),
                       "a beacon on the dock")
        elif self.kind == "usbl":
            if self.at is None:
                slant = depth
            else:
                slant = float(np.linalg.norm(self.at - np.asarray(position, dtype=float)))
            if slant > self.reach:
                return
            self._take(t, position, max(0.3, slant * self.slant_share), "a USBL fix from the surface")

    def _take(self, t: float, position, accuracy: float, from_: str, trust: float | None = None) -> None:
        said = np.array([float(position[0]) + float(self._noise.normal(0.0, accuracy)),
                         float(position[1]) + float(self._noise.normal(0.0, accuracy))])
        share = self.trust if trust is None else trust
        self.believed[:2] += (said - self.believed[:2]) * max(0.0, min(1.0, share))
        self.fixes += 1
        self.last_fix_t = t
        self.last_fix_from = from_

    # ── what it is worth ─────────────────────────────────────────────────────

    def believed_rotation(self, rotation) -> np.ndarray:
        """The attitude as the vehicle has it: level, and pointing slightly wrong.

        Roll and pitch come from gravity and are good to a fraction of a
        degree. Heading comes from a magnetometer in a steel frame beside six
        motors, and is the error that matters.
        """
        return turn_of(self.heading_bias) @ np.asarray(rotation, dtype=float)

    def drift(self, position) -> float:
        """How far its idea of where it is has come from where it is."""
        return float(np.linalg.norm(self.believed[:2] - np.asarray(position, dtype=float)[:2]))

    def said(self, position, t: float) -> dict:
        return {"believed": [round(float(v), 3) for v in self.believed],
                "trust": self.trust,
                "driftM": round(self.drift(position), 3),
                "bottomLock": self.bottom_lock,
                "headingBiasDeg": round(math.degrees(self.heading_bias), 2),
                "fixes": self.fixes,
                "fixFrom": self.last_fix_from,
                "sinceFixS": None if self.last_fix_t is None else round(t - self.last_fix_t, 1),
                "aiding": self.kind,
                "travelledM": round(self.travelled, 1)}
