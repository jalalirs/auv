"""Assets that are not reefs: each brief kind on something small, and the
arithmetic of laying a structure into a place."""

import json
import math
import pathlib
import sys
import tarfile

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))


def run_asset(tmp_path, monkeypatch, brief):
    from iocean_reconstruct import asset, job

    for module in (asset, job):
        monkeypatch.setattr(module, "INPUTS", tmp_path / "inputs")
        monkeypatch.setattr(module, "OUTPUTS", tmp_path / "outputs")
        monkeypatch.setattr(module, "SCRATCH", tmp_path / "outputs" / "scratch")
    (tmp_path / "outputs").mkdir(exist_ok=True)
    assert asset.main([json.dumps(brief)]) == 0
    with tarfile.open(tmp_path / "outputs" / "asset.tar") as archive:
        names = archive.getnames()
        made = json.load(archive.extractfile("asset.json"))
        archive.extractall(tmp_path / "unpacked", filter="data")
    assert "preview.png" in names and made["preview"] == "preview.png"
    return made, names


def test_a_geotiff_survey_is_measured_and_kept(tmp_path, monkeypatch):
    rasterio = pytest.importorskip("rasterio")
    pytest.importorskip("matplotlib")
    from rasterio.transform import from_origin

    source = tmp_path / "inputs" / "source"
    source.mkdir(parents=True)
    depth = -np.linspace(2, 20, 40 * 30, dtype="float32").reshape(30, 40)
    depth[0, 0] = -9999
    with rasterio.open(source / "survey.tif", "w", driver="GTiff", width=40, height=30, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(38.96, 22.29, 0.0001, 0.0001), nodata=-9999) as d:
        d.write(depth, 1)
    made, names = run_asset(tmp_path, monkeypatch, {"kind": "bathymetry", "datum": "MSL", "errorM": 0.3,
                                                    "file": {"path": "source/survey.tif", "name": "survey.tif",
                                                             "format": "geotiff"}})
    assert made["kind"] == "bathymetry" and made["madeFrom"] == "survey"
    assert "survey.tif" in names and made["file"]["name"] == "survey.tif"
    south, west, north, east = made["footprint"]["bbox"]
    assert math.isclose(west, 38.96, abs_tol=1e-6) and math.isclose(north, 22.29, abs_tol=1e-6)
    assert math.isclose(east, 38.964, abs_tol=1e-6) and math.isclose(south, 22.287, abs_tol=1e-6)
    stats = made["stats"]
    assert stats["datum"] == "MSL" and stats["errorM"] == 0.3
    assert 2.0 <= stats["shallowestM"] < 2.1 and stats["deepestM"] == 20.0
    assert 10.0 < stats["cellM"][0] < 10.5 and 11.0 < stats["cellM"][1] < 11.2      # 0.0001 degrees
    assert stats["cells"] == [40, 30]


def test_soundings_are_latitude_longitude_depth(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    source = tmp_path / "inputs" / "source"
    source.mkdir(parents=True)
    (source / "soundings.csv").write_text("lat,lon,depth\n22.28,38.96,4.5\n22.281,38.961,7.25\n22.282,38.962,12\n")
    made, names = run_asset(tmp_path, monkeypatch, {"kind": "bathymetry", "datum": "LAT", "errorM": 0.2,
                                                    "file": {"path": "source/soundings.csv", "name": "soundings.csv",
                                                             "format": "xyz"}})
    assert made["footprint"]["bbox"] == [22.28, 38.96, 22.282, 38.962]
    assert made["stats"]["points"] == 3 and made["stats"]["deepestM"] == 12.0
    assert made["stats"]["valuesAre"].startswith("depths")
    # Kept as longitude, latitude, height: the order the places job reads.
    assert "soundings.xyz" in names and made["file"]["name"] == "soundings.xyz"


def test_a_model_is_metres_z_up_centred_on_its_base(tmp_path, monkeypatch):
    pytest.importorskip("trimesh")
    pytest.importorskip("pxr")
    source = tmp_path / "inputs" / "source"
    source.mkdir(parents=True)
    # A cube 2 units a side, y up, its corner at (10, 5, 3): at a scale of 0.5, one metre.
    corners = [(x, y, z) for x in (10, 12) for y in (5, 7) for z in (3, 5)]
    quads = [(1, 2, 4, 3), (5, 7, 8, 6), (1, 5, 6, 2), (3, 4, 8, 7), (1, 3, 7, 5), (2, 6, 8, 4)]
    (source / "cube.obj").write_text("".join(f"v {x} {y} {z}\n" for x, y, z in corners)
                                     + "".join("f " + " ".join(map(str, q)) + "\n" for q in quads))
    made, names = run_asset(tmp_path, monkeypatch, {
        "kind": "structure", "type": "platform", "meets": "stands",
        "model": {"path": "source/cube.obj", "name": "cube.obj", "format": "obj", "scale": 0.5, "up": "y"}})
    assert made["madeFrom"] == "model" and made["type"] == "platform" and made["meets"] == "stands"
    assert made["footprint"]["sizeM"] == [1.0, 1.0, 1.0] and made["stats"]["triangles"] == 12
    assert "model.usdc" in names
    from iocean_reconstruct.asset import read_usd_mesh

    points, faces = read_usd_mesh(tmp_path / "unpacked" / "model.usdc")
    assert np.allclose(points.min(0), [-0.5, -0.5, 0.0]) and np.allclose(points.max(0), [0.5, 0.5, 1.0])
    assert faces.shape == (12, 3)


def test_a_route_is_measured(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    made, names = run_asset(tmp_path, monkeypatch, {
        "kind": "structure", "type": "pipeline", "meets": "drapes",
        "route": {"points": [[22.28, 38.96], [22.28, 38.961], [22.281, 38.961]], "diameterM": 0.5, "burial": 0.3}})
    assert made["madeFrom"] == "route" and made["footprint"]["bbox"] == [22.28, 38.96, 22.281, 38.961]
    # 0.001 degrees east and north at 22.28: about 103 m and 110.7 m.
    assert 213 < made["stats"]["lengthM"] < 214.5 and made["stats"]["diameterM"] == 0.5
    assert made["route"]["burial"] == 0.3 and len(made["route"]["points"]) == 3


def test_a_bad_route_is_refused(tmp_path, monkeypatch):
    from iocean_reconstruct import asset

    with pytest.raises(ValueError, match="two points"):
        asset.made({"kind": "structure", "route": {"points": [[22.0, 38.0]], "diameterM": 0.5}}, tmp_path)
    with pytest.raises(ValueError, match="latitude"):
        asset.made({"kind": "structure", "route": {"points": [[122.0, 38.0], [22.0, 38.0]], "diameterM": 0.5}},
                   tmp_path)
    with pytest.raises(ValueError, match="burial"):
        asset.made({"kind": "structure", "route": {"points": [[22.0, 38.0], [22.0, 38.1]], "diameterM": 0.5,
                                                   "burial": 2}}, tmp_path)


# -- laying ---------------------------------------------------------------------------------------------

def a_place(tmp_path, slope=0.01):
    """A place 200 m across whose seabed falls 1 m in 100 to the east, -10 m at the middle."""
    n = 101
    x = np.linspace(-100, 100, n)
    heights = np.tile(-10.0 - slope * x, (n, 1)).astype("<f4")
    heights.tofile(tmp_path / "seabed.f32")
    site = {"from": {"centre": {"latitude": 22.284, "longitude": 38.962}, "acrossMetres": 200.0},
            "mesh": {"heightfield": {"rows": n, "columns": n, "file": "seabed.f32"}},
            "layers": {"terrain": "seabed.usda", "heightfield": "seabed.f32"}}
    (tmp_path / "site.json").write_text(json.dumps(site))
    return site


def test_a_structure_stands_at_its_latitude_and_longitude_on_the_seabed(tmp_path):
    from iocean_reconstruct.lay import seabed_of, stand_at

    site = a_place(tmp_path)
    under = seabed_of(tmp_path, site)
    at = stand_at(site, {"lat": 22.284 + 0.0001, "lon": 38.962 + 0.0002, "headingDeg": 90}, under)
    x, y = at["at"]
    assert 20.5 < x < 20.8 and 11.0 < y < 11.1
    assert math.isclose(at["baseZ"], -10.0 - 0.01 * x, abs_tol=1e-6)
    m = np.array(at["matrix"])
    # Turned a quarter: the model's x runs north; its origin on the seabed there.
    assert np.allclose(m[:3, 0], [0, 1, 0], atol=1e-9) and np.allclose(m[:3, 3], [x, y, at["baseZ"]])


def test_a_pipeline_follows_the_seabed_sunk_by_its_burial(tmp_path):
    from iocean_reconstruct.lay import pipe_tops, seabed_of, tube

    site = a_place(tmp_path, slope=0.05)
    under = seabed_of(tmp_path, site)
    route = np.array([[-40.0, 0.0], [40.0, 0.0], [40.0, 30.0]])
    verts, faces, centre = tube(route, 0.5, 0.3, under)
    ground = under(centre[:, 0], centre[:, 1])
    assert np.allclose(centre[:, 2], ground - 0.3 * 0.5 + 0.25)
    assert np.allclose(centre[0, :2], route[0]) and np.allclose(centre[-1, :2], route[-1])
    assert faces.max() < len(verts) and np.all(np.isfinite(verts))
    # Every ring is the tube's radius round its centre.
    rings = verts[:-2].reshape(len(centre), -1, 3)
    assert np.allclose(np.linalg.norm(rings - centre[:, None, :], axis=2), 0.25)
    # Its top: one strip a leg, the crown 0.35 m over the seabed there (0.15 m of 0.5 buried).
    tops = pipe_tops(route, centre, 0.5, under)
    assert len(tops) == 2
    first = tops[0]
    g = first["grid"]
    assert np.isfinite(g).any() and np.isnan(g).any()
    rows, cols = g.shape
    middle = rows // 2
    col = cols // 2
    x = first["origin"][0] + col * first["cellM"]
    crown = float(np.nanmax(g[:, col]))
    assert math.isclose(crown, -10.0 - 0.05 * x + 0.35, abs_tol=0.02)
    assert np.isfinite(g[middle, col])
    assert math.isclose(tops[1]["headingDeg"], 90.0)


def test_a_model_top_is_its_highest_surface():
    from iocean_reconstruct.lay import cells_of, model_top

    corners = np.array([(x, y, z) for x in (0, 2) for y in (0, 1) for z in (0, 3)], float)
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                      [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    top = model_top(corners, faces, cell=0.1)
    assert math.isclose(float(np.nanmax(top["grid"])), 3.0)
    xy = cells_of(top)
    assert xy[:, 0].min() > -0.25 and xy[:, 0].max() < 2.25 and xy[:, 1].max() < 1.25
    # Solid under its whole roof.
    inside = (xy[:, 0] > 0.1) & (xy[:, 0] < 1.9) & (xy[:, 1] > 0.1) & (xy[:, 1] < 0.9)
    assert inside.sum() >= 15 * 7


def test_structures_are_laid_drawn_and_stood_on(tmp_path):
    pytest.importorskip("pxr")
    from iocean_reconstruct.asset import write_usd_mesh
    from iocean_reconstruct.lay import lay_structure, seabed_of

    place = tmp_path / "place"
    place.mkdir()
    a_place(place)
    pipe = tmp_path / "asset" / "pipe"
    pipe.mkdir(parents=True)
    (pipe / "asset.json").write_text(json.dumps({
        "kind": "structure", "type": "pipeline", "meets": "drapes", "madeFrom": "route", "stats": {"lengthM": 60.0},
        "route": {"points": [[22.284, 38.9617], [22.284, 38.9623]], "diameterM": 0.6, "burial": 0.5}}))
    box = tmp_path / "asset" / "box"
    box.mkdir(parents=True)
    corners = np.array([(x, y, z) for x in (-1, 1) for y in (-2, 2) for z in (0, 3)], float)
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                      [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    write_usd_mesh(box / "model.usdc", corners, faces)
    (box / "asset.json").write_text(json.dumps({"kind": "structure", "type": "platform", "meets": "stands",
                                                "madeFrom": "model", "model": "model.usdc"}))

    piped = lay_structure({"name": "export-line", "path": "asset/pipe", "kind": "structure"}, pipe, place, 1, 2)
    stood = lay_structure({"name": "frame", "path": "asset/box", "kind": "structure", "meets": "stands",
                           "placement": {"lat": 22.2843, "lon": 38.962, "headingDeg": 0}}, box, place, 2, 2)
    site = json.loads((place / "site.json").read_text())
    drawn = {r["name"]: r for r in site["layers"]["reconstructions"]}
    assert drawn["export-line"]["file"] == "structures/export-line/structure.usdc"
    assert drawn["frame"]["file"] == "structures/frame/structure.usda" and drawn["frame"]["kind"] == "structure"
    assert (place / "structures" / "frame" / "model.usdc").is_file()
    assert [s["name"] for s in site["structures"]] == ["export-line", "frame"]
    assert all((place / s["file"]).is_file() for s in site["surfaces"])

    # What the runtime's seabed now reads: the pipe's crown 0.3 m over the
    # bottom at its middle, the frame's roof 3 m over it, the bottom beside both.
    under = seabed_of(place, site)
    y_pipe = piped["start"][1]
    bottom = -10.0
    assert math.isclose(float(under(np.array([0.0]), np.array([y_pipe]))[0]), bottom + 0.3, abs_tol=0.03)
    assert math.isclose(float(under(np.array([0.0]), np.array([y_pipe + 2.0]))[0]), bottom, abs_tol=1e-6)
    fx, fy = stood["placed"]["at"]
    assert 33 < fy < 33.5 and abs(fx) < 1e-6
    assert math.isclose(float(under(np.array([fx]), np.array([fy]))[0]), bottom + 3.0, abs_tol=1e-3)
    assert math.isclose(float(under(np.array([fx + 3.0]), np.array([fy]))[0]), bottom - 0.03, abs_tol=1e-3)

    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(place / "structures" / "frame" / "structure.usda"))
    mesh = stage.GetPrimAtPath("/Structure/Mesh")
    world = np.array(UsdGeom.Xformable(mesh).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
    assert np.allclose(world[:3, 3], [fx, fy, bottom], atol=1e-6)


def test_a_pipe_faces_out_of_itself():
    import numpy as np
    from iocean_reconstruct.lay import tube
    verts, faces, centre = tube([[0, 0], [10, 0]], 1.0, 0.0, lambda x, y: np.zeros_like(x))
    side = faces[: len(faces) - 2 * 16]
    a, b, c = verts[side[:, 0]], verts[side[:, 1]], verts[side[:, 2]]
    normal = np.cross(b - a, c - a)
    middle = (a + b + c) / 3
    out = middle - np.c_[middle[:, 0], np.zeros(len(middle)), np.full(len(middle), 0.5)]
    assert (np.einsum("ij,ij->i", normal, out) > 0).mean() > 0.99


def test_a_standing_structure_carries_its_surface(tmp_path):
    from pxr import Usd, UsdShade
    from iocean_reconstruct.lay import STANDING, surface_of
    from iocean_reconstruct.asset import write_usd_mesh
    import numpy as np
    write_usd_mesh(tmp_path / "model.usdc", np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float), np.array([[0, 1, 2]]))
    look = surface_of("platform")
    (tmp_path / "structure.usda").write_text(STANDING.format(name="p", kind="platform", x=0.0, y=0.0, z=0.0, heading=0.0,
                                                             r=look["colour"][0], g=look["colour"][1], b=look["colour"][2],
                                                             roughness=look["roughness"], metallic=look["metallic"]))
    stage = Usd.Stage.Open(str(tmp_path / "structure.usda"))
    bound, _ = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath("/Structure/Mesh")).ComputeBoundMaterial()
    assert bound and bound.GetPath().pathString == "/Structure/Looks/Surface"


def test_a_cover_map_is_its_classes_and_their_shares(tmp_path, monkeypatch):
    rasterio = pytest.importorskip("rasterio")
    pytest.importorskip("matplotlib")
    from rasterio.transform import from_origin

    source = tmp_path / "inputs" / "source"
    source.mkdir(parents=True)
    classes = np.ones((20, 20), dtype="uint8")
    classes[:5] = 6
    with rasterio.open(source / "habitat.tif", "w", driver="GTiff", width=20, height=20, count=1, dtype="uint8",
                       crs="EPSG:4326", transform=from_origin(38.96, 22.29, 0.0001, 0.0001)) as d:
        d.write(classes, 1)
    made, names = run_asset(tmp_path, monkeypatch, {
        "kind": "cover", "origin": "public", "citation": "Allen Coral Atlas", "licence": "CC BY 4.0",
        "classes": {"1": "sediment", "6": "coral/algae"},
        "file": {"path": "source/habitat.tif", "name": "habitat.tif", "format": "geotiff"}})
    assert made["kind"] == "cover" and made["madeFrom"] == "public" and made["licence"] == "CC BY 4.0"
    assert "habitat.tif" in names
    assert made["stats"]["share"] == {"sediment": 0.75, "coral/algae": 0.25}


def test_a_species_list_counts_what_was_seen(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    source = tmp_path / "inputs" / "source"
    source.mkdir(parents=True)
    (source / "seen.json").write_text(json.dumps({"centre": [22.28, 38.96], "radiusKm": 12, "species": [
        {"taxon": "Pomacentrus sulfureus", "common": "Sulfur Damsel", "group": "Actinopterygii", "observations": 10},
        {"taxon": "Tridacna maxima", "common": "Small Giant Clam", "group": "Mollusca", "observations": 7}]}))
    made, names = run_asset(tmp_path, monkeypatch, {
        "kind": "species", "origin": "public", "citation": "iNaturalist, research grade",
        "file": {"path": "source/seen.json", "name": "seen.json", "format": "json"}})
    assert made["kind"] == "species" and "species.json" in names
    assert made["stats"]["taxa"] == 2 and made["stats"]["fish"] == 1 and made["stats"]["counted"] == 17
    assert made["footprint"]["radiusKm"] == 12
