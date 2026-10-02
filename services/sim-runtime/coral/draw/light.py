"""The lights the place carries, set by the dive's day.

Reads    light (systems/light.py): the hour, and the light as a share of full day

The same clock the fish keep. A tank's reef lights follow their schedule —
on at nine, off at nine, ramped — and the daylight coming into the room
follows the sun. The room's own lights — the ceiling and the fills that light
the room for the picture — go with the daylight, down to a sixth so that a
night is dark and still readable. (The ceiling was once left on all night, on
the guess that somebody at the bench turns it on; it is the brightest thing in
the room, and a dusk film with it on never got dark.) A dive started at dusk
is drawn at dusk, and the fish in it behave as at dusk.

What a lamp is called is the place's business; these are the names
tools/make-aquarium gives them, and a place without them is left alone.
"""

from __future__ import annotations

from systems.light import daylight

# Which lights follow which clock: the reef lights the tank's schedule, the
# window the sky.
#
# The reef lights are two things: the light each bar casts, and the bar's own
# glowing face, which a path tracer treats as a light in its own right. With
# only the first switched off, the faces went on lighting the tank all night.
ON_THE_SCHEDULE = ("/World/LedSouth", "/World/LedNorth",
                   ("/World/Looks/LedPanel/M", "inputs:emissive_intensity"),
                   ("/World/Looks/LedPanel/S", "inputs:emissiveColor"))
FROM_THE_SKY = ("/World/Daylight",)
WITH_THE_SKY_AT_LEAST = {"/World/Ceiling": 0.15, "/World/FillRoom": 0.15, "/World/FillEnd": 0.15}

# The water's veil — the light it scatters back towards the lens, which the
# renderer adds as a fog (water.py) — is set once, for the light the place has
# when the dive opens. It is that light scattered, so it follows that light:
# the reef lights, or the room's at their least. Left alone it lit everything
# seen through the water at full day, and a tank at midnight looked like noon.
VEIL = "/rtx/fog/fogColorIntensity"


class Lights:
    def __init__(self) -> None:
        self.found = None          # path -> (intensity attribute, intensity as built)
        self.veil = None           # the water's veil as the place set it

    def find(self, stage) -> None:
        self.found = {}
        for one in ON_THE_SCHEDULE + FROM_THE_SKY + tuple(WITH_THE_SKY_AT_LEAST):
            path, name = one if isinstance(one, tuple) else (one, "inputs:intensity")
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
            attribute = prim.GetAttribute(name)
            if attribute and attribute.Get() is not None:
                self.found[one] = (attribute, attribute.Get())

    def set(self, stage, light, say=None, settings=None) -> None:
        if self.found is None:
            self.find(stage)
            if settings is not None and settings.get(VEIL) is not None:
                self.veil = float(settings.get(VEIL))
            if say is not None:
                say("lamps_follow_the_day", lights=sorted("/".join(one) if isinstance(one, tuple) else one
                                                          for one in self.found), hour=round(light.hour, 2))
        for one, (attribute, built) in self.found.items():
            if one in ON_THE_SCHEDULE:
                share = light.level
            else:
                share = max(daylight(light.hour), WITH_THE_SKY_AT_LEAST.get(one, 0.0))
            share = max(0.0, min(1.0, share))
            # An intensity is a number; a glowing face's colour is three, scaled alike.
            attribute.Set(float(built) * share if isinstance(built, (int, float)) else built * share)
        if self.veil is not None:
            in_the_water = max(light.level, daylight(light.hour), min(WITH_THE_SKY_AT_LEAST.values()))
            settings.set(VEIL, self.veil * max(0.0, min(1.0, in_the_water)))
