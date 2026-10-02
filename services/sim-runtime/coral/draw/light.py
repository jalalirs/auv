"""The lights the place carries, set by the dive's day.

Reads    light (systems/light.py): the hour, and the light as a share of full day

The same clock the fish keep. A tank's reef lights follow their schedule —
on at nine, off at nine, ramped — and the daylight coming into the room
follows the sun; the room's own ceiling and fill lights are left as they are,
because somebody working at the bench at night turns them on (assumed). A
dive started at dusk is drawn at dusk, and the fish in it behave as at dusk.

What a lamp is called is the place's business; these are the names
tools/make-aquarium gives them, and a place without them is left alone.
"""

from __future__ import annotations

from systems.light import daylight

# Which lights follow which clock: the reef lights the tank's schedule, the
# window the sky.
ON_THE_SCHEDULE = ("/World/LedSouth", "/World/LedNorth")
FROM_THE_SKY = ("/World/Daylight",)


class Lights:
    def __init__(self) -> None:
        self.found = None          # path -> (intensity attribute, intensity as built)

    def find(self, stage) -> None:
        self.found = {}
        for path in ON_THE_SCHEDULE + FROM_THE_SKY:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
            attribute = prim.GetAttribute("inputs:intensity")
            if attribute and attribute.Get() is not None:
                self.found[path] = (attribute, float(attribute.Get()))

    def set(self, stage, light) -> None:
        if self.found is None:
            self.find(stage)
        for path, (attribute, built) in self.found.items():
            share = light.level if path in ON_THE_SCHEDULE else daylight(light.hour)
            attribute.Set(float(built * max(0.0, min(1.0, share))))
