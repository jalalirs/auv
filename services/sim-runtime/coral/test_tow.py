"""A ship towing a side-scan fish: how deep it flies, and what it draws.

Flown in a flat place sixty metres deep with one boulder on it, built in the
test. What is checked is what anybody who has towed a fish knows: more cable
is deeper, more speed is shallower, and a boulder off to one side comes back
as a bright face and a shadow behind it.
"""

import json
import pathlib

import numpy as np
import pytest

from hydrodynamics import Allocator, Body, Hydrodynamics
from runner import Dive

ROOT = pathlib.Path(__file__).resolve().parents[3]
FISH = ROOT / "catalog/vehicles/edgetech-2300"
DEEP = -60.0
BOULDER = (60.0, -25.0, 4.0)          # x, y, radius: four metres round, three proud


@pytest.fixture(scope="module")
def place(tmp_path_factory):
    into = tmp_path_factory.mktemp("tow-place")
    n, across = 401, 400.0
    x = np.linspace(-across / 2, across / 2, n)
    X, Y = np.meshgrid(x, x)
    h = np.full((n, n), DEEP, dtype=np.float32)
    bx, by, r = BOULDER
    h[np.hypot(X - bx, Y - by) < r] = DEEP + 3.0
    h.astype("<f4").tofile(into / "seabed.f32")
    (into / "site.json").write_text(json.dumps({
        "name": "a flat place to tow over", "from": {"acrossMetres": across},
        "mesh": {"heightfield": {"file": "seabed.f32", "rows": n, "columns": n}}}))
    return into


def towed(place, speed_kn, cable_m, seconds, frequency=850):
    model = Hydrodynamics.from_package(FISH / "dynamics.json")
    brief = {"seed": 0, "durationSeconds": seconds, "vehiclePath": str(FISH),
             "initialState": {"positionM": [-60.0, 0.0, -20.0]},
             "objective": {"kind": "hold", "tow": {"speedKn": speed_kn, "headingDeg": 0.0,
                                                   "cableOutM": cable_m, "frequencykHz": frequency}},
             "cityPath": str(place), "conditions": {"kind": "constructed", "parameters": {}}}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"), lambda k, **d: None)
    assert dive.open_dry()
    depths = []
    for _ in range(int(seconds / dive.dt)):
        dive.step()
        if dive.simulated > 0.7 * seconds:
            depths.append(-float(dive.position[2]))
    return dive, float(np.mean(depths))


def test_the_fish_keeps_up_with_the_ship_and_settles(place):
    dive, depth = towed(place, 4.0, 50.0, 60.0)
    assert abs(np.linalg.norm(dive.velocity[:3]) - 4.0 * 0.5144) < 0.15
    assert 20.0 < depth < 50.0
    assert dive.tether.verdict is None


def test_faster_flies_shallower(place):
    _, slow = towed(place, 3.0, 50.0, 60.0)
    _, fast = towed(place, 6.0, 50.0, 60.0)
    assert fast < slow - 1.0, f"{fast:.1f} m at 6 kn against {slow:.1f} m at 3 kn"


def test_a_boulder_off_to_port_is_a_bright_face_and_a_shadow(place):
    """Against the same range bins where there is no boulder: abeam of it,
    its face is brighter and the ground just beyond it is darker."""
    dive, _ = towed(place, 4.0, 50.0, 80.0)
    scan = dive.ocean.sidescan
    rows = np.array(scan.rows)
    port = rows[:, :scan.bins][:, ::-1]           # nearest the fish first
    track = np.array(scan.track)
    abeam = np.flatnonzero(np.abs(track[:, 0] - BOULDER[0]) < 1.5)
    away = np.flatnonzero(np.abs(track[:, 0] - BOULDER[0]) > 20.0)
    assert len(abeam) and len(away), "the fish never came abeam of the boulder"
    # Where its near face is and where its shadow falls, by slant range from
    # the fish: the shadow from its far edge out to as far as three metres of
    # rock throws one from this height.
    fish = track[abeam].mean(axis=0)
    aside, high = abs(fish[1] - BOULDER[1]), fish[2] - DEEP

    def bin_at(across, up):
        return int(np.hypot(across, up) / scan.range_m * scan.bins)

    near_edge, far_edge = aside - BOULDER[2], aside + BOULDER[2]
    shadow = 3.0 * far_edge / (high - 3.0)
    k = bin_at(near_edge, high - 3.0)
    lit, here, there = slice(k - 6, k + 4), port[abeam].mean(axis=0), port[away].mean(axis=0)
    shade = slice(bin_at(far_edge + 0.3, high) + 1, bin_at(far_edge + 0.8 * shadow, high))
    assert here[lit].max() > 1.5 * there[lit].mean(), "its face comes back bright"
    assert here[shade].mean() < 0.3 * there[shade].mean(), "and behind it is a shadow"
