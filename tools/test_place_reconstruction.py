"""A reconstructed reef patch put into a place: one more prototype, one
instance, and the colonies on its footprint taken out."""

import importlib.machinery
import importlib.util
import json
import pathlib

import numpy as np

import coral_hd
import reef

_path = pathlib.Path(__file__).resolve().parent / "place-reconstruction"
_spec = importlib.util.spec_from_loader("place_reconstruction",
                                        importlib.machinery.SourceFileLoader("place_reconstruction", str(_path)))
place_reconstruction = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(place_reconstruction)


def _a_place(tmp_path):
    v, f = coral_hd.upper(*coral_hd.icosphere(1))
    v[:, 2] -= v[:, 2].min()
    rng = np.random.default_rng(0)
    x, y = rng.uniform(-40, 40, 400), rng.uniform(-40, 40, 400)
    z = np.full(400, -8.0)
    text = reef._instancer([(v, f), (v * 0.5, f)], [(0.6, 0.5, 0.3), (0.5, 0.5, 0.4)], ["massive", "brain"],
                           x, y, z, rng.integers(0, 2, 400), np.full(400, 1.5), np.zeros(400))
    (tmp_path / "coral.usda").write_text(text)
    (tmp_path / "site.json").write_text(json.dumps({
        "from": {"acrossMetres": 100.0}, "beginAt": [10.0, 10.0, -5.0],
        "reef": {"colonies": 400, "prototypeKinds": ["massive", "brain"], "prototypeAreaM2": [0.8, 0.2]}}))
    return x, y


def _a_patch(folder: pathlib.Path, at, heading=0.0):
    folder.mkdir(parents=True)
    gx, gy = np.meshgrid(np.linspace(-5, 5, 11), np.linspace(-2, 2, 5))
    v = np.stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)], -1)
    f = []
    for r in range(4):
        for c in range(10):
            a = r * 11 + c
            f += [[a, a + 1, a + 12], [a, a + 12, a + 11]]
    coral_hd.write_ply(folder / "patch.ply", v, np.array(f), np.full((len(v), 3), 0.5))
    (folder / "placement.json").write_text(json.dumps({"name": "test-patch", "at": list(at), "headingDeg": heading,
                                                       "how": "coordinates given", "kind": "chosen"}))


def test_a_patch_is_planted_and_the_colonies_under_it_go(tmp_path):
    x, y = _a_place(tmp_path)
    _a_patch(tmp_path / "reconstructions" / "test-patch", (0.0, 0.0))
    place_reconstruction.apply(tmp_path)
    text = (tmp_path / "coral.usda").read_text()
    after = place_reconstruction.read_reef(text)
    assert after["prototypes"][-1] == "/Coral/Grown/Reconstruction_test_patch"
    assert 'def Material "Skin_test_patch"' in text and "corallite" not in text.split("Skin_test_patch")[1][:2000]
    under = (np.abs(x) < 5.3) & (np.abs(y) < 2.3)
    far = (np.abs(x) > 6.5) | (np.abs(y) > 3.5)
    assert len(after["which"]) <= 400 - under.sum() + 1
    assert len(after["which"]) >= 400 - (~far).sum() + 1
    assert after["which"][-1] == 2 and np.allclose(after["positions"][-1, :2], [0, 0])
    site = json.loads((tmp_path / "site.json").read_text())
    assert site["reconstructions"][0]["coloniesRemoved"] >= under.sum()
    assert site["builtBy"]["place-reconstruction"]["argv"] == [str(tmp_path.resolve())]
    # Applied twice, it is there once.
    place_reconstruction.apply(tmp_path)
    assert (tmp_path / "coral.usda").read_text().count("def Mesh \"Reconstruction_test_patch\"") == 1


def test_the_most_likely_spot_is_one_whose_cover_matches_the_video(tmp_path):
    _a_place(tmp_path)
    site = json.loads((tmp_path / "site.json").read_text())
    got = place_reconstruction.choose(site, place_reconstruction.read_reef((tmp_path / "coral.usda").read_text()),
                                      0.05, 100.0)
    assert got["kind"] == "derived" and abs(got["placeCoverThere"] - 0.05) < 0.05
    assert place_reconstruction.choose(site, place_reconstruction.read_reef(
        (tmp_path / "coral.usda").read_text()), None, 100.0)["how"] == "the middle of the site"
