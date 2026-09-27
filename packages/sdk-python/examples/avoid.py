"""Go where you were told, and decline to fly through things on the way.

The SDK had no example that reads the sonar, which is the one instrument a
controller learns something from that nobody told it: where the vehicle is, what
the dive is for and what the plan was all come from the dive, and a thing in the
water that is not in the plan only ever arrives through a return.

So this is the counterpart of the runtime's own `wary`, written against the public
interface — the thing somebody starts from when their reef has frames in it.

**How it works.** It flies to where it was sent. When the fan shows something
close ahead it looks across the whole fan for the widest run of beams with nothing
in them, steers at the middle of that gap, and eases off — both harder the closer
the thing is. When the way is clear the heading it was given takes over again.

**Why the gap and not the nearest return.** The interface says it plainly and it
is worth repeating in code: a thing dead ahead is symmetric, so the closest beam
flips between the two either side of centre as the noise moves. A controller told
to turn away from *that* is told left, then right, then left, and drives into the
thing while chattering.

**And it commits.** Once it has picked a side it keeps it until the way is clear,
because a vehicle that reconsiders every fifth of a second never finishes a turn.

    coral-city tank examples/avoid.py --task transect --trace
    coral-city deploy examples/avoid.py --slug avoid --name "Go around things"

Flown against the baselines with frames actually in the way:

    ./tools/bench --suite quick run --controller avoid --tasks transect --through
"""

from __future__ import annotations

import math

import numpy as np

from coral_city import Command, Controller, Observation


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class GoAroundThings(Controller):
    name = "avoid"
    says = "Flies where it was sent, and goes around what the sonar sees on the way."
    vehicle = "bluerov2"
    commands = "wrench"
    needs = ("dvl", "imaging_sonar")

    def __init__(self) -> None:
        super().__init__()
        self.declare("headingDeg", 0.0, -180.0, 180.0, "°", "the heading to fly")
        self.declare("speedMs", 0.4, 0.0, 1.5, "m/s", "how fast to fly it")
        self.declare("altitudeM", 3.0, 0.5, 30.0, "m", "how high over the bottom to fly")
        self.declare("depthM", 0.0, 0.0, 100.0, "m",
                     "the depth to hold when there is no bottom under it; 0 means where it was engaged")
        # How close is close. A frame two metres across seen at eight metres is
        # not yet a reason to turn; at four it is, and at two it is late.
        self.declare("noticeM", 8.0, 1.0, 40.0, "m", "a return nearer than this is something in the way")
        self.declare("clearRad", 0.09, 0.01, 0.5, "rad", "a beam this far from anything counts as open")
        self.declare("turnKp", 2.2, 0.0, 10.0, "1/s²", "yaw per radian of error")
        self.declare("turnKd", 2.8, 0.0, 10.0, "1/s", "yaw against turn rate")
        self.declare("depthKp", 0.5, 0.0, 3.0, "1/s²", "heave per metre of depth error")
        self.declare("depthKd", 1.4, 0.0, 6.0, "1/s", "heave against vertical speed")
        self.declare("speedKp", 1.2, 0.0, 6.0, "1/s", "surge per metre per second of speed error")
        dynamics = self.described.dynamics
        added = dynamics["addedMass"]["diagonal"]
        inertia = dynamics.get("inertiaTensor", [0.1] * 9)
        self.surge_mass = dynamics["massKg"] + abs(added[0])
        self.heave_mass = dynamics["massKg"] + abs(added[2])
        self.yaw_inertia = abs(inertia[8]) + abs(added[5])
        self.trim_n = -self.described.net_buoyancy_n
        # Which way it went round the last thing, kept until the way is clear.
        self.committed: float | None = None
        self.avoiding = 0

    def engage(self, seen: Observation) -> None:
        if self["depthM"] == 0.0:
            self.parameters["depthM"].set(seen.depth)
        self.parameters["headingDeg"].set(math.degrees(seen.heading))

    # There is no `tasked` hook here, and that is not an omission.
    #
    # The runtime's own controllers are handed the dive's objective — `tasked(goal)`
    # on their base class — and an SDK controller is not: nothing publishes the
    # objective and `Controller` has no hook for it. So this cannot read the
    # altitude off the task; it is a parameter, and whoever flies it sets it, by
    # `--tune altitudeM=3` or from the cockpit.
    #
    # Worth knowing before comparing this against `pursue` on a transect: the
    # baseline is told what the dive is for and this is not. The plan records that
    # asymmetry under item 4.

    # ── the fan ──────────────────────────────────────────────────────────────

    def the_widest_gap(self, fan: dict) -> float | None:
        """The middle of the longest run of beams with nothing close in them.

        None when the whole fan is clear, which is the ordinary case and the one
        worth being cheap about.
        """
        bearings = np.asarray(fan.get("bearingsRad") or [], dtype=float)
        ranges = np.asarray(fan.get("rangesM") or [], dtype=float)
        if bearings.size == 0 or bearings.size != ranges.size:
            return None
        # A beam is open when nothing came back, or what came back is far enough
        # away not to matter. NaN means nothing came back.
        open_beam = ~(np.isfinite(ranges) & (ranges < float(self["noticeM"])))
        if open_beam.all():
            return None
        best, run, start = (0, None), 0, 0
        for i, is_open in enumerate(open_beam):
            if is_open:
                if run == 0:
                    start = i
                run += 1
                if run > best[0]:
                    best = (run, (start, i))
            else:
                run = 0
        if best[1] is None:
            # Nothing open anywhere: hold what was committed, or turn hard one
            # way rather than split the difference and drive straight in.
            return self.committed if self.committed is not None else float(bearings[0])
        first, last = best[1]
        return float(bearings[first:last + 1].mean())

    def observe(self, seen: Observation) -> Command:
        most = self.described.most
        wanted = math.radians(self["headingDeg"])
        speed = float(self["speedMs"])

        gap = self.the_widest_gap(seen.sonar) if seen.sonar else None
        nearest = None
        if seen.seen is not None:
            nearest = float(seen.seen.get("rangeM") or math.inf)

        if gap is None:
            # The way is clear: the heading it was given takes over, and
            # whatever it committed to is forgotten.
            self.committed = None
        else:
            self.avoiding += 1
            # Commit to a side. `gap` is off the nose, so it is already the turn
            # to make; the sign of the first one is what is kept.
            if self.committed is None or (gap != 0.0 and (gap > 0) == (self.committed > 0)):
                self.committed = gap
            wanted = wrap(seen.heading + (self.committed if self.committed is not None else gap))
            # And ease off, harder the closer it is. A vehicle that keeps its
            # speed while turning out of the way turns into the thing's side.
            if nearest is not None and math.isfinite(nearest):
                close = max(0.0, min(1.0, nearest / max(1e-6, float(self["noticeM"]))))
                speed *= 0.2 + 0.8 * close

        turn = wrap(wanted - seen.heading)
        yaw = self.yaw_inertia * (self["turnKp"] * turn - self["turnKd"] * seen.velocity[5])
        # Altitude over the bottom where there is a bottom, depth where there is
        # not. Reef work is altitude work — a camera two metres over the coral is
        # the whole point, and a transect is scored on holding it — but a tank has
        # no seabed and a vehicle in open water has nothing under it, so depth is
        # the fallback rather than the intent.
        if seen.floor is not None:
            error = (float(seen.floor) + float(self["altitudeM"])) - float(seen.position[2])
            error = -error                      # positive error means too high
        else:
            error = seen.depth - self["depthM"]
        heave = self.heave_mass * (self["depthKp"] * error
                                   - self["depthKd"] * seen.velocity[2]) + self.trim_n
        surge = self.surge_mass * self["speedKp"] * (speed - float(seen.velocity[0]))
        return Command.wrench_of(
            surge=max(-most[0], min(most[0], surge)),
            heave=max(-most[2], min(most[2], heave)),
            yaw=max(-most[5], min(most[5], yaw)),
        )

    def status(self) -> dict:
        return {"avoiding": self.avoiding,
                "committedRad": None if self.committed is None else round(self.committed, 3)}
