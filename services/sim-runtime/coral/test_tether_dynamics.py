"""The tether as a moving cable, and the three ways it fails a dive.

No vehicle: the cable's wet end is moved by hand, which is what a vehicle does
to it, and the cable system is asked what happened.
"""

import math

import numpy as np

from systems.place import Place
from systems.tether import TetherSystem, Umbilical

FLOOR = -1.0
# A pile: from the sand up through the surface, as a jetty's is. A cable can
# slide over a rock whose top is under water; it cannot slide over this.
PILLAR = (0.0, 0.0, 0.08)        # x, y, radius


class Ground:
    """A flat floor with an optional pillar standing on it."""

    def __init__(self, pillar=None, top=0.3):
        self.pillar = pillar
        self.top = top

    def under_many(self, x, y):
        return np.array([self.under(a, b) for a, b in zip(np.atleast_1d(x), np.atleast_1d(y))])

    def normal_many(self, x, y):
        return np.array([self.normal(a, b) for a, b in zip(np.atleast_1d(x), np.atleast_1d(y))])

    def under(self, x, y):
        if self.pillar is not None:
            px, py, r = self.pillar
            if (x - px) ** 2 + (y - py) ** 2 < r * r:
                return self.top
        return FLOOR

    def normal(self, x, y):
        if self.pillar is not None:
            px, py, r = self.pillar
            d = math.hypot(x - px, y - py)
            if d < r + 0.01:
                return np.array([(x - px) / max(d, 1e-9), (y - py) / max(d, 1e-9), 0.0])
        return np.array([0.0, 0.0, 1.0])


def a_place(pillar=None):
    place = Place()
    place.seabed = Ground(pillar)
    return place


def still(points):
    return np.zeros_like(points)


def a_cable(length=1.8, weight=-0.004, **more):
    return Umbilical({"lengthM": length, "diameterM": 0.005, "weightNPerM": weight, **more})


def run(cable, end, seconds, place, flow=still, dt=0.005):
    for _ in range(int(seconds / dt)):
        cable.step(dt, end, flow, place, 0.0)


def test_a_floating_cable_lies_above_the_line_between_its_ends_and_a_heavy_one_below():
    for weight, above in ((-0.02, True), (0.05, False)):
        cable = a_cable(weight=weight)
        rim, end = np.array([0.8, 0.0, -0.05]), np.array([-0.4, 0.0, -0.5])
        cable.start(rim, end)
        run(cable, end, 4.0, a_place())
        mid = cable.shape[len(cable.shape) // 2]
        line = 0.5 * (rim + end)
        assert (mid[2] > line[2]) == above


def test_slack_it_is_never_longer_than_it_is():
    cable = a_cable()
    cable.start([0.8, 0.0, -0.05], [0.0, 0.0, -0.4])
    run(cable, np.array([0.0, 0.0, -0.4]), 3.0, a_place())
    assert cable.path_m <= 1.8 * 1.005
    assert cable.tension_n < 0.5


def test_out_of_reach_it_pulls_the_vehicle_back_towards_the_rim():
    cable = a_cable(length=1.0)
    rim = np.array([0.0, 0.0, -0.05])
    cable.start(rim, [0.9, 0.0, -0.3])
    run(cable, np.array([1.2, 0.0, -0.3]), 1.0, a_place())
    assert cable.tension_n > 5.0
    assert cable.force[0] < 0.0, "back towards the rim"


def test_a_current_streams_it_downstream():
    cable = a_cable(weight=0.0)
    cable.start([0.0, 0.0, -0.05], [0.0, 0.0, -1.0 + 0.2])
    run(cable, np.array([0.0, 0.0, -0.8]), 6.0, a_place(),
        flow=lambda p: np.tile([0.15, 0.0, 0.0], (len(p), 1)))
    assert cable.shape[len(cable.shape) // 2][0] > 0.1


def test_it_never_goes_through_the_floor_or_the_rock():
    cable = a_cable(weight=0.2)
    cable.start([0.8, 0.0, -0.05], [-0.6, 0.0, -0.9])
    place = a_place(PILLAR)
    run(cable, np.array([-0.6, 0.0, -0.9]), 4.0, place)
    for x, y, z in cable.shape[1:-1]:
        assert z >= place.seabed.under(x, y) - 1e-6


def circling(turns, sense=1.0, seconds_a_turn=12.0, radius=0.3, dt=0.005, top=0.3, can_push=8.0):
    """The wet end flown round the pillar at depth, from beside the rim, by
    something that pushes like a small vehicle: it goes where it is steered
    unless the cable pulls harder than it can push, and then it stops."""
    cable = a_cable(length=2.2, weight=0.01)
    place = a_place(PILLAR)
    place.seabed.top = top
    rim = np.array([0.9, 0.0, -0.05])
    system = TetherSystem(dt, np.zeros(3), can_push_n=can_push, rocks={"pillar": PILLAR[:2]},
                          say=lambda *a, **k: None)
    end = np.array([radius, 0.0, -0.6])
    cable.start(rim, end)
    run(cable, end, 2.0, place)
    t, judged, angle = 0.0, -1.0, 0.0
    speed = 2.0 * math.pi / seconds_a_turn
    while abs(angle) < 2.0 * math.pi * abs(turns) and t < 4 * abs(turns) * seconds_a_turn:
        free = max(0.0, 1.0 - cable.tension_n / can_push)
        angle += sense * speed * dt * free
        end = np.array([radius * math.cos(angle), radius * math.sin(angle), -0.6])
        cable.step(dt, end, still, place, 0.0)
        t += dt
        if t - judged >= 0.25:
            system.judge(cable, place, 0.25)
            judged = t
            if cable.verdict:
                break
    return cable


def test_wound_round_a_pile_it_is_fouled():
    """The REACT test: pulled as tight as it can go without passing through
    the pile, the cable is longer than what is paid out."""
    cable = circling(2.5)
    assert cable.verdict in ("wrapped", "held"), cable.said()["fouled"]
    assert abs(cable.winding["pillar"]) > 1.0
    assert cable.verdict == "wrapped" or cable.taut_path_m > cable.length_m


def test_half_way_round_and_back_it_is_not():
    """A cable that has been round half of a rock and come back is wound
    nowhere."""
    there = circling(0.5)
    assert there.verdict is None


def test_pulled_past_its_breaking_load_it_parts():
    cable = a_cable(length=1.0, breakingN=50.0)
    system = TetherSystem(0.005, np.zeros(3), can_push_n=8.0, rocks={}, say=lambda *a, **k: None)
    cable.start([0.0, 0.0, -0.05], [0.9, 0.0, -0.3])
    run(cable, np.array([1.3, 0.0, -0.3]), 0.5, a_place())
    system.judge(cable, a_place(), 0.25)
    assert cable.verdict == "parted"
