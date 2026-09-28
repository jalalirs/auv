"""What an agent can ask the platform to do.

Named after the nouns the platform already has, so that an agent reading the
tool list can guess the model from it: places, vehicles, controllers, layouts,
missions, dives, sweeps.

Kept separate from the server that serves them. The MCP protocol is one way to
reach these and an HTTP route will be another, and neither should be the place
the answers are shaped.
"""

from __future__ import annotations

from typing import Any

from .platform import Platform, Refused
from .provenance import ASSUMED, CHOSEN, DERIVED, MEASURED, said, unknown


def _newest(versions: list[dict]) -> dict | None:
    """The newest version, by when it was made rather than by where it sits.

    The client had a bug of this shape once — taking whichever build came back
    first and verifying a change against the build it replaced.
    """
    if not versions:
        return None
    return max(versions, key=lambda v: v.get("createdAt") or "")


def _site_of(platform: Platform, place: dict) -> dict | None:
    """A place's own record, out of its newest published package."""
    version = _newest(platform.versions_of_place(place["id"]))
    if version is None:
        return None
    for one in platform.files(version["id"]):
        if one["path"] == "site.json":
            import json
            import urllib.request
            with urllib.request.urlopen(one["url"], timeout=60) as answer:
                return json.loads(answer.read())
    return None


# ── looking ──────────────────────────────────────────────────────────────────

def places_list(platform: Platform) -> dict:
    """Every place this session has been granted."""
    out = []
    for place in platform.places():
        out.append({
            "id": place["id"],
            "slug": place.get("slug"),
            "name": place.get("name"),
            "summary": place.get("summary"),
        })
    return {"places": out,
            "note": "places_get returns what each one's ground came from"}


def places_get(platform: Platform, place_id: str) -> dict:
    """One place, with every number marked.

    The `calibratedToM` field is the one worth reading before planning anything
    deep. Al Fahal's seabed fits ICESat-2 to an rms of 2.00 m, and that figure
    is the top five metres: 22,430 of its 26,726 measured depths sit there, and
    below fifteen the fit is sixteen metres out. A tool that returned the rms
    and not the depth it holds to would be handing an agent the exact number
    that reads as solved.
    """
    place = next((p for p in platform.places() if p["id"] == place_id
                  or p.get("slug") == place_id), None)
    if place is None:
        raise Refused(404, "not_found", f"no place {place_id!r} is granted to you")
    site = _site_of(platform, place)
    if site is None:
        return {"id": place["id"], "name": place.get("name"),
                "published": False,
                "note": "no published package, so nothing about its ground is known"}

    came = site.get("from") or {}
    ground = site.get("ground") or {}
    reef = site.get("reef") or {}
    fitted = came.get("fittedAgainst") or {}
    surveyed = came.get("surveyed")
    surveys = [s.get("name") for s in (came.get("surveys") or []) if s.get("name")]

    depth: dict[str, Any] = {}
    if site.get("deepestM") is not None:
        depth["deepestM"] = said(
            site["deepestM"],
            MEASURED if surveyed else DERIVED,
            ", ".join(surveys) if surveys else (came.get("source") or "the place's own heightfield"))
    if fitted:
        depth["fittedAgainst"] = said(
            fitted.get("source", "a measured depth set"), DERIVED,
            came.get("source") or "satellite-derived bathymetry",
            note=f"rms {fitted.get('rmsBeforeM')} m before, {fitted.get('rmsAfterM')} m after")
        good_to = fitted.get("calibratedToM")
        depth["calibratedToM"] = (
            said(good_to, DERIVED, fitted.get("source", "the fit"),
                 note="below this the fit does not hold and the ground is not calibrated")
            if good_to is not None else unknown("the fit did not report a depth it holds to"))

    cover = reef.get("cover") or {}
    life = site.get("life") or {}
    return {
        "id": place["id"], "name": place.get("name"), "published": True,
        "ground": {
            # Whether the ground was surveyed, and who says so.
            #
            # This marked anything with no survey list as *assumed from the
            # package's own claim*, which is wrong about Al Fahal: it names a
            # Copernicus scene and says plainly that it is satellite-derived
            # and not a survey. That is a stated fact with a source, not a
            # default nobody revisited. Assumed is for when nobody said.
            "surveyed": said(
                bool(surveyed),
                MEASURED if surveys else (DERIVED if came.get("source") else ASSUMED),
                ", ".join(surveys) if surveys
                else (came.get("source") or "nobody said, and the package does not"),
                note=None if surveyed else "derived, not surveyed"),
            "method": came.get("method"),
            "colourFrom": ground.get("colourFrom"),
            **depth,
        },
        "reef": {
            "colonies": (said(reef["colonies"],
                              MEASURED if cover.get("measured") else CHOSEN,
                              reef.get("source") or cover.get("from") or "the build's own count")
                         if reef.get("colonies") else unknown("no reef here")),
            "assemblage": (reef.get("assemblage") or {}).get("name")
                          or ("surveyed" if cover.get("measured") else None),
        },
        "life": (said(life["observations"], MEASURED, life.get("source", "an observation record"),
                      note=f"{life.get('species')} species")
                 if life.get("observations") else unknown("no observation record for this place")),
        "water": ((lambda w: said(w["type"], MEASURED, w.get("from", "")) if w.get("from")
                   else said(w.get("type"), ASSUMED, "nobody said"))(site["water"])
                  if site.get("water") else unknown("no Jerlov type recorded")),
    }


def vehicles_list(platform: Platform) -> dict:
    """Every vehicle, and whether it can actually fly.

    `flyable` is the field to read. A package with dynamics and no hull cannot
    be put in the water however complete it looks, and on this platform today
    that is all of them.
    """
    out = []
    for vehicle in platform.vehicles():
        version = _newest(platform.versions_of_vehicle(vehicle["id"]))
        paths = [f["path"] for f in platform.files(version["id"])] if version else []
        hull = any(p.lower().endswith((".usd", ".usda", ".usdc", ".usdz")) for p in paths)
        out.append({
            "id": vehicle["id"], "slug": vehicle.get("slug"),
            "name": vehicle.get("name"),
            "manufacturer": vehicle.get("manufacturer"),
            "flyable": hull and "dynamics.json" in paths,
            "why_not": None if hull and "dynamics.json" in paths
                       else ("no hull in the published package" if not hull
                             else "no dynamics.json in the published package"),
            "files": paths,
        })
    return {"vehicles": out}


def controllers_list(platform: Platform) -> dict:
    """What is deployed, and what each has flown."""
    institution = platform.institution()
    if institution is None:
        raise Refused(403, "no_institution", "this session belongs to no institution")
    out = []
    for one in platform.autonomy(institution["id"]):
        out.append({"slug": one.get("slug"), "name": one.get("name"),
                    "digest": one.get("imageDigest"),
                    "wantsGpu": bool(one.get("wantsGpu"))})
    return {"controllers": out, "institution": institution.get("name")}


def dives_list(platform: Platform, limit: int = 20) -> dict:
    """The dives this institution has defined, newest first."""
    institution = platform.institution()
    if institution is None:
        raise Refused(403, "no_institution", "this session belongs to no institution")
    dives = platform.dives(institution["id"])
    dives = sorted(dives, key=lambda d: d.get("createdAt") or "", reverse=True)
    return {"dives": [{"id": d["id"], "name": d.get("name"),
                       "createdAt": d.get("createdAt")} for d in dives[:limit]],
            "total": len(dives)}


def dives_result(platform: Platform, dive_id: str, run_id: str | None = None) -> dict:
    """What a run scored, and what it left behind.

    A dive the platform could not start is not a score of zero, and comes back
    saying so. That distinction has cost this project a week before now: rows
    that never flew were averaged in as failures and made a controller look
    worse than it was.
    """
    runs = platform.runs(dive_id)
    if not runs:
        return {"dive": dive_id, "runs": 0,
                "note": "this dive has never been asked for"}
    run = (next((r for r in runs if r["id"] == run_id), None) if run_id
           else max(runs, key=lambda r: r.get("createdAt") or ""))
    if run is None:
        raise Refused(404, "not_found", f"no run {run_id!r} on that dive")
    state = run.get("state")
    if state != "succeeded":
        return {"dive": dive_id, "run": run["id"], "state": state,
                "score": unknown(f"the run {state}, so nothing was scored"),
                "note": "a run that did not finish is not a score of zero"}
    artefacts = platform.artefacts(dive_id, run["id"])
    return {
        "dive": dive_id, "run": run["id"], "state": state,
        "artefacts": [{"path": a.get("path"), "bytes": a.get("sizeBytes")}
                      for a in artefacts],
        "note": "dives_deliverables returns the geometry; every figure in it "
                "is marked in provenance.json",
    }


def dives_deliverables(platform: Platform, dive_id: str, run_id: str | None = None) -> dict:
    """The geometry a run produced, by name.

    `track.geojson` carries two lines and they are not the same claim: where the
    vehicle was, from the simulator, which is the only thing that knows — and
    where it believed it was, from its own navigation. The distance between
    them is the whole reason this platform exists rather than a video of a
    vehicle looking confident.
    """
    runs = platform.runs(dive_id)
    run = (next((r for r in runs if r["id"] == run_id), None) if run_id
           else max(runs, key=lambda r: r.get("createdAt") or "", default=None))
    if run is None:
        raise Refused(404, "not_found", "that dive has no such run")
    wanted = ("track.geojson", "track.csv", "coverage.geojson",
              "planting.geojson", "colonies.geojson", "provenance.json")
    found = {}
    for one in platform.artefacts(dive_id, run["id"]):
        name = (one.get("path") or "").split("/")[-1]
        if name in wanted:
            found[name] = one.get("url")
    return {
        "dive": dive_id, "run": run["id"], "files": found,
        "missing": [w for w in wanted if w not in found],
        "note": ("track.geojson holds where it was and where it believed it "
                 "was as separate features; coverage.geojson is what was "
                 "actually seen, not what was planned"),
    }
