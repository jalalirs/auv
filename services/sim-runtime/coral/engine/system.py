"""What a system is.

Four things, and nothing else:

    reads      the parts of the world it needs as they are *now*, this tick:
               it runs after whatever writes them
    before     the parts it needs as they were at the *start* of the tick: it
               runs before whatever writes them, and sees last tick's values
    writes     the parts it owns. Nothing else may write them
    every      how often it runs, in seconds of simulated time; None is every
               tick

and `step(world)`, which does the work.

`before` is how a loop is closed without hiding it. The vehicle stirs the water
and the water drags the vehicle; the controller reads the vehicle and the
vehicle obeys the controller. Something in every loop has to act on what was
true a moment ago, as it does in the sea: a controller commands on the
position it had at the start of the step, which is what one on a real vehicle
does. Saying which side waits makes the delay a line in a declaration rather
than an accident of call order.
"""

from __future__ import annotations


class System:
    """A part of the dive that does one thing to the world each time it runs."""

    name: str = ""
    reads: tuple[str, ...] = ()
    before: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    every: float | None = None

    def step(self, world) -> None:
        raise NotImplementedError(f"{type(self).__name__} does nothing")

    def __repr__(self) -> str:
        return f"<{self.name or type(self).__name__}>"
