"""Coral that stands in the vehicle's way and breaks when it should.

Checked against the number the break is taken from — Acropora cervicornis's
dynamic fracture strength, 20.8 MPa — and against what growth forms do: a
branching colony snaps, a brain coral does not, a soft coral bends.
"""

import numpy as np

from engine import Clock
from systems import contact
from systems.contact import Contacts
from systems.coral import BREAKING_STRESS, Colonies, CoralSystem, stress_of
from systems.place import Place
from systems.vehicle import Vehicle


class Body:
    def __init__(self, mass=4.0):
        self.mass = mass

    def effective_mass(self, submerged=1.0):
        return np.array([self.mass, self.mass, self.mass, 0.1, 0.1, 0.1])


def a_colony(kind, size=0.16):
    c = Colonies()
    c.at = np.array([[0.0, 0.0, -1.0]])
    c.size = np.array([size])
    c.kind = np.array([kind], dtype=object)
    c.prim = [None]
    c.height = c.size.copy()
    c.broken = np.zeros(1, dtype=bool)
    c.broken_at = np.full(1, np.nan)
    c.struck = np.zeros(1, dtype=int)
    c.brushed = np.zeros(1, dtype=int)
    c.worst_stress = np.zeros(1)
    c.torn_off = np.zeros(1, dtype=bool)
    c.smothered = np.zeros(1, dtype=int)
    return c


def driven_into(kind, speed, size=0.16, mass=4.0):
    """A four-kilogram hull driven along x into a colony at the height of its
    middle."""
    coral = a_colony(kind, size)
    v = Vehicle(Body(mass), [-0.4, 0.0, -1.0 + 0.5 * size])
    v.half_width, v.half_height = 0.17, 0.06
    v.velocity[0] = speed
    contacts, place, said = Contacts(), Place(), []

    class World:
        pass

    world = World()
    from systems.sediment import Sediment

    world.coral, world.contacts, world.clock = coral, contacts, Clock(0.005)
    world.sediment = Sediment()
    system = CoralSystem(lambda kind, **d: said.append((kind, d)))
    for _ in range(800):
        v.position += v.velocity[:3] * 0.005
        contact.keep_out_of_coral(v, coral, contacts, lambda *a, **k: None)
        system.step(world)
        world.clock.simulated += 0.005
    return coral, v, contacts, said


def test_a_stony_colony_stops_the_vehicle():
    coral, v, contacts, _ = driven_into("brain", 0.15)
    assert v.position[0] < 0.0, "it should not pass through"
    assert coral.struck[0] == 1 and len(contacts.strikes) == 1


def test_a_strike_is_recorded_with_its_speed_and_impulse():
    _, _, contacts, _ = driven_into("brain", 0.15)
    hit = contacts.strikes[0]
    assert abs(hit["speedMs"] - 0.15) < 0.01
    assert abs(hit["impulseNs"] - 4.0 * 0.15) < 0.05


def test_cruising_into_a_branching_colony_does_not_break_it():
    coral, _, _, _ = driven_into("branching", 0.15)
    assert not coral.broken[0]
    assert 0.0 < coral.worst_stress[0] < BREAKING_STRESS


def test_at_speed_it_snaps():
    coral, _, _, said = driven_into("branching", 0.3)
    assert coral.broken[0]
    assert coral.height[0] < coral.size[0]
    assert any(kind == "coral_broken" for kind, _ in said)


def test_a_brain_coral_does_not_break_whatever_hits_it():
    coral, _, _, _ = driven_into("brain", 0.6)
    assert not coral.broken[0]


def test_a_soft_coral_bends_out_of_the_way_and_is_brushed():
    coral, v, _, _ = driven_into("plume", 0.15)
    assert v.position[0] > 0.15, "it went through"
    assert coral.brushed[0] == 1 and coral.struck[0] == 0


def test_the_stress_is_the_order_the_skeleton_breaks_at():
    """A small vehicle at a quarter of a metre a second puts tens of
    megapascals on a tank frag's branches: the same order as the skeleton's
    strength, which is why it is the speed that matters."""
    stress = stress_of(4.0 * 0.25, 0.16, "branching", 0.16)
    assert 5e6 < stress < 1e8


def test_a_brain_coral_is_torn_off_its_rock_by_a_heavy_vehicle_and_not_a_light_one():
    """The rock under a colony is a tenth as strong as its skeleton (Madin &
    Connolly 2006): a massive colony does not snap, but a heavy enough blow
    levers it off its base."""
    light, _, _, _ = driven_into("brain", 0.4, size=0.1)        # four kilograms, the same colony
    assert not light.torn_off[0]

    heavy, v, _, said = driven_into("brain", 0.4, size=0.1, mass=40.0)   # Luna-sized, into a ten-centimetre colony
    assert heavy.torn_off[0]
    assert any(kind == "coral_torn_off" for kind, _ in said)


def test_sand_settling_on_a_colony_smothers_it_past_the_dose():
    """Harm from about 10 mg/cm² a day (Erftemeijer et al. 2012), as a rate:
    two milligrams a square centimetre in an hour is 48 a day."""
    from systems.coral import _judge

    coral, said = a_colony("brain"), []
    _judge(coral, np.array([2.0]), 3600.0, lambda kind, **d: said.append(kind))
    assert coral.smothered[0] == 1 and said == ["coral_smothered"]
    _judge(coral, np.array([3.0]), 3600.0, lambda kind, **d: said.append(kind))
    assert coral.smothered[0] == 2


def test_driven_into_the_glass_it_stops_comes_back_a_little_and_the_strike_is_recorded():
    """r6 item 4: a strike has a place, a speed and an impulse, and a hull that
    hits something hard under water comes back off it — a little."""
    from systems.contact import RESTITUTION, keep_inside_the_glass

    v = Vehicle(Body(), [0.95, 0.0, -0.5])
    v.half_width = 0.1
    v.velocity[0] = 0.3
    place, contacts = Place(), Contacts()
    place.interior = (np.array([-1.0, -0.5, -1.0]), np.array([1.0, 0.5, 0.0]))
    keep_inside_the_glass(v, place, contacts, lambda *a, **k: None)
    assert v.position[0] <= 0.9 + 1e-9
    assert np.isclose(v.velocity[0], -RESTITUTION * 0.3)
    hit = contacts.strikes[0]
    assert hit["what"] == "glass" and np.isclose(hit["speedMs"], 0.3) and hit["impulseNs"] > 0
