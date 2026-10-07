# The depth model

Depth, and how sure it is, from Sentinel-2: for any reef, a seabed with an
error on every cell, where today a place gets one only where ICESat-2's tracks
cross it. It becomes a model in the places module (packages/places) once it
beats the colour fit the places use now.

## What it learns from

| | |
|---|---|
| Input | Sentinel-2 L2A over 1.3 km chips at 10 m: seven bands (coastal blue to shortwave infrared), each the cloud-masked median of 8 clear scenes |
| Labels | NOAA topobathy lidar over coral reefs (Florida Keys, Dry Tortugas, Puerto Rico, the US Virgin Islands, Hawaii, Guam and the Marianas, American Samoa), averaged into each cell; ICESat-2 photons over the Red Sea places |
| depth-v1 | 3,267 chips, 35.0 M measured cells, 1.5 to 21 m deep (5th to 95th percentile) |

## How it learns

A U-Net (models/unet.py): 128 by 128 cells in, depth and the log of its
variance out, trained on the Gaussian likelihood of the measured depth over
measured cells only. Spatial on purpose: a reef's depth is in its shape as much
as its colour. It is tested only on regions it never saw, and against the
per-pixel linear fit the places use (models/linear.py), fitted on the same
training chips.

## Results so far

unet-v1, 7 October 2026 (runs unet-v1-20261007-1744 and unet-v1-no-florida-20261007-1747
on the box). Depth error in metres against measured seabed on regions the model never
saw; the linear baseline is fitted on the same training chips.

| held out | U-Net rms | linear rms | U-Net bias |
|---|---|---|---|
| Florida (Keys blocks 1 to 4, Dry Tortugas) | 1.33 | 5.58 | -0.07 |
| US Virgin Islands | 1.58 | 2.42 | +0.69 |
| Guam and the Marianas | 3.56 | 5.46 | -0.38 |
| Red Sea, ICESat-2 tracks (4 chips) | 2.1 to 2.4 | 2.7 to 3.4 | |

Kauai (a validation survey) is the weakest, at about 5 m. American Samoa's three surveys
are excluded: their heights are above the ellipsoid, not sea level, which the first run
found as a 17 m "error". The stated uncertainty, calibrated on the validation surveys
(a factor of 1.15 to 1.24), puts 58% to 71% of held-out cells within one sigma, where
68% is honest.

## Running it

On the box, from the repository; everything runs in the container on GPU 1:

    just ml-depth dataset build --config dataset/depth-v1.yaml     # resumes; hours from nothing
    just ml-depth dataset summary
    just ml-depth train --config train/unet-v1.yaml                # trains, then evaluates
    just ml-depth evaluate --run <run>
    just ml-depth runs
    just ml-depth-test

## Layout

    configs/dataset/   how a dataset is made (the lidar surveys, chip size, bands, thresholds)
    configs/train/     how a model is trained (split, model, optimiser)
    iocean_depth/
      data/            lidar, Sentinel-2, chips, the dataset build, reading it back and splitting it
      models/          the U-Net and the linear baseline
      train.py         a run: config, commit, history, best checkpoint
      evaluate.py      held-out regions, the baseline, the Red Sea; report.json and report.md
      metrics.py       rms, bias, by depth, and whether the stated uncertainty is honest
      cli.py           iocean-depth
    tests/

Data lives under `IOCEAN_ML_DATA` (on the box `~/iocean/ml/depth`, in the
container `/data`): `datasets/<name>/` with its `manifest.json`, and
`runs/<run>/` with `config.yaml`, `run.json`, `history.jsonl`, `model.pt`,
`report.json` and `report.md`.
