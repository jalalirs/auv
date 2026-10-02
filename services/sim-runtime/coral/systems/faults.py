"""What the dive was told would go wrong, and when.

Reads    the clock, at the start of the tick
Writes   faults: dead thrusters, sensors out until when, and gusts of current

A dive's conditions can schedule failures: a thruster dying, the sensors
dropping out for a few seconds, a sudden gust. This applies each when its time
comes, once. It does not act on anything itself: the thrusters read which are
dead, the instruments read whether they are out, and the water adds the gust.
"""

from __future__ import annotations

import numpy as np

from engine import System


class Faults:
    def __init__(self) -> None:
        self.failures: list[dict] = []
        self.dead: set[int] = set()
        self.sensors_out_until = 0.0
        # Every gust so far, in the order they came. The water adds each one
        # once, and counts how many it has.
        self.gusts: list[np.ndarray] = []


class FaultsSystem(System):
    name = "faults"
    before = ("clock",)
    writes = ("faults",)

    def __init__(self, thrusters: int, say) -> None:
        self.thrusters = int(thrusters)
        self.say = say

    def step(self, world) -> None:
        faults, now = world.faults, world.clock.simulated
        for failure in faults.failures:
            if failure.get("done") or now < failure["at"]:
                continue
            failure["done"] = True
            kind = failure["kind"]
            if kind == "thruster":
                which = failure.get("which")
                dead = (list(range(self.thrusters)) if which is None
                        else [int(which)] if not isinstance(which, list) else [int(w) for w in which])
                for one_of_them in dead:
                    if 0 <= one_of_them < self.thrusters:
                        faults.dead.add(one_of_them)
                self.say("thruster_failed", which=sorted(faults.dead))
            elif kind == "sensors":
                faults.sensors_out_until = now + float(failure.get("forS") or 5.0)
                self.say("sensors_out", untilS=round(faults.sensors_out_until, 1))
            elif kind == "current":
                speed = float(failure.get("which") or 0.5)
                faults.gusts.append(np.array([speed, 0.0, 0.0]))
