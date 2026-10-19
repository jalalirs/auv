"""Deploying a controller from its source through MCP."""

from __future__ import annotations

import pytest

from iocean_mcp import tools
from iocean_mcp.platform import Refused
from iocean_mcp.provenance import numbers


class Builds:
    def __init__(self, view=None):
        self.sent = []
        self.view = view or {"id": "ctlb_1", "slug": "wary", "state": "queued", "steps": [],
                             "brief": {"source": {"kind": "git", "url": "https://github.com/iocean/wary"}}}

    def institution(self):
        return {"id": "org_k", "name": "KAUST"}

    def request(self, method, path, body=None):
        self.sent.append((method, path, body))
        if path in ("/api/v1/organisations/org_k/controller-builds", "/api/v1/controller-builds/ctlb_1",
                    "/api/v1/controller-builds/ctlb_1/again"):
            return self.view
        raise AssertionError(path)


def test_a_repository_is_built_with_only_what_was_said():
    platform = Builds()
    said = tools.controllers_build(platform, url="https://github.com/iocean/wary", ref="v1", path="src")
    assert platform.sent[-1][1:] == ("/api/v1/organisations/org_k/controller-builds",
                                     {"source": {"kind": "git", "url": "https://github.com/iocean/wary",
                                                 "ref": "v1", "path": "src"}})
    assert said["build"] == "ctlb_1" and "controllers_build_status" in said["note"]


def test_a_zip_is_built_and_one_source_is_asked_for():
    platform = Builds()
    tools.controllers_build(platform, zip_object="obj_z", zip_name="wary.zip", slug="wary")
    assert platform.sent[-1][2] == {"source": {"kind": "zip", "objectId": "obj_z", "name": "wary.zip"}, "slug": "wary"}
    with pytest.raises(Refused):
        tools.controllers_build(platform)
    with pytest.raises(Refused):
        tools.controllers_build(platform, url="https://github.com/a/b", zip_object="obj_z")


def test_each_controller_says_its_tank_check_and_the_stack_it_registered():
    platform = Builds({"id": "ctlb_1", "slug": "iocean-controllers", "state": "ready",
                       "steps": [{"say": "tank check", "n": 2, "of": 2}],
                       "brief": {"source": {"kind": "git", "url": "https://github.com/jalalirs/iocean-controllers"}},
                       "report": {"ok": True, "source": {"kind": "git", "commit": "abc123"}},
                       "controllers": [
                           {"ok": True, "slug": "station-hold", "controller": "controllers/station-hold/controller.py:StationHold",
                            "commands": "wrench", "stackId": "stack_9",
                            "checks": {"tank": {"ok": True, "seconds": 20.4, "said": "held station"},
                                       "vehicle": {"ok": True, "problems": []}}},
                           {"ok": False, "slug": "sawtooth", "failure": "the tank check raised",
                            "checks": {"vehicle": {"ok": False, "problems": ["no buoyancy engine on this vehicle"]}}}]})
    said = tools.controllers_build_status(platform, "ctlb_1")
    hold, saw = said["controllers"]
    assert hold["stack"] == "stack_9" and hold["tank"]["seconds"]["kind"] == "measured"
    assert saw["ok"] is False and saw["failure"] and saw["problems"]
    assert said["source"]["commit"] == "abc123" and "dives_start" in said["next"]
    assert numbers(said) == []
    again = tools.controllers_build_again(platform, "ctlb_1")
    assert platform.sent[-1][:2] == ("POST", "/api/v1/controller-builds/ctlb_1/again")
    assert "new build" in again["note"]


def test_some_controllers_are_asked_for_by_slug():
    platform = Builds()
    tools.controllers_build(platform, url="https://github.com/jalalirs/iocean-controllers",
                            controllers=["station-hold", "sawtooth"])
    assert platform.sent[-1][2]["controllers"] == ["station-hold", "sawtooth"]


def test_a_repository_is_looked_into_with_only_what_was_said():
    class Look(Builds):
        def request(self, method, path, body=None):
            self.sent.append((method, path, body))
            return {"controllers": [{"slug": "station-hold", "name": "Station hold"}]}
    platform = Look()
    said = tools.controllers_look(platform, "https://github.com/jalalirs/iocean-controllers", ref="main")
    assert platform.sent[-1][1] == ("/api/v1/controller-sources/look?url=https%3A%2F%2Fgithub.com%2Fjalalirs"
                                    "%2Fiocean-controllers&ref=main")
    assert said["controllers"][0]["slug"] == "station-hold" and "controllers_build" in said["note"]
