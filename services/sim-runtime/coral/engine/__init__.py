"""The engine: one clock, one world, and the systems that step it.

Everything that happens in a dive is a system. A system says which parts of the
world it reads and which it writes, and the engine works out from those
declarations the order they run in each tick. Systems never call each other:
the thrusters do not push the fish, they write their jets into the water, and
the fish read the water. That is what makes the ocean coupled, and it is also
what lets each system be read, and tested, on its own.

    world.py      the named parts of the world, and who may write each
    system.py     what a system is: reads, writes, how often, and a step
    schedule.py   the order, worked out from the declarations
    engine.py     the clock, the tick, and what each system cost

See docs/plan/r6-engine.md for why it is built this way.
"""

from engine.engine import Clock, Engine
from engine.schedule import order, describe
from engine.system import System
from engine.world import World

__all__ = ["Clock", "Engine", "System", "World", "order", "describe"]
