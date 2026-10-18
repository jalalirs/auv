"""Putting a reef onto a place through MCP: what is sent, and what an agent is told."""

from __future__ import annotations

import pytest

from iocean_mcp import tools
from iocean_mcp.platform import Refused
from iocean_mcp.provenance import numbers


class Mappings:
    """Enough platform to start a mapping, watch it and accept a candidate."""

    def __init__(self, view=None):
        self.sent = []
        self.view = view or {"id": "map_1", "mode": "onto", "state": "resolving", "cityId": "city_1",
                             "reconstructionId": "recon_1", "steps": [], "brief": {"mode": "onto"}}

    def request(self, method, path, body=None):
        self.sent.append((method, path, body))
        if path in ("/api/v1/reconstructions/recon_1/mappings", "/api/v1/mappings/map_1",
                    "/api/v1/mappings/map_1/accept"):
            return self.view
        raise AssertionError(path)


def test_onto_a_place_sends_only_what_was_said():
    platform = Mappings()
    said = tools.mappings_create(platform, "recon_1", "onto", place="city_1", start=[22.3, 38.9], within_m=800)
    method, path, body = platform.sent[-1]
    assert (method, path) == ("POST", "/api/v1/reconstructions/recon_1/mappings")
    assert body == {"mode": "onto", "cityId": "city_1", "withinM": 800.0, "start": {"lat": 22.3, "lon": 38.9}}
    assert said["mapping"] == "map_1" and "mappings_accept" in said["note"]


def test_a_place_of_its_own_needs_a_name_and_onto_needs_a_place():
    platform = Mappings()
    with pytest.raises(Refused):
        tools.mappings_create(platform, "recon_1", "own")
    with pytest.raises(Refused):
        tools.mappings_create(platform, "recon_1", "onto")
    with pytest.raises(Refused):
        tools.mappings_create(platform, "recon_1", "sideways", place="city_1")
    assert platform.sent == []
    tools.mappings_create(platform, "recon_1", "own", name="Thuwal reef", depth_m=6, pad="coral")
    assert platform.sent[-1][2] == {"mode": "own", "name": "Thuwal reef", "pad": "coral", "depthM": 6.0}


def test_candidates_are_shown_compactly_and_marked():
    platform = Mappings({
        "id": "map_1", "mode": "onto", "state": "choosing", "cityId": "city_1", "reconstructionId": "recon_1",
        "brief": {"mode": "onto", "start": {"lat": 22.3, "lon": 38.85}, "startAssumed": True},
        "steps": [{"phase": "resolve", "say": "searching headings", "n": 36, "of": 36}],
        "candidates": [{"at": [12.0, -4.0], "headingDeg": 30.0, "dz": -8.2, "matrix": [[1]],
                        "fit": {"rmsM": 0.31, "score": 0.9, "placeGroundM": -8.4}}],
        "start": [0.0, 0.0]})
    said = tools.mappings_status(platform, "map_1")
    one = said["candidates"][0]
    assert one["index"] == 0 and one["rmsM"]["value"] == 0.31 and one["groundDepthM"]["value"] == -8.4
    assert "matrix" not in one
    assert said["start"]["kind"] == "assumed"
    assert said["steps"] == ["resolve: searching headings (36 of 36)"]
    assert "mappings_accept" in said["next"]
    # An index is what to accept by, not a figure about the sea.
    assert [n for n in numbers(said) if not n.endswith(".index")] == []


def test_accepting_sends_a_candidate_or_a_placement():
    platform = Mappings({"id": "map_1", "mode": "onto", "state": "laying", "steps": [], "brief": {},
                         "chosen": {"at": [12.0, -4.0], "headingDeg": 30.0, "dz": -8.2}})
    tools.mappings_accept(platform, "map_1", candidate=0)
    assert platform.sent[-1][1:] == ("/api/v1/mappings/map_1/accept", {"candidate": 0})
    said = tools.mappings_accept(platform, "map_1", at=[3, 4], heading_deg=45, dz=-1)
    assert platform.sent[-1][2] == {"placement": {"at": [3.0, 4.0], "headingDeg": 45.0, "dz": -1.0}}
    assert said["chosen"]["headingDeg"]["kind"] == "chosen"
    with pytest.raises(Refused):
        tools.mappings_accept(platform, "map_1", at=[3, 4])
    with pytest.raises(Refused):
        tools.mappings_accept(platform, "map_1")
