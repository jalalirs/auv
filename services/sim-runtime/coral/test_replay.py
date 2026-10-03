"""A dive flown again from its commands is the same dive, tick for tick:
how a path-traced film is made of a run somebody watched live."""

import numpy as np

from test_nothing_to_see import a_dive, a_place


def flown(city, seed, **brief):
    dive = a_dive(city, seed=seed, durationSeconds=20,
                  objective={"kind": "reach", "dx": 6.0, "dy": 2.0, "radiusM": 0.5, "timeLimitS": 20.0}, **brief)
    assert dive.open_dry()
    track = []
    while not dive.done:
        dive.step()
        track.append(np.array(dive.position, dtype=float))
    helm = next(s for s in dive.engine.systems if s.name == "helm")
    return np.array(track), helm.commands()


def test_the_commands_fly_the_same_dive(tmp_path):
    city = a_place(tmp_path)
    track, commands = flown(city, seed=4)
    assert commands.shape[0] == len(track) and np.abs(commands).max() > 0
    np.save(tmp_path / "commands.npy", commands)
    again, replayed = flown(city, seed=4, replay={"commands": str(tmp_path / "commands.npy")})
    assert np.array_equal(again, track)
    assert np.array_equal(replayed, commands)


def test_other_commands_fly_another_dive(tmp_path):
    city = a_place(tmp_path)
    track, commands = flown(city, seed=4)
    np.save(tmp_path / "commands.npy", -commands)
    again, _ = flown(city, seed=4, replay={"commands": str(tmp_path / "commands.npy")})
    assert not np.allclose(again, track)
