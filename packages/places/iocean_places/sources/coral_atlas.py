"""The Allen Coral Atlas: which ground is reef flat, crest and slope, and
what covers it, mapped from Sentinel-2 at 10 m (CC BY 4.0).

Read from the GeoJSON tools/coral-atlas fetched. Two layers of classes:
`geomorphic` (reef flat, crest, slope...) and `benthic` (sand, rubble, rock,
seagrass, coral/algae). "Coral/Algae" is one class: Sentinel-2 cannot tell
living coral from the algae beside it, so it is an upper bound on coral cover
and never read as coral.
"""

from __future__ import annotations

import json

import numpy as np

from ..grid import Grid, metres_per_degree
from ..layer import Layer, Provenance
from . import fetched, where

# Drawn in this order where polygons overlap, so the more particular one wins:
# sand is the background of a reef and coral the exception.
BENTHIC_ORDER = ("Sand", "Microalgal Mats", "Seagrass", "Rubble", "Rock", "Coral/Algae")


def rasterised(grid: Grid, collection: dict, order: tuple[str, ...] | None = None) -> tuple[np.ndarray, tuple[str, ...]]:
    """Polygons in degrees onto the grid, by which cell centres fall inside:
    0 unmapped, k for the k-th class name (sorted). Later polygons overwrite
    earlier ones, in `order` of class where one is given."""
    from matplotlib.path import Path

    east, north = metres_per_degree(grid.latitude)
    names = tuple(sorted({f["properties"]["class_name"] for f in collection["features"]}))
    X, Y = grid.xy()
    cells = np.stack([X.ravel(), Y.ravel()], 1)
    out = np.zeros((grid.cells, grid.cells), dtype=int)
    features = collection["features"]
    if order:
        rank = {name: k for k, name in enumerate(order)}
        features = sorted(features, key=lambda f: rank.get(f["properties"]["class_name"], -1))
    for f in features:
        code = names.index(f["properties"]["class_name"]) + 1
        shape = f["geometry"]
        polygons = shape["coordinates"] if shape["type"] == "MultiPolygon" else [shape["coordinates"]]
        for polygon in polygons:
            ring = np.asarray(polygon[0], dtype=float)
            xy = np.stack([(ring[:, 0] - grid.longitude) * east, (ring[:, 1] - grid.latitude) * north], 1)
            out[Path(xy).contains_points(cells).reshape(grid.cells, grid.cells)] = code
    return out, names


class CoralAtlas:
    name = "allen-coral-atlas"
    gives = ("geomorphic", "benthic")

    def __init__(self, path: str | None = None, geomorphic: str = "coral-atlas-geomorphic.geojson",
                 benthic: str = "coral-atlas-benthic.geojson", fetch: bool = True) -> None:
        self.path, self.files, self.fetch = path, {"geomorphic": geomorphic, "benthic": benthic}, bool(fetch)

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        folder = where(self.path, cache)
        if not any((folder / f).is_file() for f in self.files.values()) and self.fetch:
            from ..fetch.coral_atlas import main
            folder.mkdir(parents=True, exist_ok=True)
            fetched(self.name, main, [folder.name, grid.latitude, grid.longitude, "--across", grid.across,
                                      "--into", folder.parent])
        out = []
        for quantity, file in self.files.items():
            if not (folder / file).is_file():
                continue
            codes, names = rasterised(grid, json.loads((folder / file).read_text()),
                                      BENTHIC_ORDER if quantity == "benthic" else None)
            value = np.where(codes > 0, codes, np.nan)
            out.append(Layer.of(grid, quantity, value, np.nan,
                                Provenance(self.name, "derived",
                                           f"Allen Coral Atlas {quantity} map, 10 m, classified from Sentinel-2",
                                           "CC BY 4.0"), classes=names))
        return out
