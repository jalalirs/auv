"""A grid of cells, and what it would take to work all of them.

One dive is a demonstration. Nobody at a reef programme has the problem of
one dive — they have a grid, a fleet and a boat calendar, and no way to turn
one into the others.
"""

import importlib.machinery
import importlib.util
import json
import math
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _tool():
    loader = importlib.machinery.SourceFileLoader("campaign", str(HERE / "campaign"))
    spec = importlib.util.spec_from_loader("campaign", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _a_place(tmp_path, across=100.0, rows=16):
    """A square place: deep in the middle, dry along the north edge."""
    place = tmp_path / "somewhere"
    place.mkdir(exist_ok=True)
    heights = np.full((rows, rows), -10.0, dtype="<f4")
    heights[rows - rows // 4:, :] = 0.5   # land: the northern quarter
    heights.tofile(place / "seabed.f32")
    (place / "site.json").write_text(json.dumps({
        "name": "somewhere",
        "from": {"centre": {"latitude": 24.5, "longitude": -81.4},
                 "acrossMetres": across, "sampleMetres": 1.0},
        "mesh": {"heightfield": {"rows": rows, "columns": rows,
                                 "file": "seabed.f32"}},
        "layers": {"coral": "coral.usda"},
    }))
    # Four colonies, all in the south-west quarter.
    points = ", ".join("(%.1f, %.1f, -9.0)" % (x, y)
                       for x, y in [(-40, -40), (-38, -41), (-35, -44), (-30, -30)])
    (place / "coral.usda").write_text(
        'def PointInstancer "Coral" {\n    point3f[] positions = [%s]\n'
        '    int[] protoIndices = [0, 0, 0, 0]\n'
        '    float3[] scales = [(1,1,1), (1,1,1), (1,1,1), (1,1,1)]\n}\n' % points)
    return place


def test_the_grid_comes_off_the_places_own_seabed(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    assert grid["across"] == 4 and len(grid["cells"]) == 16
    assert grid["cellM"] == pytest.approx(25.0)
    # The north edge is land and is not water to work.
    assert grid["dry"] == 4 and grid["wet"] == 12


def test_only_the_cells_with_something_in_them_are_worked(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="reef")
    assert len(grid["working"]) == 1, [c["colonies"] for c in grid["cells"]]
    assert grid["colonies"] == 4
    everything = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    assert len(everything["working"]) == 12


def test_it_will_not_turn_cells_into_days_without_a_flown_dive(tmp_path):
    """Cells times a number nobody measured is a promise, not a plan."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    said = tool.a_campaign(grid, cost={}, vehicles=1, day_hours=10.0, survives=None)
    assert "workingDays" not in said
    assert "nothing has been flown" in said["cannotSay"]


def test_a_flown_mission_says_what_a_cell_takes(tmp_path):
    tool = _tool()
    flown = tmp_path / "mission.json"
    flown.write_text(json.dumps({"seconds": 1800.0,
                                 "task": {"achieved": {"energyWh": 120.0}}}))
    cost = tool.cost_from(flown)
    assert cost["hours"] == pytest.approx(0.5)
    assert cost["from"] == tool.FLOWN


def test_a_sweep_says_what_a_cell_takes_and_what_the_weather_costs(tmp_path):
    """Only a sweep can say the share that survives: it flies a stated list
    of doubts once each. A mission's past runs are whatever happened to be
    flown, which is not a sample of anything."""
    tool = _tool()
    found = tmp_path / "findings.json"
    found.write_text(json.dumps({"cost": {"diveHours": 0.5, "diveEnergyWh": 120.0,
                                          "perCharge": 2.0, "survives": 0.5,
                                          "runs": 24}}))
    cost = tool.cost_from(found)
    assert cost["from"] == tool.SWEEP and cost["survives"] == 0.5


def test_days_are_the_fleets_hours_and_not_its_headcount(tmp_path):
    """Vehicles times cells would let half a dive count as a day's work."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")   # 12 cells
    cost = {"hours": 2.0, "from": tool.FLOWN}
    one = tool.a_campaign(grid, cost, vehicles=1, day_hours=10.0, survives=None)
    two = tool.a_campaign(grid, cost, vehicles=2, day_hours=10.0, survives=None)
    assert one["vehicleHours"] == pytest.approx(24.0)
    assert one["workingDays"] == 3          # 24 h over 10 h days
    assert two["workingDays"] == 2          # 24 h over 20 fleet-hours a day


def test_the_weather_turns_working_days_into_ship_days(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    said = tool.a_campaign(grid, {"hours": 2.0, "from": tool.FLOWN},
                           vehicles=1, day_hours=10.0, survives=0.5)
    assert said["workingDays"] == 3 and said["shipDays"] == 6, said


def test_the_cells_are_worked_in_lanes(tmp_path):
    """A boat that hops to the densest cell and then the next spends the day
    moving."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    order = tool.in_lanes(grid["working"])
    rows = [one["row"] for one in order]
    assert rows == sorted(rows), "the lanes are not worked in order"
    first = [one for one in order if one["row"] == order[0]["row"]]
    second = [one for one in order if one["row"] == first[-1]["row"] + 1]
    assert [c["column"] for c in first] == sorted(c["column"] for c in first)
    assert [c["column"] for c in second] == sorted(
        (c["column"] for c in second), reverse=True), "the lane did not turn back"


def test_the_page_says_where_every_figure_came_from(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    cost = {"hours": 2.0, "energyWh": 120.0, "from": tool.SWEEP, "survives": 0.5}
    said = tool.a_campaign(grid, cost, vehicles=2, day_hours=10.0, survives=0.5)
    page = tool.page(grid, said, cost, tool.in_lanes(grid["working"]))
    assert "from the place" in page and "from a sweep" in page and "chosen" in page
    for fetched in ("<script", "@import", "<link", "src=", 'href="http'):
        assert fetched not in page, fetched
    assert "-apple-system" in page


def test_the_page_says_so_when_it_cannot_say(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]))
    assert "No days here, and that is the point" in page
    assert "working days" not in page.lower().split("what it takes")[0]


def test_the_page_is_named_once(tmp_path):
    """The title said the place, then said "the whole grid" twice."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]))
    assert page.count("the whole grid") == 1
    assert "<h1>somewhere</h1>" in page


# ── and afterwards, what was actually covered ────────────────────────────────
#
# Every one of these programmes can tell you what they set out to do; none
# can hand a regulator a map of what they actually covered.

def _flown(tmp_path, place, cells, what="coverage.geojson"):
    """A folder of what `deliver --dive` produced, covering the named cells."""
    tool = _tool()
    deliver = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(
            "deliver", importlib.machinery.SourceFileLoader("deliver", str(HERE / "deliver"))))
    importlib.machinery.SourceFileLoader("deliver", str(HERE / "deliver")).exec_module(deliver)
    grid = tool.cells_over(place, cell_m=25.0, where="all")
    centre = grid["centre"]
    features = []
    for row, column in cells:
        one = next(c for c in grid["cells"] if c["row"] == row and c["column"] == column)
        latitude, longitude = deliver.where_on_earth(centre, one["x"], one["y"])
        features.append({"type": "Feature", "properties": {"what": "seen"},
                         "geometry": {"type": "Point",
                                      "coordinates": [longitude, latitude]}})
    flown = tmp_path / "flown" / "run_1"
    flown.mkdir(parents=True, exist_ok=True)
    (flown / what).write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}))
    return tmp_path / "flown"


def test_a_round_trip_through_wgs84_lands_in_the_cell_it_left(tmp_path):
    """The whole proof rests on this: metres out to the Earth and back."""
    tool = _tool()
    place = _a_place(tmp_path)
    grid = tool.cells_over(place, cell_m=25.0, where="all")
    covered = tool.covered_by(_flown(tmp_path, place, [(0, 0), (1, 2)]), grid)
    assert set(covered["hit"]) == {(0, 0), (1, 2)}


def test_it_says_which_planned_cells_were_missed(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    grid = tool.cells_over(place, cell_m=25.0, where="reef")   # one cell: (0, 0)
    nothing = tool.covered_by(_flown(tmp_path, place, [(1, 2)]), grid)
    assert nothing["cellsCovered"] == 0 and nothing["cellsMissed"] == 1
    # And ground covered that nobody planned to work is named, not counted
    # as coverage of the grid.
    assert nothing["cellsOutsideThePlan"] == 1


def test_a_missed_cell_is_not_allowed_to_look_like_water(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    grid = tool.cells_over(place, cell_m=25.0, where="reef")
    covered = tool.covered_by(_flown(tmp_path, place, [(1, 2)]), grid)
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]), covered)
    assert "MISSED" in page
    assert "were not reached" in page
    assert "#b04a4a" in page, "a missed cell was not drawn as missed"


def test_planted_corals_count_as_coverage_too(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    grid = tool.cells_over(place, cell_m=25.0, where="reef")
    covered = tool.covered_by(
        _flown(tmp_path, place, [(0, 0)], what="planting.geojson"), grid)
    assert covered["cellsCovered"] == 1
    assert covered["missions"][0]["what"] == "planted"


def test_a_folder_with_nothing_in_it_says_so_rather_than_claiming_nothing_flew(tmp_path):
    tool = _tool()
    place = _a_place(tmp_path)
    grid = tool.cells_over(place, cell_m=25.0, where="reef")
    empty = tmp_path / "empty" / "run_1"
    empty.mkdir(parents=True)
    covered = tool.covered_by(tmp_path / "empty", grid)
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]), covered)
    assert "none of those folders holds what a mission produced" in page


def test_one_dive_per_cell_is_an_assumption_and_says_so(tmp_path):
    """A cell four times the size of what a dive covers is four dives, and
    a plan that quietly called it one is out by a factor of four."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    said = tool.a_campaign(grid, {"hours": 1.0, "from": tool.FLOWN},
                           vehicles=1, day_hours=10.0, survives=None)
    assert said["divesPerCell"] == 1.0
    assert said["divesPerCellFrom"] == tool.CHOSEN
    page = tool.page(grid, said, {"hours": 1.0, "from": tool.FLOWN},
                     tool.in_lanes(grid["working"]))
    assert "one cell is one dive" in page


def test_a_survey_that_says_what_it_covered_settles_it(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")   # 625 m2
    cost = {"hours": 1.0, "from": tool.FLOWN, "coveredM2": 125.0}
    said = tool.a_campaign(grid, cost, vehicles=1, day_hours=10.0, survives=None)
    assert said["divesPerCell"] == pytest.approx(5.0)
    assert said["hoursPerCell"] == pytest.approx(5.0)
    assert said["dives"] == 12 * 5
    assert said["divesPerCellFrom"] == tool.FLOWN


def test_a_survey_records_the_ground_it_covered_not_only_a_fraction(tmp_path):
    """A fraction of a rectangle is not an area, and a campaign needs an
    area."""
    deliver = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(
            "deliver", importlib.machinery.SourceFileLoader("deliver", str(HERE / "deliver"))))
    importlib.machinery.SourceFileLoader("deliver", str(HERE / "deliver")).exec_module(deliver)
    geometry = {
        "rectangle": [{"x": 0.0, "y": 0.0}, {"x": 4.0, "y": 0.0},
                      {"x": 4.0, "y": 4.0}, {"x": 0.0, "y": 4.0}],
        "seen": {"rows": 2, "columns": 2,
                 "cells": list(np.packbits(np.array([[1, 0], [0, 1]], dtype=np.uint8)).tolist())},
    }
    said = deliver.coverage_file(tmp_path, geometry,
                                 {"latitude": 24.5, "longitude": -81.4, "name": "x"})
    assert said["rectangleM2"] == pytest.approx(16.0)
    assert said["seenM2"] == pytest.approx(8.0)      # two of four 2x2 m cells


def test_a_chart_says_how_much_ground_was_covered_when_no_camera_did(tmp_path):
    """A bathymetric survey covers a wider strip than the camera sees, and
    when the product is a chart that is the right ground to plan against."""
    tool = _tool()
    flown = tmp_path / "mission.json"
    flown.write_text(json.dumps({
        "seconds": 1800.0,
        "task": {"achieved": {"energyWh": 120.0}},
        "bathymetry": {"cellsWithASounding": 4000, "cellM": 0.5},
    }))
    cost = tool.cost_from(flown)
    assert cost["coveredM2"] == pytest.approx(1000.0)
    assert cost["coveredBy"] == "the multibeam's soundings"


def test_the_camera_wins_when_both_instruments_answered(tmp_path):
    """A dive that charted more than it photographed has not photographed
    it."""
    tool = _tool()
    flown = tmp_path / "mission.json"
    flown.write_text(json.dumps({
        "seconds": 1800.0, "task": {"achieved": {}},
        "coverage": {"seenM2": 300.0},
        "bathymetry": {"cellsWithASounding": 4000, "cellM": 0.5},
    }))
    cost = tool.cost_from(flown)
    assert cost["coveredM2"] == pytest.approx(300.0)
    assert cost["coveredBy"] == "the camera's footprint"


# ── which cell to plant next ─────────────────────────────────────────────────
#
# KCRI's gap in their own words: which cell to plant next given depth,
# substrate and current. Two of those three a place can answer.

def _tmp_place():
    """A place in a scratch directory, for the tests that do not take one."""
    import tempfile
    return _a_place(pathlib.Path(tempfile.mkdtemp()))


def _cells(*specs):
    return [{"row": r, "column": c, "depthM": d, "colonies": n,
             "x": 0.0, "y": 0.0, "wetShare": 1.0}
            for r, c, d, n in specs]


def test_a_cell_outside_the_planting_band_ranks_below_every_one_inside():
    """Too shallow and it bleaches and gets broken; too deep and there is
    not the light."""
    tool = _tool()
    order = tool.by_suitability(
        _cells((0, 0, 1.0, 500), (0, 1, 40.0, 500), (0, 2, 8.0, 10)),
        cell_m=25.0, band=(3.0, 12.0), room=0.25)
    assert (order[0]["row"], order[0]["column"]) == (0, 2)


def test_where_coral_already_grows_comes_first():
    """Substrate demonstrated rather than inferred: a cell with colonies in
    it has hard bottom at a survivable depth, proven by the coral on it."""
    tool = _tool()
    order = tool.by_suitability(
        _cells((0, 0, 8.0, 0), (0, 1, 8.0, 60), (0, 2, 8.0, 5)),
        cell_m=25.0, band=(3.0, 12.0), room=1.0)
    assert [one["colonies"] for one in order] == [60, 5, 0]


def test_a_cell_that_is_already_full_has_nowhere_to_put_anything():
    """Not obvious to a spreadsheet, and the reason this is a ranking for
    planting and not a ranking of reef."""
    tool = _tool()
    # 25 m cells are 625 m2; 250 colonies is 0.4 a square metre.
    order = tool.by_suitability(
        _cells((0, 0, 8.0, 250), (0, 1, 8.0, 100)),
        cell_m=25.0, band=(3.0, 12.0), room=0.25)
    assert order[0]["colonies"] == 100, "the full cell was ranked first"
    assert order[1]["colonies"] == 250


def test_the_page_says_what_it_cannot_rank_on():
    """Nothing in a place records the current, and a number invented for it
    would be the kind of claim the rest of this platform refuses."""
    tool = _tool()
    grid = tool.cells_over(_tmp_place(), cell_m=25.0, where="all")
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    order = tool.by_suitability(grid["working"], grid["cellM"], (3.0, 12.0), 0.25)
    page = tool.page(grid, said, {}, order, None, "suitability", (3.0, 12.0), 0.25)
    assert "Where to plant next" in page
    assert "nothing in the place records it" in page
    assert "substrate demonstrated rather than inferred" in page


def test_lanes_are_still_how_a_survey_is_worked():
    tool = _tool()
    grid = tool.cells_over(_tmp_place(), cell_m=25.0, where="all")
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]))
    assert "Worked in lanes" in page and "The order" in page


def test_the_picture_has_a_legend_so_red_cannot_be_misread(tmp_path):
    """A whole reef drawn red could be read as a reef in trouble. It means
    planned and not reached."""
    tool = _tool()
    place = _a_place(tmp_path)
    grid = tool.cells_over(place, cell_m=25.0, where="reef")
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    plain = tool.page(grid, said, {}, tool.in_lanes(grid["working"]))
    assert "to work, darker where there is more coral" in plain
    covered = tool.covered_by(_flown(tmp_path, place, [(1, 2)]), grid)
    shown = tool.page(grid, said, {}, tool.in_lanes(grid["working"]), covered)
    assert "planned and missed" in shown and "covered" in shown


def test_a_cost_from_a_dive_that_worked_no_ground_is_refused(tmp_path):
    """A reach that went somewhere and held station will happily multiply
    out to four working days over ninety-four cells, and every figure in
    that column would have the wrong name on it."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    reach = {"hours": 0.33, "from": tool.FLOWN, "task": "reach"}
    said = tool.a_campaign(grid, reach, vehicles=1, day_hours=10.0, survives=None)
    assert "workingDays" not in said
    assert "does not work a cell" in said["cannotSay"]


def test_a_survey_is_a_dive_a_cell_can_be_costed_from(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    survey = {"hours": 0.5, "from": tool.FLOWN, "task": "survey"}
    said = tool.a_campaign(grid, survey, vehicles=1, day_hours=10.0, survives=None)
    assert said["workingDays"] == 1


def test_a_sweep_that_does_not_name_a_task_is_still_trusted(tmp_path):
    """A sweep's cost is over a stated list of doubts on one mission; it
    does not carry a task kind and must not be refused for that."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    sweep = {"hours": 0.5, "from": tool.SWEEP, "survives": 0.5}
    said = tool.a_campaign(grid, sweep, vehicles=1, day_hours=10.0, survives=None)
    assert said["workingDays"] == 1


def test_a_dive_with_no_duration_is_not_reported_as_no_dive(tmp_path):
    """Saying "nothing has been flown here" when something was sends
    somebody to fly a dive that has already been flown."""
    tool = _tool()
    grid = tool.cells_over(_a_place(tmp_path), cell_m=25.0, where="all")
    nothing = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    assert "nothing has been flown here" in nothing["cannotSay"]
    timeless = tool.a_campaign(grid, {"from": tool.FLOWN, "task": "survey"},
                               vehicles=1, day_hours=10.0, survives=None)
    assert "does not say how long it took" in timeless["cannotSay"]


# ── which cells are the reef ─────────────────────────────────────────────────
#
# Al Fahal is three kilometres across and its record says its reef is
# 269,804 m2 — three per cent of the site. Asked for "cells with colonies in
# them" it returned 3,418 of 3,600, because four hundred thousand colonies
# scattered over nine square kilometres put one in almost every cell.

def _scattered(tmp_path, across=100.0, rows=16, per_cell=1):
    """A place with a colony in every cell and a reef that is a quarter of
    it, which is the shape of the fault."""
    place = tmp_path / "scattered"
    place.mkdir(exist_ok=True)
    heights = np.full((rows, rows), -10.0, dtype="<f4")
    heights.tofile(place / "seabed.f32")
    points = []
    # One colony in every 25 m cell, and a hundred more in one of them.
    for x in (-37.5, -12.5, 12.5, 37.5):
        for y in (-37.5, -12.5, 12.5, 37.5):
            points.extend([(x, y)] * per_cell)
    points.extend([(-37.5, -37.5)] * 100)
    (place / "site.json").write_text(json.dumps({
        "name": "scattered",
        "from": {"centre": {"latitude": 24.5, "longitude": -81.4},
                 "acrossMetres": across, "sampleMetres": 1.0},
        "mesh": {"heightfield": {"rows": rows, "columns": rows, "file": "seabed.f32"}},
        "layers": {"coral": "coral.usda"},
        # One cell of 25 m: 625 m2 of a 10,000 m2 site.
        "reef": {"colonies": len(points), "reefAreaM2": 625.0},
    }))
    (place / "coral.usda").write_text(
        'def PointInstancer "Coral" {\n    point3f[] positions = [%s]\n'
        '    int[] protoIndices = [%s]\n    float3[] scales = [%s]\n}\n'
        % (", ".join("(%.1f, %.1f, -9.0)" % p for p in points),
           ", ".join("0" for _ in points),
           ", ".join("(1,1,1)" for _ in points)))
    return place


def test_the_reef_is_what_the_place_says_it_is_not_every_cell_with_a_colony(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_scattered(tmp_path), cell_m=25.0, where="reef")
    # Every one of the sixteen cells holds a colony; the reef is 625 m2,
    # which is one cell of twenty-five metres — and it is the dense one.
    assert len(grid["working"]) == 1
    assert grid["working"][0]["colonies"] == 101
    assert "own record says its reef is" in grid["reefFrom"]


def test_a_place_that_does_not_say_falls_back_and_says_so(tmp_path):
    tool = _tool()
    place = _scattered(tmp_path)
    said = json.loads((place / "site.json").read_text())
    del said["reef"]["reefAreaM2"]
    (place / "site.json").write_text(json.dumps(said))
    grid = tool.cells_over(place, cell_m=25.0, where="reef")
    assert len(grid["working"]) == 16
    assert "does not say how much of it is reef" in grid["reefFrom"]


def test_where_it_came_from_is_on_the_page(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_scattered(tmp_path), cell_m=25.0, where="reef")
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]))
    assert "own record says its reef is" in page


def test_a_place_that_disagrees_with_itself_is_told_it_does(tmp_path):
    """The restored Al Fahal says its reef is 269,804 m2 and its coral
    layer puts nine tenths of its colonies outside that. One of the two is
    wrong, and a plan built on either alone would be too."""
    tool = _tool()
    place = _scattered(tmp_path, per_cell=50)      # the scatter dominates
    grid = tool.cells_over(place, cell_m=25.0, where="reef")
    assert "do not describe the same reef" in grid["reefFrom"]
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]))
    assert "This place disagrees with itself" in page


def test_a_place_that_agrees_with_itself_is_not_warned(tmp_path):
    tool = _tool()
    grid = tool.cells_over(_scattered(tmp_path, per_cell=1), cell_m=25.0, where="reef")
    assert "do not describe the same reef" not in grid["reefFrom"]
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    assert "disagrees with itself" not in tool.page(
        grid, said, {}, tool.in_lanes(grid["working"]))


def test_two_warnings_are_both_shown(tmp_path):
    """It was an assignment, so a page with two things to warn about
    showed the second and swallowed the first."""
    tool = _tool()
    grid = tool.cells_over(_scattered(tmp_path, per_cell=50), cell_m=25.0, where="reef")
    said = tool.a_campaign(grid, {}, vehicles=1, day_hours=10.0, survives=None)
    page = tool.page(grid, said, {}, tool.in_lanes(grid["working"]))
    assert "This place disagrees with itself" in page
    assert "No days here" in page
