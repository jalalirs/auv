"""A place's world: written from the place until one is saved, then kept as versions."""

from __future__ import annotations

import pytest

from iocean_mcp import tools
from iocean_mcp.platform import Refused


class Worlds:
    """A tank with a package and an arrangement, and no world yet."""

    def __init__(self):
        self.sent = []
        self.worlds = []

    def places(self):
        return [{"id": "city_t", "slug": "tank", "name": "Tank",
                 "extent": {"west": 0, "south": 0, "east": 0, "north": 0}}]

    def versions_of_place(self, place):
        return [{"id": "ver_1", "ordinal": 3, "publishedAt": "2026-11-01T00:00:00Z", "createdAt": "2026-11-01T00:00:00Z"}]

    def files(self, version):
        return []

    def layouts_of(self, place):
        return [{"id": "lay_1"}]

    def request(self, method, path, body=None):
        self.sent.append((method, path, body))
        if path == "/api/v1/cities/city_t/worlds" and method == "GET":
            return {"worlds": self.worlds}
        if path == "/api/v1/cities/city_t/worlds":
            self.worlds.append({"id": "wld_1", **body})
            return self.worlds[-1]
        if path == "/api/v1/layouts/lay_1/versions":
            return {"versions": [{"id": "v", "ordinal": 1, "createdAt": "2026-11-02T00:00:00Z",
                                  "document": {"things": [{"id": "t1", "kind": "transponder", "x": 1, "y": 2}]}}]}
        if path == "/api/v1/worlds/wld_1/versions":
            return {"id": "ver_w1", "ordinal": 1}
        raise AssertionError(path)


def test_a_place_with_no_world_is_given_one_written_from_it(monkeypatch):
    platform = Worlds()
    monkeypatch.setattr(tools, "_site_of", lambda p, place: {"enclosed": True, "water": {"type": "I"},
                                                             "from": {"acrossMetres": 2}})
    got = tools.worlds_get(platform, "tank")
    document = got["document"]
    assert got["world"] is None and document["iocean"] == "world/1"
    assert document["georef"] is None and document["frame"]["extentM"] == [2, 2]
    assert document["bake"]["version"] == "ver_1"
    structures = next(l for l in document["layers"] if l["kind"] == "structures")
    assert structures["items"] == [{"id": "t1", "kind": "transponder", "x": 1, "y": 2}]


def test_saving_makes_the_world_first(monkeypatch):
    platform = Worlds()
    said = tools.worlds_save(platform, "tank", {"iocean": "world/1", "layers": []}, "first")
    assert said == {"place": "Tank", "world": "wld_1", "version": "ver_w1", "ordinal": 1}
    assert platform.sent[-1] == ("POST", "/api/v1/worlds/wld_1/versions",
                                 {"label": "first", "document": {"iocean": "world/1", "layers": []}})
    with pytest.raises(Refused):
        tools.worlds_save(platform, "tank", {"things": []})
