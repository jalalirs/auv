"""What the platform-wide check says about places that are finished.

Two rows read as outstanding work on places that have none. Thuwal Deep is
638 m of bathyal seabed with no coral on it, and its density row said
UNSOURCED — which is a reef nobody cited, not a depth where nothing grows. And
`red-sea` is built by tools/fringing rather than surveyed, so it has no ground
material for aim-water to bake a medium into; its row said "tools/aim-water has
not been run on it", naming a command that cannot help.

Same trap as Looe Key's "unnamed mix", which was a surveyed reef being asked
which distribution it was drawn from. A check that reports a fact about a place
as a gap in it teaches everybody to ignore the check.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def _tool():
    loader = importlib.machinery.SourceFileLoader("check_places", str(HERE / "check-places"))
    spec = importlib.util.spec_from_loader("check_places", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _a_place(root: pathlib.Path, name: str, site: dict) -> pathlib.Path:
    where = root / name
    where.mkdir(parents=True, exist_ok=True)
    site.setdefault("name", name)
    (where / "site.json").write_text(json.dumps(site))
    return where


def test_a_constructed_place_is_not_waiting_for_aim_water(tmp_path):
    tool = _tool()
    where = _a_place(tmp_path, "red-sea", {
        "beginAt": [1.0, 2.0, -6.0],
        "from": {"constructed": {"morphology": "fringing reef"}},
        "ground": {},
    })
    mark, why = tool.water_of(where, json.loads((where / "site.json").read_text()))
    assert mark == "constructed", (mark, why)
    assert "aim-water" not in why, why
    assert "built, not surveyed" in why


def test_a_surveyed_place_with_no_medium_still_says_to_run_it(tmp_path):
    tool = _tool()
    where = _a_place(tmp_path, "looe-key", {
        "beginAt": [1.0, 2.0, -6.0],
        "from": {"surveyed": True},
        "ground": {},
    })
    mark, why = tool.water_of(where, json.loads((where / "site.json").read_text()))
    assert mark == "NOT BAKED" and "aim-water" in why


def test_a_place_where_nothing_begins_is_unchanged(tmp_path):
    tool = _tool()
    where = _a_place(tmp_path, "thuwal-deep", {"from": {}, "ground": {}})
    mark, why = tool.water_of(where, json.loads((where / "site.json").read_text()))
    assert mark == "no dive", (mark, why)
