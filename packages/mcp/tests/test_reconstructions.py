"""Making a reef from a dive video through MCP: what is sent, and what an agent is told."""

from __future__ import annotations

import pytest

from iocean_mcp import tools
from iocean_mcp.platform import Refused
from iocean_mcp.provenance import numbers


class Reconstructions:
    """Enough platform to start a reconstruction and watch it."""

    def __init__(self, view=None):
        self.sent = []
        self.view = view or {"id": "recon_1", "name": "GX010", "state": "queued", "steps": [],
                             "brief": {"video": {"objectId": "obj_v"}}}

    def institution(self):
        return {"id": "org_k", "name": "KAUST"}

    def request(self, method, path, body=None):
        self.sent.append((method, path, body))
        if path == "/api/v1/organisations/org_k/reconstructions" and method == "POST":
            return self.view
        if path == "/api/v1/organisations/org_k/reconstructions":
            return {"reconstructions": [self.view]}
        if path == "/api/v1/reconstructions/recon_1":
            return self.view
        raise AssertionError(path)


def test_a_reconstruction_is_asked_for_the_institution_with_only_what_was_said():
    platform = Reconstructions()
    said = tools.reconstructions_create(platform, "obj_v", "GX010.MP4", camera_height_m=1.5,
                                        start=[22.3, 38.9], label="Al Fahal north")
    method, path, brief = platform.sent[-1]
    assert (method, path) == ("POST", "/api/v1/organisations/org_k/reconstructions")
    assert brief == {"video": {"objectId": "obj_v", "name": "GX010.MP4"}, "label": "Al Fahal north",
                     "cameraHeightM": 1.5, "start": {"lat": 22.3, "lon": 38.9}}
    assert said["reconstruction"] == "recon_1" and said["state"] == "queued"
    assert "reconstructions_status" in said["note"]


def test_a_start_that_is_not_a_place_is_refused_before_anything_is_sent():
    platform = Reconstructions()
    with pytest.raises(Refused):
        tools.reconstructions_create(platform, "obj_v", start=[22.3])
    assert platform.sent == []


def test_a_finished_reconstruction_says_how_big_the_reef_is_and_that_its_scale_was_assumed():
    platform = Reconstructions({
        "id": "recon_1", "name": "GX010", "state": "ready",
        "brief": {"video": {"objectId": "obj_v"}},
        "steps": [{"say": "training piece", "n": 3, "of": 3}],
        "manifest": {"frames": 240, "registered": 236, "extentM": [18.2, 9.5],
                     "pieces": [{"part": "parts/part-1.usdz", "splats": 300000},
                                {"part": "parts/part-2.usdz", "splats": 250000}],
                     "scale": {"factor": 1.0, "how": "assumed", "from": "camera height 1.92 m"}}})
    said = tools.reconstructions_status(platform, "recon_1")
    reef = said["reef"]
    assert reef["pieces"]["value"] == 2 and reef["splats"]["value"] == 550000
    assert reef["extentM"]["kind"] == "assumed" and "1.92" in reef["extentM"]["from"]
    assert said["steps"] == ["training piece (3 of 3)"]
    assert numbers(said) == []
    assert "objects" in said["next"]


def test_a_list_is_the_institutions_own():
    platform = Reconstructions()
    said = tools.reconstructions_list(platform)
    assert platform.sent[-1][:2] == ("GET", "/api/v1/organisations/org_k/reconstructions")
    assert [r["reconstruction"] for r in said["reconstructions"]] == ["recon_1"]
