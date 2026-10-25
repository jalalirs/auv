"""Retiring a place through MCP: it leaves the list, and still reads by id."""

from __future__ import annotations

import pytest

from iocean_mcp import server, tools
from iocean_mcp.platform import Refused

LIVE = {"id": "city_t1", "slug": "test-one", "name": "Test one"}
RETIRED = {**LIVE, "retiredAt": "2026-10-25T09:00:00Z", "retiredBy": "prin_r"}


class Places:
    """A platform with one place, listed until it is retired."""

    def __init__(self, retired=False):
        self.retired = retired
        self.sent = []

    def places(self):
        return [] if self.retired else [LIVE]

    def place(self, place):
        if place != LIVE["id"]:
            raise Refused(404, "not_found", "no such place")
        return RETIRED if self.retired else LIVE

    def request(self, method, path, body=None):
        self.sent.append((method, path))
        if path == "/api/v1/cities/city_t1/retire":
            self.retired = True
            return RETIRED
        if path == "/api/v1/cities/city_t1/unretire":
            self.retired = False
            return LIVE
        raise AssertionError(path)


def test_a_place_is_retired_by_its_slug_and_says_when_and_by_whom():
    platform = Places()
    said = tools.places_retire(platform, "test-one")
    assert platform.sent == [("POST", "/api/v1/cities/city_t1/retire")]
    assert said["retired"] == {"at": "2026-10-25T09:00:00Z", "by": "prin_r"}
    assert "history" in said["retiredNote"]


def test_a_retired_place_is_brought_back_by_its_id():
    platform = Places(retired=True)
    said = tools.places_unretire(platform, "city_t1")
    assert platform.sent == [("POST", "/api/v1/cities/city_t1/unretire")]
    assert said["retired"] is False


def test_places_get_still_reads_a_retired_place_and_says_so(monkeypatch):
    monkeypatch.setattr(tools, "_site_of", lambda platform, place: None)
    said = tools.places_get(Places(retired=True), "city_t1")
    assert said["id"] == "city_t1"
    assert said["retired"]["at"] == "2026-10-25T09:00:00Z"


def test_a_place_in_use_says_nothing_about_retiring(monkeypatch):
    monkeypatch.setattr(tools, "_site_of", lambda platform, place: None)
    said = tools.places_get(Places(), "test-one")
    assert "retired" not in said


def test_an_unknown_place_is_not_found():
    with pytest.raises(Refused):
        tools.places_retire(Places(), "nowhere")


def test_both_tools_are_offered():
    assert {"places_retire", "places_unretire"} <= set(server.TOOLS)
