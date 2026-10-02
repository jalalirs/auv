"""What the thrusters actually do with what they were asked.

Reads    asked (the helm's command), faults; the task at the start of the tick
Writes   thrust (the commands the thrusters get), power (the battery)

Asked is not given. A thruster that has failed produces nothing, whatever it
is asked for; the allocator does not know, which is the point — the vehicle is
now asymmetric and the controller has to cope. A flat battery is a vehicle
with no thrusters. What the thrusters draw is taken from the battery here, and
a vehicle sitting on its dock has it put back.

When propellers are drawn turning (r6 item 2), their speed is read from here:
the command the thruster got, not the one the controller wished for.
"""

from __future__ import annotations

import numpy as np

from engine import System


class Thrust:
    """The commands the thrusters got, and how fast their propellers turn.

    A propeller's thrust goes as the square of its speed (the propeller law,
    thrust = K_T ρ n² D⁴ at a fixed advance), and thrust here is linear in
    the command, so the speed is the full speed times the square root of the
    command, signed. The full speed is the vehicle package's `maxRpm`, or a
    T200's 3,600 rpm at 16 V when the package does not say — and says so in
    `rpm_from`.
    """

    ASSUMED_RPM = 3600.0

    def __init__(self, thrusters: int) -> None:
        self.commands = np.zeros(int(thrusters))
        self.max_rpm = np.full(int(thrusters), self.ASSUMED_RPM)
        self.rpm_from = "assumed: a Blue Robotics T200's 3,600 rpm at 16 V"
        self.rpm = np.zeros(int(thrusters))
        # Where each propeller is in its turn, radians, on simulated time: so
        # the blades drawn in a frame are where they were at that moment of
        # the dive, however fast or slow it is being drawn.
        self.angle = np.zeros(int(thrusters))
        self.diameter_m = None

    def read_the_package(self, dynamics) -> None:
        """What the vehicle package says about its propellers, if anything:
        `maxRpm`, `propellerDiameterM` (which is what decides whether they are
        drawn), and `rpmFrom`, where the speed came from."""
        import json
        import pathlib

        self.diameter_m = None
        try:
            units = json.loads(pathlib.Path(dynamics).read_text()).get("thrusters") or {}
        except Exception:
            return
        if units.get("maxRpm"):
            self.max_rpm = np.full(len(self.commands), float(units["maxRpm"]))
            self.rpm_from = str(units.get("rpmFrom") or "the vehicle package")
        if units.get("propellerDiameterM"):
            self.diameter_m = float(units["propellerDiameterM"])

    def turn(self, dt: float) -> None:
        c = np.clip(np.asarray(self.commands, dtype=float), -1.0, 1.0)
        self.rpm = self.max_rpm * np.sign(c) * np.sqrt(np.abs(c))
        self.angle = (self.angle + self.rpm / 60.0 * 2.0 * np.pi * dt) % (2.0 * np.pi)


class Power:
    def __init__(self) -> None:
        self.battery = None
        self.charging = False


class ThrustersSystem(System):
    name = "thrusters"
    reads = ("asked", "faults")
    before = ("task",)
    writes = ("thrust", "power")

    def __init__(self, dt: float, dock_watts: float) -> None:
        self.dt = float(dt)
        self.dock_watts = float(dock_watts)

    def step(self, world) -> None:
        thrust, power = world.thrust, world.power
        thrust.commands = world.asked.commands
        dead = world.faults.dead
        if dead:
            for one_of_them in dead:
                if one_of_them < len(thrust.commands):
                    thrust.commands[one_of_them] = 0.0
        battery = power.battery
        if battery is not None:
            battery.draw(thrust.commands if not battery.flat else np.zeros_like(thrust.commands), self.dt)
            if battery.flat:
                thrust.commands = np.zeros_like(thrust.commands)
        self.charge_at_the_dock(power, world.task.task)
        thrust.turn(self.dt)

    def charge_at_the_dock(self, power, task) -> None:
        """On the station, the battery fills. That is what a dock is for."""
        power.charging = False
        if power.battery is None or task is None:
            return
        from tasks import Dock, Mission, Wait

        stage = task.stage if isinstance(task, Mission) else task
        docked = False
        if isinstance(task, Mission):
            docked = any(one.get("kind") == "dock" and one.get("achieved", {}).get("docked")
                         for one in task.finished)
        if isinstance(stage, Wait) and docked:
            power.charging = True
            power.battery.charge(self.dock_watts, self.dt)
        elif isinstance(stage, Dock) and stage.docked:
            power.charging = True
            power.battery.charge(self.dock_watts, self.dt)
