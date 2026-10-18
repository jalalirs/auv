"""Where in a place a reconstruction fits: candidates, best first, for
somebody to choose from before it is laid in (lay.py).

    python -m iocean_reconstruct.resolve '<brief>'

The brief (services/control-plane/internal/mapping):

    {"start": {"lat", "lon"},      where the video was said to start; optional
     "withinM": 400,               how far from it the start may land
     "depthM": 8,                  how deep the reef was said to be; optional
     "depthSlackM": 3, "count": 5}

Inputs: /work/inputs/place/ (site.json and the heightfield it names) and
/work/inputs/reconstruction/ (reconstruction.json, surface.f32, surface.json).
Written: /work/outputs/candidates.json, {"candidates": [{headingDeg, at, dz,
centre, matrix, startAt, fit}], "start": [X, Y] or null, "searched": ...},
each a placement lay.py takes as it is.
"""

from __future__ import annotations

import json
import math
import sys
import time
import traceback

from .job import INPUTS, OUTPUTS, SPLAT, tell

sys.path.insert(0, str(SPLAT))


def local_of(site: dict, lat: float, lon: float) -> tuple[float, float]:
    """A latitude and longitude as the place's metres east and north of its centre."""
    centre = site.get("from", {}).get("centre") or site.get("centre") or {}
    lat0 = float(centre.get("latitude", centre.get("lat", 0.0)))
    lon0 = float(centre.get("longitude", centre.get("lon", 0.0)))
    north = 111132.92 - 559.82 * math.cos(2 * math.radians(lat0)) + 1.175 * math.cos(4 * math.radians(lat0))
    east = 111412.84 * math.cos(math.radians(lat0)) - 93.5 * math.cos(3 * math.radians(lat0))
    return (lon - lon0) * east, (lat - lat0) * north


def main(argv: list[str]) -> int:
    started = time.time()
    brief = json.loads(argv[0])
    from place_choose import candidates

    place, rec = INPUTS / "place", INPUTS / "reconstruction"
    try:
        site = json.loads((place / "site.json").read_text())
        manifest = json.loads((rec / "reconstruction.json").read_text())
        start_eye = manifest.get("startEye")
        near = None
        if brief.get("start"):
            near = local_of(site, float(brief["start"]["lat"]), float(brief["start"]["lon"]))
            half = float(site["from"]["acrossMetres"]) / 2
            if abs(near[0]) > half or abs(near[1]) > half:
                raise ValueError(f"the video's start is {math.hypot(*near):.0f} m from the place's centre, "
                                 "outside the place")
        tell("resolve", "fitting the reef's ground to the place's"
             + (f" within {brief.get('withinM', 400)} m of where the video starts" if near else ", anywhere in it"))
        found = candidates(place, rec, near=near, within=float(brief.get("withinM", 400.0)),
                           depth_slack=float(brief.get("depthSlackM", 3.0)), start=start_eye[:2] if start_eye else None,
                           depth=brief.get("depthM"), count=int(brief.get("count", 5)),
                           step=float(brief.get("stepM", 10.0)), own_depth_penalty=False)
        if not found:
            raise ValueError("nowhere in the place fits: every spot puts the reef outside it or out of the water")
    except Exception as failed:
        traceback.print_exc()
        tell("failed", str(failed)[:2000])
        return 1
    (OUTPUTS / "candidates.json").write_text(json.dumps({
        "candidates": found, "start": list(near) if near else None,
        "searched": {"withinM": brief.get("withinM", 400.0) if near else None, "depthM": brief.get("depthM"),
                     "stepM": brief.get("stepM", 10.0), "headingsDeg": 10}}, indent=1))
    best = found[0]
    tell("done", f"{len(found)} places it fits; the best {best['fit']['rmsM']:.2f} m rms at "
                 f"({best['at'][0]:.0f}, {best['at'][1]:.0f}), {best['fit']['placeGroundM']:.1f} m deep",
         seconds=round(time.time() - started), candidates=len(found))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
