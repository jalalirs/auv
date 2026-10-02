"""One clock for the day: the light the fish keep, and the lamps that are drawn by it."""

import math

from systems.light import Light, daylight, lamps


def test_noon_is_bright_and_midnight_dark():
    assert daylight(12.0) > 0.99 and daylight(0.0) < 0.01


def test_dawn_and_dusk_are_ramps_not_switches():
    assert 0.2 < daylight(6.0) < 0.8 and 0.2 < daylight(18.5) < 0.8


def test_a_tanks_lights_keep_their_schedule():
    assert lamps(8.0) == 0.0 and lamps(12.0) == 1.0 and lamps(22.0) == 0.0
    assert 0.0 < lamps(9.25) < 1.0


def test_a_short_day_comes_round_in_the_seconds_asked():
    light = Light()
    light.set_for({"localTimeH": 18.0, "dayLengthS": 240.0}, indoors=False)
    light.at(30.0)                      # an eighth of a day on: three hours
    assert math.isclose(light.hour, 21.0)
    assert light.level < 0.05


def test_lamps_follow_the_clock_and_the_room_its_window():
    from draw.light import Lights

    class Attribute:
        def __init__(self, v):
            self.v = v

        def Get(self):
            return self.v

        def Set(self, v):
            self.v = v

    class Prim:
        def __init__(self, v):
            self.a = Attribute(v)

        def IsValid(self):
            return True

        def GetAttribute(self, name):
            return self.a

    class Stage:
        def __init__(self):
            self.prims = {"/World/LedSouth": Prim(1000.0), "/World/Daylight": Prim(450.0),
                          "/World/FillRoom": Prim(1100.0), "/World/Ceiling": Prim(500.0)}

        def GetPrimAtPath(self, path):
            return self.prims.get(path)

    stage, light, drawn = Stage(), Light(), Lights()
    light.set_for({"localTimeH": 23.0}, indoors=True)
    drawn.set(stage, light)
    assert stage.prims["/World/LedSouth"].a.v == 0.0
    assert stage.prims["/World/Daylight"].a.v < 10.0
    assert abs(stage.prims["/World/FillRoom"].a.v - 0.15 * 1100.0) < 1e-6, "the fills dim, not out"
    assert abs(stage.prims["/World/Ceiling"].a.v - 0.15 * 500.0) < 1e-6, "the ceiling too: a night tank is dark"
    light.set_for({"localTimeH": 13.0}, indoors=True)
    drawn.set(stage, light)
    assert stage.prims["/World/LedSouth"].a.v == 1000.0
