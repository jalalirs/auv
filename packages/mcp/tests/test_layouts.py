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

from coral_city_mcp import chart, tools
from coral_city_mcp.platform import Refused


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
