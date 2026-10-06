"""Sources, layers, models, fusion, place, scene: a place built from a recipe.

Every product is named `<as>.<quantity>` (a source's `as` defaults to its
`use`), and soundings `<as>.<quantity>.points`. Models take products by name
and add their own. The seabed is the fusion of the depth layers the scene names
(`scene.depth`), or, when it names none, of every depth layer no model used.

What this builds is the seabed, with the error and the source of every cell
beside it, and a heights note (`heights.json`) that tools/make-site builds the
rest of the place from: the reef, the ground's colour, the life and the water
are still the tools', and move in later.
"""

from __future__ import annotations

import json
import pathlib
import time

import numpy as np

from .fusion import fuse
from .layer import Layer, Soundings
from .models import model_from
from .recipe import Recipe
from .scene import where_a_dive_begins, write_place
from .sources import source_from


def products_of(recipe: Recipe, cache: pathlib.Path | None = None) -> dict[str, Layer | Soundings]:
    """Every layer and every set of soundings every source gives, by name."""
    out: dict[str, Layer | Soundings] = {}
    for entry in recipe.sources:
        name = entry.get("as", entry["use"])
        source = source_from(entry)
        for layer in source.layers(recipe.grid, cache):
            out[f"{name}.{layer.quantity}"] = layer
        if hasattr(source, "soundings"):
            for one in source.soundings(recipe.grid, cache):
                out[f"{name}.{one.quantity}.points"] = one
    return out


def layers_of(recipe: Recipe, cache: pathlib.Path | None = None) -> dict[str, list[Layer]]:
    """Every layer every source gives, by quantity."""
    out: dict[str, list[Layer]] = {}
    for product in products_of(recipe, cache).values():
        if isinstance(product, Layer):
            out.setdefault(product.quantity, []).append(product)
    return out


def run_models(recipe: Recipe, products: dict) -> tuple[dict, set[str]]:
    """Each model in turn, its layers added to the products; returns what each
    said about how it was fitted, and which products the models used."""
    said, used = {}, set()

    def take(name: str):
        if name not in products:
            raise ValueError(f"nothing called {name!r}; there is {', '.join(sorted(products))}")
        return products[name]

    for entry in recipe.models:
        name = entry.get("as", entry["use"])
        model = model_from(entry)
        used |= {v for v in model.inputs.values() if v}
        layers, record = model.run(recipe.grid, take)
        for layer in layers:
            products[f"{name}.{layer.quantity}"] = layer
        said[name] = {"model": entry["use"], "inputs": {k: v for k, v in model.inputs.items() if v}, **record}
    return said, used


def build(recipe: Recipe, into: pathlib.Path, cache: pathlib.Path | None = None) -> dict:
    """Build the place into `into`; returns its record (also written as site.json)."""
    into = pathlib.Path(into).expanduser()
    into.mkdir(parents=True, exist_ok=True)
    products = products_of(recipe, cache)
    models, used = run_models(recipe, products)
    named = recipe.scene.get("depth")
    if named:
        missing = [n for n in named if n not in products]
        if missing:
            raise ValueError(f"the scene names {', '.join(missing)}, which nothing made")
        chosen = [products[n] for n in named]
    else:
        chosen = [p for n, p in products.items() if isinstance(p, Layer) and p.quantity == "depth" and n not in used]
    if not chosen:
        raise ValueError("no source gave a depth; a place needs a seabed")
    depth = fuse(chosen, feather=int(recipe.scene.get("featherCells", 3)))
    if not depth.covers().all():
        missing = 1.0 - depth.share()
        raise ValueError(f"{missing:.1%} of the square has no depth from any source; add one that covers it "
                         "(a 'flat' source says what is assumed where nothing is known)")
    mesh = write_place(into, recipe.name, depth, recipe.grid, tile=float(recipe.scene.get("tileM", 10.0)),
                       texture=recipe.scene.get("texture"))
    height = depth.value
    depth_said = depth.said()
    measured = sum(s["share"] for s in depth_said["sources"] if s["kind"] == "measured")
    # The model that made most of the seabed says how it was fitted, under the
    # key every place has always carried it in.
    by_share = {s["source"]: s["share"] for s in depth_said["sources"]}
    leading = max((n for n in models if models[n]["model"] in by_share),
                  key=lambda n: by_share[models[n]["model"]], default=None)
    centre = {"latitude": recipe.grid.latitude, "longitude": recipe.grid.longitude}
    note = {
        "rows": recipe.grid.cells, "columns": recipe.grid.cells, "acrossMetres": recipe.grid.across,
        "file": mesh["heightfield"]["file"], "format": mesh["heightfield"]["format"], "centre": centre,
        "surveyed": measured >= 0.5, "surveyedFraction": round(measured, 4),
        **({"fittedAgainst": {k: v for k, v in models[leading].items() if k not in ("model", "inputs")}}
           if leading else {}),
        "depth": depth_said, "models": models,
    }
    (into / "heights.json").write_text(json.dumps(note, indent=1) + "\n")
    site = {
        "name": recipe.name,
        "from": {"centre": centre, "acrossMetres": recipe.grid.across, "sampleMetres": round(recipe.grid.cell, 3),
                 "surveyed": note["surveyed"], "depth": depth_said, "models": models},
        "datum": "mean sea level; z = 0 is the surface and depth is negative z",
        "deepestM": round(float(-height.min()), 2),
        "shallowestM": round(float(-height.max()), 2),
        "mesh": {"lowest": float(height.min()), "highest": float(height.max()),
                 "heightfield": mesh["heightfield"], "errorFile": mesh["errorFile"],
                 "sourcesFile": mesh["sourcesFile"]},
        "beginAt": where_a_dive_begins(height, recipe.grid.across).get("beginAt"),
        "builtBy": {"places": {"recipe": "recipe.json", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}},
    }
    (into / "recipe.json").write_text(json.dumps(recipe.said(), indent=2) + "\n")
    (into / "site.json").write_text(json.dumps(site, indent=2) + "\n")
    return site
