"""What built this place, recorded so it can be built again.

Five places, each made by a hand-typed command with a dozen arguments, and no
record anywhere of what those arguments were. Every rebuild was reconstructed
from memory or from a shell history, and a place rebuilt with one argument
different is a place whose record no longer describes it.

So each tool that writes `site.json` writes down how it was called. `tools/
rebuild` replays them in order.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys


def carry_the_record_forward(site: dict, was: pathlib.Path) -> dict:
    """Keep what the old site.json knew about how this place was built.

    `make-site` writes a whole new record from nothing, which is right for
    everything in it except this one field: the place was also surveyed and
    had its water aimed, by tools that run afterwards and write themselves
    down. Overwriting the record with only `make-site` in it leaves a place
    that `tools/rebuild` will rebuild as bare ground — no reef, no dive start,
    no medium — and it will say it rebuilt it from its own record while doing
    so, because as far as the record goes it did.

    That is exactly what happened to Looe Key: eighty-three thousand surveyed
    colonies, rebuilt to nought, by a tool reporting success.
    """
    if not was.is_file():
        return site
    try:
        before = json.loads(was.read_text()).get("builtBy") or {}
    except (OSError, ValueError):
        return site
    keep = site.setdefault("builtBy", {})
    for tool, call in before.items():
        keep.setdefault(tool, call)
    # And what those later tools wrote about the place, beside the files they
    # left in it. `tools/surroundings` writes a "surroundings" record and the
    # fauna step a "life" one; a rebuild left their files in the folder and
    # took their records out of site.json, so the place still had its GEBCO
    # seabed and its fish on disk and no longer said so. Shushah, 4 October.
    try:
        whole = json.loads(was.read_text())
    except (OSError, ValueError):
        return site
    for key in LATER:
        record = whole.get(key)
        if key in site or not isinstance(record, dict):
            continue
        named = [record.get(k) for k in ("file", "tidFile") if record.get(k)]
        if all((was.parent / name).exists() for name in named):
            site[key] = record
    return site


# The site.json records written by tools that run after make-site.
LATER = ("surroundings", "life")


def record_call(site: dict, tool: str) -> dict:
    """Put this invocation into the place's own record, under `builtBy`."""
    site.setdefault("builtBy", {})[tool] = {
        "argv": [str(one) for one in sys.argv[1:]],
        "cwd": str(pathlib.Path.cwd()),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
    }
    return site


# What make-site lifts off a heights note straight into the place's `from`.
# Kept here because three separate tools write such a note — tools/ground,
# tools/fit-depths, tools/get-bathymetry — and each one that omits a key
# *deletes* it from the place on the next rebuild.
#
# All three omitted keys, and each was found separately. Al Fahal's seabed is
# Copernicus Sentinel-2 S2B_T37QDE_20240223T080223_L2A, Stumpf log-ratio,
# uncalibrated, optical limit 22 m, a quarter of it continued past the sensor.
# A note that describes what it just did to the square and nothing about where
# the square came from replaces all of that with its own sentence.
CARRIED = ("source", "method", "observedAt", "opticalLimitM",
           "bottomVisibleFraction", "beyondOpticalDepthFraction",
           "medianDetailM", "toCalibrate", "constructedPastTheSensor",
           "fittedAgainst", "surveys", "surveyed", "surveyedFraction")


def where_the_ground_came_from(site_from: dict, *, minus: tuple = ()) -> dict:
    """The provenance a heights note has to carry forward from the place.

    `minus` names the keys this writer sets for itself — a fit records its own
    `fittedAgainst`, a merge its own `surveys` — so the caller's value wins
    and everything else is passed through untouched.
    """
    return {k: site_from[k] for k in CARRIED
            if k in site_from and k not in minus}
