# places

Builds a place from whatever data a site has.

```
sources  →  layers  →  fusion  →  place  →  scene
```

- **Sources** (`iocean_places/sources/`) read one kind of data and hand back layers, and soundings where the data are points:
  - `sentinel2-stumpf`: get-reef's satellite-derived depth (uncalibrated) and the land it saw;
  - `sentinel2-median`: the median true colour of the clearest scenes (tools/reference);
  - `allen-coral-atlas`: the geomorphic and benthic maps, as layers of classes;
  - `icesat2`: ATL24 seafloor photons, as soundings and gridded near the tracks;
  - `gebco`: GEBCO 2026 with an error per cell from its type identifier, and the DCDB multibeam where there is any;
  - `geotiff`, `points` (XYZ), `place` (an existing place), `flat` (an assumed depth).

  Today they read what the fetching tools wrote (a place's reference folder, `--cache`); the fetching itself moves in next.
- **Models** (`iocean_places/models/`) turn named layers into another layer, with an error checked on held-out 200 m blocks and a record of the fit: `curve-depth` (one curve of the claim, from tools/fit-depths) and `colour-depth` (the colour and the reef map, from tools/fit-colour-depths). The tools now use them from here.
- **A layer** (`layer.py`) is one quantity on the site's grid with, cell by cell, a value, an error in metres and the source it came from. Every source is cited with a kind: measured, derived, chosen or assumed.
- **Fusion** (`fusion.py`) believes the source with the smallest error in each cell, and tapers a source off over `featherCells` at the edge of what it covers, so seams are slopes, not steps.
- **The scene** (`scene.py`) writes what a dive opens: `seabed.f32`, `seabed.usda`, and alongside them `error.f32` and `sources.u8`, the error and the source of every cell; and `heights.json`, which `tools/make-site --heights` builds the reef, ground and record from.

Every product is named `<as>.<quantity>` (soundings `<as>.<quantity>.points`), and models and the scene refer to them by name. `recipes/shushah.json` is a real one: it rebuilds Shushah's published seabed from its reference folder.

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
tools/places build packages/places/recipes/shushah.json --into /tmp/shushah --cache ~/iocean/reference/shushah
```

The recipe is kept with the place as `recipe.json`, so rebuilding is running it again. `site.json` says, under `from.depth`, what share of the place each source made and how wrong it may be there.

Tests: `python -m pytest packages/places/tests`.
