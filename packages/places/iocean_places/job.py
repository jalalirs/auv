"""A place built as a platform job.

    python -m iocean_places.job '<brief>'

The brief is what somebody asked for (control plane: internal/building):

    {"centre": [lat, lon], "acrossM": 1000, "cells": 512,
     "sources": ["gebco", "sentinel2", "icesat2", "allen-coral-atlas", "learned-depth"],
     "files": [{"use": "raster", "path": "files/01-survey.tif", "errorM": 0.1, "name": "survey.tif"}],
     "name": "Our Reef", "slug": "our-reef"}

It is turned into a recipe here, because what goes with what (a satellite
depth is calibrated against the laser's, the coral atlas says which pixels are
reef) is the places module's knowledge, not the platform's. The build runs in
the job's sandbox: the files it was given under /work/inputs, everything it
writes under /work/outputs, and the package is /work/outputs/place.tar. Each
stage is one line of JSON on stdout, {"progress": {...}}, which the worker
passes on while the job runs.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tarfile
import time
import traceback

INPUTS = pathlib.Path(os.environ.get("IOCEAN_JOB_INPUTS", "/work/inputs"))
OUTPUTS = pathlib.Path(os.environ.get("IOCEAN_JOB_OUTPUTS", "/work/outputs"))
MODELS = pathlib.Path(os.environ.get("IOCEAN_DEPTH_MODELS", "/opt/iocean/depth-models"))
# The tools that grow a reef and lay its ground on a seabed (tools/make-site,
# tools/aim-water), and the stock surfaces they would otherwise fetch.
TOOLS = pathlib.Path(os.environ.get("IOCEAN_TOOLS", "/opt/iocean/tools"))
SURFACES = pathlib.Path(os.environ.get("IOCEAN_GROUND_SURFACES", "/opt/iocean/ground-surfaces"))

# The Red Sea, where the model trained on its own laser depths is the better
# one; elsewhere the one trained on reef lidar.
RED_SEA = (12.0, 30.5, 32.0, 44.0)


# Which of the platform's reefs a square is, by where it is: the coral mix it
# is grown from and the water it is seen through. Chosen by region, and said
# to be: none of these is a survey of the reef being built.
CARIBBEAN = (5.0, 33.0, -100.0, -30.0)          # and the rest of the tropical Atlantic
HAWAII = (18.0, 29.0, -179.0, -154.0)
RED_SEA_WATER = ("Kd(PAR) 0.049-0.119 per metre at the pelagic station offshore of KAUST: Overmans & Agusti "
                 "2020, Front. Mar. Sci. 7:111. Taken for this square because it is in the Red Sea, not measured here")


def inside(lat: float, lon: float, box: tuple) -> bool:
    south, north, west, east = box
    return south <= lat <= north and west <= lon <= east


def life_of(lat: float, lon: float, atlas: bool) -> dict:
    """The arguments make-site grows a reef and lays its ground with, each
    with where it came from."""
    if inside(lat, lon, RED_SEA):
        mix = ("red-sea", "the platform's Red Sea mix, from Khalil, Bouwmeester and Berumen 2017 (PeerJ 5:e3410) "
                          "line-intercept transects off Thuwal; chosen because this square is in the Red Sea")
    elif inside(lat, lon, HAWAII):
        mix = ("hawaii", "the platform's Hawaiian mix (Porites, Montipora, Pocillopora); chosen because this "
                         "square is in Hawaii")
    elif inside(lat, lon, CARIBBEAN):
        mix = ("caribbean", "the platform's Caribbean mix (Orbicella, brain, Acropora, gorgonians); chosen because "
                            "this square is in the tropical Atlantic")
    else:
        mix = ("red-sea", "the platform's Red Sea mix, as the nearest Indo-Pacific reef it has a library for; "
                          "not this reef's own species, which nobody has given the platform")
    water = (("IB", RED_SEA_WATER) if inside(lat, lon, RED_SEA) else
             ("1C", "assumed: Jerlov 1C, clear coastal water, the platform's default; nothing measured here"))
    cover = ("Allen Coral Atlas benthic map of this square, 10 m, CC BY 4.0, read through the platform's one "
             "table of density per class and zone (zonation.ATLAS_DENSITY); not a transect of this reef"
             if atlas else
             "inferred from the shape of the seabed (zonation), with no map or survey of coral here")
    return {"assemblage": mix[0], "assemblageFrom": mix[1], "water": water[0], "waterFrom": water[1],
            "coverFrom": cover}


def tell(step: str, say: str, **detail) -> None:
    print(json.dumps({"progress": {"step": step, "say": say, **detail}}), flush=True)


def depth_model(lat: float, lon: float) -> pathlib.Path:
    south, north, west, east = RED_SEA
    red_sea = south <= lat <= north and west <= lon <= east
    return MODELS / ("unet-v2-final" if red_sea else "unet-v1")


def recipe_of(brief: dict, inputs: pathlib.Path = INPUTS, nasa: bool | None = None) -> tuple[dict, list[str], list[str]]:
    """The recipe a brief asks for, what was left out and why, and the depth
    layers it is expected to fuse."""
    asked = list(dict.fromkeys(brief.get("sources") or []))
    lat, lon = (float(v) for v in brief["centre"])
    nasa = bool(os.environ.get("NASA_TOKEN")) if nasa is None else nasa
    left_out = []
    if "icesat2" in asked and not nasa:
        asked.remove("icesat2")
        left_out.append("icesat2: this platform has no NASA Earthdata token, so the laser's depths were not "
                        "fetched; satellite depths are then not calibrated against anything measured")
    sources, models, scene = [], [], []

    files = brief.get("files") or []
    for n, f in enumerate(files, 1):
        path = str(inputs / f["path"])
        name = f.get("name") or pathlib.Path(f["path"]).name
        citation = f.get("citation") or f"the organisation's own {f['use']}: {name}"
        if f["use"] == "raster":
            entry = {"use": "raster", "as": f"own{n}", "file": path, "error": float(f.get("errorM") or 0.3),
                     "citation": citation}
            if f.get("datum"):
                entry["datum"] = f["datum"]
            sources.append(entry)
            scene.append(f"own{n}.depth")
        elif f["use"] == "points":
            sources.append({"use": "points", "as": f"own{n}", "path": path, "degrees": True,
                            "error": float(f.get("errorM") or 0.2), "citation": citation})
            scene.append(f"own{n}.depth")
        elif f["use"] == "ortho":
            sources.append({"use": "ortho", "as": f"photo{n}", "file": path, "citation": citation})

    stumpf = "sentinel2" in asked or "learned-depth" in asked
    if stumpf:
        sources.append({"use": "sentinel2-stumpf", "as": "stumpf", "place": brief.get("slug") or "place"})
    if "sentinel2" in asked:
        sources.append({"use": "sentinel2-median", "as": "sentinel"})
    if "allen-coral-atlas" in asked:
        sources.append({"use": "allen-coral-atlas", "as": "atlas"})
    if "icesat2" in asked:
        sources.append({"use": "icesat2", "as": "icesat"})
    if "learned-depth" in asked:
        model = depth_model(lat, lon)
        if (model / "model.onnx").is_file():
            sources.append({"use": "learned-depth", "as": "learned", "model": str(model)})
        else:
            left_out.append(f"learned-depth: no model at {model}")
            asked.remove("learned-depth")
    # Under everything, always: GEBCO covers the whole Earth, so every cell has
    # a depth even where nothing better reaches.
    sources.append({"use": "gebco"})

    laser = "icesat2" in asked
    if "learned-depth" in asked:
        if laser:
            models.append({"use": "curve-depth", "as": "corrected", "depth": "learned.depth",
                           "truth": "icesat.depth.points", "land": "stumpf.land", "landHeight": "stumpf.depth"})
            scene.append("corrected.depth")
        else:
            scene.append("learned.depth")
    if "sentinel2" in asked:
        if laser:
            curve = {"use": "curve-depth", "as": "curve", "depth": "stumpf.depth", "truth": "icesat.depth.points",
                     "land": "stumpf.land"}
            if "allen-coral-atlas" in asked:
                curve["reef"] = "atlas.geomorphic"
                models.append({"use": "colour-depth", "as": "colour", "depth": "stumpf.depth",
                               "red": "sentinel.red", "green": "sentinel.green", "blue": "sentinel.blue",
                               "classes": "atlas.geomorphic", "truth": "icesat.depth.points",
                               "land": "stumpf.land"})
                scene.append("colour.depth")
            models.insert(0, curve)
            scene.append("curve.depth")
        else:
            scene.append("stumpf.depth")
    scene.append("gebco.depth")

    # The scene names no depth layers: every one no model used is fused, and
    # fusion keeps the least wrong in each cell. Naming them would mean knowing
    # in advance which a source will give (GEBCO's multibeam is only where a
    # ship has been). `scene` above is what that is expected to be, for the plan.
    recipe = {"name": brief.get("slug") or "place",
              "site": {"centre": [lat, lon], "acrossM": float(brief["acrossM"]),
                       "cells": int(brief.get("cells") or 512)},
              "sources": sources, "models": models,
              "scene": {"featherCells": 10 if files else 0}}
    return recipe, left_out, scene


def run_tool(step: str, argv: list[str]) -> None:
    """One of the place tools, each line it prints passed on as progress."""
    import subprocess

    tell(step, pathlib.Path(argv[0]).name + " started")
    done = subprocess.Popen([sys.executable, *argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            cwd=str(OUTPUTS))
    said = []
    for line in done.stdout:
        line = line.rstrip()
        said.append(line)
        if line.strip():
            tell(step, line.strip())
    if done.wait() != 0:
        raise RuntimeError(f"{pathlib.Path(argv[0]).name} failed: " + " | ".join(said[-6:]))


def grow(seabed: pathlib.Path, place: pathlib.Path, cache: pathlib.Path, brief: dict, recipe: dict) -> dict:
    """The place on the seabed just built: ground, reef and water."""
    import shutil

    lat, lon = recipe["site"]["centre"]
    atlas = (cache / "coral-atlas-benthic.geojson").is_file()
    life = life_of(lat, lon, atlas)
    tell("life", f"growing the reef ({life['assemblage']} mix) and laying the ground",
         assemblage=life["assemblage"], water=life["water"], atlas=atlas)
    # The stock surfaces, from the image rather than fetched: make-site takes
    # a file that is already there as fetched.
    if SURFACES.is_dir():
        (place / "textures").mkdir(parents=True, exist_ok=True)
        for one in SURFACES.glob("*.jpg"):
            shutil.copy(one, place / "textures" / one.name)
    run_tool("reef", [str(TOOLS / "make-site"), place.name, "--heights", str(seabed / "heights.json"),
                      "--most", str(recipe["site"]["cells"]), "--ground", str(cache),
                      "--cover-from", life["coverFrom"],
                      "--assemblage", life["assemblage"], "--assemblage-from", life["assemblageFrom"],
                      "--water", life["water"], "--water-from", life["waterFrom"],
                      "--into", str(place.parent)])
    run_tool("water", [str(TOOLS / "aim-water"), str(place)])
    # The seabed's own recipe goes with the place; what grew on it is in site.json.
    shutil.copy(seabed / "recipe.json", place / "recipe.json")
    site = json.loads((place / "site.json").read_text())
    site.setdefault("builtBy", {})["places"] = json.loads((seabed / "site.json").read_text())["builtBy"]["places"]
    reef = site.get("reef") or {}
    tell("life", f"{reef.get('colonies', 0):,} colonies", colonies=reef.get("colonies", 0),
         coverWhereItGrows=reef.get("coverWhereItGrows"), beginAt=site.get("beginAt"))
    return site


def main(argv: list[str]) -> int:
    started = time.time()
    brief = json.loads(argv[0])
    # The sandbox's root is read-only; whatever a library caches goes here.
    home = OUTPUTS / "home"
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ.setdefault("MPLCONFIGDIR", str(home / "matplotlib"))

    recipe, left_out, expected = recipe_of(brief)
    tell("plan", f"{len(recipe['sources'])} sources, {len(recipe['models'])} models",
         sources=[s["use"] for s in recipe["sources"]], models=[m["use"] for m in recipe["models"]],
         depthFrom=expected)
    for why in left_out:
        tell("left-out", why)

    from .build import build
    from .recipe import Recipe

    place, cache = OUTPUTS / "place", OUTPUTS / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "recipe.json").write_text(json.dumps(recipe, indent=1))
    # The seabed alone, unless asked otherwise, is built beside the place and
    # the place grown on it: its ground and its reef, as every hand-built
    # place has (tools/make-site), and its water baked from where a dive
    # begins (tools/aim-water).
    alive = brief.get("life", True) and (TOOLS / "make-site").is_file()
    seabed = OUTPUTS / "seabed" if alive else place
    try:
        site = build(Recipe.read(OUTPUTS / "recipe.json"), seabed, cache, tell=tell)
        if alive:
            site = grow(seabed, place, cache, brief, recipe)
    except Exception as failed:
        traceback.print_exc()
        tell("failed", str(failed))
        return 1

    # What a dive opens, said rather than guessed.
    site.setdefault("layers", {})["terrain"] = "seabed.usda"
    if brief.get("name"):
        site["title"] = brief["name"]
    if left_out:
        site.setdefault("builtBy", {}).setdefault("places", {})["leftOut"] = left_out
    (place / "site.json").write_text(json.dumps(site, indent=2) + "\n")

    tell("package", "packing the place")
    with tarfile.open(OUTPUTS / "place.tar", "w") as archive:
        for path in sorted(place.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=str(path.relative_to(place)))
    weak = site["from"]["depth"].get("weak", {})
    tell("done", "built", seconds=round(time.time() - started),
         deepestM=site.get("deepestM"), shallowestM=site.get("shallowestM"),
         errorM=weak.get("errorM"), byKind=weak.get("byKind"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
