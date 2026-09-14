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
        # A depth gauge is a pressure sensor and a division, and the number it
        # divides by is a density somebody chose on shore. Get the water wrong
        # and every depth is wrong in proportion: a gauge set for ordinary
        # seawater, flown in the Red Sea, reads four tenths of a metre deep at
        # a hundred. Both the same by default, which is a gauge that happens to
        # suit its water — what every dive before this one assumed.
        self.gauge_scale = float(suite.get("depthGaugeScale", 1.0))

        # What is deployed in this water, if anything.
        self.aiding = dict(aiding or {})
        self.kind = str(self.aiding.get("kind", "none"))
        self.every = float(self.aiding.get("everyS", 3.0))
        self.fix_accuracy = float(self.aiding.get("accuracyM", 1.0))
        self.slant_share = float(self.aiding.get("accuracyPercent", 0.5)) / 100.0
        self.reach = float(self.aiding.get("rangeM", 300.0))
        self.at = None if self.aiding.get("at") is None else np.array(self.aiding["at"], dtype=float)
        # An array with no stated position is an array laid around where the
        # dive began. It has to be somewhere: without a position it has no
        # extent either, and a set of transponders that can be heard from
        # anywhere in the sea is not a thing that exists — nor is it something
        # a picture can show the vehicle leaving.
        if self.at is None and self.kind == "lbl" and began_at is not None:
            self.at = np.array(began_at, dtype=float)
        # The transponders themselves, when somebody laid them out rather than
        # asking for "an array, around here". An array is not a circle: it is
        # four or five things on the seabed, and where a fix can be had is
        # decided by how many of them the vehicle can hear. Empty unless a
        # layout put some in the water, in which case they replace the circle.
        self.transponders: list[np.ndarray] = []
        self.hears_at_least = int(self.aiding.get("hearsAtLeast", 3))
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
        # A vehicle that flies a model it has been calibrated against knows its
        # speed through the water rather better than one guessing from thrust:
        # a glider's flight model is fitted to its own dives and is good to a
        # few per cent. What it still cannot see is the water itself.
        self.flight_model = bool(suite.get("flightModel", False))
        self.flight_scale = 1.0 + float(draw.normal(0.0, float(suite.get("flightModelError", 0.03))))
        self._noise = draw

        # What the water is doing, when the dive has told us. It matters here
        # for one reason and it is the whole of underwater navigation: a log
        # that reads off the bottom measures the ground going past, and one
        # that does not measures the water going past. The difference between
        # those two is the current, and a vehicle without bottom lock has no
        # way of knowing it is being carried.
        self.current = np.zeros(3)
        # Where and when it last had a real fix, for working out what the water
        # did while it was under.
        self.down_since: float | None = None
        self.down_from: np.ndarray | None = None
        self.depth_averaged_current: np.ndarray | None = None
        self.current_estimates = 0

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
        over_ground = np.asarray(velocity[:3], dtype=float)
        if self.bottom_lock:
            # A Doppler log pings the seabed, so what it measures is the ground
            # going past: the current is already in it and costs nothing.
            read = over_ground * self.scale + self._noise.normal(0.0, self.dvl_noise, 3)
        else:
            # Nothing to ping. Whatever the vehicle knows about its own motion
            # is motion through the water, and the water is moving. This is the
            # error that no amount of better instrumentation fixes and the
            # reason a glider's position is a guess until it surfaces.
            through_water = over_ground - measured.T @ self.current
            scale = self.flight_scale if self.flight_model else self.blind_scale
            spread = self.dvl_noise * (2.0 if self.flight_model else 5.0)
            read = through_water * scale + self._noise.normal(0.0, spread, 3)

        self.believed[:2] += (measured @ read)[:2] * dt
        self.travelled += float(np.linalg.norm(np.asarray(velocity[:3]))) * dt
        # Depth is not dead reckoned. Pressure is depth, to a centimetre or so,
        # for as long as the vehicle is in the water — which is why an AUV's
        # error is a horizontal error and never a vertical one.
        #
        # Never a *random* vertical one, at least. A gauge calibrated for the
        # wrong sea is biased rather than noisy: it does not wander, it reads
        # the same fraction wrong at every depth, and it gets worse the deeper
        # the vehicle goes.
        self.believed[2] = (float(position[2]) * self.gauge_scale
                            + float(self._noise.normal(0.0, self.depth_noise)))

        self.maybe_fix(t, position)

    def estimate_the_current(self, t: float, position) -> None:
        """What the water did, from the gap between belief and the sky.

        Only worth anything for a vehicle that had nothing else the whole time
        it was down — a glider, or any AUV with no log and no acoustics. A
        vehicle that was taking fixes all the way has already been corrected
        towards the truth and the gap says nothing about the water.
        """
        if self.down_since is None or self.down_from is None:
            return
        under = float(t) - float(self.down_since)
        if under < 60.0 or self.bottom_lock or self.kind in ("lbl", "usbl", "beacon"):
            return
        drift = np.asarray(position, dtype=float)[:2] - self.believed[:2]
        self.depth_averaged_current = np.array([drift[0] / under, drift[1] / under, 0.0])
        self.current_estimates += 1

    def went_under(self, t: float, position) -> None:
        """Note the vehicle leaving the surface with a known position."""
        self.down_since = float(t)
        self.down_from = np.asarray(position, dtype=float).copy()

    def maybe_fix(self, t: float, position) -> None:
        """A fix from outside, if there is anything out there to give one."""
        depth = float(-position[2])
        if depth <= self.surface_fix_at and self.kind in ("gnss", "usbl", "lbl", "none"):
            # At the surface there is sky. Every AUV that can afford the time
            # comes up for this, and it is the only thing that resets the drift
            # to nothing.
            if self.kind == "none" and not self.aiding.get("gnss", True):
                return
            # Before the fix wipes it out: what the water did while it was
            # under. This is not an aside — for a glider it is the product.
            #
            # The vehicle dead reckoned through the column on its own speed
            # through the water, and arrived somewhere the water put it. The
            # difference between where it reckoned it would surface and where
            # it actually did, divided by the time it was down, is the current
            # averaged over everything it flew through. Every other row in the
            # positioning table treats that difference as the error being
            # studied. This one sells it.
            self.estimate_the_current(t, position)
            # At the surface there is nothing better to be had, so the fix is
            # taken whole rather than blended: that is the reset an AUV
            # surfaces for.
            self._take(t, position, 2.5, "a satellite fix at the surface", trust=1.0)
            self.down_since, self.down_from = None, None
            return
        if self.down_since is None and depth > self.surface_fix_at:
            self.went_under(t, position)
        if self.kind == "none" or (self.last_fix_t is not None and t - self.last_fix_t < self.every):
            return
        if self.kind == "lbl":
            # Inside the array or nothing: ranging to transponders you cannot
            # hear is not a degraded fix, it is no fix.
            #
            # When the array is a set of things somebody laid, "inside" means
            # what it means at sea — enough of them in range to cut a position,
            # which is three. That is not the same shape as a circle round a
            # centre: at the edge of a real array you lose the far side first
            # and the fixes stop before you have left the middle of anything.
            if self.transponders:
                heard = sum(1 for one in self.transponders
                            if float(np.linalg.norm(one[:2] - position[:2])) <= self.reach)
                if heard < self.hears_at_least:
                    return
                self._take(t, position, self.fix_accuracy,
                           f"an LBL fix from {heard} transponders")
            else:
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
                "travelledM": round(self.travelled, 1),
                **({} if self.depth_averaged_current is None else {
                    "depthAveragedCurrentMs": [round(float(v), 4)
                                               for v in self.depth_averaged_current[:2]],
                    "depthAveragedCurrentSpeedMs": round(
                        float(np.hypot(*self.depth_averaged_current[:2])), 4),
                    "currentEstimates": self.current_estimates,
                })}
