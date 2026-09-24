"""The towing tank: the only geometry on this platform that is known.

Every other place is derived — a bathymetric survey interpolated between
fifteen-metre samples, a reef grown from a cover figure, a colour map worked
out from depth and hardness. That is fine for a reef and it is not fine for
checking the physics, because a drag number measured over a reef is a drag
number plus an unknown amount of terrain.
"""

import importlib.machinery
import importlib.util
import json
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _make_tank():
    loader = importlib.machinery.SourceFileLoader(
        "make_tank", str(HERE / "make-tank"))
    spec = importlib.util.spec_from_loader("make_tank", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_a_tank_is_closed_on_five_sides_and_open_at_the_top():
    tank = _make_tank()
    points, faces, low, high = tank.walls(109.73, 6.71, 3.05)
    assert len(points) == 8 and len(faces) == 5
    assert low == pytest.approx((-54.865, -3.355, -3.05))
    assert high == pytest.approx((54.865, 3.355, 0.0))
    # The rim is the water surface, so nothing is drawn above z = 0.
    assert max(p[2] for p in points) == pytest.approx(0.0)


def test_every_face_looks_into_the_tank():
    """A wall wound the wrong way is a wall a vehicle can see out through, and
    on a single-sided renderer it simply is not there. Five quads is few enough
    to get wrong by hand and few enough to check."""
    tank = _make_tank()
    points, faces, _, _ = tank.walls(40.0, 5.0, 2.0)
    p = np.array(points)
    middle = p.mean(axis=0)
    for face in faces:
        corners = p[list(face)]
        normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
        normal = normal / np.linalg.norm(normal)
        inwards = middle - corners.mean(axis=0)
        assert float(normal @ inwards) > 0, (face, normal)


def test_it_will_not_build_a_tank_whose_size_came_from_nowhere():
    """A number with no provenance gets cited back as though this platform had
    measured it. The whole reason the tank exists is that its three dimensions
    are published, so a tank whose size was chosen is a reef with extra steps.
    """
    source = (HERE / "make-tank").read_text()
    assert '"--from", dest="source", required=True' in source
    for needed in ("--long", "--wide", "--deep"):
        assert f'parse.add_argument("{needed.lstrip("-")}"' in source \
            or f'"{needed}", type=float, required=True' in source, needed


def test_the_record_says_it_was_read_and_not_fetched():
    tank = _make_tank()
    made = {"points": 8, "quads": 5, "lowest": -3.05, "highest": 0.0}
    site = tank.a_place("mhl-tank", 109.73, 6.71, 3.05, "a published tank", made)
    assert site["from"]["measured"] is True
    assert site["from"]["surveyed"] is False
    # The same word `tools/cite` uses, and for the same distinction: nobody
    # ran a query for these. Somebody read them.
    assert site["from"]["fetched"] is False
    assert site["reef"]["colonies"] == 0


def test_a_dive_begins_in_the_water_on_the_centre_line():
    tank = _make_tank()
    made = {"points": 8, "quads": 5, "lowest": -3.05, "highest": 0.0}
    site = tank.a_place("mhl-tank", 109.73, 6.71, 3.05, "a published tank", made)
    x, y, z = site["beginAt"]
    assert y == 0.0
    assert -3.05 < z < 0.0, z
    assert -54.865 < x < 54.865, x
    # And the steady section it starts at is inside the tank, both ends.
    tow = site["tow"]
    assert -54.865 < tow["steadyFromM"] < tow["steadyToM"] < 54.865
    assert tow["steadyLengthM"] > 0.5 * 109.73 * 0.5


def test_only_the_held_part_of_a_run_is_a_measurement():
    """A carriage accelerates, holds and decelerates. A drag number averaged
    through the acceleration is not a drag number."""
    tank = _make_tank()
    assert 0.0 < tank.STEADY_FROM < tank.STEADY_TO < 1.0
    assert tank.STEADY_FROM >= 0.1 and tank.STEADY_TO <= 0.9


def test_rebuild_knows_how_to_replay_one():
    """A place carries its own copy of how it was built, and tools/rebuild
    replays it in dependency order. A tank built by a tool rebuild has never
    heard of is a place that cannot be built again."""
    source = (HERE / "rebuild").read_text()
    assert '"make-tank"' in source
    order = source[source.index("IN_ORDER"):source.index("HERE =")]
    assert order.index('"make-site"') < order.index('"make-tank"')
