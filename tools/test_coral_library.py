"""A reef planted from a coral library, where the place's assemblage has one."""

import json
import re

import numpy as np

import coral_hd
import reef


def test_a_colony_comes_back_as_it_was_written(tmp_path):
    v, f = coral_hd.upper(*coral_hd.icosphere(2))
    c = np.random.default_rng(0).random((len(v), 3))
    coral_hd.write_ply(tmp_path / "a.ply", v, f, c)
    v2, f2, c2 = coral_hd.read_ply(tmp_path / "a.ply")
    assert np.allclose(v, v2, atol=1e-6) and (f == f2).all()
    assert np.allclose(c, c2, atol=1 / 255)


def test_a_crevice_is_darker_than_an_open_top():
    # Two upright fingers two centimetres apart: their facing sides are shut
    # in, their tops are open.
    field = coral_hd.Field([-0.08, -0.05, -0.01], [0.08, 0.05, 0.15], 0.002, k=0.002)
    field.capsule([-0.02, 0, 0], [-0.02, 0, 0.1], 0.01)
    field.capsule([0.02, 0, 0], [0.02, 0, 0.1], 0.01)
    v, f, _ = field.mesh()
    open_to = coral_hd.occlusion(v, f)
    tops = v[:, 2] > 0.105
    facing = (np.abs(v[:, 0]) < 0.012) & (v[:, 2] > 0.03) & (v[:, 2] < 0.08)
    assert tops.any() and facing.any()
    assert open_to[tops].mean() > 0.85
    assert open_to[facing].mean() < open_to[tops].mean() - 0.3


def test_a_reef_plants_the_kinds_its_library_has(tmp_path, monkeypatch):
    shelf = tmp_path / "library" / "red-sea"
    shelf.mkdir(parents=True)
    v, f = coral_hd.upper(*coral_hd.icosphere(3))
    v[:, 2] -= v[:, 2].min()
    coral_hd.write_ply(shelf / "massive-0.ply", v * 0.3, f, np.full((len(v), 3), 0.5))
    (shelf / "library.json").write_text(json.dumps({"made": "now", "commit": "test", "how": "a test",
                                                    "kinds": {"massive": [{"file": "massive-0.ply", "form": "porites",
                                                                           "corallite": "porites",
                                                                           "colour": [0.6, 0.5, 0.3]}]}}))
    monkeypatch.setenv("IOCEAN_CORAL_LIBRARY", str(tmp_path / "library"))
    height = np.full((48, 48), -6.0)
    said = reef.plant(tmp_path / "place", height, 60.0, 1, 3000, cover_from="a test", assemblage="red-sea")
    assert said["fromLibrary"]["prototypes"] == 6                     # every massive variant, and only those
    text = (tmp_path / "place" / "coral.usda").read_text()
    assert text.count('subdivisionScheme = "none"') == 6
    # Each library colony carries its colour at every point, for the material.
    import re
    painted = re.findall(r'primvars:displayColor = \[[^\]]*\] \(\s*interpolation = "vertex"', text)
    assert len(painted) == 6
    assert (tmp_path / "place" / "textures" / "corallite_porites_normal.png").is_file()
    massive = [i for i, k in enumerate(said["prototypeKinds"]) if k == "massive"]
    # Scaled to stand as tall as the grown prototype of that size would.
    assert all(said["prototypeAreaM2"][i] > 0 for i in massive)


def test_without_a_library_nothing_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("IOCEAN_CORAL_LIBRARY", str(tmp_path / "none"))
    said = reef.plant(tmp_path / "place", np.full((48, 48), -6.0), 60.0, 1, 3000, cover_from="a test",
                      assemblage="red-sea")
    assert said["fromLibrary"] is None
    assert 'subdivisionScheme = "none"' not in (tmp_path / "place" / "coral.usda").read_text()


def test_a_library_with_rock_lays_the_reef_framework_and_it_is_not_coral(tmp_path, monkeypatch):
    shelf = tmp_path / "library" / "red-sea"
    shelf.mkdir(parents=True)
    v, f = coral_hd.upper(*coral_hd.icosphere(2))
    v[:, 2] -= v[:, 2].min()
    v[:, 2] *= 0.3
    coral_hd.write_ply(shelf / "rock-0.ply", v, f, np.full((len(v), 3), 0.3))
    (shelf / "library.json").write_text(json.dumps({"made": "now", "commit": "test", "how": "a test",
                                                    "kinds": {"rock": [{"file": "rock-0.ply", "form": "reef_rock",
                                                                        "corallite": None,
                                                                        "colour": [0.3, 0.3, 0.3]}]}}))
    monkeypatch.setenv("IOCEAN_CORAL_LIBRARY", str(tmp_path / "library"))
    height = np.full((48, 48), -6.0)
    said = reef.plant(tmp_path / "place", height, 60.0, 1, 3000, cover_from="a test", assemblage="red-sea",
                      hard=np.ones((48, 48)))
    frame = said["framework"]
    assert frame and frame["pieces"] > 0 and frame["prototypes"] == 1
    assert said["prototypeKinds"][-1] == "rock" and len(said["prototypeKinds"]) == len(said["prototypeAreaM2"])
    assert said["prototypeKinds"].count("rock") == 1
    text = (tmp_path / "place" / "coral.usda").read_text()
    indices = [int(i) for i in re.search(r"int\[\] protoIndices = \[(.*)\]", text).group(1).split(", ")]
    assert len(indices) == said["colonies"] + frame["pieces"]
    assert indices.count(frame["firstPrototype"]) == frame["pieces"]
