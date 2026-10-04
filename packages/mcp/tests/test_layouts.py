"""Putting marks on a place, and drawing what is there.

Two operations and not one. `layouts_add_line` changes the arrangement and
answers with the arrangement; `layouts_chart` draws it. Returning a picture from
an edit would make every edit cost what a picture costs, and an agent placing a
transect edits twenty times and looks once.

Neither is a render. What a camera would see from a point in the water needs a
scene, a GPU, a hull, and a position and an orientation — a third operation.
"""

from __future__ import annotations

import base64
import math

import pytest

from iocean_mcp import chart, tools
from iocean_mcp.platform import Refused


class Arranged:
    """Enough platform to arrange one place."""

    def __init__(self):
        self.saved = []

    def request(self, method, path, body=None):
        if path.endswith("/versions") and method == "POST":
            self.saved.append(body)
            return {"id": "ver_new"}
        if path.endswith("/versions"):
            return {"versions": [{"id": "ver_1", "createdAt": "2026-01-01T00:00:00Z",
                                  "document": {"things": [
                                      {"id": "a", "kind": "buoy", "x": 0.0, "y": 0.0}]}}]}
        return {"id": "lay_1", "name": "a plot", "cityId": "cty_1"}


def test_a_line_includes_both_its_ends():
    """A hundred metres at twenty-five is five marks, not four. Somebody asking
    for a line between two points means the points."""
    platform = Arranged()
    said = tools.layouts_add_line(platform, "lay_1", [0, 0], [100, 0], 25)
    assert len(said["added"]) == 5
    assert said["added"][0]["x"] == 0.0
    assert said["added"][-1]["x"] == 100.0
    assert said["lineLengthM"] == 100.0


def test_marks_are_evenly_spaced_along_a_diagonal():
    platform = Arranged()
    said = tools.layouts_add_line(platform, "lay_1", [0, 0], [30, 40], 10)
    put = [(m["x"], m["y"]) for m in said["added"]]
    assert len(put) == 6                       # a 50 m run at 10 m
    for at in range(1, len(put)):
        gap = math.dist(put[at - 1], put[at])
        assert gap == pytest.approx(10.0, abs=0.001)


def test_it_adds_to_what_is_there_rather_than_replacing_it():
    platform = Arranged()
    said = tools.layouts_add_line(platform, "lay_1", [0, 0], [10, 0], 10)
    assert said["things"] == 3                 # one buoy already, two new
    kept = platform.saved[0]["document"]["things"]
    assert any(t["kind"] == "buoy" for t in kept)


def test_an_edit_does_not_return_a_picture():
    """The whole point of the split: twenty edits cost twenty edits."""
    platform = Arranged()
    said = tools.layouts_add_line(platform, "lay_1", [0, 0], [10, 0], 10)
    assert "image" not in said
    assert "separate operation" in said["note"]


def test_a_line_with_no_length_is_refused():
    platform = Arranged()
    with pytest.raises(Refused):
        tools.layouts_add_line(platform, "lay_1", [5, 5], [5, 5], 10)


def test_a_spacing_of_nothing_is_refused():
    platform = Arranged()
    with pytest.raises(Refused):
        tools.layouts_add_line(platform, "lay_1", [0, 0], [10, 0], 0)


def test_the_saved_document_says_which_frame_its_numbers_are_in():
    """A frame each reader has to guess is a frame three of them get wrong."""
    platform = Arranged()
    tools.layouts_add_line(platform, "lay_1", [0, 0], [10, 0], 10)
    assert "east" in platform.saved[0]["document"]["frame"]


# ── the chart ────────────────────────────────────────────────────────────────

def test_north_is_up_and_east_is_right():
    """The flip a chart gets wrong once: +y north is a *smaller* image row."""
    canvas = chart.Chart(1000.0, side=101)
    middle = canvas.at(0, 0)
    assert middle == (50, 50)
    assert canvas.at(100, 0)[0] > middle[0]       # east is right
    assert canvas.at(0, 100)[1] < middle[1]       # north is up


def test_a_chart_is_a_real_png():
    canvas = chart.Chart(1000.0, side=32)
    canvas.disc(0, 0, 3, (255, 0, 0))
    raw = canvas.png()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert b"IHDR" in raw[:32] and raw[-8:-4] == b"IEND"
    assert base64.b64encode(raw)                  # and it survives the transport


def test_the_scale_bar_stands_for_a_round_number():
    """The property, not numbers I guessed: a bar somebody can read off, and a
    useful fraction of the width. A chart without one is a picture — an agent
    cannot tell a fifty-metre plot from a five-hundred-metre one, and distance
    is the whole question it is being asked."""
    for across in (60.0, 100.0, 250.0, 1000.0, 3000.0, 8000.0):
        metres = chart.Chart(across, side=128).rule()
        assert metres > 0
        assert 0.05 <= metres / across <= 0.35, (across, metres)
        # Round: one or two significant figures, nothing like 137.
        leading = 10 ** (len(str(int(metres))) - 1)
        assert metres % leading == 0, (across, metres)


def test_depth_shading_is_darker_where_it_is_deeper():
    canvas = chart.Chart(100.0, side=8)
    # Row 0 of a heightfield is south, so it lands at the *bottom* of the image.
    canvas.seabed([-40.0] * 32 + [-2.0] * 32, rows=8, columns=8)
    def brightness(row):
        at = (row * 8 + 4) * 3
        return sum(canvas.pixels[at:at + 3])
    assert brightness(1) > brightness(6), "the shallow half should be lighter"


def test_ground_above_the_water_is_not_drawn_as_sea():
    canvas = chart.Chart(100.0, side=8)
    canvas.seabed([5.0] * 64, rows=8, columns=8)
    at = (4 * 8 + 4) * 3
    assert tuple(canvas.pixels[at:at + 3]) == chart.DRY


# ── the first tool that spends anything ──────────────────────────────────────

class Fleet:
    """A platform with one place and two vehicles, one of which can fly."""

    def __init__(self):
        self.asked = []

    def places(self):
        return [{"id": "cty_1", "slug": "al-fahal", "name": "Al Fahal"}]

    def vehicles(self):
        return [{"id": "veh_1", "slug": "bluerov2", "name": "BlueROV2"},
                {"id": "veh_2", "slug": "seaglider", "name": "Seaglider"}]

    def versions_of_place(self, _):
        return [{"id": "cv", "createdAt": "2026-09-28T00:00:00Z"}]

    def versions_of_vehicle(self, _):
        return [{"id": "vv", "createdAt": "2026-09-28T00:00:00Z"}]

    def files(self, version):
        if getattr(self, "hull", True):
            return [{"path": "BROV_low.usd"}, {"path": "dynamics.json"}]
        return [{"path": "dynamics.json"}]

    def institution(self):
        return {"id": "org_1", "name": "iocean"}

    def queues(self):
        return [{"id": "q_1", "slug": "box-gpus"}]

    def request(self, method, path, body=None):
        self.asked.append((path, body))
        if path.endswith("/conditions"):
            return {"id": "cond_1"}
        if path.endswith("/dives"):
            return {"id": "dive_1"}
        return {"id": "run_1", "state": "queued"}


def test_a_dive_names_the_sea_it_was_flown_in():
    """Required, not optional: a dive whose water nobody stated cannot be
    compared with another."""
    platform = Fleet()
    said = tools.dives_start(platform, "al-fahal", "bluerov2",
                             {"kind": "hold-station", "seconds": 60},
                             water="one-knot")
    conditions = next(b for p, b in platform.asked if p.endswith("/conditions"))
    assert conditions["name"] == "one-knot"
    assert conditions["parameters"]["currentMetresPerSecond"] == 0.51
    assert said["water"] == "one-knot"


def test_water_is_constructed_and_never_dressed_as_a_reading():
    """Nobody measured a current at Al Fahal today."""
    platform = Fleet()
    tools.dives_start(platform, "al-fahal", "bluerov2", {"kind": "reach"})
    conditions = next(b for p, b in platform.asked if p.endswith("/conditions"))
    assert conditions["kind"] == "constructed"


def test_a_vehicle_with_no_hull_is_refused_before_anything_is_spent():
    """The refusal has to come before a machine is asked for, and it has to say
    which tool answers 'which ones can'."""
    platform = Fleet()
    platform.hull = False
    with pytest.raises(Refused) as no:
        tools.dives_start(platform, "al-fahal", "seaglider", {"kind": "reach"})
    assert "no hull" in no.value.message
    assert "vehicles_list" in no.value.message
    assert platform.asked == [], "it asked the platform for something anyway"


def test_pictures_are_off_unless_asked_for():
    """A drawn dive is a sixth of real time and an undrawn one is fifteen times
    it, on the same trajectory."""
    platform = Fleet()
    said = tools.dives_start(platform, "al-fahal", "bluerov2", {"kind": "reach"})
    dive = next(b for p, b in platform.asked if p.endswith("/dives"))
    assert dive["objective"]["pictures"] is False
    assert said["drawn"] is False


def test_the_objective_is_carried_through_whole():
    platform = Fleet()
    tools.dives_start(platform, "al-fahal", "bluerov2",
                      {"kind": "transect", "lengthM": 80, "altitudeM": 2.5},
                      pictures=True)
    dive = next(b for p, b in platform.asked if p.endswith("/dives"))
    assert dive["objective"]["lengthM"] == 80
    assert dive["objective"]["altitudeM"] == 2.5
    assert dive["objective"]["pictures"] is True


def test_it_asks_for_a_runtime_a_host_offers_not_an_image_tag():
    """An image tag is not a runtime.

    This sent "r1", which is what the image was built under, and the platform
    answered "no host on that queue offers the runtime r1". Hosts advertise
    isaac-6.0.1+oceansim — the engine and the extension that contributes the
    underwater sensors.
    """
    platform = Fleet()
    tools.dives_start(platform, "al-fahal", "bluerov2", {"kind": "reach"})
    run = platform.asked[-1][1]
    assert run["runtimeVersion"] == "isaac-6.0.1+oceansim"
    assert run["runtimeVersion"] != "r1"


def test_the_runtime_can_be_overridden_for_a_platform_that_runs_another(monkeypatch):
    monkeypatch.setenv("IOCEAN_RUNTIME_VERSION", "isaac-7.0.0+oceansim")
    platform = Fleet()
    said = tools.dives_start(platform, "al-fahal", "bluerov2", {"kind": "reach"})
    assert said["runtime"] == "isaac-7.0.0+oceansim"


# ── dives_frame ──────────────────────────────────────────────────────────────

class Undrawn(Fleet):
    def runs(self, dive):
        return [{"id": "run_1", "createdAt": "2026-10-01T00:00:00Z"}]

    def artefacts(self, dive, run):
        return [{"path": "poses.jsonl", "url": "x"}, {"path": "manifest.json", "url": "x"}]


def test_an_undrawn_dive_says_how_to_get_one_that_can_be_seen():
    """It has its numbers and no pictures, and the refusal names the switch."""
    with pytest.raises(Refused) as no:
        tools.dives_frame(Undrawn(), "dive_1", 10.0)
    assert no.value.code == "not_drawn"
    assert "pictures=true" in no.value.message


# ── dives_result ─────────────────────────────────────────────────────────────

class Scored(Fleet):
    def runs(self, dive):
        return [{"id": "run_1", "state": "succeeded", "createdAt": "2026-10-01T00:00:00Z",
                 "outcome": {"ended": "time", "task": {
                     "kind": "waypoints", "score": 0.6, "seconds": 48, "energyWh": 0.59,
                     "flownBy": {"mostly": "pursue"},
                     "achieved": {"reached": 3, "of": 5, "radiusM": 0.08}},
                     "navigation": {"aiding": "camera", "driftM": 0.002}}}]

    def artefacts(self, dive, run):
        return [{"path": "poses.jsonl", "sizeBytes": 10}]


def test_a_finished_run_comes_back_with_its_score():
    """Every finished run used to come back with no score, which reads like a
    run that scored nothing. The judge's number is there, marked derived."""
    said = tools.dives_result(Scored(), "dive_1")
    assert said["score"]["value"] == 0.6
    assert said["score"]["kind"] == "derived"
    assert "3 of 5" in said["score"]["note"]
    assert said["flownBy"] == "pursue"
    assert said["navigation"]["aiding"] == "camera"


class OnTheReef(Scored):
    def runs(self, dive):
        run = Scored.runs(self, dive)[0]
        run["outcome"].update({
            "life": {"fish": 28, "bySpecies": {"chromis_viridis": 12}, "bumped": 1, "scattered": 0.1,
                     "spent": {"chromis_viridis": {"school": 0.6}}},
            "coral": {"colonies": 23, "struck": 1, "brushed": 1, "broken": [], "from": "the coral system"},
            "sediment": {"liftedG": 0.1, "settledG": 0.08, "worstVisibilityM": 9.0,
                         "worstOnACoralMgCm2": 0.02, "from": "the sediment system"},
            "hardestStrike": {"what": "coral-16", "speedMs": 0.02, "impulseNs": 0.1},
            "tether": {"lengthM": 1.8, "taut": False, "tensionN": 0.0, "mostTensionN": 0.14,
                       "fouled": None, "winding": {"rock-8": 0.1}}})
        return [run]


def test_what_the_dive_did_to_the_reef_comes_back_marked():
    """The fish it frightened and struck, the coral it touched, the sand it
    lifted, its hardest strike: each derived, each saying from what."""
    said = tools.dives_result(OnTheReef(), "dive_1")
    reef = said["reef"]
    assert reef["fish"]["value"]["struckByTheVehicle"] == 1 and reef["fish"]["kind"] == "derived"
    assert reef["coral"]["value"]["struck"] == 1
    assert reef["sediment"]["value"]["worstVisibilityM"] == 9.0
    assert reef["hardestStrike"]["value"]["what"] == "coral-16"
    assert said["tether"]["mostTensionN"] == 0.14


def test_a_run_from_before_the_reef_was_alive_has_no_reef_section():
    assert "reef" not in tools.dives_result(Scored(), "dive_1")
