# Tools

The human entry points. Each does one thing and says what it did.

| Tool | What it does |
| --- | --- |
| `gpu` | Runs a command on the GPU host, or forwards its ports here (`gpu web`) |
| `git-sync` | Commits and synchronises a change across this machine, GitHub, and the GPU host |
| `deploy-gpu` | Builds for the GPU host's architecture, streams the images, migrates, starts, and checks |
| `build-workflows` | Builds the workflow images and reports their content identities |
| `daily-loop` | Stands up the recurring ingestion against a running deployment |
| `e2e` | Checks a running deployment end to end |
| `reference` | Fetches what is measured about a place: habitat map, monitoring tables, licensed photographs, survey imagery, satellite colour |
| `ground` | Builds the ground from that record: a 1 m heightfield with the survey merged in, habitat classes, and colour maps |
| `terrain-flyover` | Flies a camera over that ground in Blender on the box and brings the video back: the ground alone, `--corals` with the surveyed colonies on it, `--corals --water` as a dive sees it. Same flight every time, so the three compare frame for frame |
| `flyover.py` | The Blender script `terrain-flyover` runs; `flyover_corals.py` and `flyover_water.py` are its two layers; `uav terrain` reaches it |
| `benthos` | Lists every colony standing on a surveyed seabed, from the survey's elevation model and orthomosaic |
| `reef-survey` | Writes that list into a place as its coral layer, and says where a dive on it begins |

Most are reached through `just`; run `just` with no arguments to see what it
offers.

## Why images are streamed rather than pushed

The GPU host cannot reliably reach a package registry. `deploy-gpu` builds for
its architecture here and streams the result over the SSH connection that
already exists, and workflow images are named by their content identity —
`sha256:…` — rather than by a registry digest, so that work can name exactly one
image without a registry existing at all.

## Why `gpu web` forwards two ports

The application is reached on the first. Stored bytes are read and written
directly on the second, because a presigned URL is signed over its host and so
cannot be proxied through the first.

## Why the ground is built from a record

A reef modelled from a general idea of a reef is wrong in every particular and
nobody can tell, because there is nothing to hold it against. `reference`
fetches the record for a place — the habitat polygons, the monitoring
station tables, the photographs divers have taken there, a survey's
orthomosaic and elevation model, the satellite's view — and writes the licence
of each beside it. `ground` turns that into what a renderer draws, and every
colour and contour in the result can be traced to one of those sources. What
is on the seabed is decided the same way, from the same directory.

`reference` and `ground` want numpy, scipy, pillow and rasterio. On a machine
whose system Python refuses packages, make a virtual environment and run them
with its interpreter:

```bash
python3 -m venv ~/coral-city/venv && ~/coral-city/venv/bin/pip install numpy scipy pillow rasterio
~/coral-city/venv/bin/python tools/reference looe-key 24.54586 -81.4072 --cremp-site "Looe Key" --usgs-doi 10.5066/P1QRS3SK
~/coral-city/venv/bin/python tools/ground ~/coral-city/places/looe-key ~/coral-city/reference/looe-key
tools/terrain-flyover looe-key
```
