"""Every mission in the repository, checked against what can actually fly one.

A mission is a JSON document nobody compiles. It is read by the control plane,
crossed with its doubts into a sweep, and handed to the runtime — and a typo in
an objective kind or a doubt verb does not fail anywhere, it flies a dive that
is not the dive that was written. `section-thuwal` was the only mission Thuwal
Deep had and nothing had ever checked that its objective was one the runtime
knows.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MISSIONS = sorted((ROOT / "missions").glob("*.json"))

# The verbs `apply` in services/control-plane/internal/dive/sweep.go handles by
# name. Everything else a setting says goes into the water as-is, which is what
# makes a misspelt one silent.
DOUBT_VERBS = {"objective", "world", "failures", "fitted"}


def task_kinds():
    """The kinds the runtime registers, read out of its own table."""
    source = (ROOT / "services" / "sim-runtime" / "coral" / "tasks"
              / "__init__.py").read_text()
    inside = source[source.index("TASKS"):source.index("KINDS")]
    return set(re.findall(r'"([a-z-]+)":', inside)) | {"mission"}


def places():
    return {"al-fahal", "looe-key", "kaneohe", "red-sea", "thuwal-deep",
            "tank"}


@pytest.mark.parametrize("path", MISSIONS, ids=lambda p: p.stem)
def test_a_mission_asks_for_something_that_can_be_flown(path):
    said = json.loads(path.read_text())
    for needed in ("name", "note", "place", "vehicle", "objective"):
        assert needed in said, (path.name, needed)
    assert said["place"] in places(), (path.name, said["place"])
    assert said["objective"].get("kind") in task_kinds(), said["objective"]


@pytest.mark.parametrize("path", MISSIONS, ids=lambda p: p.stem)
def test_every_doubt_resolves_to_something(path):
    """A doubt with one setting is not a doubt, and a doubt with none is a
    sweep the control plane refuses."""
    for name, settings in (json.loads(path.read_text()).get("doubts") or {}).items():
        assert isinstance(settings, dict), (path.name, name)
        assert len(settings) >= 2, (path.name, name, "a doubt needs two ways to go")
        for which, setting in settings.items():
            assert isinstance(setting, dict), (path.name, name, which)


@pytest.mark.parametrize("path", MISSIONS, ids=lambda p: p.stem)
def test_a_doubt_that_changes_the_objective_says_so(path):
    """`{"altitudeM": 4.0}` at the top of a setting does not change the
    objective — it goes into the *water*, silently, under a key nothing reads.
    Changing what is asked of the vehicle needs the `objective` verb."""
    said = json.loads(path.read_text())
    asked = set(said["objective"])
    for name, settings in (said.get("doubts") or {}).items():
        for which, setting in settings.items():
            loose = asked & set(setting) - DOUBT_VERBS
            assert not loose, (
                path.name, name, which,
                f"{sorted(loose)} names an objective field at the top of a "
                f"setting, where it becomes a water parameter nothing reads. "
                f"Put it under \"objective\".")


def test_thuwal_deep_has_a_dive_that_looks_at_the_bottom():
    """It had a glider section through the water column and nothing that ever
    looked at the ground — on the one place whose ground is the whole point."""
    flown = [json.loads(p.read_text()) for p in MISSIONS]
    deep = [m for m in flown if m["place"] == "thuwal-deep"]
    assert deep, "Thuwal Deep has no mission at all"
    benthic = [m for m in deep
               if m["objective"]["kind"] in ("transect", "survey", "inspect",
                                             "search")]
    assert benthic, [m["objective"]["kind"] for m in deep]
