"""Which camera a dive that asked for several is looking through.

Reads    the clock, at the start of the tick
Writes   camera: the view

A dive nobody is watching has one camera and its video one view; an agent that
wants to see a tank from the room and from the vehicle in the same run asks
for both, and gets each for a stretch in turn. On simulated time, so a drawn
dive and its record agree on when the view changed.
"""

from __future__ import annotations

from engine import System


class Camera:
    def __init__(self) -> None:
        self.view = "chase"


class ViewsSystem(System):
    name = "views"
    before = ("clock",)
    writes = ("camera",)

    def __init__(self, objective: dict | None, offered, say) -> None:
        self.objective = objective or {}
        self.offered = offered           # the views this place has, when asked
        self.say = say

    def step(self, world) -> None:
        asked = self.objective.get("views")
        if not isinstance(asked, list) or not asked:
            return
        offered = self.offered()
        names = [v for v in asked if isinstance(v, str) and v in offered]
        if not names:
            return
        every = float(self.objective.get("viewEveryS", 4.0) or 4.0)
        want = names[int(world.clock.simulated // max(0.5, every)) % len(names)]
        if want != world.camera.view:
            world.camera.view = want
            self.say("view", view=want, scheduled=True)
