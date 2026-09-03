"""Coral City's controller SDK.

A controller is a class: it is handed what the vehicle knows about itself and
answers with what it wants the vehicle to do, and it declares what a hand may
move while it runs. The same class flies in three places without changing —
the headless tank on your own machine, a dive on the platform over ROS 2, and,
because nothing in it knows about a simulator, a real vehicle.

    from coral_city import Controller, Command

    class Hold(Controller):
        vehicle = "bluerov2"
        commands = "wrench"

        def __init__(self):
            super().__init__()
            self.declare("depthM", 5.0, 0.0, 30.0, "m", "the depth to hold")

        def observe(self, seen):
            heave = 20.0 * (seen.depth - self["depthM"]) - 30.0 * seen.velocity[2]
            return Command.wrench_of(heave=heave)

Then `coral-city tank hold.py` to try it, `coral-city deploy hold.py` to put it
on the platform, and `coral-city dive` to fly it there.
"""

from .controller import Command, Controller, Observation, Parameter
from .vehicle import Vehicle
from . import vehicles

__all__ = ["Command", "Controller", "Observation", "Parameter", "Vehicle", "vehicles"]
__version__ = "0.1.0"
