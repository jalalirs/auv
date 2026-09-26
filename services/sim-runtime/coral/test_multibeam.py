"""A swath of soundings under the vehicle.

The forward-looking sonar exists so a controller can avoid something nobody
told it about. This is the other instrument, and the one the survey
programmes actually buy.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from multibeam import Multibeam  # noqa: E402


class Flat:
    """A seabed at a stated depth, everywhere."""

    def __init__(self, at=-20.0):
        self.at = at

    def under(self, x, y):
        return self.at


class Slope:
    """A bottom that falls away to starboard, one in ten."""

    def under(self, x, y):
        return -20.0 - 0.1 * y


LEVEL = np.eye(3)


def test_the_swath_is_the_width_the_geometry_says():
    """The number a survey plan is made of: lines this far apart with no
    overlap leave gaps the moment the vehicle rolls."""
    one = Multibeam({"halfSwathDeg": 60.0})
    assert one.swath_width(10.0) == pytest.approx(2 * 10.0 * math.tan(math.radians(60)))
    # Three and a half times the altitude, which is how a 60-degree swath is
    # quoted.
    assert one.swath_width(10.0) == pytest.approx(34.64, abs=0.01)


def test_a_flat_bottom_comes_back_flat():
    one = Multibeam({"beams": 33, "depthNoiseM": 0.0, "acrossNoiseM": 0.0})
    swath = one.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat(-20.0))
    assert swath["beams"] == 33
    # Within the ray walk's own resolution and not the instrument's: the
    # beam is stepped at half a metre and bisected eight times, which is a
    # couple of millimetres along the beam. Anything tighter would be
    # testing the search rather than the sounder.
    assert np.allclose(swath["depthM"], 20.0, atol=0.005)
    # And it is spread across the track, not piled under the vehicle.
    assert min(swath["y"]) < -20.0 and max(swath["y"]) > 20.0


def test_the_outer_beams_are_further_out_than_the_inner_ones():
    one = Multibeam({"beams": 5, "depthNoiseM": 0.0, "acrossNoiseM": 0.0})
    swath = one.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat(-20.0))
    across = [abs(v) for v in swath["acrossM"]]
    assert across[0] > across[1] > across[2]
    assert across[2] == pytest.approx(0.0, abs=1e-9)


def test_a_sounding_further_off_nadir_is_a_worse_sounding():
    """A fixed error would say a beam at sixty degrees is as good as one
    straight down, which is the single thing everybody who has used one of
    these knows to be false."""
    one = Multibeam({"beams": 3, "halfSwathDeg": 60.0, "depthNoiseM": 0.1,
                     "acrossNoiseM": 0.0}, seed=7)
    scatter = {0: [], 1: [], 2: []}
    for n in range(300):
        one.last_t = None
        swath = one.ping(float(n), np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat(-20.0))
        for beam in range(3):
            scatter[beam].append(swath["depthM"][beam])
    middle = float(np.std(scatter[1]))
    edge = float(np.std(scatter[0]))
    assert edge > 1.5 * middle, (edge, middle)


def test_a_rolled_vehicle_surveys_a_rolled_strip():
    """Exactly the error a survey has to correct for, and the reason
    attitude is logged beside every ping."""
    heel = math.radians(20.0)
    rolled = np.array([[1.0, 0.0, 0.0],
                       [0.0, math.cos(heel), -math.sin(heel)],
                       [0.0, math.sin(heel), math.cos(heel)]])
    level = Multibeam({"beams": 3, "depthNoiseM": 0.0, "acrossNoiseM": 0.0})
    over = Multibeam({"beams": 3, "depthNoiseM": 0.0, "acrossNoiseM": 0.0})
    straight = level.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat(-20.0))
    heeled = over.ping(0.0, np.array([0.0, 0.0, -5.0]), rolled, seabed=Flat(-20.0))
    # The nadir beam is no longer under the vehicle.
    assert abs(heeled["y"][1]) > 4.0
    assert abs(straight["y"][1]) < 1e-6


def test_it_finds_a_slope_where_the_slope_is():
    one = Multibeam({"beams": 21, "depthNoiseM": 0.0, "acrossNoiseM": 0.0})
    swath = one.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Slope())
    # Deeper to starboard, because the bottom falls away that way.
    port = [d for d, y in zip(swath["depthM"], swath["y"]) if y < -5]
    starboard = [d for d, y in zip(swath["depthM"], swath["y"]) if y > 5]
    assert np.mean(starboard) > np.mean(port) + 1.0


def test_a_beam_that_finds_nothing_is_dropped_and_counted():
    one = Multibeam({"beams": 9, "rangeM": [0.5, 8.0]})
    swath = one.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat(-20.0))
    assert swath["beams"] == 0
    assert one.dropped == 9
    assert one.said()["dropped"] == 9


def test_it_pings_at_its_own_rate_and_not_every_step():
    one = Multibeam({"pingsPerSecond": 10.0})
    assert one.due(0.0) is True
    one.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat())
    assert one.due(0.05) is False
    assert one.due(0.11) is True


def test_two_runs_of_one_seed_sound_the_same():
    """Everything the platform claims about a result rests on this."""
    a = Multibeam({"beams": 7}, seed=3)
    b = Multibeam({"beams": 7}, seed=3)
    first = a.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat())
    second = b.ping(0.0, np.array([0.0, 0.0, -5.0]), LEVEL, seabed=Flat())
    assert first["depthM"] == second["depthM"]


# ── fitted to a vehicle, and kept ────────────────────────────────────────────

def test_a_dive_fits_the_multibeam_its_package_declares(tmp_path):
    """The REMUS, because that is what carries one.

    It was fitted to the BlueROV2 first, which was wrong twice over: a
    stock BlueROV2 does not have a multibeam, and declaring one added
    twenty-eight watts to the hotel load of every dive the platform has
    ever flown that hull on. A survey AUV is what a survey head goes on.
    """
    from hydrodynamics import Allocator, Body, Hydrodynamics
    from runner import Dive

    package = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/remus-100"
    model = Hydrodynamics.from_package(package / "dynamics.json")
    said = []
    dive = Dive({"durationSeconds": 2, "initialState": {"positionM": [0, 0, -7]},
                 "vehiclePath": str(package), "recordInto": str(tmp_path / "rec")},
                Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **d: said.append((kind, d)))
    dive.begin_task({"kind": "transect", "lengthM": 20.0})
    assert dive.multibeam is not None
    on = next(d for kind, d in said if kind == "multibeam_on")
    assert on["beams"] == 256 and on["halfSwathDeg"] == 60.0
    # And it is a different instrument from the forward-looking one.
    assert dive.sonar is not None and dive.sonar is not dive.multibeam


def test_a_hull_that_does_not_carry_one_is_not_given_one():
    """A stock BlueROV2 has no multibeam, and saying it did put twenty-eight
    watts on every dive's hotel load."""
    import json

    package = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2"
    said = json.loads((package / "dynamics.json").read_text())
    assert not any(one["kind"] == "multibeam" for one in said.get("sensors", []))


def test_the_soundings_are_kept_in_a_file_of_their_own(tmp_path):
    """A swath is a few hundred numbers a ping and would swamp the sensor
    trace; what it is for is a chart rather than a line nobody reads."""
    from recording import Recorder

    into = tmp_path / "rec"
    recorder = Recorder(into, frames_hz=1.0)
    recorder.sounded({"t": 0.1, "beams": 3, "x": [0, 1, 2], "y": [0, 0, 0],
                      "depthM": [20.0, 20.1, 20.2], "angleRad": [-0.1, 0.0, 0.1],
                      "acrossM": [-1.0, 0.0, 1.0]})
    recorder.sounded({"t": 0.2, "beams": 2, "x": [0, 1], "y": [1, 1],
                      "depthM": [20.0, 20.1], "angleRad": [0.0, 0.1],
                      "acrossM": [0.0, 1.0]})
    lines = (into / "soundings.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert recorder.soundings == 5
    assert json.loads(lines[0])["depthM"][0] == 20.0


def test_a_dive_with_no_multibeam_leaves_no_file(tmp_path):
    from recording import Recorder

    into = tmp_path / "rec"
    recorder = Recorder(into, frames_hz=1.0)
    assert not (into / "soundings.jsonl").exists()
    assert recorder.soundings == 0
