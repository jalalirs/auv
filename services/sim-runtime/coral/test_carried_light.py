"""A place that brings its own light turns the water's effects off."""

from runner import CARRIED_LIGHT, light_carried_by


def test_a_place_of_splats_turns_the_water_off(monkeypatch):
    for k in CARRIED_LIGHT:
        monkeypatch.delenv(k, raising=False)
    assert light_carried_by({"light": {"carriedByThePlace": True}}) == CARRIED_LIGHT


def test_an_ordinary_place_changes_nothing():
    assert light_carried_by({"water": {"type": "IB"}}) == {}
    assert light_carried_by({}) == {}


def test_what_a_dive_set_by_hand_is_kept(monkeypatch):
    for k in CARRIED_LIGHT:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("IOCEAN_ISO", "120")
    assert "IOCEAN_ISO" not in light_carried_by({"light": {"carriedByThePlace": True}})
