# Models

What iOcean trains, each as its own project: its data built from a config, its
training and evaluation in a container, its runs recorded where they were made.

| Project | What it learns | Status |
|---|---|---|
| `depth/` | Seabed depth and its uncertainty from Sentinel-2, trained on NOAA reef lidar and tested on regions it never saw | depth-v1 built (3,267 chips); unet-v2-redsea-w10: 1.94 m on held-out Red Sea areas against 2.30 m for the per-pixel fit, 1.3 m on held-out Florida (unet-v1) |

Data is never in git (the repository is public and the data is gigabytes). Each
project keeps it under one root on the machine it runs on, and keeps in git the
configs that say how it was made.
