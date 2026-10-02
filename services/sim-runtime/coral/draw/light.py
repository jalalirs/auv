"""The lights the place carries, set by the dive's day.

Reads    light (systems/light.py): the hour, and the light as a share of full day

The same clock the fish keep. A tank's reef lights follow their schedule —
on at nine, off at nine, ramped — and the daylight coming into the room
follows the sun. The fill lights that light the room for the picture go with
the daylight, down to a sixth so that a night is dark and still readable; the
ceiling light is left on, because somebody at the bench at night turns it on
(assumed). A dive started at dusk is drawn at dusk, and the fish in it behave
as at dusk.

What a lamp is called is the place's business; these are the names
tools/make-aquarium gives them, and a place without them is left alone.
"""

from __future__ import annotations

from systems.light import daylight

# Which lights follow which clock: the reef lights the tank's schedule, the
# window the sky.
ON_THE_SCHEDULE = ("/World/LedSouth", "/World/LedNorth")
FROM_THE_SKY = ("/World/Daylight",)
WITH_THE_SKY_AT_LEAST = {"/World/FillRoom": 0.15, "/World/FillEnd": 0.15}


class Lights:
    def __init__(self) -> None:
        self.found = None          # path -> (intensity attribute, intensity as built)

    def find(self, stage) -> None:
        self.found = {}
        for path in ON_THE_SCHEDULE + FROM_THE_SKY + tuple(WITH_THE_SKY_AT_LEAST):
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
            attribute = prim.GetAttribute("inputs:intensity")
            if attribute and attribute.Get() is not None:
                self.found[path] = (attribute, float(attribute.Get()))

    def set(self, stage, light, say=None) -> None:
        if self.found is None:
            self.find(stage)
            if say is not None:
                say("lamps_follow_the_day", lights=sorted(self.found), hour=round(light.hour, 2))
        for path, (attribute, built) in self.found.items():
            if path in ON_THE_SCHEDULE:
                share = light.level
            else:
                share = max(daylight(light.hour), WITH_THE_SKY_AT_LEAST.get(path, 0.0))
            attribute.Set(float(built * max(0.0, min(1.0, share))))
