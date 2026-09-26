"""A dive that is for something leaves a recording a person can open with nothing."""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from hydrodynamics import Allocator, Body, Hydrodynamics
from runner import Dive

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2"


def test_a_survey_records_poses_sensors_task_and_a_manifest():
    model = Hydrodynamics.from_package(PACKAGE / "dynamics.json")
    into = pathlib.Path(tempfile.mkdtemp()) / "recording"
    said = []
    dive = Dive({"durationSeconds": 4, "initialState": {"positionM": [0, 0, -7]},
                 "vehiclePath": str(PACKAGE), "recordInto": str(into)},
                Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **d: said.append((kind, d)))
    dive.begin_task({"kind": "survey", "widthM": 10, "heightM": 5})
    assert dive.view == "down", "a survey looks down"
    while not dive.done:
        if dive.recorder.due(dive.simulated):
            dive.recorder.captured()
        dive.step()
    dive.close()

    manifest = json.loads((into / "manifest.json").read_text())
    assert manifest["poses"] == 20 and manifest["frames"] == 32
    assert manifest["camera"]["focalLengthMm"] == 21
    assert manifest["task"]["kind"] == "survey"
    assert "rectangle" in manifest["geometry"], "a replay draws what the task asked for"
    assert "site" in manifest, "a replay's chart stands on the recording alone"
    poses = [json.loads(line) for line in (into / "poses.jsonl").read_text().splitlines()]
    assert poses[0]["view"] == "down"
    # A pose points at a moment in the dive's video rather than at a file of
    # its own, because the video's clock is the dive's clock.
    assert poses[-1]["frame"].startswith("dive.mp4#")
    sensors = [json.loads(line) for line in (into / "sensors.jsonl").read_text().splitlines()]
    assert "/depth" in sensors[0] and len(sensors) == 20
    kinds = [kind for kind, _ in said]
    assert "recording" in kinds and "recorded" in kinds
    settled = next(d for kind, d in said if kind == "settled")
    assert settled["task"]["achieved"]["swathFrom"] == "camera footprint"


def test_coral_is_read_off_the_place_for_the_chart(tmp_path):
    from runner import coral_positions
    (tmp_path / "site.json").write_text('{"layers": {"coral": "coral.usda"}}')
    (tmp_path / "coral.usda").write_text(
        'def PointInstancer "Coral" {\n    point3f[] positions = [(-160.4, -14.33, -3.707), (1, 2, 3), (4.25, -5.5, 0)]\n}\n')
    assert coral_positions(tmp_path) == [[-160.4, -14.3], [1.0, 2.0], [4.2, -5.5]]
    assert coral_positions(tmp_path / "nowhere") == []


def test_a_recording_says_which_reef_it_was_and_where_that_is(tmp_path):
    """Without it a mission's product is metres from a centre nobody wrote
    down, and nothing it produced can be put on a map."""
    model = Hydrodynamics.from_package(PACKAGE / "dynamics.json")
    city = tmp_path / "city"
    city.mkdir()
    (city / "site.json").write_text(json.dumps({
        "name": "red-sea", "from": {"centre": {"latitude": 22.305, "longitude": 38.97},
                                    "acrossMetres": 1000.0, "sampleMetres": 1.96,
                                    "surveyed": False}}))
    into = tmp_path / "recording"
    dive = Dive({"durationSeconds": 2, "initialState": {"positionM": [0, 0, -7]},
                 "vehiclePath": str(PACKAGE), "cityPath": str(city),
                 "recordInto": str(into)},
                Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **d: None)
    dive.begin_task({"kind": "survey", "widthM": 10, "heightM": 5})
    while not dive.done:
        dive.step()
    dive.close()
    place = json.loads((into / "manifest.json").read_text())["place"]
    assert place["name"] == "red-sea"
    assert place["centre"] == {"latitude": 22.305, "longitude": 38.97}
    assert place["surveyed"] is False


def test_a_place_that_does_not_say_where_it_is_leaves_the_field_empty(tmp_path):
    """Empty rather than a guess: `deliver` refuses a recording it cannot
    georeference, and it can only refuse one that admits it."""
    model = Hydrodynamics.from_package(PACKAGE / "dynamics.json")
    city = tmp_path / "city"
    city.mkdir()
    (city / "site.json").write_text('{"name": "a tank", "from": {}}')
    into = tmp_path / "recording"
    dive = Dive({"durationSeconds": 2, "initialState": {"positionM": [0, 0, -7]},
                 "vehiclePath": str(PACKAGE), "cityPath": str(city),
                 "recordInto": str(into)},
                Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **d: None)
    dive.begin_task({"kind": "survey", "widthM": 10, "heightM": 5})
    while not dive.done:
        dive.step()
    dive.close()
    assert json.loads((into / "manifest.json").read_text())["place"] is None
