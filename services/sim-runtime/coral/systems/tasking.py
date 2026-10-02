"""The task: how it is to be done, how it is going, and whether the dive is over.

Reads    the vehicle, contacts, the clock (at the end of the tick), navigation,
         the sonar, the helm, power, thrust
Writes   task (the task and how the dive stands), orders (for the helm)

Three things, in this order, on the state the tick produced:

  **Plan.** When the task's goal changes — a new task, or a mission's next
  stage — work out how to do it: a plan given with the dive is flown as given,
  otherwise the platform's planner (controllers/plan.py) draws one. What the
  helm should do about it (the goal, which controller, how it is tuned, the
  route) is left as orders, which the helm carries out before it next
  commands. The helm is the only thing that changes the helm.
  **End.** Every way a dive can be over other than its clock running out: the
  task done, the battery flat, the failsafe home or on the surface.
  **Score.** The task (tasks/) scores what happened, once a step, on
  simulated time.
"""

from __future__ import annotations

import numpy as np

from engine import System
from systems.helm import observe


class Task:
    """The task, and how the dive stands against it."""

    def __init__(self) -> None:
        self.task = None
        # Why the dive stopped, in one word, decided by whatever stopped it.
        self.ended = ""
        self.task_over = False
        self.attempts = 1
        self.route_flying = ""
        self.document: dict | None = None
        self.planned_by = ""
        self.asked_for = None
        self.tuned_from_objective = False


class TaskingSystem(System):
    name = "tasking"
    reads = ("vehicle", "contacts", "clock", "navigation", "sonar", "helm", "power", "water", "place", "thrust")
    writes = ("task", "orders")

    def __init__(self, brief: dict, say, who_should_fly, envelope, camera_half_angle) -> None:
        self.brief = brief
        self.say = say
        # What the vehicle and the dive say about themselves: read when a plan
        # is drawn, and not state.
        self.who_should_fly = who_should_fly
        self.envelope = envelope
        self.camera_half_angle = camera_half_angle

    def step(self, world) -> None:
        self.plan(world)
        self.consider_the_end(world)
        task = world.task.task
        if task is None:
            return
        v, navigator = world.vehicle, world.navigation
        floor = world.place.bottom_under(v.position)
        task.step(world.clock.simulated, v.position,
                  float(np.arctan2(v.rotation[1, 0], v.rotation[0, 0])), floor, world.thrust.commands,
                  believed=None if navigator is None else navigator.believed,
                  # Whether the log has the bottom: a descent is scored partly
                  # on how much of it was flown blind.
                  locked=None if navigator is None else navigator.bottom_lock)

    # ── plan ─────────────────────────────────────────────────────────────────

    def plan(self, world) -> None:
        """Plan a way of doing what the task asks, when what it asks changes."""
        stands, orders = world.task, world.orders
        task = stands.task
        if task is None:
            return
        which = task.goal_id()
        if which == stands.route_flying:
            return
        from controllers import plan

        goal = task.goal()
        # Every controller is told what the dive is for. One that plans for
        # itself needs the goal and not a route — that is the whole of the
        # difference between a vehicle being asked and one being driven.
        orders.waiting.append(("tasked", goal))
        named = self.who_should_fly()
        if named and named != stands.asked_for:
            stands.asked_for = named
            orders.waiting.append(("engage", named, observe(world)))
        # And how it is set, when the dive says: a stand-off sized for a reef is
        # wider than a tank. Applied once, the same way a console's `tune` is.
        tuning = (self.brief.get("objective") or {}).get("tune")
        if isinstance(tuning, dict) and not stands.tuned_from_objective:
            stands.tuned_from_objective = True
            for controller, values in tuning.items():
                for name, value in (values or {}).items():
                    orders.waiting.append(("tune", controller, name, value))
        # A plan given to the dive is flown as given, after it is checked: a
        # plan naming a manoeuvre that does not exist is a vehicle that stops
        # in the water for no reason anyone can see. It may come with the dive
        # or ride inside the objective it satisfies.
        given = self.brief.get("plan")
        if not isinstance(given, dict):
            given = (self.brief.get("objective") or {}).get("plan") \
                if isinstance(self.brief.get("objective"), dict) else None
        if isinstance(given, dict) and given.get("manoeuvres"):
            wrong = plan.what_is_wrong(given, self.envelope())
            if wrong:
                self.say("plan_refused", why=wrong[:4])
                given = None
            else:
                stands.document = given
                stands.planned_by = str(given.get("by") or "the plan it was given")
        if not isinstance(stands.document, dict) or given is None:
            believed = (np.asarray(world.navigation.believed, dtype=float) if world.navigation is not None
                        else np.asarray(world.vehicle.position, dtype=float))
            stands.document = plan.plan_for(goal, believed=believed,
                                            camera_half_angle=self.camera_half_angle(),
                                            named=task.kind)
            stands.planned_by = "the platform's planner"
        route = plan.legs_of(stands.document)
        stands.route_flying = which
        orders.waiting.append(("fly", route))
        if route or stands.document:
            self.say("planned", legs=len(route),
                     manoeuvres=len(stands.document.get("manoeuvres", [])),
                     forTask=task.kind, goal=goal.get("kind"),
                     stage=which, by=stands.planned_by)

    # ── end ──────────────────────────────────────────────────────────────────

    def finish(self, world, why: str) -> None:
        stands = world.task
        if not stands.ended:
            stands.ended = why
            self.say("ending", why=why, t=round(world.clock.simulated, 2))

    def consider_the_end(self, world) -> None:
        """A task that is done is a dive that is done: the machine goes back
        rather than holding station for the rest of an hour somebody asked for
        because they did not know how long the job would take."""
        stands = world.task
        if stands.ended:
            return
        task = stands.task
        if task is not None and task.done:
            if str(self.brief.get("mode", "batch")) == "interactive":
                # Somebody is watching. Ending here would take the water away
                # at the exact moment there is something to look at. The
                # vehicle holds, the console says how it went, and they can try
                # again or surface.
                if not stands.task_over:
                    stands.task_over = True
                    self.say("task_over", result=task.result(), attempt=stands.attempts)
                return
            self.finish(world, "failed" if task.failed() else "achieved")
            return
        battery = world.power.battery
        if battery is not None and battery.flat:
            self.finish(world, "battery")
            return
        # The failsafe has taken the vehicle and got it there.
        failsafe = world.helm.failsafe
        if failsafe.decided == "surface" and world.vehicle.submerged(world.water.level) < 1.0:
            self.finish(world, "surfaced")
        elif failsafe.decided == "dock" and failsafe.pursue.holding:
            self.finish(world, "home")
