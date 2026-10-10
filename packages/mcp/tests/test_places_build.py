"""Building a place through MCP: what is sent, and what an agent is told."""

from __future__ import annotations

from iocean_mcp import tools
from iocean_mcp.platform import Refused


class Builds:
    """Enough platform to found a place and build it; the first slug is taken."""

    def __init__(self):
        self.sent = []

    def institution(self):
        return {"id": "org_k", "name": "KAUST"}

    def request(self, method, path, body=None):
        self.sent.append((method, path, body))
        if path == "/api/v1/organisations/org_k/cities":
            if body["slug"] == "thuwal-north":
                raise Refused(400, "invalid", 'invalid value: a city named "thuwal-north" already exists')
            return {"id": "city_1", "slug": body["slug"], "name": body["name"]}
        if path == "/api/v1/cities/city_1/builds":
            return {"id": "bld_1", "state": "queued", "steps": []}
        raise AssertionError(path)


def test_a_place_is_founded_for_the_institution_and_built_from_public_data():
    platform = Builds()
    said = tools.places_build(platform, "Thuwal North", [22.3, 38.95], 1000)
    founded = [b for m, p, b in platform.sent if p.endswith("/cities")]
    assert [f["slug"] for f in founded] == ["thuwal-north", "thuwal-north-2"]
    extent = founded[-1]["extent"]
    assert abs((extent["north"] - extent["south"]) * 111_320 - 1000) < 1
    brief = platform.sent[-1][2]
    assert brief == {"centre": [22.3, 38.95], "acrossM": 1000.0,
                     "sources": ["gebco", "sentinel2", "allen-coral-atlas"]}
    assert said["place"]["slug"] == "thuwal-north-2" and said["build"] == "bld_1"
    assert said["state"] == "queued"


def test_a_finished_build_says_how_wrong_its_depth_may_be_and_what_made_it():
    said = tools._build_summary({
        "id": "bld_1", "state": "ready", "versionId": "ver_9",
        "steps": [{"say": "reading gebco", "n": 4, "of": 4}, {"say": "built"}],
        "result": {"deepestM": 31.2, "depth": {
            "sources": [{"source": "sentinel2-stumpf", "kind": "derived", "share": 0.7},
                        {"source": "gebco", "kind": "measured", "share": 0.3}],
            "weak": {"errorM": {"median": 4.1, "p90": 10.0, "worst": 10.0}, "byKind": {"derived": 0.7}}}}})
    assert said["version"] == "ver_9" and said["published"] is False
    assert said["howWrongTheDepthMayBe"]["medianM"]["value"] == 4.1
    assert said["howWrongTheDepthMayBe"]["medianM"]["kind"] == "derived"
    assert said["madeBy"][0]["share"] == 0.7
    assert said["steps"] == ["reading gebco (4 of 4)", "built"]
    assert "places_publish" in said["next"]
