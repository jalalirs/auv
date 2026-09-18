"""What a fish is shaped like."""

import numpy as np
import pytest

from coral import fishform, life


@pytest.mark.parametrize("plan", sorted(fishform.PLANS))
def test_a_body_is_a_metre_long_facing_forwards(plan):
    points, _ = fishform.body(plan)
    assert abs(float(np.ptp(points[:, 0])) - 1.0) < 1e-5
    # Centred on its own length, so scaling it scales about the middle.
    assert abs(float(points[:, 0].mean())) < 0.2


@pytest.mark.parametrize("plan", sorted(fishform.PLANS))
def test_the_faces_are_faces(plan):
    points, faces = fishform.body(plan)
    assert faces.min() >= 0 and faces.max() < len(points)
    assert (faces[:, 0] != faces[:, 1]).all()


def test_the_plans_are_actually_different_shapes():
    """A fish at three metres through this water is a silhouette, and the
    silhouette is the whole reason there are three of these."""
    deep = {p: float(np.ptp(fishform.body(p)[0][:, 2])) for p in fishform.PLANS}
    assert deep["deep"] > deep["fusiform"] > deep["elongate"]


def test_a_fish_is_taller_than_it_is_wide():
    """Almost all of them are. A body of revolution reads as a sausage."""
    for plan in fishform.PLANS:
        points, _ = fishform.body(plan)
        assert np.ptp(points[:, 2]) > np.ptp(points[:, 1])


def test_every_group_has_a_plan_and_a_colour():
    for group in life.GROUPS:
        assert fishform.OF_GROUP[group] in fishform.PLANS
        assert group in fishform.COLOURS


def test_a_colour_is_inside_the_range_its_group_covers():
    rng = np.random.default_rng(3)
    for group, (low, high) in fishform.COLOURS.items():
        for _ in range(8):
            got = fishform.a_colour(group, rng)
            assert all(a <= c <= b for a, b, c in zip(low, high, got)), (group, got)


def test_a_school_is_not_one_colour():
    rng = np.random.default_rng(5)
    drawn = {fishform.a_colour("snapper", rng) for _ in range(10)}
    assert len(drawn) > 1


def test_swimming_forwards_does_not_turn_the_body():
    assert np.allclose(fishform.facing((1.0, 0.0, 0.0)), (1.0, 0.0, 0.0, 0.0),
                       atol=1e-6)


def test_a_fish_faces_the_way_it_is_going():
    for going in ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.4, -0.3, 0.2)):
        w, x, y, z = fishform.facing(going)
        # Turn +x by the quaternion and it should point along `going`.
        nose = np.array([1.0, 0.0, 0.0])
        q = np.array([x, y, z])
        turned = (nose * (w * w - q @ q) + 2 * q * (q @ nose)
                  + 2 * w * np.cross(q, nose))
        want = np.array(going) / np.linalg.norm(going)
        assert np.allclose(turned, want, atol=1e-5), (going, turned)


def test_a_fish_that_is_not_moving_is_not_turned_to_nothing():
    """A quaternion of zeros is not a rotation, and the renderer draws whatever
    that turns out to be."""
    got = fishform.facing((0.0, 0.0, 0.0))
    assert abs(np.linalg.norm(got) - 1.0) < 1e-6


def test_a_fish_does_not_roll():
    """It does, and a fish that rolls in a flocking model rolls because the
    arithmetic wobbled, which reads as a dying fish rather than a swimming one."""
    w, x, y, z = fishform.facing((0.3, 0.9, -0.2))
    up = np.array([0.0, 0.0, 1.0])
    q = np.array([x, y, z])
    turned = (up * (w * w - q @ q) + 2 * q * (q @ up) + 2 * w * np.cross(q, up))
    assert turned[2] > 0.9, turned
