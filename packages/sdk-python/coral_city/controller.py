"""What a controller is.

The interface is the runtime's own — literally: `Observation`, `Command` and
`Parameter` are declared once, in `coral_city.interface`, and the simulation
runtime imports that same file. A controller written here is not an
approximation of one that runs on the platform; it is one. The differences
are in what fills the observation: on a dive, sensors; in the tank, the
physics or the same sensor path, as you choose.

Frames and units are the vehicle's: body frame with x forward, y to starboard,
z up; a wrench is surge, sway, heave, roll, pitch, yaw; metres, radians,
seconds, newtons.
"""

from __future__ import annotations

from .interface import Command, Observation, Parameter

__all__ = ["Command", "Controller", "Observation", "Parameter"]


class Controller:
    """Subclass this. Say which vehicle it is for, fill in observe(), and
    declare what may be moved."""

    name: str = "controller"
    says: str = ""
    # Which vehicle this controller is written for, by its catalogue slug.
    # Checked against the vehicle's description before the controller is
    # deployed, so that one asking for a sensor the vehicle lacks is refused
    # here rather than left waiting on a dive for a message that never comes.
    vehicle: str = "bluerov2"
    # What it commands with: "wrench" (allocated by the vehicle) or "thrusters".
    commands: str = "wrench"
    # Sensor kinds it cannot do without, beyond depth, attitude and rates.
    needs: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.parameters: dict[str, Parameter] = {}
        from . import vehicles
        self.described = vehicles.load(self.vehicle)

    def declare(self, name: str, value: float, low: float, high: float,
                unit: str = "", says: str = "") -> Parameter:
        parameter = Parameter(name, float(value), float(low), float(high), unit, says)
        self.parameters[name] = parameter
        return parameter

    def __getitem__(self, name: str) -> float:
        return self.parameters[name].value

    def tune(self, name: str, value: float) -> bool:
        parameter = self.parameters.get(name)
        if parameter is None:
            return False
        parameter.set(value)
        return True

    # ── what a subclass fills in ─────────────────────────────────────────────

    def engage(self, seen: Observation) -> None:
        """Told it now has the vehicle, and where the vehicle is."""

    def observe(self, seen: Observation) -> Command:
        raise NotImplementedError

    def status(self) -> dict:
        return {}

    def describe(self) -> dict:
        return {"name": self.name, "kind": "external", "says": self.says,
                "vehicle": self.vehicle, "commands": self.commands,
                "parameters": [p.describe() for p in self.parameters.values()],
                "status": self.status()}
