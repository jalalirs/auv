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


LAYER = """#usda 1.0
def PointInstancer "Coral"
{
    point3f[] positions = [(1, 2, -5.02), (10.5, -3, -6), (40, 40, -7)]
    int[] protoIndices = [0, 2, 1]
    float3[] scales = [(0.3, 0.3, 0.2), (0.25, 0.25, 0.9), (1.1, 1.1, 0.4)]
    quath[] orientations = [(1, 0, 0, 0), (1, 0, 0, 0), (1, 0, 0, 0)]
}
"""


def test_a_reef_drawn_as_a_layer_is_read_back_as_its_colonies(tmp_path):
    """A surveyed reef lists no colonies; it draws them, prototypes a unit
    across and a unit high scaled to each. Those are the colonies."""
    from systems.coral import colonies_of

    (tmp_path / "coral.usda").write_text(LAYER)
    described = {"layers": {"coral": "coral.usda"}, "reef": {"swaysWith": {"fan": [2]}}}
    c = colonies_of(described, lambda x, y: -5.0, tmp_path)
    assert len(c) == 3
    assert np.allclose(c.at[1], [10.5, -3.0, -6.0])
    assert np.allclose(c.radius, [0.3, 0.25, 1.1]) and np.allclose(c.height, [0.2, 0.9, 0.4])
    assert list(c.kind) == ["massive", "fan", "massive"]
    assert list(c.solid()) == [True, False, True], "a fan bends"


def test_near_finds_what_is_near_and_not_the_rest():
    """Asked about a point, the colonies within reach of it — and the whole
    reef is never what is asked."""
    rng = np.random.default_rng(0)
    c = Colonies()
    c.at = np.column_stack([rng.uniform(-200, 200, (20000, 2)), np.full(20000, -8.0)])
    c.size = rng.uniform(0.1, 0.6, 20000)
    c.kind = np.array(["massive"] * 20000, dtype=object)
    found = set(c.near([12.0, -7.0], 3.0).tolist())
    within = np.flatnonzero(np.hypot(c.at[:, 0] - 12.0, c.at[:, 1] + 7.0) < 3.0 + c.radius)
    assert set(within.tolist()) <= found
    assert len(found) < 200


def test_polyps_are_out_at_night_and_in_by_day_and_in_when_disturbed():
    """Stony coral feeds at night; soft coral by day; any closes at a touch or
    in moving water, and opens again slowly."""
    from types import SimpleNamespace

    from systems.coral import CoralSystem, _fresh

    c = Colonies()
    c.at = np.array([[0.0, 0.0, -1.0], [0.3, 0.0, -1.0]])
    c.size = np.array([0.2, 0.2])
    c.height = c.size.copy()
    c.kind = np.array(["brain", "plume"], dtype=object)
    c.prim = [None, None]
    _fresh(c, 2)
    still = SimpleNamespace(efflux=np.zeros(1), at=lambda p: np.zeros((len(p), 3)))
    world = SimpleNamespace(coral=c, clock=SimpleNamespace(simulated=0.0), light=SimpleNamespace(level=0.0, day_s=240.0),
                            wash=still, vehicle=SimpleNamespace(position=np.array([5.0, 5.0, -0.5])),
                            contacts=SimpleNamespace(coral_hits=[]))
    corals = CoralSystem(lambda *a, **k: None)
    corals.the_polyps(world)
    assert c.polyps.tolist() == [1.0, 0.0], "night: the brain coral's out, the soft coral's in"
    # Touched at night: the brain coral closes within seconds.
    world.contacts.coral_hits.append({"colony": 0, "impulseNs": 0.1, "speedMs": 0.1})
    for k in range(1, 9):
        world.clock.simulated = 0.5 * k
        corals.the_polyps(world)
    assert c.polyps[0] < 0.4, "closing within seconds of the touch"
    # Left alone, it opens again, slowly (the strike stays in the record).
    for k in range(12, 200):
        world.clock.simulated = 0.5 * k
        corals.the_polyps(world)
    assert c.polyps[0] > 0.6
