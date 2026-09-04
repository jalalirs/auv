"""What a dive costs, and what happens when it runs out.

Nothing in a vehicle cost anything until now, so nothing had to be decided:
a controller that flew twice as hard to do the same job looked exactly as
good, and a dive could go anywhere because it could always come back. Energy
is what makes a mission a mission.

The model is small and every number in it comes from the vehicle package
rather than from here. A hotel load the vehicle draws whether or not it is
moving — electronics, camera, lights — and the thrusters on top of it, whose
power goes as thrust to the three halves the way a propeller's does. Charge
comes back the same way at a dock.

Flat is flat. There is no reserve that quietly keeps the lights on: the
thrusters stop, and the hull does whatever its buoyancy says it does, which
for a BlueROV2 trimmed slightly heavy is settle onto the bottom.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

WATT_SECONDS_PER_WH = 3600.0


class Battery:
    """A pack, its draw, and what is left of it."""

    def __init__(self, capacity_wh: float, hotel_w: float, thruster_max_w: float,
                 exponent: float = 1.5, voltage: float = 14.8,
                 reserve: float = 0.1, charge: float = 1.0) -> None:
        self.capacity_wh = float(capacity_wh)
        self.hotel_w = float(hotel_w)
        self.thruster_max_w = float(thruster_max_w)
        self.exponent = float(exponent)
        self.voltage = float(voltage)
        # What the vehicle is expected to keep back for getting home. It is not
        # taken away from it — a reserve nothing may spend is a smaller battery
        # — it is the line the failsafe watches.
        self.reserve = float(reserve)
        self.remaining_wh = self.capacity_wh * float(charge)
        self.spent_wh = 0.0
        self.watts = 0.0
        self.flat = False

    @classmethod
    def of(cls, package: pathlib.Path):
        """The battery a vehicle package declares, or nothing if it declares none."""
        try:
            described = json.loads((package / "dynamics.json").read_text())
        except Exception:
            return None
        power = described.get("power")
        if not isinstance(power, dict) or not power.get("capacityWh"):
            return None
        return cls(capacity_wh=float(power["capacityWh"]),
                   hotel_w=float(power.get("hotelW", 0.0)),
                   thruster_max_w=float(power.get("thrusterMaxW", 0.0)),
                   exponent=float(power.get("powerExponent", 1.5)),
                   voltage=float(power.get("nominalVoltage", 12.0)),
                   reserve=float(power.get("reserveFraction", 0.1)))

    # ── what it does ─────────────────────────────────────────────────────────

    def draw(self, commands, dt: float) -> float:
        """Spend a step's worth. Returns the watts drawn while doing it."""
        thrusters = float(np.sum(np.abs(np.asarray(commands, dtype=float)) ** self.exponent))
        self.watts = self.hotel_w + self.thruster_max_w * thrusters
        if self.flat:
            self.watts = 0.0
            return 0.0
        spent = self.watts * dt / WATT_SECONDS_PER_WH
        if spent >= self.remaining_wh:
            spent = self.remaining_wh
            self.flat = True
        self.remaining_wh -= spent
        self.spent_wh += spent
        return self.watts

    def charge(self, watts: float, dt: float) -> float:
        """Take charge from a dock. Returns the watt-hours actually taken."""
        room = self.capacity_wh - self.remaining_wh
        taken = min(room, max(0.0, watts) * dt / WATT_SECONDS_PER_WH)
        self.remaining_wh += taken
        if taken > 0.0:
            self.flat = False
        return taken

    # ── what it is worth ─────────────────────────────────────────────────────

    @property
    def fraction(self) -> float:
        return 0.0 if self.capacity_wh <= 0 else self.remaining_wh / self.capacity_wh

    def endurance_s(self, watts: float | None = None) -> float:
        """How long what is left lasts at a draw, in seconds."""
        rate = self.watts if watts is None else watts
        if rate <= 1e-6:
            return float("inf")
        return self.remaining_wh * WATT_SECONDS_PER_WH / rate

    def enough_for(self, seconds: float, watts: float | None = None) -> bool:
        """Whether what is left covers a journey of this long, reserve kept back."""
        rate = max(self.hotel_w, self.watts if watts is None else watts)
        need = rate * seconds / WATT_SECONDS_PER_WH
        return (self.remaining_wh - self.capacity_wh * self.reserve) >= need

    def said(self) -> dict:
        return {"capacityWh": round(self.capacity_wh, 1),
                "remainingWh": round(self.remaining_wh, 2),
                "spentWh": round(self.spent_wh, 3),
                "fraction": round(self.fraction, 4),
                "watts": round(self.watts, 1),
                "volts": round(self.voltage * (0.85 + 0.15 * self.fraction), 2),
                "enduranceS": None if self.watts <= 1e-6 else round(self.endurance_s(), 0),
                "reserveFraction": self.reserve,
                "flat": self.flat}
