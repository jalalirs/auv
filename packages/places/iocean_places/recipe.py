"""How a place is made, written down so it can be made again.

    {
      "name": "shushah",
      "site": {"centre": [27.9366, 34.9108], "acrossM": 2000, "cells": 512},
      "sources": [
        {"use": "geotiff", "path": "survey.tif", "error": 0.3},
        {"use": "place", "path": "~/iocean/places/shushah"}
      ],
      "scene": {"tileM": 10}
    }

The recipe is kept with the place it made (recipe.json), so rebuilding is
running it again, and the place's record says which recipe it came from.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from .grid import Grid


@dataclass
class Recipe:
    name: str
    grid: Grid
    sources: list[dict]
    models: list[dict] = field(default_factory=list)
    scene: dict = field(default_factory=dict)

    @classmethod
    def read(cls, path: str | pathlib.Path) -> "Recipe":
        return cls.of(json.loads(pathlib.Path(path).expanduser().read_text()))

    @classmethod
    def of(cls, said: dict) -> "Recipe":
        site = said["site"]
        latitude, longitude = (float(v) for v in site["centre"])
        grid = Grid(latitude, longitude, float(site["acrossM"]), int(site.get("cells", 512)))
        if not said.get("sources"):
            raise ValueError("a recipe names at least one source")
        return cls(str(said["name"]), grid, list(said["sources"]), list(said.get("models", [])),
                   dict(said.get("scene", {})))

    def said(self) -> dict:
        return {"name": self.name,
                "site": {"centre": [self.grid.latitude, self.grid.longitude], "acrossM": self.grid.across,
                         "cells": self.grid.cells},
                "sources": self.sources, "models": self.models, "scene": self.scene}
