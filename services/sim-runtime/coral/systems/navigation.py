"""Where the vehicle believes it is.

Reads    the vehicle and the clock at the start of the tick; the water; the place
Writes   navigation: the navigator (navigation.py) and its estimate

The navigator itself — dead reckoning on the log, the compass, the depth gauge,
a fix when there is one — is navigation.py, unchanged. This runs it once a
tick, before anything is asked of the controller: a controller commands on the
estimate it had at the start of the step, which is what one on a real vehicle
does.
"""

from __future__ import annotations

from engine import System


class NavigationSystem(System):
    name = "navigation"
    reads = ("water", "place")
    before = ("vehicle", "clock")
    writes = ("navigation",)

    def __init__(self, dt: float) -> None:
        self.dt = float(dt)

    def step(self, world) -> None:
        navigator = world.navigation
        if navigator is None:
            return
        vehicle = world.vehicle
        floor = world.place.bottom_under(vehicle.position)
        # What the water is doing, so that a vehicle without a log can be
        # carried by it without noticing — which is the whole of why an AUV's
        # position is a guess.
        navigator.current = world.water.current
        navigator.step(world.clock.simulated, vehicle.position, vehicle.velocity,
                       vehicle.rotation, floor, self.dt)
