"""Asking for the film of a run: the run is chosen here, the rest by the platform."""

import pytest

from coral_city_mcp import tools
from coral_city_mcp.tools import Refused


class Platform:
    def __init__(self, runs):
        self._runs = runs
        self.asked = []

    def runs(self, dive_id):
        return self._runs

    def request(self, method, path, body=None):
        self.asked.append((method, path, body))
        return {"dive": {"id": "dive_film"}, "run": {"id": "run_film", "state": "queued", "seed": 7}}


def test_the_latest_run_is_filmed_unless_one_is_named():
    p = Platform([{"id": "run_a", "createdAt": "2026-10-04T01:00:00Z"},
                  {"id": "run_b", "createdAt": "2026-10-04T02:00:00Z"}])
    said = tools.dives_film(p, "dive_x", views=["glass"], view_every_s=5)
    assert p.asked == [("POST", "/api/v1/dives/dive_x/runs/run_b/film", {"views": ["glass"], "viewEveryS": 5.0})]
    assert said["filmOf"] == "run_b" and said["dive"] == "dive_film" and said["seed"] == 7
    tools.dives_film(p, "dive_x", run_id="run_a")
    assert p.asked[-1] == ("POST", "/api/v1/dives/dive_x/runs/run_a/film", {})


def test_a_dive_never_flown_has_nothing_to_film():
    with pytest.raises(Refused):
        tools.dives_film(Platform([]), "dive_x")
    with pytest.raises(Refused):
        tools.dives_film(Platform([{"id": "run_a"}]), "dive_x", run_id="run_z")
