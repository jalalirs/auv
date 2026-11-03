"""Assets of every kind through MCP: what is sent, and what an agent is told."""

from __future__ import annotations

import pytest

from iocean_mcp import server, tools
from iocean_mcp.platform import Refused
from iocean_mcp.provenance import numbers


class Assets:
    """Enough platform to make assets, watch them, map them and build on them."""

    def __init__(self, view=None):
        self.sent = []
        self.view = view or {"id": "recon_a", "name": "north", "kind": "bathymetry", "madeFrom": "survey",
                             "state": "queued", "steps": []}

    def institution(self):
        return {"id": "org_k", "name": "KAUST"}

    def request(self, method, path, body=None):
        self.sent.append((method, path, body))
        if path in ("/api/v1/organisations/org_k/assets", "/api/v1/organisations/org_k/assets?kind=structure"):
            return self.view if method == "POST" else {"assets": [self.view]}
        if path == "/api/v1/assets/recon_a":
            return self.view
        if path == "/api/v1/cities/city_1/mappings":
            return {"id": "map_1", "mode": "onto", "state": "laying", "cityId": "city_1", "steps": [],
                    "assets": [{"ordinal": 0, "reconstructionId": "recon_s", "name": "jacket", "state": "chosen",
                                "chosen": {"lat": 22.3, "lon": 38.85, "headingDeg": 45}}]}
        if path == "/api/v1/organisations/org_k/cities":
            return {"id": "city_1", "slug": body["slug"], "name": body["name"]}
        if path == "/api/v1/cities/city_1/builds":
            return {"id": "bld_1", "state": "queued", "steps": [], "brief": body}
        raise AssertionError(path)


def test_a_survey_is_sent_with_its_datum_and_error():
    platform = Assets()
    said = tools.assets_create(platform, "bathymetry", object="obj_s", name="north.tif", datum="MSL", error_m=0.3)
    method, path, body = platform.sent[-1]
    assert (method, path) == ("POST", "/api/v1/organisations/org_k/assets")
    assert body == {"kind": "bathymetry", "file": {"name": "north.tif"}, "datum": "MSL", "errorM": 0.3,
                    "object": "obj_s"}
    assert said["asset"] == "recon_a" and said["state"] == "queued" and "assets_status" in said["note"]


def test_a_model_and_a_route_are_structures():
    platform = Assets()
    tools.assets_create(platform, "structure", object="obj_m", name="jacket.glb", type="platform", scale=0.01, up="z")
    assert platform.sent[-1][2] == {"kind": "structure", "type": "platform", "object": "obj_m",
                                    "model": {"name": "jacket.glb", "up": "z", "scale": 0.01}}
    tools.assets_create(platform, "structure", route=[[22.3, 38.85], [22.31, 38.86]], diameter_m=0.5, burial=0.3)
    assert platform.sent[-1][2] == {"kind": "structure", "type": "pipeline",
                                    "route": {"points": [[22.3, 38.85], [22.31, 38.86]], "diameterM": 0.5, "burial": 0.3}}


def test_what_cannot_be_an_asset_is_refused_before_anything_is_sent():
    platform = Assets()
    for asked in ({"kind": "reef", "object": "obj_v"},
                  {"kind": "bathymetry", "object": "obj_s"},
                  {"kind": "structure", "object": "obj_m"},
                  {"kind": "structure", "route": [[22.3, 38.85]], "diameter_m": 0.5},
                  {"kind": "structure", "route": [[22.3, 38.85], [22.4, 38.9]], "diameter_m": 0.5, "object": "obj_m"}):
        with pytest.raises(Refused):
            tools.assets_create(platform, **asked)
    assert platform.sent == []


def test_a_ready_survey_says_which_of_its_figures_were_measured():
    platform = Assets({"id": "recon_a", "name": "north", "kind": "bathymetry", "madeFrom": "survey", "state": "ready",
                       "steps": [{"say": "reading the survey"}], "preview": "https://x/preview.png",
                       "footprint": {"bbox": [22.29, 38.84, 22.31, 38.86]},
                       "stats": {"depthRangeM": [2.1, 31.0], "cellM": 0.5, "datum": "MSL", "errorM": 0.3}})
    said = tools.assets_status(platform, "recon_a")
    assert numbers(said) == []
    assert said["stats"]["depthRangeM"]["kind"] == "measured"
    assert said["stats"]["errorM"]["kind"] == "chosen"
    assert said["stats"]["cellM"]["kind"] == "derived"
    assert said["footprint"]["bbox"]["kind"] == "derived"
    assert "places_build" in said["next"]


def test_a_list_has_every_kind_and_a_reef_speaks_as_a_reconstruction():
    reef = {"id": "recon_r", "name": "GX010", "kind": "reef", "madeFrom": "video", "state": "ready", "steps": [],
            "brief": {"video": {"objectId": "obj_v"}}}
    platform = Assets(reef)
    said = tools.assets_list(platform, "structure")
    assert platform.sent[-1][:2] == ("GET", "/api/v1/organisations/org_k/assets?kind=structure")
    only = said["assets"][0]
    assert only["asset"] == "recon_r" and only["kind"] == "reef" and only["reconstruction"] == "recon_r"


def test_a_structure_is_mapped_with_its_placement():
    platform = Assets()
    said = tools.mappings_create(platform, mode="onto", place="city_1",
                                 assets=[{"asset": "recon_s", "placement": [22.3, 38.85, 45]}, "recon_d"])
    assert platform.sent[-1][2] == {"assets": [
        {"reconstructionId": "recon_s", "placement": {"lat": 22.3, "lon": 38.85, "headingDeg": 45.0}},
        {"reconstructionId": "recon_d"}]}
    assert said["chosen"]["lat"]["kind"] == "chosen"
    assert numbers(said["chosen"]) == []
    with pytest.raises(Refused):
        tools.mappings_create(platform, mode="onto", place="city_1", assets=[{"asset": "recon_s", "placement": [22.3]}])


def test_a_place_is_built_on_a_survey_over_the_square_it_covers():
    platform = Assets({"id": "recon_a", "footprint": {"bbox": [22.29, 38.84, 22.31, 38.86]}})
    said = tools.places_build(platform, "North survey", survey=["recon_a"], sources=["allen-coral-atlas"])
    brief = platform.sent[-1][2]
    assert brief["survey"] == ["recon_a"]
    assert brief["centre"] == pytest.approx([22.30, 38.85])
    assert brief["acrossM"] == pytest.approx(0.02 * 111_320, rel=1e-6)
    assert said["build"] == "bld_1"


def test_the_asset_tools_are_offered():
    for name in ("assets_create", "assets_list", "assets_status"):
        assert name in server.TOOLS
    assert "survey" in server.TOOLS["places_build"][1]["properties"]
    assert "placement" in server.TOOLS["mappings_create"][1]["properties"]


def test_a_cover_map_carries_its_classes_and_where_it_came_from():
    platform = Assets()
    tools.assets_create(platform, "cover", object="obj_c", name="habitat.tif", citation="Allen Coral Atlas",
                        classes={1: "sand", 3: "seagrass"}, origin="public", licence="CC BY 4.0")
    assert platform.sent[-1][2] == {"kind": "cover", "file": {"format": "geotiff", "name": "habitat.tif"},
                                    "object": "obj_c", "citation": "Allen Coral Atlas",
                                    "classes": {"1": "sand", "3": "seagrass"}, "origin": "public",
                                    "licence": "CC BY 4.0"}
    tools.assets_create(platform, "species", object="obj_l", citation="RSG reef survey 2025")
    assert platform.sent[-1][2]["file"] == {"format": "json"}
