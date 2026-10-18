"""The map store through MCP: what an agent is shown, and how it uses a place."""

from __future__ import annotations

import pytest

from iocean_mcp import tools
from iocean_mcp.platform import Refused
from iocean_mcp.provenance import numbers

AL_FAHAL = {"id": "city_af", "slug": "al-fahal", "name": "Al Fahal", "summary": "a reef off Thuwal",
            "extent": {"west": 38.947, "south": 22.270, "east": 38.977, "north": 22.297},
            "versionId": "ver_10", "deepestM": 31.0, "shallowestM": 0.4, "surveyed": False,
            "method": "Sentinel-2, calibrated by ICESat-2", "colonies": 2400000, "adopted": False,
            "picture": {"path": "picture.jpg", "objectId": "obj_p"}, "distanceM": 120.4}


class Store:
    def __init__(self):
        self.sent = []

    def institution(self):
        return {"id": "org_k", "name": "KAUST"}

    def request(self, method, path, body=None):
        self.sent.append((method, path, body))
        if path.startswith("/api/v1/store/places"):
            return {"places": [AL_FAHAL]}
        if path == "/api/v1/organisations/org_k/store/city_af/adopt":
            return {"id": "bind_1", "via": "store"}
        if path == "/api/v1/organisations/org_k/cities":
            return {"id": "city_new", "slug": body["slug"], "name": body["name"]}
        if path == "/api/v1/cities/city_new/builds":
            return {"id": "bld_1", "state": "queued", "steps": [], "brief": body}
        raise AssertionError(path)


def test_the_store_near_an_area_is_asked_for_that_area_and_every_number_is_marked():
    platform = Store()
    said = tools.store_places(platform, near=[22.284, 38.962], across_m=500)
    assert platform.sent[-1][1] == "/api/v1/store/places?near=22.284,38.962&acrossM=500.0"
    card = said["places"][0]
    assert card["place"] == "city_af" and card["picture"] is True and card["adopted"] is False
    assert card["colonies"]["kind"] == "assumed" and "estimated" in card["measured"]
    assert numbers(said) == []
    assert "overlap" in said["note"]


def test_a_store_place_is_adopted_for_the_institution():
    platform = Store()
    said = tools.store_adopt(platform, "city_af")
    assert platform.sent[-1][:2] == ("POST", "/api/v1/organisations/org_k/store/city_af/adopt")
    assert said["adopted"] is True and said["share"] == "bind_1"


def test_building_on_a_store_place_takes_its_square_and_names_it_as_the_base():
    platform = Store()
    said = tools.places_build(platform, "Al Fahal with our survey", base_place="city_af",
                              files=[{"objectId": "obj_dem", "use": "raster", "name": "dem.tif"}])
    brief = platform.sent[-1][2]
    assert brief["base"] == {"cityId": "city_af"} and brief["sources"] == []
    assert abs(brief["centre"][0] - 22.2835) < 1e-6 and abs(brief["acrossM"] - 3005.6) < 1
    assert said["builtOn"] == {"cityId": "city_af"}


def test_a_base_outside_the_store_needs_its_centre_given():
    platform = Store()
    with pytest.raises(Refused):
        tools.places_build(platform, "x", base_place="city_elsewhere")
