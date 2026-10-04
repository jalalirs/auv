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

    iocean tank examples/avoid.py --task transect --trace
    iocean deploy examples/avoid.py --slug avoid --name "Go around things"

Flown against the baselines with frames actually in the way:

    ./tools/bench --suite quick run --controller avoid --tasks transect --through
"""

from __future__ import annotations

import math

import numpy as np

from iocean import Command, Controller, Observation


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
        # Which side it went round the last thing — +1 starboard, -1 port — kept
        # until the way is clear. The side, never the bearing: see `the_widest_gap`.
        self.committed: float | None = None
        self.avoiding = 0

    def engage(self, seen: Observation) -> None:
        if self["depthM"] == 0.0:
            self.parameters["depthM"].set(seen.depth)
        # The heading it was engaged at, unless the task named one.
        if self.goal.get("headingDeg") is None:
            self.parameters["headingDeg"].set(math.degrees(seen.heading))

    def tasked(self, goal: dict) -> None:
        """Take the altitude and the heading the dive asks for.

        A controller that ignored the task and flew its own default would score
        badly for a reason that has nothing to do with what it is for — and worse,
        it would fly a different path from the baseline it is being compared
        against, which makes the comparison meaningless rather than merely unfair.

        The goal arrives latched on `/task` before engagement, and again whenever a
        mission moves to its next stage.
        """
        super().tasked(goal)
        for field, parameter in (("altitudeM", "altitudeM"),
                                 ("headingDeg", "headingDeg"),
                                 ("speedMs", "speedMs")):
            said = self.goal.get(field)
            if said is None:
                continue
            try:
                self.parameters[parameter].set(float(said))
            except (TypeError, ValueError):
                pass

    # ── the fan ──────────────────────────────────────────────────────────────

    def the_widest_gap(self, fan: dict, prefer: float | None = None) -> float | None:
        """The middle of the longest run of beams with nothing close in them.

        None when the whole fan is clear, which is the ordinary case and the one
        worth being cheap about.

        `prefer` is the side already committed to — positive for starboard. When
        there is an opening on that side it is taken even if a wider one has
        appeared on the other, because a vehicle that changes its mind halfway
        round a frame passes neither side of it.

        Always measured from **this** sweep. An earlier answer cannot be reused:
        a gap is a bearing off the nose, so a bearing stored one tick and applied
        the next — after the vehicle has turned towards it — asks for the same turn
        again, and again, which is a vehicle going in circles rather than round
        something. That was the first version of this file.
        """
        # Never `or []` on these: a fan may arrive as numpy arrays — the runtime's
        # does — and `array or []` raises rather than defaulting.
        said, got = fan.get("bearingsRad"), fan.get("rangesM")
        if said is None or got is None:
            return None
        bearings = np.asarray(said, dtype=float)
        ranges = np.asarray(got, dtype=float)
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
            # Nothing open anywhere: turn hard, to the side already chosen if
            # there is one, rather than split the difference and drive straight in.
            edge = float(bearings[-1] if (prefer or 0.0) > 0 else bearings[0])
            return edge
        # Every run of open beams, so the committed side can be honoured.
        runs, run, start = [], 0, 0
        for i, is_open in enumerate(open_beam):
            if is_open:
                if run == 0:
                    start = i
                run += 1
            elif run:
                runs.append((run, start, i - 1))
                run = 0
        if run:
            runs.append((run, start, len(open_beam) - 1))
        middles = [(width, float(bearings[a:b + 1].mean())) for width, a, b in runs]
        if prefer is not None:
            same = [one for one in middles if (one[1] > 0) == (prefer > 0)]
            if same:
                return max(same)[1]
        return max(middles)[1]

    def observe(self, seen: Observation) -> Command:
        most = self.described.most
        wanted = math.radians(self["headingDeg"])
        speed = float(self["speedMs"])

        gap = self.the_widest_gap(seen.sonar, self.committed) if seen.sonar else None
        nearest = None
        if seen.seen is not None:
            nearest = float(seen.seen.get("rangeM") or math.inf)

        if gap is None:
            # The way is clear: the heading it was given takes over, and
            # whatever it committed to is forgotten.
            self.committed = None
        else:
            self.avoiding += 1
            # Commit to a side, once, and keep the side — not the bearing. The
            # bearing is remeasured every tick from the current sweep; only which
            # way round is remembered.
            if self.committed is None:
                self.committed = 1.0 if gap >= 0 else -1.0
            wanted = wrap(seen.heading + gap)
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
                "goingRound": None if self.committed is None
                              else ("starboard" if self.committed > 0 else "port")}
