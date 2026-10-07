# Models

What iOcean trains, each as its own project: its data built from a config, its
training and evaluation in a container, its runs recorded where they were made.

| Project | What it learns | Status |
|---|---|---|
| `depth/` | Seabed depth and its uncertainty from Sentinel-2, trained on NOAA reef lidar and tested on regions it never saw | dataset depth-v1 built; unet-v1 training |

Data is never in git (the repository is public and the data is gigabytes). Each
project keeps it under one root on the machine it runs on, and keeps in git the
configs that say how it was made.
