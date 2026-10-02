"""The clock and the tick.

The clock is a part of the world like any other, owned by the engine and
advanced by a system of its own, so the order the declarations give says
exactly which systems see the time at the start of a tick and which see it at
the end. Sensing and deciding happen at the start; what is judged and recorded
is judged at the end, on the state the tick produced.

A system with a rate runs on the ticks where its next due time has come, so a
sonar at ten hertz on a two-hundred-hertz clock runs every twentieth tick and
never drifts.

What each system cost is kept, because a coupled ocean is only worth having
if it runs, and "the frames stopped coming" is not a measurement.
"""

from __future__ import annotations

import time

from engine.schedule import check, describe, order
from engine.system import System


class Clock:
    """Simulated time: the step, how far in, and how many steps taken."""

    def __init__(self, dt: float) -> None:
        self.dt = float(dt)
        self.simulated = 0.0
        self.taken = 0


class Tick(System):
    """Advances the clock. Runs after everything that integrates and before
    everything that judges, because the declarations put it there."""

    name = "clock"
    writes = ("clock",)

    def __init__(self, after: tuple[str, ...] = ()) -> None:
        # What the time moves on after: the parts whose new values belong to
        # the end of the tick.
        self.reads = tuple(after)

    def step(self, world) -> None:
        clock = world.clock
        clock.simulated += clock.dt
        clock.taken += 1


class Engine:
    """Runs a world's systems, in order, one tick at a time."""

    def __init__(self, world, systems) -> None:
        check(systems, world)
        self.world = world
        self.systems = order(systems)
        self._due = {s.name: 0.0 for s in self.systems}
        self.cost = {s.name: 0.0 for s in self.systems}
        self.ticks = 0

    def tick(self) -> None:
        world = self.world
        # Due on the time at the start of the tick, whichever side of the
        # clock a system runs: a rate is a rate of the dive.
        now = world.clock.simulated
        for s in self.systems:
            if s.every is not None:
                if now + 1e-9 < self._due[s.name]:
                    continue
                self._due[s.name] = self._due[s.name] + s.every
            began = time.perf_counter()
            s.step(world)
            self.cost[s.name] += time.perf_counter() - began
        self.ticks += 1

    def order(self) -> str:
        return describe(self.systems)

    def costs(self) -> dict:
        """Milliseconds a tick, each system, so far."""
        n = max(1, self.ticks)
        return {name: round(1000.0 * spent / n, 3) for name, spent in self.cost.items()}
