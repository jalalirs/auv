"""Who has the vehicle.

One thing decides, every step, which controller's command reaches the
thrusters, and the rule is short: a hand on the controls wins; otherwise a
stack that is talking; otherwise the hold. When the vehicle passes from one to
another, the one taking it is told where the vehicle is, so the hold picks up
the pose the pilot left it at rather than the one the dive began with.

There is no blending and there should not be. Two things flying one vehicle
is not a mode anybody wants, and a pilot who has taken hold has said which wins.
"""

from __future__ import annotations

import numpy as np

from .base import Command, Controller, Observation, Parameter
from .external import StackController
from .failsafe import Failsafe
from .hold import HoldController
from .manual import ManualController
from .ponder import PonderController
from .pursue import PursueController
from .thinking import Thinking


# The controllers that fly a route the planner drew. They are the same
# controller with the sonar off and on, and which of them is flying is a choice
# somebody makes rather than a mode.
ROUTE_FLYERS = ("pursue", "wary")


class Helm:
    def __init__(self, allocator, dt: float, bridge=None) -> None:
        self.allocator = allocator
        self.capability = allocator.capability()
        model = allocator.model
        # The hold wants to know how heavy the hull is to accelerate and how
        # much it sinks or floats on its own; both are the model's to say.
        self.hold = HoldController(self.capability, model.effective_mass(), -model.net_buoyancy_n, dt)
        self.manual = ManualController(self.capability, self.hold)
        # The platform's own answer to a route, so a task can be flown by
        # somebody who has not written a controller.
        self.pursue = PursueController(self.capability, model.effective_mass(), -model.net_buoyancy_n, dt)
        # And the same controller with the sonar switched on. Not a mode of the
        # planner: a controller somebody chooses, so that the difference
        # between flying a route blind and flying it with eyes is one row in a
        # comparison rather than a flag nobody finds.
        from .wary import WaryController

        self.wary = WaryController(self.capability, model.effective_mass(),
                                   -model.net_buoyancy_n, dt)
        # And one that is handed the goal instead of a route and works out its
        # own way of doing it, on a clock slow enough for something real to be
        # doing the working out. Nobody flies with it unless it is asked for.
        self.ponder = PonderController(self.capability, model.effective_mass(),
                                       -model.net_buoyancy_n, dt)
        # And one that asks a model instead of working it out. Asked for by
        # name like the ponder, and for the same reason: nobody should be
        # spending somebody's tokens because a route happened to exist.
        from .asking import AskingController

        self.asking = AskingController(self.capability, model.effective_mass(),
                                       -model.net_buoyancy_n, dt)
        # And the one controller that outranks a hand on the keys.
        self.failsafe = Failsafe(self.capability, model.effective_mass(), -model.net_buoyancy_n, dt)
        self.stack = None if bridge is None else StackController(bridge)
        self.controllers: dict[str, Controller] = {
            "hold": self.hold, "manual": self.manual, "pursue": self.pursue,
            "wary": self.wary, "ponder": self.ponder, "asking": self.asking,
            "failsafe": self.failsafe,
        }
        # A vehicle with no thrusters gets the controller that can fly it, and
        # loses the ones that cannot. A hold that commands a wrench on a hull
        # with nothing to produce one is not a controller holding station
        # badly; it is a controller that does nothing at all while the vehicle
        # falls, and offering it is worse than not having it.
        self.glide = None
        if getattr(model, "commanded_in", "wrench") == "buoyancy":
            from .glide import GlideController

            self.glide = GlideController(dt)
            self.controllers = {"glide": self.glide, "failsafe": self.failsafe}
            if self.stack is not None:
                self.controllers["stack"] = self.stack
        if self.stack is not None:
            self.controllers["stack"] = self.stack
        self.flying: Controller = self.hold if self.glide is None else self.glide
        self.steps_flown: dict[str, int] = {}
        # A slow loop for each controller that wants one, started the first
        # time it has the vehicle. Most never will.
        self.thinking: dict[str, Thinking] = {}
        self.engaged = False
        self.changes = 0
        # What the console asked to have the vehicle when no hand is on it:
        # "hold" keeps the hold even while a stack is talking, "manual" keeps
        # the assisted manual with no keys down, None is the ordinary rule.
        self.prefer: str | None = None

        # The attitude guard. On a vehicle whose thrusters sit above or below
        # its centre of gravity, pushing ahead pitches it and pushing sideways
        # rolls it, and the only thing righting it is the distance between its
        # centres of buoyancy and gravity — two centimetres on a BlueROV2,
        # which is a couple of newton-metres against the six that full surge
        # produces. Left alone, a hard push turns the vehicle over. So a wrench
        # somebody asked for is scaled down until the roll and pitch moments
        # it would produce stay inside a fraction of what the hull can right.
        # The hull leans until sin(lean) matches that fraction, so 0.35 is a
        # lean of about twenty degrees at the stop. A stack's thruster commands
        # are not touched: it asked for those.
        self.righting_nm = float(model.buoyancy_n * abs(
            float(model.centre_of_buoyancy[2] - model.centre_of_gravity[2])))
        # The bottom guard. Nothing in the vehicle knows that the ground is a
        # thing to avoid: the hold will happily hold a depth the reef is
        # already at, and a hand pushing down finds the seabed at full thrust.
        # This defends a clearance the way the attitude guard defends the
        # righting moment — by taking the descent away as it runs out, so the
        # vehicle settles onto the guard rather than into the coral.
        self.parameters = {
            "attitudeGuard": Parameter(
                "attitudeGuard", float(getattr(model, "attitude_guard", 0.5)), 0.0, 1.0, "",
                "the share of the hull's righting moment a command may lean on; 0 turns the guard off"),
            "bottomGuardM": Parameter(
                "bottomGuardM", 0.5, 0.0, 5.0, "m",
                "clearance over the seabed the guard defends; 0 turns the guard off"),
        }
        self.guarded = 0
        self.grounded = 0
        # What the last controller asked of a vehicle that is not moved by
        # thrust, for the dive to apply and the console to show.
        self.actuators: dict | None = None
        # What the guard actually cost, rather than how often it spoke. A dive
        # can be held back for its whole length and score two per cent with
        # nothing in the record saying the vehicle was never allowed to try —
        # which reads as a controller that cannot fly, and is not.
        self.steps = 0
        self.withheld_n = 0.0
        self.worst_withheld_n = 0.0
        self.at_the_stop = 0
        self.altitude: float | None = None
        # Whether the route the platform flies is what has the vehicle when
        # nobody else asks for it. Set when a dive is given a task to fly.
        self.flying_the_route = False
        for each in (self.hold, self.pursue, self.failsafe):
            each.limit(self.authority())

    # ── what the console may do ──────────────────────────────────────────────

    def hands(self, fraction) -> None:
        # A hand on the keys is a person taking the vehicle back, which is the
        # one thing that ends a failsafe.
        if self.failsafe.decided is not None and float(np.max(np.abs(np.asarray(fraction, dtype=float)))) > 0.01:
            self.failsafe.stand_down()
        self.manual.ask(fraction)

    def tune(self, controller: str, name: str, value: float) -> bool:
        if controller == "helm":
            parameter = self.parameters.get(name)
            if parameter is None:
                return False
            parameter.set(value)
            for each in (self.hold, self.pursue, self.failsafe):
                each.limit(self.authority())
            return True
        one = self.controllers.get(controller)
        return False if one is None else one.tune(name, value)

    def authority(self) -> np.ndarray:
        """What each axis may use once the guard has had its say, in newtons.

        A newton of heave on a frame whose vertical thrusters sit ahead of the
        centre of gravity leans the hull by a fixed moment, so the guard turns
        into a plain per-axis limit — which is what a loop needs to know so it
        does not wind up asking for more.
        """
        share = self.parameters["attitudeGuard"].value
        allowed = share * self.righting_nm
        most = self.capability.copy()
        if share <= 0.0 or self.righting_nm <= 0.0:
            return most
        for axis in range(6):
            unit = np.zeros(6)
            unit[axis] = 1.0
            produced = self.allocator.matrix @ (self.allocator.inverse @ unit)
            lean = float(max(abs(produced[3]), abs(produced[4])))
            # A commanded roll or pitch is a lean asked for directly, and is
            # held to the same share of the righting moment as the lean any
            # other axis causes by accident. At full key that is a hull tipped
            # twenty degrees that comes back level when the key is let go —
            # not one rolled onto its side with its heave pointing sideways,
            # which is what a roll at the thrusters' full moment does.
            if lean > 1e-9:
                most[axis] = min(most[axis], allowed / lean)
        return most

    def guard(self, wrench: np.ndarray) -> np.ndarray:
        """Trim a wrench until it cannot turn the vehicle over.

        Each axis is first held to its own authority, so that a hand pushing
        hard ahead is the thing that gets cut and not the heave the assist is
        using to keep the depth — scaling the whole wrench by one factor did
        exactly that, and the vehicle sank while its pilot drove forward. If
        the axes together still lean the hull too far, the horizontal push
        gives way and the heave is kept: a vehicle that goes ahead slower is
        a nuisance, a vehicle that leaves its depth is a hazard.
        """
        share = self.parameters["attitudeGuard"].value
        if share <= 0.0 or self.righting_nm <= 0.0:
            return wrench
        allowed = share * self.righting_nm
        most = self.authority()
        trimmed = np.clip(wrench, -most, most)

        def lean(part: np.ndarray) -> np.ndarray:
            return (self.allocator.matrix @ (self.allocator.inverse @ part))[3:5]

        horizontal = trimmed * np.array([1, 1, 0, 0, 0, 0])
        rest = trimmed - horizontal
        h, v = lean(horizontal), lean(rest)
        if np.all(np.abs(h + v) <= allowed + 1e-9):
            if np.any(trimmed != wrench):
                self.guarded += 1
            return trimmed
        # The largest share s of the horizontal push with |s·h + v| ≤ allowed
        # on both roll and pitch; the heave alone is already within it.
        s = 1.0
        for axis in range(2):
            if abs(h[axis]) < 1e-9:
                continue
            bounds = sorted(((allowed - v[axis]) / h[axis], (-allowed - v[axis]) / h[axis]))
            s = min(s, max(0.0, bounds[1]))
        self.guarded += 1
        return horizontal * s + rest

    def bottom(self, wrench: np.ndarray, seen: Observation) -> np.ndarray:
        """Take the descent away as the clearance runs out.

        Only the descent, and only what is commanded: a vehicle already on the
        bottom is left there, a vehicle rising is never held back, and every
        other axis is untouched, so a survey flying a foot off the reef still
        goes where it was sent. The guard fades in over the clearance rather
        than switching, because a step change in heave is a controller
        fighting a wall.
        """
        guard = self.parameters["bottomGuardM"].value
        if guard <= 0.0 or seen.floor is None:
            self.altitude = None
            return wrench
        self.altitude = float(seen.position[2]) - float(seen.floor)
        if wrench[2] >= 0.0:
            return wrench
        # Nothing left at the hull, everything at the guard.
        share = max(0.0, min(1.0, self.altitude / guard))
        allowed = float(self.capability[2]) * share
        if -wrench[2] <= allowed:
            return wrench
        self.grounded += 1
        held = wrench.copy()
        held[2] = -allowed
        return held

    def hold_here(self, seen: Observation) -> None:
        """Re-engage the hold at wherever the vehicle is now."""
        self.hold.engage(seen)
        self._hand_over(self.hold, seen)

    def engage(self, name: str, seen: Observation) -> bool:
        """Give the vehicle to a named controller, from the console.

        A hand on the keys still wins while it is there; this is what has the
        vehicle when it is not. Asking for the stack means the ordinary rule —
        the stack while it talks, the hold when it stops — because a stack that
        has gone silent should not keep a vehicle it is not flying.
        """
        if name not in self.controllers:
            return False
        if name == "failsafe":
            return False        # it takes the vehicle; it is not given it
        if name == "hold":
            self.prefer = "hold"
            self.failsafe.stand_down()
            self.hold_here(seen)
        elif name == "manual":
            self.prefer = "manual"
            self._hand_over(self.manual, seen)
        elif name in ("ponder", "asking"):
            # Asked for by name, and kept: a controller that plans for itself
            # is not chosen because a route happens to exist, since nobody
            # gave it one.
            self.prefer = name
            self.failsafe.stand_down()
            self._hand_over(self.controllers[name], seen)
        elif name in ROUTE_FLYERS:
            # Both of these fly the route the planner drew; which of them does
            # is the whole of the difference being measured. Asking for one and
            # silently getting the other made a comparison that could not
            # differ, which is worse than no comparison at all.
            self.prefer = name
            self.failsafe.stand_down()
        else:
            self.prefer = None
            if self.stack is not None and self.stack.talking(seen.t):
                self._hand_over(self.stack, seen)
        return True

    # ── the decision ─────────────────────────────────────────────────────────

    def fly(self, route) -> None:
        """Give the platform's own controllers a route, and the vehicle with it.

        A dive with something to do is flown by one of these unless somebody
        takes it: a hand at the keys wins, and a stack that is talking wins,
        because both are somebody saying they would rather fly it themselves.

        Both route-flyers are steered, not just the one that will fly it: they
        are the same controller with the sonar off and on, and a dive that
        switched between them mid-route should not find the other one holding
        an empty route.
        """
        for name in ROUTE_FLYERS:
            self.controllers[name].steer(route)
        self.flying_the_route = bool(route)

    def the_route_flyer(self) -> Controller:
        """Which of them has the route: the one asked for, or the ordinary one."""
        if self.prefer in ROUTE_FLYERS:
            return self.controllers[self.prefer]
        return self.pursue

    def deliberating(self) -> bool:
        """Whether anything here wants a slow clock.

        A dive with one does not run faster than the clock on the wall: a
        thought that takes two seconds in reality has to cost two seconds
        here, or a benchmark rewards being slow.
        """
        return any(getattr(c, "thinks_every", None) for c in self.controllers.values()
                   if c is self.flying or self.prefer == c.name)

    def tasked(self, goal: dict) -> None:
        """Tell every controller what the dive is for.

        Not a route: the goal. A controller that plans for itself is handed
        this and works out its own way of doing it, which is the difference
        between a vehicle that is asked and one that is driven.
        """
        for controller in self.controllers.values():
            try:
                controller.tasked(goal)
            except Exception:
                # A controller that cannot be told what the dive is for is
                # still allowed to fly it.
                pass

    def thought(self) -> dict:
        """What the slow loops did, for the record and for the console."""
        return {name: slow.said() for name, slow in self.thinking.items()}

    def watch_the_battery(self, battery, dock=None) -> None:
        self.failsafe.watch(battery, dock)

    def _choose(self, seen: Observation) -> Controller:
        # Above everything, including a hand on the keys: there is no time to
        # ask, and what is being prevented is a vehicle that never comes back.
        if self.failsafe.must_come_home(seen):
            return self.failsafe
        if self.manual.active:
            return self.manual
        if self.prefer == "hold":
            return self.hold
        if self.prefer == "manual":
            return self.manual
        # Asked for by name. A controller that plans for itself is not chosen
        # because a route happens to exist — nobody gave it one.
        if self.prefer in ("ponder", "asking"):
            return self.controllers[self.prefer]
        if self.stack is not None and self.stack.talking(seen.t):
            return self.stack
        # The route, while it is being flown — and again if the end of it
        # stops being where the vehicle is. A fix that lands after arrival
        # moves the vehicle's idea of itself, and the hold would sit at the
        # old place for the rest of the dive believing it had arrived.
        if self.glide is not None:
            return self.glide
        flyer = self.the_route_flyer()
        if self.flying_the_route and (not flyer.holding or flyer.wants_back(seen)):
            return flyer
        return self.hold

    def _hand_over(self, to: Controller, seen: Observation) -> None:
        if to is self.flying and self.engaged:
            return
        leaving = self.flying if self.engaged else None
        to.engage(seen)
        if to is self.hold and leaving is self.manual:
            # A pilot who let go of the keys was still holding a depth and a
            # heading through the assist; the hold keeps those, not whatever
            # the vehicle happened to be doing in the moment the hand came off.
            self.hold.hold_at(depth=self.manual.assisted_depth, heading=self.manual.assisted_heading)
        self.flying = to
        self.engaged = True
        self.changes += 1

    def command(self, seen: Observation) -> np.ndarray:
        """Thruster commands for this step, from whoever has the vehicle."""
        if not self.engaged:
            # The first step of the dive: whatever flies this hull takes it.
            first = self.hold if self.glide is None else self.glide
            first.engage(seen)
            self._hand_over(first, seen)
        chosen = self._choose(seen)
        # Whatever has the vehicle gets its slow loop turned, before it is
        # asked what to do — so a thought that landed since the last step is
        # already applied when the flight loop reads it.
        if getattr(chosen, "thinks_every", None):
            slow = self.thinking.get(chosen.name)
            if slow is None:
                slow = self.thinking[chosen.name] = Thinking(chosen)
            slow.tick(seen)
        # Who actually flew it, counted rather than assumed. A dive was
        # recorded as flown by whatever was configured, which is not the same
        # thing as what had the vehicle: a failsafe that took over for the
        # last third of a dive is a different result, and until this was
        # counted the difference had to be inferred from the trajectory.
        self.steps_flown[chosen.name] = self.steps_flown.get(chosen.name, 0) + 1
        if chosen is not self.flying:
            self._hand_over(chosen, seen)
        asked: Command = chosen.observe(seen)
        # A vehicle asked for in its own terms is handed over untouched. Not
        # guarded, because the attitude guard defends a hull from the moment
        # its own thrusters produce and a glider has none — and because what a
        # guard would be protecting here is the vehicle's whole method: a
        # glider flies at twenty to forty-five degrees of pitch on purpose, and
        # a rule that holds lean under thirty would stop it flying at all.
        self.actuators = asked.actuators
        if asked.actuators is not None:
            return np.zeros(len(self.allocator.matrix[0]) if len(self.allocator.matrix) else 0)
        if asked.thrusters is not None:
            return np.clip(asked.thrusters, -1.0, 1.0)
        wrench = asked.wrench if asked.wrench is not None else np.zeros(6)
        given = self.bottom(self.guard(wrench), seen)
        self._withheld(wrench, given)
        # What the guards left, told back to whoever asked — so a loop sitting
        # against a ceiling knows it is, rather than winding up against it.
        chosen.delivered(wrench, given)
        return self.allocator.allocate(given)

    # ── what the console is told ─────────────────────────────────────────────

    def _withheld(self, asked: np.ndarray, given: np.ndarray) -> None:
        """Note how far this step was held short of what was wanted.

        Two ways, because the guard bites in two places and the obvious one is
        not the one that matters. `guard()` trims a wrench that leans the hull
        too far — but every loop is already limited to `authority()`, which is
        that same allowance worked out per axis, so by the time a wrench gets
        here it has usually been cut already and `guard()` finds nothing left
        to do. Counting only what `guard()` took reported a vehicle pinned at
        its ceiling for a whole dive as never having been held back at all.

        So the ceiling is asked about directly: a horizontal command sitting
        at the most its axis is allowed is a vehicle pushing as hard as it is
        permitted to, whoever did the cutting.
        """
        self.steps += 1
        lost = float(np.hypot(asked[0] - given[0], asked[1] - given[1]))
        self.withheld_n += lost
        self.worst_withheld_n = max(self.worst_withheld_n, lost)
        most = self.authority()
        for axis in (0, 1):
            ceiling = float(most[axis])
            if ceiling > 0.0 and abs(float(given[axis])) >= ceiling - 1e-6:
                self.at_the_stop += 1
                return

    def held_back(self) -> dict | None:
        """What the vehicle was not allowed to do, for the dive's result.

        None when the guards never bit, so that a result only carries this
        when it explains something. A dive that failed because its vehicle
        leans too easily to push hard is a different fact from a dive that
        failed because nothing flew it well, and the number is the difference.
        """
        if self.steps == 0 or (self.guarded == 0 and self.at_the_stop == 0):
            return None
        return {
            "trimmedSteps": self.guarded,
            "atTheStopSteps": self.at_the_stop,
            "shareOfDive": round(max(self.guarded, self.at_the_stop) / self.steps, 3),
            "meanWithheldN": round(self.withheld_n / self.steps, 2),
            "worstWithheldN": round(self.worst_withheld_n, 2),
            "horizontalCeilingN": round(float(self.authority()[0]), 2),
            "heldOffTheBottom": self.grounded,
            "why": "the attitude guard held the push down to keep the hull from leaning over",
        }

    def who_flew(self) -> dict:
        """What share of the dive each controller had of the vehicle."""
        total = sum(self.steps_flown.values())
        if total == 0:
            return {}
        return {"mostly": max(self.steps_flown, key=self.steps_flown.get),
                "shares": {name: round(count / total, 3)
                           for name, count in sorted(self.steps_flown.items(),
                                                     key=lambda kv: -kv[1])}}

    def describe(self) -> dict:
        return {
            "flying": self.flying.name,
            "preferred": self.prefer,
            "changes": self.changes,
            "controllers": [c.describe() for c in self.controllers.values()] + [{
                "name": "helm", "kind": "builtin",
                "says": "What sits between any controller and the thrusters.",
                "parameters": [p.describe() for p in self.parameters.values()],
                "status": {"rightingNm": round(self.righting_nm, 3), "guarded": self.guarded,
                           "altitudeM": None if self.altitude is None else round(self.altitude, 2),
                           "heldOffTheBottom": self.grounded,
                           "authorityN": [round(float(a), 1) for a in self.authority()]},
            }],
        }
