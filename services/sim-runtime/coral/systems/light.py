"""The day: what hour it is, and how much light there is.

Reads    the clock, at the start of the tick
Writes   light: the hour, and the light as a share of full day, 0..1

One clock for everything that cares what time it is. On a reef that is the
sun: a smooth dawn and dusk about six and half past six (assumed — the place's
latitude and date would give the real ones, NREL's solar position algorithm,
r6 item 9). In a tank it is the lights: on at nine, off at nine, ramped over
half an hour as a reef tank's controller does (assumed: the common hobby
schedule). The fish read it to decide whether they are awake, and later so do
the coral's polyps, the scene's lighting and the camera's exposure.

The dive says when it starts (`localTimeH`) and how long its day is
(`dayLengthS`, a real day unless it says otherwise — a dive that wants to see
dusk come in a minute asks for a short one).
"""

from __future__ import annotations

import math

from engine import System


def daylight(hour: float, rises: float = 6.0, sets: float = 18.5, twilight: float = 0.75) -> float:
    """How much light there is from the sky, 0..1, from the hour."""
    up = 0.5 + 0.5 * math.tanh((hour - rises) / (twilight / 2.0))
    down = 0.5 - 0.5 * math.tanh((hour - sets) / (twilight / 2.0))
    return float(max(0.0, min(1.0, up * down)))


def lamps(hour: float, on: float = 9.0, off: float = 21.0, ramp: float = 0.5) -> float:
    """How bright a tank's lights are, 0..1, on a schedule with ramps."""
    if hour < on or hour >= off + ramp:
        return 0.0
    if hour < on + ramp:
        return (hour - on) / ramp
    if hour >= off:
        return 1.0 - (hour - off) / ramp
    return 1.0


class Light:
    def __init__(self) -> None:
        self.starts_at_h = 11.0
        self.day_s = 86400.0
        self.indoors = False             # a tank: its lights, not the sky
        self.hour = self.starts_at_h
        self.level = daylight(self.hour)
        self.from_ = "assumed: a sunrise at six and a sunset at half past six"

    def set_for(self, parameters: dict, indoors: bool) -> None:
        """From the dive's conditions and whether the place is a room."""
        self.starts_at_h = float(parameters.get("localTimeH", 11.0)) % 24.0
        self.day_s = max(1.0, float(parameters.get("dayLengthS", 86400.0)))
        self.indoors = bool(indoors)
        self.from_ = ("assumed: a reef tank's lights, on at nine and off at nine with half-hour ramps"
                      if indoors else "assumed: a sunrise at six and a sunset at half past six")
        self.at(0.0)

    def at(self, simulated: float) -> None:
        self.hour = (self.starts_at_h + 24.0 * simulated / self.day_s) % 24.0
        self.level = lamps(self.hour) if self.indoors else daylight(self.hour)

    def said(self) -> dict:
        return {"hour": round(self.hour, 2), "light": round(self.level, 3),
                "dayLengthS": self.day_s, "indoors": self.indoors, "from": self.from_}


class LightSystem(System):
    name = "light"
    before = ("clock",)
    writes = ("light",)

    def step(self, world) -> None:
        world.light.at(world.clock.simulated)
