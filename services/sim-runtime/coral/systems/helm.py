"""Who flies, and what they command.

Reads    navigation, the sonar and the place; the vehicle and the clock at the
         start of the tick; orders, as they were left at the end of the last
Writes   helm (the controllers, controllers/), asked (what they commanded)

The helm decides every step whether the thrusters follow a hand on the
controls, a stack talking over ROS 2, or the platform's own controllers, and
asks it for a command. It is handed what the vehicle *knows* — the estimate,
the sonar's fan — and never what is true (`observe`, below).

What the task wants of the helm (a goal, a route, which controller, how it is
tuned) arrives as orders from tasking, and is carried out here, before the
command: the helm is the only thing that changes the helm.
"""

from __future__ import annotations

from engine import System


class Orders:
    """What tasking decided the helm should be doing, not yet carried out."""

    def __init__(self) -> None:
        self.waiting: list[tuple] = []


def observe(world, sensors_out: bool = False):
    """What the vehicle knows about itself — not what is true about it.

    The difference is the whole of underwater navigation. A controller is
    handed where the vehicle believes it is, worked out from its log, its
    compass and its pressure sensor, and where it believes it is pointing,
    which is out by whatever the compass is out by. What is actually true
    stays in the world, for the tasks to score against and for the console to
    draw beside it.
    """
    from controllers import Observation

    vehicle, navigator, sonar = world.vehicle, world.navigation, world.sonar
    floor = world.place.bottom_under(vehicle.position)
    t = world.clock.simulated
    if navigator is None:
        # Nothing between the controller and the truth. Said out loud,
        # because a controller scored against the truth while steering on an
        # estimate is a different problem from one holding the truth.
        return Observation(t=t, position=vehicle.position, velocity=vehicle.velocity,
                           rotation=vehicle.rotation, floor=floor, on_the_bottom=vehicle.on_the_bottom,
                           seen=None if sonar is None else sonar.nearest(),
                           sonar=None if sonar is None else sonar.fan(),
                           estimated=False)
    believed_floor = None if floor is None else floor + (navigator.believed[2] - float(vehicle.position[2]))
    return Observation(t=t,
                       position=navigator.believed.copy(),
                       velocity=vehicle.velocity,
                       rotation=navigator.believed_rotation(vehicle.rotation),
                       floor=believed_floor,
                       on_the_bottom=vehicle.on_the_bottom,
                       seen=None if sonar is None else sonar.nearest(),
                       sonar=None if sonar is None else sonar.fan(),
                       estimated=True)


class Asked:
    def __init__(self, commands) -> None:
        self.commands = commands
        # A dive flown from a recording of another's commands has had the
        # last of them: it is over where that one was.
        self.replay_over = False


class HelmSystem(System):
    name = "helm"
    reads = ("navigation", "sonar", "place")
    before = ("vehicle", "clock", "orders")
    writes = ("helm", "asked")

    def __init__(self, say, replay=None) -> None:
        self.say = say
        # Every tick's command, kept, so that the dive can be flown again
        # exactly: a person at the keys or a stack over ROS 2 is not a thing a
        # second run can ask, but what they commanded is. And a dive given a
        # recording of them plays it back in place of asking anybody — the same
        # seed and the same commands are the same dive, which is how a
        # path-traced film is made of a run that was watched live.
        self.kept: list = []
        self.replay = replay
        self.ticks = 0

    def step(self, world) -> None:
        import numpy as np

        helm = world.helm
        self.carry_out(helm, world.orders)
        if self.replay is not None:
            # Past the end of what was recorded the vehicle is let go: nothing
            # was commanded there, because the first dive was over.
            here = self.replay[self.ticks] if self.ticks < len(self.replay) else np.zeros(self.replay.shape[1])
            world.asked.commands = np.array(here, dtype=float)
        else:
            world.asked.commands = helm.command(observe(world))
        self.kept.append(np.array(world.asked.commands, dtype=float))
        self.ticks += 1
        world.asked.replay_over = self.replay is not None and self.ticks >= len(self.replay)

    def commands(self):
        """Every tick's command so far, (ticks, thrusters)."""
        import numpy as np

        return np.array(self.kept, dtype=float).reshape(len(self.kept), -1)

    def carry_out(self, helm, orders) -> None:
        """The orders tasking left, in the order it left them."""
        waiting, orders.waiting = orders.waiting, []
        for order in waiting:
            what = order[0]
            if what == "tasked":
                helm.tasked(order[1])
            elif what == "engage":
                named, seen = order[1], order[2]
                if helm.engage(named, seen):
                    self.say("flying_with", controller=named)
                else:
                    self.say("no_such_controller", asked=named)
            elif what == "tune":
                controller, parameter, value = order[1], order[2], order[3]
                took = helm.tune(str(controller), str(parameter), float(value))
                self.say("tuned" if took else "not_tuned", controller=controller,
                         parameter=parameter, value=value, by="the objective")
            elif what == "fly":
                helm.fly(order[1])
