"""Sources, layers, fusion, place, scene: a place built from a recipe.

What step 1 of r8 builds is the seabed: every depth layer the recipe's sources
give, fused cell by cell, written as the heightfield and mesh a dive opens,
with the error and the source of every cell beside it. The reef, the ground's
colour, the life and the water are still made by the tools (make-site and the
rest) and move in from step 2 on.
"""

from __future__ import annotations

import json
import pathlib
import time

import numpy as np

from .fusion import fuse
from .layer import Layer
from .recipe import Recipe
from .scene import where_a_dive_begins, write_place
from .sources import source_from


def layers_of(recipe: Recipe, cache: pathlib.Path | None = None) -> dict[str, list[Layer]]:
    """Every layer every source gives, by quantity."""
    out: dict[str, list[Layer]] = {}
    for entry in recipe.sources:
        source = source_from(entry)
        for layer in source.layers(recipe.grid, cache):
            out.setdefault(layer.quantity, []).append(layer)
    return out


def build(recipe: Recipe, into: pathlib.Path, cache: pathlib.Path | None = None) -> dict:
    """Build the place into `into`; returns its record (also written as site.json)."""
    into = pathlib.Path(into).expanduser()
    into.mkdir(parents=True, exist_ok=True)
    found = layers_of(recipe, cache)
    if "depth" not in found:
        raise ValueError("no source gave a depth; a place needs a seabed")
    depth = fuse(found["depth"], feather=int(recipe.scene.get("featherCells", 3)))
    if not depth.covers().all():
        missing = 1.0 - depth.share()
        raise ValueError(f"{missing:.1%} of the square has no depth from any source; add one that covers it "
                         "(a 'flat' source says what is assumed where nothing is known)")
    mesh = write_place(into, recipe.name, depth, recipe.grid, tile=float(recipe.scene.get("tileM", 10.0)),
                       texture=recipe.scene.get("texture"))
    height = depth.value
    site = {
        "name": recipe.name,
        "from": {"centre": {"latitude": recipe.grid.latitude, "longitude": recipe.grid.longitude},
                 "acrossMetres": recipe.grid.across, "sampleMetres": round(recipe.grid.cell, 3),
                 "surveyed": any(p.kind == "measured" for p in depth.provenance
                                 if (depth.source == depth.provenance.index(p)).any()),
                 "depth": depth.said()},
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
