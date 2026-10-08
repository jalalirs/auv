# Coral cover

What covers the seabed (living hard coral, soft coral, dead coral, algae,
sand, rubble...) from underwater imagery: a diver's or a vehicle's photos, or a
photogrammetric survey's orthomosaic.

We do not train this model; a good open one exists. It is **CoralscapesV2's
SegFormer-B5** (EPFL ECEO, Apache 2.0): 95 classes, trained on 1,790 densely
labelled video frames from 34 Red Sea dive sites, tested on 5 sites it never
saw (Sauder et al. 2026). This project pins it, checks it, and runs it over
photo mosaics to make cover maps the places module can read.

| Step | What | Where it goes |
|---|---|---|
| `fetch` | the model and the test split, at the revisions `configs/cover.yaml` pins | `models/`, `datasets/` |
| `check` | the model on the test split: pixels (accuracy, IoU) and cover (each group's share of the seabed, per frame) | `checks/<name>/` |
| `look` | a patch of a mosaic and what the model says of it, side by side | `looks/` |
| `map` | a cover map from a photo mosaic: per 0.5 m cell, each group's share of the seabed | `maps/<name>/` |
| `video` | cover along a video transect: a frame a second, each counted over its seabed, placed between the transect's marked ends | `transects/<name>/` |
| `finetune` | the model fine-tuned on photo-quadrats labelled at points, held out by country | `runs/<run>/` |
| `bands` | a map's shares by depth, from the survey's elevation model | `maps/<name>/bands.json` |

The 95 classes are gathered into groups in `configs/cover.yaml`; every class
is in exactly one, and fish, divers, transect tapes and open water are left out
of every share.

## Results so far

**On its own ground, it is good.** CoralscapesV2's test split, 464 frames from
five Red Sea dive sites it never saw (`check`, 2026-10-08):

| group | IoU | seabed share drawn | said | mean error per frame | correlation |
|---|---|---|---|---|---|
| hard coral | 80% | 20.8% | 21.9% | 2.3 points | 0.98 |
| algae | 61% | 16.1% | 13.6% | 5.0 points | 0.90 |
| sand | 80% | 14.5% | 15.2% | 2.2 points | 0.97 |
| dead coral | 39% | 6.1% | 4.5% | 3.0 points | 0.65 |

Pixel accuracy 80.6%, mean IoU over 95 classes 39.5% (its card: 37.2%).

**On a Caribbean photo mosaic, it is not yet to be trusted.** Looe Key's
SQUID-5 mosaic (2022, 124,000 m2 imaged, read at 1 cm, `map` then `bands`):

| depth (NAVD88) | hard coral | algae | sand | hard substrate |
|---|---|---|---|---|
| 1-3 m | 22.1% | 5.0% | 0.0% | 72.0% |
| 3-5 m | 5.2% | 2.0% | 1.4% | 83.2% |
| 5-7 m | 1.2% | 2.2% | 28.2% | 64.1% |
| 7-9 m | 0.8% | 0.5% | 46.7% | 50.2% |

Over the whole mosaic it says 3.7% hard coral, and FWC's CREMP stations at
Looe Key measured 3.4% (7 m) and 4.4% (12.5 m) stony coral in 2024. But the
agreement is an average of errors: on the reef crest it calls the brown mats
(zoanthids, fire coral, turf) encrusting coral; at 5 to 9 m, where CREMP
measures 3.4%, it finds under 2% of the hard bottom; and it finds 2% algae and
almost no soft coral where CREMP measures 17 to 22% macroalgae and 5 to 10%
octocorals. Gorgonians and Caribbean macroalgae are not in its training. Left
to itself it also calls the hazy deep parts of a top-down mosaic open water,
which `only_seabed` rules out.

**Red Sea video transects.** DeepReefMap's example GoPro videos (Sauder et al.,
Zenodo 10624794, CC BY 4.0), with the model as it is, a frame a second:

| transect | frames | hard coral | dead coral | algae | rubble | hard substrate |
|---|---|---|---|---|---|---|
| a single 6-minute video | 378 | 9.7% | 3.3% | 0% | 16.5% | 64.4% |
| one transect cut into two 12-minute files | 711 | 41.8% | 4.0% | 16.8% | 0.5% | 30.3% |

The frames are the model's own ground (CoralscapesV2 is frames of such videos),
so its check holds: about 2.3 points of hard coral per frame. Their dive sites
were not published with them, so they are not laid into a place; a client's
transect with its ends marked is (`cover-transect` in the places module).

**Caribbean fine-tune (caribbean-v1).** The XL Catlin Seaview Survey's
Atlantic photo-quadrats (1,407 photos of about a square metre, 13 countries,
about 66 expert points each), gathered into the cover groups. Trained on 836
from 10 countries, chosen on Curaçao, tested on the Bahamas and Belize (334
quadrats neither model saw), cover per quadrat over the whole photo:

| group | experts | base | base error | fine-tuned | fine-tuned error | correlation |
|---|---|---|---|---|---|---|
| hard coral | 6.6% | 5.7% | 2.9 points | 6.5% | 2.3 points | 0.92 |
| soft coral (gorgonians) | 8.3% | 5.6% | 4.1 points | 9.1% | 2.6 points | 0.94 |
| algae (turf and macroalgae) | 76.1% | 16.2% | 60.3 points | 78.6% | 5.7 points | 0.88 |
| sand | 5.5% | 4.5% | 2.9 points | 3.6% | 2.7 points | 0.88 |

Part of the algae gain is naming, not seeing: the survey calls turf-covered
rock algae, CoralscapesV2 calls it hard substrate. **Licence:** Seaview's
repository page says CC BY 3.0 and its own documentation CC BY-NC-SA 4.0, so
until that is settled caribbean-v1 is for research, not for sale.

**Looe Key with caribbean-v1.** Over the mosaic, read at 1 cm: hard coral
1.0%, soft coral 1.0%, algae 73.7%, sand 22.6%. The algae and turf now match
what CREMP measures (about 80% together), but the coral is under CREMP's 3.4
to 4.4% stony coral and 5 to 10% octocorals. Patches show why it cannot settle
the question: where the water is clear the model finds the coral heads and
the gorgonians; at 5 to 9 m the mosaic itself is a haze nobody could count
coral in. A mosaic is only as good as its water, and Looe Key's deep half is
not a test of any model.

## Running it

On the box, in the container on GPU 1, data under `~/iocean/ml/cover`:

    docker compose -f ml/cover/compose.yaml build cover
    docker compose -f ml/cover/compose.yaml run --rm cover fetch
    docker compose -f ml/cover/compose.yaml run --rm cover check

or `just ml-cover ...` from the repository.
