# places

Builds a place from whatever data a site has.

```
sources  →  layers  →  fusion  →  place  →  scene
```

- **Sources** (`iocean_places/sources/`) read or fetch one kind of data and hand back layers. Today: `geotiff`, `points` (XYZ soundings), `place` (an existing place's heightfield) and `flat` (an assumed depth, for filling). The existing tools move in here one at a time (r8 step 2).
- **A layer** (`layer.py`) is one quantity on the site's grid with, cell by cell, a value, an error in metres and the source it came from. Every source is cited with a kind: measured, derived, chosen or assumed.
- **Fusion** (`fusion.py`) believes the source with the smallest error in each cell, and tapers a source off over `featherCells` at the edge of what it covers, so seams are slopes, not steps.
- **The scene** (`scene.py`) writes what a dive opens: `seabed.f32`, `seabed.usda`, and alongside them `error.f32` and `sources.u8`, the error and the source of every cell.

A **recipe** says the site, the sources and the scene:

```json
{"name": "a-reef",
 "site": {"centre": [27.9, 34.9], "acrossM": 400, "cells": 513},
 "sources": [{"use": "flat", "depth": 12.0},
             {"use": "geotiff", "path": "survey.tif", "error": 0.2, "kind": "measured"}],
 "scene": {"featherCells": 3}}
```

```
tools/places build a-reef.json --into ~/iocean/places/a-reef
```

The recipe is kept with the place as `recipe.json`, so rebuilding is running it again. `site.json` says, under `from.depth`, what share of the place each source made and how wrong it may be there.

Tests: `python -m pytest packages/places/tests`.
