"""A tank's glass, square or round: what is kept in, and how far a beam goes."""

import numpy as np

from systems.glass import Glass, held_in, out_through


def round_tank():
    return Glass([-5.0, -5.0, -14.0], [5.0, 5.0, 0.0], round=(0.0, 0.0, 5.0))


def test_a_glass_is_still_its_box():
    low, high = round_tank()
    assert low[0] == -5.0 and high[2] == 0.0
    low, high = Glass([-1, -0.5, -1], [1, 0.5, 0])
    assert high[1] == 0.5


def test_round_glass_holds_a_point_in_the_corner_of_its_box():
    """A square box's corner is outside a round tank: (4.5, 4.5) is 6.4 m out."""
    held, out, inward = held_in([[4.5, 4.5], [1.0, 0.0]], round_tank(), margin=0.2)
    assert out.tolist() == [True, False]
    assert abs(np.hypot(*held[0]) - 4.8) < 1e-9
    assert np.allclose(inward[0], -np.array([1.0, 1.0]) / np.sqrt(2.0))
    assert np.allclose(held[1], [1.0, 0.0])


def test_square_glass_is_held_as_before():
    held, out, inward = held_in([[1.2, 0.0]], Glass([-1, -0.5, -1], [1, 0.5, 0]), margin=0.1)
    assert out[0] and np.allclose(held[0], [0.9, 0.0]) and np.allclose(inward[0], [-1.0, 0.0])


def test_a_beam_from_the_middle_meets_round_glass_at_its_radius():
    t = out_through(np.array([0.0, 0.0, -5.0]), np.array([0.6, 0.8, 0.0]), round_tank())
    assert abs(t - 5.0) < 1e-9
    t = out_through(np.array([3.0, 0.0, -5.0]), np.array([1.0, 0.0, 0.0]), round_tank())
    assert abs(t - 2.0) < 1e-9


def test_the_vehicle_stops_at_round_glass():
    from systems import contact
    from systems.contact import Contacts
    from systems.place import Place
    from systems.vehicle import Vehicle

    class Body:
        mass = 4.0

        def effective_mass(self, submerged=1.0):
            return np.array([4.0, 4.0, 4.0, 0.1, 0.1, 0.1])

    place = Place()
    place.interior = round_tank()
    v = Vehicle(Body(), np.array([3.5, 3.5, -5.0]))  # 4.95 m out, past 5 - 0.2
    v.half_width = 0.2
    v.velocity = np.array([0.3, 0.3, 0.0, 0.0, 0.0, 0.0])
    said = []
    contact.keep_inside_the_glass(v, place, Contacts(), lambda kind, **d: said.append(kind))
    assert abs(np.hypot(*v.position[:2]) - 4.8) < 1e-9
    outward = np.dot(v.velocity[:2], v.position[:2] / np.hypot(*v.position[:2]))
    assert outward <= 0.0 and said == ["touched_the_glass"]
