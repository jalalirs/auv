"""What an agent can ask the platform to do.

Named after the nouns the platform already has, so that an agent reading the
tool list can guess the model from it: places, vehicles, controllers, layouts,
missions, dives, sweeps.

Kept separate from the server that serves them. The MCP protocol is one way to
reach these and an HTTP route will be another, and neither should be the place
the answers are shaped.
"""

from __future__ import annotations

import base64
import json
import math
import os
import pathlib
import re
import struct
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


def _error_at_begin(platform: Platform, place: dict, site: dict) -> float | None:
    """How wrong the seabed may be where a dive begins, read off the place's
    own per-cell error at its own start: the start is chosen after the seabed
    is built, by whichever tool knew the reef, so only the place knows both."""
    cells, begin = site.get("perCell") or {}, site.get("beginAt")
    field = (site.get("mesh") or {}).get("heightfield") or {}
    across = (site.get("from") or {}).get("acrossMetres")
    if not (cells.get("error") and begin and field.get("rows") and across):
        return None
    version = _newest(platform.versions_of_place(place["id"]))
    url = next((one["url"] for one in platform.files(version["id"]) if one["path"] == cells["error"]), None)
    if url is None:
        return None
    import math
    import struct
    import urllib.request
    rows, columns = field["rows"], field["columns"]
    row = min(max(round((begin[1] / across + 0.5) * (rows - 1)), 0), rows - 1)
    col = min(max(round((begin[0] / across + 0.5) * (columns - 1)), 0), columns - 1)
    with urllib.request.urlopen(url, timeout=60) as answer:
        (value,) = struct.unpack_from("<f", answer.read(), 4 * (row * columns + col))
    return round(value, 2) if math.isfinite(value) else None


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

    # Where the ground is weak, cell by cell, for a place built by the places
    # module: how much of it is measured, derived, chosen or assumed, how much
    # may be more than a metre or five out, the weakest blocks, and the error
    # where a dive begins. Absent for a place built before the module.
    weak = (came.get("depth") or {}).get("weak")
    if weak:
        depth["weak"] = said(
            {"byKind": weak.get("byKind"), "byError": weak.get("byError"), "errorM": weak.get("errorM"),
             "landShare": weak.get("landShare"), "weakest": weak.get("weakest"),
             "atBeginM": _error_at_begin(platform, place, site)},
            DERIVED, "each cell's source: a measurement's own uncertainty, or a model's held-out error at the cell's depth",
            note="perCell in the package holds the error and source of every cell, and a picture (weak.png)")

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
                 if life.get("observations")
                 else said(life["count"], CHOSEN, life.get("from", "the tank's stocking"))
                 if life.get("tank") and life.get("count")
                 else unknown("no observation record for this place")),
        # A water type somebody chose for a tank is chosen, not measured,
        # however confidently its "from" is written.
        # And one a place was given for want of anything known is assumed.
        "water": ((lambda w: said(w["type"], CHOSEN if str(w.get("from", "")).startswith("chosen")
                                  else ASSUMED if str(w.get("from", "")).startswith("assumed")
                                  else MEASURED, w.get("from", "")) if w.get("from")
                   else said(w.get("type"), ASSUMED, "nobody said"))(site["water"])
                  if site.get("water") else unknown("no Jerlov type recorded")),
        "enclosed": bool(site.get("enclosed", False)),
        # Every view a dive here can be asked for: the built-in ones and the
        # place's own fixed cameras, each with what it shows.
        "views": {"follow": ["chase", "front", "down", "top", "orbit"],
                  "fixed": {name: v.get("what", "") for name, v in
                            ((site.get("cameras") or {}).get("fixed") or {}).items()}},
        **({"rig": site["rig"]} if site.get("rig") else {}),
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
    # The score. This answer used to stop at the list of files, so every run
    # that finished came back with no score at all, which reads exactly like
    # a run that scored nothing. The runtime's judge writes it into the run's
    # outcome, and it is derived: the simulator's own truth, held against
    # what the task asked for.
    outcome = run.get("outcome") or {}
    task = outcome.get("task") or {}
    if task.get("score") is not None:
        score = said(task["score"], DERIVED,
                     f"the runtime's judge of {task.get('kind', 'the task')}, against the simulator's truth",
                     note=_says_of(task))
    else:
        score = unknown("the run finished without a task to judge it by")
    navigation = outcome.get("navigation") or {}
    tether = outcome.get("tether") or {}
    return {
        "dive": dive_id, "run": run["id"], "state": state,
        "score": score,
        "achieved": task.get("achieved"),
        "ended": outcome.get("ended"),
        "flownBy": (task.get("flownBy") or {}).get("mostly"),
        "seconds": task.get("seconds"),
        "energyWh": task.get("energyWh"),
        # How it was flown, beside whether it did the job: effort, roll and
        # pitch, and time off the line for a task flown along one.
        "ride": (said(task["ride"], DERIVED,
                      "the simulator's own state, step by step: the thrusters' commands, the "
                      "vehicle's roll and pitch, and its distance from the line the task is flown along")
                 if task.get("ride") else unknown("this run was flown before results said how it was flown")),
        "struck": outcome.get("hit"),
        **({"navigation": {"aiding": navigation.get("aiding"), "fixFrom": navigation.get("fixFrom"),
                           "driftM": navigation.get("driftM"), "travelledM": navigation.get("travelledM")}}
           if navigation else {}),
        **({"tether": {"lengthM": tether.get("lengthM"), "taut": tether.get("taut"),
                       "tensionN": tether.get("tensionN"), "timesHeldBack": tether.get("timesHeldBack"),
                       **({k: tether[k] for k in ("mostTensionN", "fouled", "why", "winding")
                           if tether.get(k) is not None})}}
           if tether else {}),
        **({"reef": _reef_of(outcome)} if _reef_of(outcome) else {}),
        "artefacts": [{"path": a.get("path"), "bytes": a.get("sizeBytes")}
                      for a in artefacts],
        "note": "dives_deliverables returns the geometry; every figure in it "
                "is marked in provenance.json",
    }


def _reef_of(outcome: dict) -> dict:
    """What the dive did to the place and what lived in it, from the
    runtime's own account (r6: fish with minds, solid coral, sediment). Each
    figure says what it is: the runtime counts what happened in the
    simulation, so the counts are derived; the models behind them carry
    assumptions, which each part names in its `from`."""
    out = {}
    life = outcome.get("life") or {}
    if life:
        out["fish"] = said({"present": life.get("fish"), "bySpecies": life.get("bySpecies"),
                            "struckByTheVehicle": life.get("bumped"), "scatteredAtTheEnd": life.get("scattered"),
                            "howTheySpentIt": life.get("spent")},
                           DERIVED, "the fish system: each fish's mind, its species' sheet, and the vehicle "
                                    "as it saw it (Hein's looming rule; Calovi/Lei swimming)")
    coral = outcome.get("coral") or {}
    if coral:
        out["coral"] = said({"colonies": coral.get("colonies"), "struck": coral.get("struck"),
                             "brushed": coral.get("brushed"), "broken": coral.get("broken"),
                             **{k: coral[k] for k in ("tornOff", "smothered", "smotheredBadly",
                                                      "smotheredOver", "worstSmothered") if k in coral}},
                            DERIVED, coral.get("from") or "the coral system")
    sediment = outcome.get("sediment") or {}
    if sediment:
        out["sediment"] = said({k: sediment.get(k) for k in ("liftedG", "settledG", "dredgedKg", "inTheWaterG",
                                                             "worstVisibilityM", "worstOnACoralMgCm2")
                                if k in sediment},
                               DERIVED, sediment.get("from") or "the sediment system")
    if outcome.get("hardestStrike"):
        out["hardestStrike"] = said(outcome["hardestStrike"], DERIVED,
                                    "the contact the vehicle took hardest: speed into the surface, and the "
                                    "impulse to stop it from its effective mass")
    if outcome.get("day"):
        out["day"] = outcome["day"]
    return out


def _says_of(task: dict) -> str | None:
    """The task's own sentence about how it went, where it left the pieces."""
    got = task.get("achieved") or {}
    if "reached" in got and "of" in got:
        return f"{got['reached']} of {got['of']} reached"
    return task.get("says")


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
    # What a dive produces, and not what a place does. This listed
    # colonies.geojson too, so every dive reported it missing — and a colony
    # inventory belongs to a reef rather than to one flight over it.
    # coverage.geojson appears only when the dive was asked to cover a plot,
    # and planting.geojson only when it was asked to plant.
    wanted = ("track.geojson", "track.csv", "provenance.json",
              "coverage.geojson", "planting.geojson")
    always = ("track.geojson", "track.csv", "provenance.json")
    found = {}
    for one in platform.artefacts(dive_id, run["id"]):
        name = (one.get("path") or "").split("/")[-1]
        if name in wanted:
            found[name] = one.get("url")
    missing = [w for w in always if w not in found]

    # The files themselves, not only links to them.
    #
    # A link the platform hands out points at its object store on the tailnet,
    # so an agent calling from anywhere else is handed a URL it cannot open.
    # This server runs beside the store, so it fetches them and returns what is
    # in them. They are small — a track is a few hundred points, a coverage a
    # few hundred cells — and an agent wants the geometry, not an errand.
    contents: dict[str, object] = {}
    for name, url in found.items():
        try:
            raw = _fetch(url)
        except Exception as problem:
            contents[name] = {"unreadable": f"{type(problem).__name__}: {problem}"}
            continue
        if len(raw) > INLINE_LIMIT:
            contents[name] = {"tooLarge": len(raw), "limit": INLINE_LIMIT}
        elif name.endswith((".geojson", ".json")):
            contents[name] = json.loads(raw)
        else:
            contents[name] = raw.decode("utf-8", "replace")
    raw = {(one.get("path") or "").split("/")[-1]
           for one in platform.artefacts(dive_id, run["id"])}
    out = {
        "dive": dive_id, "run": run["id"], "files": found, "missing": missing,
        "contents": contents,
        "note": ("track.geojson holds where it was and where it believed it "
                 "was as separate features; coverage.geojson is what was "
                 "actually seen, not what was planned"),
    }
    if missing and raw:
        # Why they are missing, not just that they are.
        #
        # A run's artefacts are its raw recording — poses.jsonl, sensors.jsonl,
        # task.jsonl. The geometry is made from those by tools/deliver, which
        # runs on somebody's workstation against a recording on disk, and
        # nothing uploads what it produces. So the platform holds every number
        # needed to draw the track and does not hold the track, and an agent
        # asking for the geometry is asking for a file that was never put
        # anywhere it could reach.
        #
        # Listing six missing filenames without saying that would send it
        # looking for a permissions problem.
        out["why_missing"] = (
            "this run carries its raw recording (" + ", ".join(sorted(raw)[:4]) +
            ") and not its deliverables: the geometry is produced by "
            "tools/deliver from the recording, and nothing uploads the result "
            "to the platform yet")
    return out


# ── arranging a place ────────────────────────────────────────────────────────
#
# Drawing a line and looking at the result are two operations, not one. This
# half changes the arrangement and answers with the arrangement; `layouts_chart`
# draws what is there from the numbers; and rendering what a camera would see
# from a point in the water is a third thing again, with a GPU behind it and a
# position and an orientation to be given. Putting a picture in the return of an
# edit would have made every edit cost what the picture costs.

def _fetch(url: str) -> bytes:
    import urllib.request
    with urllib.request.urlopen(url, timeout=120) as answer:
        return answer.read()


def _layout_document(platform: Platform, layout_id: str) -> tuple[dict, dict]:
    """A layout and the document of its newest version."""
    layout = platform.request("GET", f"/api/v1/layouts/{layout_id}")
    versions = platform.request(
        "GET", f"/api/v1/layouts/{layout_id}/versions")["versions"]
    newest = _newest(versions)
    document = (newest or {}).get("document") or {"things": []}
    return layout, document


def layouts_list(platform: Platform, place: str) -> dict:
    """Every arrangement of a place."""
    found = next((p for p in platform.places()
                  if p["id"] == place or p.get("slug") == place), None)
    if found is None:
        raise Refused(404, "not_found", f"no place {place!r} is granted to you")
    return {"place": found.get("name"),
            "layouts": [{"id": one["id"], "slug": one.get("slug"),
                         "name": one.get("name")}
                        for one in platform.layouts_of(found["id"])]}


def layouts_create(platform: Platform, place: str, name: str,
                   slug: str = "") -> dict:
    """Start an arrangement of a place, belonging to whoever asked for it.

    Anybody who can look at a place can have their own scenarios over it. What
    separates one person's plot from another's is who made it, so this is how an
    agent gets something it is allowed to change: its own.
    """
    found = next((p for p in platform.places()
                  if p["id"] == place or p.get("slug") == place), None)
    if found is None:
        raise Refused(404, "not_found", f"no place {place!r} is granted to you")
    handle = slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    made = platform.request("POST", f"/api/v1/cities/{found['id']}/layouts",
                            {"slug": handle, "name": name})
    return {"id": made["id"], "slug": made.get("slug"), "name": made.get("name"),
            "place": found.get("name"),
            "note": "yours: layouts_add_line can change this one"}


def layouts_get(platform: Platform, layout: str) -> dict:
    """What is in the water, as the arrangement says."""
    one, document = _layout_document(platform, layout)
    things = document.get("things") or []
    kinds: dict[str, int] = {}
    for thing in things:
        kinds[thing.get("kind", "?")] = kinds.get(thing.get("kind", "?"), 0) + 1
    return {
        "id": one["id"], "name": one.get("name"),
        "frame": document.get("frame")
                 or "metres, origin at the middle of the site, +x east, +y north",
        "things": len(things), "kinds": kinds,
        "document": document,
    }


def layouts_add_line(platform: Platform, layout: str,
                     start: list, end: list, spacing_m: float,
                     kind: str = "transponder", name: str = "") -> dict:
    """Put a row of marks along a line, evenly spaced, and save it.

    Returns the arrangement, not a picture. Ask `layouts_chart` for the picture
    when you want to look — the two are separate so that twenty edits cost
    twenty edits rather than twenty pictures.

    `start` and `end` are [x, y] in site metres, origin at the middle of the
    site, +x east and +y north, which is the frame a vehicle's own positions are
    in. The depth each mark sits at is the place's business, not this one's: a
    transponder lands on the ground and a buoy floats, and the platform resolves
    that when the layout is drawn.
    """
    if spacing_m <= 0:
        raise Refused(400, "invalid", "a spacing of metres has to be more than nothing")
    one, document = _layout_document(platform, layout)
    things = list(document.get("things") or [])

    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    run = math.hypot(x1 - x0, y1 - y0)
    if run == 0:
        raise Refused(400, "invalid", "a line needs two different ends")
    # Both ends included, so a hundred-metre line at twenty-five metres is five
    # marks and not four: somebody asking for a line between two points means
    # the points.
    count = int(run // spacing_m) + 1
    made = []
    for at in range(count):
        part = 0.0 if count == 1 else (at * spacing_m) / run
        thing = {
            "id": f"{name or kind}-{at + 1}",
            "kind": kind,
            "x": round(x0 + (x1 - x0) * part, 3),
            "y": round(y0 + (y1 - y0) * part, 3),
        }
        things.append(thing)
        made.append(thing)

    document = dict(document)
    document["things"] = things
    document.setdefault(
        "frame", "metres, origin at the middle of the site, +x east, +y north")
    saved = platform.request("POST", f"/api/v1/layouts/{layout}/versions", {
        "label": name or f"a line of {count} {kind}",
        "document": document,
    })
    return {
        "layout": one.get("name"), "version": saved.get("id"),
        "added": made, "things": len(things),
        "lineLengthM": round(run, 2),
        "note": ("saved as a new version; layouts_chart draws it, and nothing "
                 "here renders — a camera view is a separate operation with a "
                 "position and an orientation of its own"),
    }


def layouts_chart(platform: Platform, layout: str) -> dict:
    """A plan view of the place with the arrangement on it, as a PNG.

    Drawn from the heightfield and the coordinates: no scene, no camera, no
    GPU. It answers "did my line land where I meant and does it clear the edge
    of the reef", which is the question an edit needs answered. It cannot answer
    what anything looks like.
    """
    from . import chart as drawing

    one, document = _layout_document(platform, layout)
    place_id = one.get("cityId") or one.get("placeId")
    place = next((p for p in platform.places() if p["id"] == place_id), None)
    if place is None:
        raise Refused(404, "not_found", "that layout's place is not granted to you")

    version = _newest(platform.versions_of_place(place["id"]))
    files = {f["path"]: f for f in platform.files(version["id"])} if version else {}
    if "site.json" not in files:
        raise Refused(409, "not_published", f"{place.get('name')} has no published package")
    site = json.loads(_fetch(files["site.json"]["url"]))
    across = float((site.get("from") or {}).get("acrossMetres") or 1000.0)

    canvas = drawing.Chart(across)
    field = (site.get("mesh") or {}).get("heightfield") or {}
    name = field.get("file")
    if name and name in files:
        raw = _fetch(files[name]["url"])
        rows, columns = int(field.get("rows", 0)), int(field.get("columns", 0))
        if rows and columns and len(raw) >= rows * columns * 4:
            depths = list(struct.unpack(f"<{rows * columns}f", raw[:rows * columns * 4]))
            canvas.seabed(depths, rows, columns)

    drew: dict[str, int] = {}
    for thing in document.get("things") or []:
        kind = thing.get("kind", "?")
        colour = drawing.MARKS.get(kind, drawing.OTHER)
        ends = thing.get("ends") or []
        corners = thing.get("corners") or []
        if len(ends) >= 2 and ends[0].get("x") is not None:
            canvas.line(float(ends[0]["x"]), float(ends[0]["y"]),
                        float(ends[1]["x"]), float(ends[1]["y"]), colour, width=2)
        elif len(corners) >= 3:
            canvas.box(corners, colour)
        elif thing.get("x") is not None:
            canvas.disc(float(thing["x"]), float(thing["y"]), 3, colour)
        else:
            continue
        drew[kind] = drew.get(kind, 0) + 1

    bar = canvas.rule()
    return {
        "layout": one.get("name"), "place": place.get("name"),
        "acrossMetres": across,
        "drew": drew,
        "scaleBarMetres": bar,
        "legend": {k: "as " + ("a line" if k == "line" else
                               "an outline" if k == "cell" else "a dot")
                   for k in drew},
        "image": base64.b64encode(canvas.png()).decode(),
        "note": ("plan view, north up, +x east. Shaded by depth from the "
                 "place's own heightfield: darker is deeper. This is not a "
                 "render and says nothing about what anything looks like."),
    }


# ── putting one in the water ─────────────────────────────────────────────────

def dives_start(platform: Platform, place: str, vehicle: str,
                objective: dict, water: str = "still",
                controller: str = "", name: str = "",
                pictures: bool = False, views: list | None = None,
                view_every_s: float = 4.0, start: list | None = None) -> dict:
    """Define a dive and ask for it. The first tool here that spends anything.

    A dive names four things and the platform refuses it without them: the
    place, pinned to a version; the vehicle, pinned to a version; **the sea it
    was flown in**; and what it is for. The sea is not optional and that is
    deliberate — a dive whose water nobody stated is a dive nobody can compare
    against another.

    `pictures` is the expensive switch. A drawn dive renders every frame and
    runs at about a sixth of real time; an undrawn one runs at fifteen times it
    on the same trajectory and produces the same numbers. Ask for pictures when
    somebody is going to look, and not otherwise.

    `views` takes the camera through those views in turn, `view_every_s` each,
    so one drawn run can be looked at from the room and from the vehicle.
    Which views a place offers is in places_get; a name it does not offer is
    skipped by the runtime rather than guessed at.

    `start` puts the vehicle in somewhere other than where the place says a
    dive begins: [x, y, z] in the site's metres, +x east, +y north, z up (so
    a depth is negative). It is how a dive goes to look at something the
    place holds, a reconstructed patch say, rather than at the place's start.
    """
    if start is not None and len(start) != 3:
        raise Refused(400, "bad_start", "start is [x, y, z] in the site's metres")
    found = next((p for p in platform.places()
                  if p["id"] == place or p.get("slug") == place), None)
    if found is None:
        raise Refused(404, "not_found", f"no place {place!r} is granted to you")
    machine = next((v for v in platform.vehicles()
                    if v["id"] == vehicle or v.get("slug") == vehicle), None)
    if machine is None:
        raise Refused(404, "not_found", f"no vehicle {vehicle!r} is granted to you")

    city_version = _newest(platform.versions_of_place(found["id"]))
    vehicle_version = _newest(platform.versions_of_vehicle(machine["id"]))
    if city_version is None or vehicle_version is None:
        raise Refused(409, "not_published", "that place or vehicle has no published package")
    paths = [f["path"] for f in platform.files(vehicle_version["id"])]
    if not any(p.lower().endswith((".usd", ".usda", ".usdc", ".usdz")) for p in paths):
        raise Refused(409, "cannot_fly",
                      f"{machine.get('name')} has no hull in its published "
                      f"package, so nothing can be put in the water. "
                      f"vehicles_list says which can.")

    institution = platform.institution()
    if institution is None:
        raise Refused(403, "no_institution", "this session belongs to no institution")

    # What flies it: a deployed controller, by slug or id, flies its newest
    # build; any other name is one of the platform's own, said in the
    # objective. This was accepted and dropped, so every dive an agent asked
    # for was held by the runtime whatever it named.
    stack_id = None
    if controller:
        stacks = platform.request("GET", f"/api/v1/organisations/{institution['id']}/autonomy").get("autonomy", [])
        named = [s for s in stacks if controller in (s.get("id"), s.get("slug"))]
        if named:
            stack_id = max(named, key=lambda s: s.get("createdAt") or "")["id"]
        else:
            objective = {**objective, "controller": controller}

    sea = platform.request(
        "POST", f"/api/v1/organisations/{institution['id']}/conditions",
        {"kind": "constructed", "name": water,
         "parameters": WATERS.get(water, WATERS["still"])})

    dive = platform.request(
        "POST", f"/api/v1/organisations/{institution['id']}/dives", {
            "name": name or f"{objective.get('kind', 'a dive')} at {found.get('name')}",
            "cityVersionId": city_version["id"],
            "vehicleVersionId": vehicle_version["id"],
            "conditionsId": sea["id"],
            "objective": {**objective, "pictures": bool(pictures),
                          **({"views": list(views), "viewEveryS": float(view_every_s)} if views else {})},
            **({"initialState": {"positionM": [float(v) for v in start]}} if start else {}),
            **({"autonomyStackId": stack_id} if stack_id else {}),
        })

    queues = platform.queues()
    if not queues:
        raise Refused(409, "no_queue", "no queue is open to this session")

    # The runtime a host actually offers, not a name that looked like one.
    #
    # This sent "r1", which is the *image tag* — and the platform answered "no
    # host on that queue offers the runtime r1". Hosts advertise
    # `isaac-6.0.1+oceansim`: the engine and the extension that contributes the
    # underwater sensors, which is a version of the thing that integrates and
    # renders, and is not the tag somebody happened to build it under.
    runtime = os.environ.get("IOCEAN_RUNTIME_VERSION", RUNTIME)
    run = platform.request("POST", f"/api/v1/dives/{dive['id']}/runs", {
        "queueId": queues[0]["id"], "mode": "batch",
        "runtimeVersion": runtime})

    return {
        "dive": dive["id"], "run": run["id"], "state": run.get("state"),
        "place": found.get("name"), "vehicle": machine.get("name"),
        "water": water, "drawn": bool(pictures), "runtime": runtime,
        **({"flownBy": controller, "stack": stack_id} if stack_id else {"flownBy": controller} if controller else {}),
        **({"views": list(views), "viewEveryS": float(view_every_s)} if views else {}),
        "note": ("queued. dives_result says how it went; a drawn dive runs at "
                 "about a sixth of real time and an undrawn one at fifteen "
                 "times it, on the same trajectory"),
    }


def dives_film(platform: Platform, dive_id: str, run_id: str | None = None,
               views: list | None = None, view_every_s: float = 6.0,
               film: dict | None = None) -> dict:
    """The path-traced film of a run already flown.

    A film cannot be made while somebody flies — a path-traced frame takes
    seconds — and whoever flew cannot be asked to fly it again. What they
    commanded can be: the platform defines a new dive copied from the record
    of this one, and flies it on the same seed from the commands the run kept.
    Everything that makes it the same dive is copied by the platform, not
    here, so nothing an agent passes can make it a different one.
    """
    runs = platform.runs(dive_id)
    if not runs:
        raise Refused(404, "not_found", "that dive has never been flown")
    run = (next((r for r in runs if r["id"] == run_id), None) if run_id
           else max(runs, key=lambda r: r.get("createdAt") or ""))
    if run is None:
        raise Refused(404, "not_found", f"no run {run_id!r} on that dive")
    body = {**({"views": list(views), "viewEveryS": float(view_every_s)} if views else {}),
            **({"film": film} if film else {})}
    made = platform.request("POST", f"/api/v1/dives/{dive_id}/runs/{run['id']}/film", body)
    return {"dive": made["dive"]["id"], "run": made["run"]["id"], "state": made["run"].get("state"),
            "filmOf": run["id"], "seed": made["run"].get("seed"),
            "note": ("queued: the run flown again from its commands, drawn. dives_result on the new dive "
                     "says how it went; the film is about a sixth of real time to make")}


# The seas a dive can be asked for, by name. Constructed rather than observed:
# nobody measured a current at these places today, and a made-up reading
# dressed as an observation is the one thing this platform will not do.
# How big a file this server will hand over in a tool's answer rather than
# as a link: enough for any track or coverage a dive produces, short of a video.
INLINE_LIMIT = 4 * 1024 * 1024

# What the hosts on this platform run. An image tag is not a runtime: the tag
# says which build, and this says which engine, so a dive asking for one by tag
# is refused with "no host on that queue offers the runtime r1".
RUNTIME = "isaac-6.0.1+oceansim"

WATERS = {
    "still": {"currentMetresPerSecond": 0.0, "currentHeadingDeg": 0.0},
    "gentle": {"currentMetresPerSecond": 0.13, "currentHeadingDeg": 45.0},
    "half-knot": {"currentMetresPerSecond": 0.26, "currentHeadingDeg": 45.0},
    "one-knot": {"currentMetresPerSecond": 0.51, "currentHeadingDeg": 45.0},
}
# A tank's waters: the fan on the rim blows west across the surface and the
# pump on the back glass pushes east. Clear, filtered water, and the gantry
# camera fixing the vehicle's position off the tag on its lid — which is what
# a tank has instead of a Doppler log.
_TANK = {"waterType": "I",
         # The room is lit; a vehicle's own lamps in a daylit tank only glare
         # off the glass in front of it.
         "fitted": {"lights": False},
         "positioning": {
    "kind": "camera", "accuracyM": 0.005, "everyS": 0.1,
    "from": "chosen: a camera 1.2 m over the water tracking an AprilTag on the lid"}}
WATERS.update({
    "tank-still": {**_TANK, "currentMetresPerSecond": 0.0, "currentHeadingDeg": 0.0},
    "fan-low": {**_TANK, "windMetresPerSecond": 2.0, "windHeadingDeg": 270.0},
    "fan-high": {**_TANK, "windMetresPerSecond": 5.0, "windHeadingDeg": 270.0},
    "pump": {**_TANK, "currentMetresPerSecond": 0.06, "currentHeadingDeg": 90.0},
    "fan-and-pump": {**_TANK, "windMetresPerSecond": 4.0, "windHeadingDeg": 270.0,
                     "currentMetresPerSecond": 0.06, "currentHeadingDeg": 90.0},
})


# ── what the camera saw ──────────────────────────────────────────────────────

def _cached(run_id: str, name: str, url: str) -> pathlib.Path:
    """A run's file, fetched once. Recordings are immutable: a run that has
    ended never changes, so asking for six frames of one dive should download
    its video once and not six times."""
    import tempfile
    import urllib.request

    where = pathlib.Path(tempfile.gettempdir()) / "iocean-mcp" / run_id
    where.mkdir(parents=True, exist_ok=True)
    path = where / name
    if not path.exists() or path.stat().st_size == 0:
        urllib.request.urlretrieve(url, path)
    return path


def dives_frame(platform: Platform, dive_id: str, at_seconds: float,
                run_id: str | None = None) -> dict:
    """What the camera saw at a moment of a dive, as an image, and from where.

    Read out of the dive's own video, whose clock is the dive's clock: a frame
    is captured every eighth of a simulated second and encoded at eight a
    second, so a moment in the dive is that many seconds into the video.

    Returned with the pose it was seen from — the position, the heading, and
    the camera — because a picture an agent cannot place is a picture it will
    describe as though it knew where it was. That is the same rule views_render
    keeps: the camera comes back beside the image.
    """
    import shutil
    import subprocess

    runs = platform.runs(dive_id)
    run = (next((r for r in runs if r["id"] == run_id), None) if run_id
           else max(runs, key=lambda r: r.get("createdAt") or "", default=None))
    if run is None:
        raise Refused(404, "not_found", "that dive has no such run")
    files = {(a.get("path") or "").split("/")[-1]: a
             for a in platform.artefacts(dive_id, run["id"])}
    if "dive.mp4" not in files:
        raise Refused(409, "not_drawn",
                      "this dive was flown undrawn, so there is nothing to look at: "
                      "it has its numbers and no pictures. dives_start with "
                      "pictures=true flies one that can be seen.")
    if shutil.which("ffmpeg") is None:
        raise Refused(501, "no_decoder",
                      "reading a frame out of dive.mp4 needs ffmpeg on the machine "
                      "this server runs on")

    video = _cached(run["id"], "dive.mp4", files["dive.mp4"]["url"])
    out = video.parent / f"at-{at_seconds:.3f}.png"
    if not out.exists():
        done = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", f"{max(0.0, at_seconds):.3f}",
             "-i", str(video), "-frames:v", "1", "-y", str(out)],
            capture_output=True, timeout=120)
        if done.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            raise Refused(416, "out_of_range",
                          f"no frame at {at_seconds} s: the dive's video is shorter "
                          f"than that, or it would not decode")

    # Where it was seen from: the nearest pose in the recording.
    seen_from = None
    if "poses.jsonl" in files:
        poses = _cached(run["id"], "poses.jsonl", files["poses.jsonl"]["url"])
        best = None
        with poses.open() as handle:
            for line in handle:
                try:
                    pose = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = pose.get("t")
                if t is None:
                    continue
                gap = abs(float(t) - at_seconds)
                if best is None or gap < best[0]:
                    best = (gap, pose)
        if best is not None:
            pose = best[1]
            seen_from = {
                "t": pose.get("t"),
                "position": pose.get("position"),
                "headingDeg": pose.get("headingDeg"),
                "altitudeM": pose.get("altitudeM"),
                "believed": pose.get("believed"),
                "camera": pose.get("camera"),
                "frame": "metres, origin at the middle of the site, +x east, +y north, z up",
            }

    return {
        "dive": dive_id, "run": run["id"], "atSeconds": at_seconds,
        "seenFrom": seen_from,
        "image": base64.b64encode(out.read_bytes()).decode(),
        "note": ("a rendered frame from a simulator, not a photograph of a real "
                 "reef. seenFrom is where the vehicle actually was; `believed` is "
                 "where it thought it was"),
    }


# ── one mission against everything nobody can promise ────────────────────────

def missions_list(platform: Platform, place: str) -> dict:
    """A place's plans of work. A sweep flies one of these, not a place."""
    found = next((p for p in platform.places()
                  if p["id"] == place or p.get("slug") == place), None)
    if found is None:
        raise Refused(404, "not_found", f"no place {place!r} is granted to you")
    out = []
    for one in platform.missions_of(found["id"]):
        versions = platform.request("GET", f"/api/v1/missions/{one['id']}/versions")["versions"]
        newest = _newest(versions)
        stages = ((newest or {}).get("document") or {}).get("stages") or []
        out.append({"id": one["id"], "name": one.get("name"),
                    "stages": [s.get("kind") for s in stages]})
    return {"place": found.get("name"), "missions": out}


def sweeps_run(platform: Platform, mission: str, vehicle: str,
               doubts: dict, repeats: int = 2, name: str = "") -> dict:
    """Fly one mission against every combination of the doubts named.

    This is the tool that is not a demonstration. One dive says a plan worked
    once in one water. A sweep says which of the things nobody can promise —
    the current, the mooring thirty metres from where the chart says, the
    transponder that did not come up — break it, and which one change saves the
    most of the failures. sweeps_findings reads that answer, and it is readable
    before the sweep has finished.

    Every combination is flown `repeats` times, because one run of a scenario
    that goes either way is a coin toss reported as a result.
    """
    from . import doubts as catalogue

    try:
        said = catalogue.asked(doubts)
    except KeyError as unknown:
        raise Refused(400, "invalid", unknown.args[0]) from unknown
    count = catalogue.scenarios(doubts)
    runs = count * max(1, int(repeats))

    machine = next((v for v in platform.vehicles()
                    if v["id"] == vehicle or v.get("slug") == vehicle), None)
    if machine is None:
        raise Refused(404, "not_found", f"no vehicle {vehicle!r} is granted to you")
    vehicle_version = _newest(platform.versions_of_vehicle(machine["id"]))
    mission_version = _newest(
        platform.request("GET", f"/api/v1/missions/{mission}/versions")["versions"])
    if vehicle_version is None or mission_version is None:
        raise Refused(409, "not_published", "that mission or vehicle has no saved version")

    institution = platform.institution()
    queues = platform.queues()
    if institution is None or not queues:
        raise Refused(409, "nowhere_to_fly", "no institution or no queue for this session")

    sweep = platform.request(
        "POST", f"/api/v1/organisations/{institution['id']}/sweeps", {
            "name": name or f"a sweep of {count} scenarios",
            "missionVersionId": mission_version["id"],
            "vehicleVersionId": vehicle_version["id"],
            "doubts": said,
            "repeats": int(repeats),
            "queueId": queues[0]["id"],
            "runtimeVersion": os.environ.get("IOCEAN_RUNTIME_VERSION", RUNTIME),
        })
    return {
        "sweep": sweep["id"], "scenarios": count, "runs": runs,
        "vehicle": machine.get("name"),
        "note": (f"{runs} dives queued — {count} combinations, {repeats} of each. "
                 "sweeps_findings answers from whatever has flown so far, so it "
                 "can be read before the sweep finishes"),
    }


def sweeps_findings(platform: Platform, sweep: str) -> dict:
    """What breaks the mission, and the one change that saves the most of it.

    Ranked by how much each doubt *changes* the outcome, not by how often it was
    present when the mission failed — the second is misleading, and is the
    mistake a person reading a table of failures makes first.
    """
    return platform.request("GET", f"/api/v1/sweeps/{sweep}/findings")


# ── building a place ─────────────────────────────────────────────────────────


def places_sources(platform: Platform) -> dict:
    """What a place can be built from."""
    said = platform.request("GET", "/api/v1/build-sources")
    return {**said, "note": "places_build names some of these; gebco is laid under everything anyway, "
                            "so every cell has a depth"}


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:56] or "place"
    return slug if len(slug) >= 3 else slug + "-place"


def places_build(platform: Platform, name: str, centre: list | None = None, across_m: float = 1000.0,
                 sources: list | None = None, files: list | None = None, cells: int | None = None,
                 base_place: str = "", flat_depth_m: float | None = None, coral: bool | None = None,
                 survey: list | None = None) -> dict:
    """Found a place of the institution's own and build it from its data."""
    if survey and centre is None and not base_place:
        # The square the first survey covers, as its import read it.
        bbox = (platform.request("GET", f"/api/v1/assets/{survey[0]}").get("footprint") or {}).get("bbox")
        if not bbox or len(bbox) != 4:
            raise Refused(400, "invalid", "give centre too: the survey does not say what it covers yet")
        south, west, north, east = (float(v) for v in bbox)
        centre = [(south + north) / 2, (west + east) / 2]
        across_m = max((north - south) * 111_320.0,
                       (east - west) * 111_320.0 * math.cos(math.radians(centre[0])), 100.0)
    if base_place and centre is None:
        # The new place takes the base's square; the founding record needs
        # one, so it is read from the store, where a base usually comes from.
        listed = {p["id"]: p for p in platform.request("GET", "/api/v1/store/places").get("places") or []}
        extent = (listed.get(base_place) or {}).get("extent")
        if not extent:
            raise Refused(400, "invalid", "give centre too: the base is not in the map store, so its square is not known here")
        centre = [(extent["south"] + extent["north"]) / 2, (extent["west"] + extent["east"]) / 2]
        across_m = max((extent["north"] - extent["south"]) * 111_320.0, 100.0)
    if not isinstance(centre, (list, tuple)) or len(centre) != 2:
        raise Refused(400, "invalid", "centre is [latitude, longitude] in degrees")
    lat, lon = float(centre[0]), float(centre[1])
    institution = platform.institution()
    if institution is None:
        raise Refused(403, "forbidden", "this session belongs to no institution, and a place is built for one")
    half_lat = across_m / 2 / 111_320.0
    half_lon = across_m / 2 / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    extent = {"west": lon - half_lon, "south": lat - half_lat, "east": lon + half_lon, "north": lat + half_lat}
    base = _slug(name)
    place = None
    for attempt in range(6):
        slug = base if attempt == 0 else f"{base}-{attempt + 1}"
        try:
            made_of = (f"a flat seabed at {flat_depth_m:g} m" if flat_depth_m is not None
                       else ", ".join(sources) if sources else (f"the place {base_place}" if base_place else "every public source"))
            if survey:
                made_of += " and the survey " + ", ".join(survey)
            place = platform.request("POST", f"/api/v1/organisations/{institution['id']}/cities", {
                "slug": slug, "name": name, "verticalDatum": "mean sea level",
                "summary": f"built from {made_of}", "extent": extent})
            break
        except Refused as refused:
            if refused.status != 400 or "already exists" not in str(refused):
                raise
    if place is None:
        raise Refused(409, "conflict", f"places called {base} and five more like it exist; choose another name")
    # No sources named means every public source that reaches the place; the
    # platform fills them in and says so.
    brief: dict[str, Any] = {"centre": [lat, lon], "acrossM": float(across_m), "sources": list(sources or [])}
    if base_place:
        brief["base"] = {"cityId": base_place}
    if flat_depth_m is not None:
        if base_place:
            raise Refused(400, "invalid", "a flat seabed or a place to build on, not both")
        brief["flatDepthM"] = float(flat_depth_m)
        brief["sources"] = []
    if coral is not None:
        brief["coral"] = bool(coral)
    if files:
        brief["files"] = files
    if survey:
        brief["survey"] = [str(one) for one in survey]
    if cells:
        brief["cells"] = int(cells)
    build = platform.request("POST", f"/api/v1/cities/{place['id']}/builds", brief)
    return {"place": {"id": place["id"], "slug": place["slug"], "name": place["name"],
                      "ownedBy": institution.get("name")},
            **_build_summary(build),
            "note": "places_build_status says how it is going; a build from public data takes minutes, "
                    "longer when the laser's depths are fetched"}


def _build_summary(build: dict) -> dict:
    steps = build.get("steps") or []
    brief = build.get("brief") or {}
    out: dict[str, Any] = {
        "build": build.get("id"), "state": build.get("state"),
        "steps": [(f"{s.get('say')} ({s['n']} of {s['of']})" if s.get("of") else s.get("say")) for s in steps][-12:],
    }
    if brief.get("sources"):
        out["sources"] = brief["sources"]
        if brief.get("allSources"):
            out["sourcesNote"] = "none were named, so every public source was used"
    if brief.get("base"):
        out["builtOn"] = brief["base"]
    if build.get("failure"):
        out["failure"] = build["failure"]
    if build.get("said"):
        out["said"] = build["said"][-1500:]
    result = build.get("result") or {}
    depth = result.get("depth") or {}
    weak = depth.get("weak") or {}
    if build.get("versionId"):
        out["version"] = build["versionId"]
        out["published"] = False
    if weak:
        error = weak.get("errorM") or {}
        out["howWrongTheDepthMayBe"] = {
            "medianM": said(error.get("median"), DERIVED, "each cell's error from the source that made it"),
            "p90M": said(error.get("p90"), DERIVED, "each cell's error from the source that made it"),
            "worstM": said(error.get("worst"), DERIVED, "each cell's error from the source that made it")}
        if weak.get("byKind"):
            out["shareByKind"] = weak["byKind"]
        if weak.get("weakest"):
            out["weakest"] = weak["weakest"]
    if depth.get("sources"):
        out["madeBy"] = [{"source": s.get("source"), "kind": s.get("kind"), "share": s.get("share")}
                         for s in depth["sources"]]
    for key in ("deepestM", "shallowestM"):
        if result.get(key) is not None:
            out[key] = said(result[key], DERIVED, "the built seabed")
    if build.get("state") == "ready":
        out["next"] = "places_publish with this version lets dives use it"
    return out


def places_build_status(platform: Platform, build: str) -> dict:
    """How a build is going, and when it is done, where the place it made is weak."""
    return _build_summary(platform.request("GET", f"/api/v1/builds/{build}"))


def places_publish(platform: Platform, version: str) -> dict:
    """Publish a version a build made, so dives can use it."""
    published = platform.request("POST", f"/api/v1/versions/{version}/publish")
    return {"version": published.get("id", version), "published": True,
            "note": "dives_start can now fly in it; places_get reads what its ground came from"}


# ── a reef from a dive video ─────────────────────────────────────────────────


def _organisation(platform: Platform, org: str) -> str:
    """The organisation named, or the session's own."""
    if org:
        return org
    institution = platform.institution()
    if institution is None:
        raise Refused(403, "forbidden", "this session belongs to no institution, and a reconstruction is made for one")
    return institution["id"]


def uploads_start(platform: Platform, size_bytes: int, sha256: str, media_type: str = "",
                  org: str = "") -> dict:
    """Ask to place a file in the institution's storage; the bytes go in parts."""
    if int(size_bytes) <= 0:
        raise Refused(400, "invalid", "size_bytes is the file's length, more than 0")
    sha = str(sha256).lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise Refused(400, "invalid", "sha256 is the file's digest as 64 hex characters")
    organisation = _organisation(platform, org)
    grant = platform.request("POST", f"/api/v1/organisations/{organisation}/uploads", {
        "bucket": "evidence", "sha256": sha, "sizeBytes": int(size_bytes),
        "mediaType": media_type or "application/octet-stream"})
    parts = grant.get("parts") or {}
    return {
        "grant": grant.get("id"), "expiresAt": grant.get("expiresAt"),
        "parts": parts.get("count"), "partBytes": parts.get("partBytes"),
        "partPath": f"/api/v1/organisations/{organisation}/uploads/{grant.get('id')}/parts/{{n}}",
        "note": "PUT each part's bytes (n from 1, partBytes each, the last one shorter) to partPath "
                "on this server's address, with the same Authorization header this MCP call used. "
                "Then uploads_confirm with the grant gives the object id.",
    }


def uploads_confirm(platform: Platform, grant: str, org: str = "") -> dict:
    """Check what arrived against what was declared; the object id comes back."""
    organisation = _organisation(platform, org)
    made = platform.request("POST", f"/api/v1/organisations/{organisation}/uploads/{grant}/confirm", {})
    return {"object": made.get("id"), "sizeBytes": made.get("sizeBytes"), "sha256": made.get("sha256"),
            "note": "give this object to reconstructions_create as video, or to assets_create as object"}


def reconstructions_create(platform: Platform, video: str, name: str = "", org: str = "",
                           camera_height_m: float | None = None, start: Any = None,
                           label: str = "", fps: float | None = None, tape: str = "") -> dict:
    """Make a reef from a dive video the institution holds."""
    brief: dict[str, Any] = {"video": {"objectId": video}}
    if name:
        brief["video"]["name"] = name
    if label:
        brief["label"] = label
    if camera_height_m is not None:
        brief["cameraHeightM"] = float(camera_height_m)
    if start is not None:
        if isinstance(start, dict):
            lat, lon = start.get("lat"), start.get("lon")
        elif isinstance(start, (list, tuple)) and len(start) == 2:
            lat, lon = start
        else:
            raise Refused(400, "invalid", "start is [latitude, longitude] in degrees")
        brief["start"] = {"lat": float(lat), "lon": float(lon)}
    if fps is not None:
        brief["fps"] = float(fps)
    if tape:
        brief["tape"] = tape
    made = platform.request("POST", f"/api/v1/organisations/{_organisation(platform, org)}/reconstructions", brief)
    return {**_reconstruction_summary(made),
            "note": "reconstructions_status says how it is going; a reconstruction runs on a GPU "
                    "for hours, most of it training the reef's splats"}


def _reconstruction_summary(made: dict) -> dict:
    steps = made.get("steps") or []
    brief = made.get("brief") or {}
    out: dict[str, Any] = {
        "reconstruction": made.get("id"), "name": made.get("name"), "state": made.get("state"),
        "video": (brief.get("video") or {}).get("objectId"),
        "steps": [(f"{s.get('say')} ({s['n']} of {s['of']})" if s.get("of") else s.get("say")) for s in steps][-12:],
    }
    if made.get("failure"):
        out["failure"] = made["failure"]
    if made.get("said"):
        out["said"] = made["said"][-1500:]
    manifest = made.get("manifest") or {}
    if manifest:
        scale = manifest.get("scale") or {}
        how = str(scale.get("how") or "")
        # The reef's size is only as good as what gave it its scale: a camera
        # height nobody stated is the job's default, and says so.
        kind = ASSUMED if "assum" in how.lower() or brief.get("cameraHeightM") is None else DERIVED
        source = f"scale {how or 'unstated'}" + (f" from {scale['from']}" if scale.get("from") else "")
        pieces = manifest.get("pieces") or []
        out["reef"] = {
            "pieces": said(len(pieces), DERIVED, "the reconstruction's own manifest"),
            "frames": said(manifest.get("frames"), DERIVED, "frames read from the video"),
            "registered": said(manifest.get("registered"), DERIVED, "frames the reconstruction placed"),
            "splats": said(sum(int(p.get("splats") or 0) for p in pieces), DERIVED, "the reconstruction's pieces"),
        }
        if manifest.get("extentM"):
            out["reef"]["extentM"] = said(manifest["extentM"], kind, source)
        if scale.get("factor") is not None:
            out["reef"]["scale"] = said(scale["factor"], kind, source)
        if made.get("state") == "ready":
            out["next"] = ("its files are at GET /api/v1/reconstructions/{id}/objects; laying it into a "
                           "place is a separate step")
    return out


def reconstructions_status(platform: Platform, reconstruction: str) -> dict:
    """How a reconstruction is going, and when it is done, what it made."""
    return _reconstruction_summary(platform.request("GET", f"/api/v1/reconstructions/{reconstruction}"))


def reconstructions_list(platform: Platform, org: str = "") -> dict:
    """An institution's reconstructions, newest first."""
    said_ = platform.request("GET", f"/api/v1/organisations/{_organisation(platform, org)}/reconstructions")
    return {"reconstructions": [_reconstruction_summary(one) for one in said_.get("reconstructions") or []]}


# ── assets of every kind ─────────────────────────────────────────────────────


def assets_create(platform: Platform, kind: str, object: str = "", name: str = "", format: str = "",
                  type: str = "", meets: str = "", datum: str = "", error_m: float | None = None,
                  citation: str = "", scale: float | None = None, up: str = "", route: list | None = None,
                  diameter_m: float | None = None, burial: float | None = None, label: str = "",
                  org: str = "") -> dict:
    """Make a structure or a seabed survey into an asset, from an uploaded file or a pipeline's route."""
    brief: dict[str, Any] = {"kind": kind}
    if kind == "bathymetry":
        if not object or not datum or error_m is None:
            raise Refused(400, "invalid", "a survey is an uploaded file (object) with its datum and error_m")
        brief["file"] = {k: v for k, v in (("name", name), ("format", format)) if v}
        brief.update({"datum": datum, "errorM": float(error_m), "object": object})
        if citation:
            brief["citation"] = citation
    elif kind == "structure":
        if route is not None:
            if object:
                raise Refused(400, "invalid", "a structure is a model (object) or a route, not both")
            if not isinstance(route, (list, tuple)) or len(route) < 2 or diameter_m is None:
                raise Refused(400, "invalid", "a route is two or more [latitude, longitude] points, with diameter_m")
            points = []
            for one in route:
                if not isinstance(one, (list, tuple)) or len(one) != 2:
                    raise Refused(400, "invalid", "each point of a route is [latitude, longitude]")
                points.append([float(one[0]), float(one[1])])
            brief["type"] = type or "pipeline"
            brief["route"] = {"points": points, "diameterM": float(diameter_m)}
            if burial is not None:
                brief["route"]["burial"] = float(burial)
        else:
            if not object or not type:
                raise Refused(400, "invalid", "a structure is an uploaded model (object) with its type, or a pipeline's route")
            brief["type"] = type
            brief["model"] = {k: v for k, v in (("name", name), ("format", format), ("up", up)) if v}
            if scale is not None:
                brief["model"]["scale"] = float(scale)
            brief["object"] = object
        if meets:
            brief["meets"] = meets
    else:
        raise Refused(400, "invalid", "assets_create makes a structure or a bathymetry survey; a reef comes from "
                                      "reconstructions_create")
    if label:
        brief["label"] = label
    made = platform.request("POST", f"/api/v1/organisations/{_organisation(platform, org)}/assets", brief)
    return {**_asset_summary(made),
            "note": "assets_status says how it is going; an import takes minutes on processors"}


# Who to blame for each of an asset's figures, by its kind: a survey's depths
# were measured by whoever surveyed it; what somebody typed when importing it
# was chosen; everything the import job worked out is derived.
_STATED = {"errorM", "datum", "diameterM", "scale", "burial"}


def _asset_figures(kind: str, made_from: str, figures: dict, source: str) -> dict:
    out: dict[str, Any] = {}
    for key, value in figures.items():
        if key in _STATED:
            out[key] = said(value, CHOSEN, "stated when it was imported")
        elif kind == "bathymetry" and "depth" in key.lower():
            out[key] = said(value, MEASURED, "the survey, as uploaded")
        else:
            out[key] = said(value, DERIVED, source)
    return out


def _asset_summary(made: dict) -> dict:
    if made.get("madeFrom") == "video":
        # A reef says what it is in a reconstruction's words.
        return {**_reconstruction_summary(made), "asset": made.get("id"), "kind": "reef", "madeFrom": "video"}
    steps = made.get("steps") or []
    kind, made_from = made.get("kind"), made.get("madeFrom")
    out: dict[str, Any] = {
        "asset": made.get("id"), "name": made.get("name"), "kind": kind, "madeFrom": made_from,
        "state": made.get("state"),
        "steps": [(f"{s.get('say')} ({s['n']} of {s['of']})" if s.get("of") else s.get("say")) for s in steps][-12:],
    }
    for key in ("type", "meets", "failure", "preview"):
        if made.get(key):
            out[key] = made[key]
    if made.get("said"):
        out["said"] = made["said"][-1500:]
    source = {"survey": "the import's reading of the survey file", "model": "the import's reading of the model",
              "route": "the route as given"}.get(made_from or "", "the import job")
    if made.get("footprint"):
        out["footprint"] = _asset_figures(kind, made_from, made["footprint"], source)
    if made.get("stats"):
        out["stats"] = _asset_figures(kind, made_from, made["stats"], source)
    if made.get("state") == "ready":
        out["next"] = ("places_build with survey lays it in as the place's ground" if kind == "bathymetry" else
                       "mappings_create with it as an asset (and a placement when it stands) lays it into a place")
    return out


def assets_status(platform: Platform, asset: str) -> dict:
    """How an asset is going, and when it is ready, what it is."""
    return _asset_summary(platform.request("GET", f"/api/v1/assets/{asset}"))


def assets_list(platform: Platform, kind: str = "", org: str = "") -> dict:
    """An institution's assets of every kind, newest first."""
    query = f"?kind={kind}" if kind else ""
    said_ = platform.request("GET", f"/api/v1/organisations/{_organisation(platform, org)}/assets{query}")
    return {"assets": [_asset_summary(one) for one in said_.get("assets") or []]}


# ── a reef put onto a place ──────────────────────────────────────────────────


def _latlon(start: Any) -> dict:
    if isinstance(start, dict):
        lat, lon = start.get("lat"), start.get("lon")
    elif isinstance(start, (list, tuple)) and len(start) == 2:
        lat, lon = start
    else:
        raise Refused(400, "invalid", "start is [latitude, longitude] in degrees")
    return {"lat": float(lat), "lon": float(lon)}


def _placement(placement: Any) -> dict:
    """Where a structure that stands goes: [lat, lon, heading] or {lat, lon, heading_deg}."""
    if isinstance(placement, dict):
        lat, lon = placement.get("lat"), placement.get("lon")
        heading = placement.get("heading_deg", placement.get("headingDeg", 0))
    elif isinstance(placement, (list, tuple)) and len(placement) in (2, 3):
        lat, lon, heading = (list(placement) + [0])[:3]
    else:
        lat = lon = heading = None
    if lat is None or lon is None:
        raise Refused(400, "invalid", "a placement is [latitude, longitude, heading_deg]")
    return {"lat": float(lat), "lon": float(lon), "headingDeg": float(heading)}


def _asset_of(one: Any) -> dict:
    """One asset of several, as the platform is told it."""
    if isinstance(one, str):
        return {"reconstructionId": one}
    named = isinstance(one, dict) and (one.get("asset") or one.get("reconstruction") or one.get("reconstructionId"))
    if not named:
        raise Refused(400, "invalid", "each asset is an id, or {asset, placement} for a structure that stands, "
                                      "or {asset, start, depth_m, within_m} for a reef")
    asset: dict[str, Any] = {"reconstructionId": named}
    if one.get("placement") is not None:
        asset["placement"] = _placement(one["placement"])
    if one.get("start") is not None:
        asset["start"] = _latlon(one["start"])
    for key, field in (("depth_m", "depthM"), ("within_m", "withinM")):
        if one.get(key) is not None:
            asset[field] = float(one[key])
    if one.get("count") is not None:
        asset["count"] = int(one["count"])
    return asset


def mappings_create(platform: Platform, reconstruction: str = "", mode: str = "onto", place: str = "",
                    version: str = "", start: Any = None, within_m: float | None = None,
                    depth_m: float | None = None, count: int | None = None, name: str = "",
                    across_m: float | None = None, pad: str = "", heading_deg: float | None = None,
                    assets: list | None = None, placement: Any = None) -> dict:
    """Put reefs and structures onto a place, or give a reef a place of its own."""
    if assets:
        if mode != "onto" or not place:
            raise Refused(400, "invalid", "several reefs are put onto a place that exists: mode onto, and the place")
        request: dict[str, Any] = {"assets": [_asset_of(one) for one in assets]}
        if version:
            request["versionId"] = version
        made = platform.request("POST", f"/api/v1/cities/{place}/mappings", request)
        return {**_mapping_summary(made),
                "note": "mappings_status says how each reef's search is going; mappings_accept each, or "
                        "mappings_drop one whose search failed, and they are laid in together"}
    if not reconstruction:
        raise Refused(400, "invalid", "name the reconstruction, or several as assets")
    if mode not in ("onto", "own"):
        raise Refused(400, "invalid", "mode is onto (a place that exists) or own (a flat place of its own)")
    request: dict[str, Any] = {"mode": mode}
    if mode == "onto":
        if not place:
            raise Refused(400, "invalid", "onto names the place (its id)")
        request["cityId"] = place
        if version:
            request["versionId"] = version
        if within_m is not None:
            request["withinM"] = float(within_m)
        if count is not None:
            request["count"] = int(count)
        if placement is not None:
            request["placement"] = _placement(placement)
    else:
        if not name:
            raise Refused(400, "invalid", "a place of its own has a name")
        request["name"] = name
        if across_m is not None:
            request["acrossM"] = float(across_m)
        if pad:
            request["pad"] = pad
        if heading_deg is not None:
            request["headingDeg"] = float(heading_deg)
    if start is not None:
        request["start"] = _latlon(start)
    if depth_m is not None:
        request["depthM"] = float(depth_m)
    made = platform.request("POST", f"/api/v1/reconstructions/{reconstruction}/mappings", request)
    note = ("mappings_status says how it is going; the search takes minutes, and then waits for "
            "mappings_accept" if mode == "onto" else
            "mappings_status says how it is going; the flat seabed builds in minutes, then the reef is laid in on a GPU")
    return {**_mapping_summary(made), "note": note}


def _candidates_of(found: list) -> list:
    fits = "the search's fit of the reef's ground to the place's"
    return [{
        "index": i,
        "at": said(c.get("at"), DERIVED, fits),
        "headingDeg": said(c.get("headingDeg"), DERIVED, fits),
        "rmsM": said((c.get("fit") or {}).get("rmsM"), DERIVED, fits),
        "groundDepthM": said((c.get("fit") or {}).get("placeGroundM"), DERIVED, "the place's seabed where it fits"),
    } for i, c in enumerate(found)]


def _chosen_of(chosen: dict) -> dict:
    return {k: said(v, CHOSEN, "accepted for this mapping") for k, v in chosen.items()
            if k in ("at", "headingDeg", "dz", "centre", "depthM", "lat", "lon", "alongRoute")}


def _mapping_summary(made: dict) -> dict:
    steps = made.get("steps") or []
    brief = made.get("brief") or {}
    out: dict[str, Any] = {
        "mapping": made.get("id"), "mode": made.get("mode"), "state": made.get("state"),
        "place": made.get("cityId"),
        "steps": [f"{s.get('phase')}" + (f" {s['asset']}" if s.get("asset") is not None else "") + ": "
                  + (f"{s.get('say')} ({s['n']} of {s['of']})" if s.get("of") else str(s.get("say")))
                  for s in steps][-12:],
    }
    if brief.get("start"):
        where = [brief["start"]["lat"], brief["start"]["lon"]]
        out["start"] = (said(where, ASSUMED, "nobody said where the video starts; a nominal Red Sea point")
                        if brief.get("startAssumed") else
                        said(where, CHOSEN, "where the video starts, as stated"))
    for key in ("failure", "waiting"):
        if made.get(key):
            out[key] = made[key]
    if made.get("said"):
        out["said"] = made["said"][-1500:]
    reefs = made.get("assets")
    if reefs is None:
        # A mapping as one reef said it, before there could be several.
        reefs = [{"ordinal": 0, "reconstructionId": made.get("reconstructionId"), "state": made.get("state"),
                  "candidates": made.get("candidates"), "chosen": made.get("chosen")}]
    out["assets"] = []
    for one in reefs:
        reef: dict[str, Any] = {"asset": one.get("ordinal"), "reconstruction": one.get("reconstructionId"),
                                "name": one.get("name"), "state": one.get("state")}
        if one.get("candidates"):
            reef["candidates"] = _candidates_of(one["candidates"])
        if one.get("chosen"):
            reef["chosen"] = _chosen_of(one["chosen"])
        if one.get("failure"):
            reef["failure"] = one["failure"]
        out["assets"].append(reef)
    if len(out["assets"]) == 1:
        # One reef, as a mapping of one always said it.
        only = out["assets"][0]
        out["reconstruction"] = only["reconstruction"]
        for key in ("candidates", "chosen"):
            if key in only:
                out[key] = only[key]
    if made.get("overlaps"):
        out["overlaps"] = made["overlaps"]
    if made.get("versionId"):
        out["version"] = made["versionId"]
        out["published"] = False
    if made.get("state") == "choosing":
        out["next"] = ("mappings_accept with an asset and a candidate's index, or at/heading_deg/dz by hand; "
                       "mappings_drop a reef whose search failed")
    elif made.get("state") == "ready":
        out["next"] = "places_publish with this version lets dives use it"
    return out


def mappings_status(platform: Platform, mapping: str) -> dict:
    """How a mapping is going, and what the search found."""
    return _mapping_summary(platform.request("GET", f"/api/v1/mappings/{mapping}"))


def mappings_accept(platform: Platform, mapping: str, candidate: int | None = None, at: list | None = None,
                    heading_deg: float | None = None, dz: float | None = None, asset: int | None = None) -> dict:
    """Choose where a reef goes; when every reef has somewhere, they are laid in."""
    if candidate is not None and at is not None:
        raise Refused(400, "invalid", "accept a candidate or a placement (at, heading_deg, dz), not both")
    if candidate is not None:
        choice: dict[str, Any] = {"candidate": int(candidate)}
    elif at is not None:
        if not isinstance(at, (list, tuple)) or len(at) != 2 or heading_deg is None or dz is None:
            raise Refused(400, "invalid", "a placement by hand is at [x, y] metres, heading_deg and dz")
        choice = {"placement": {"at": [float(at[0]), float(at[1])], "headingDeg": float(heading_deg), "dz": float(dz)}}
    else:
        raise Refused(400, "invalid", "accept a candidate (its index from mappings_status) or at, heading_deg and dz")
    if asset is not None:
        choice["asset"] = int(asset)
    made = platform.request("POST", f"/api/v1/mappings/{mapping}/accept", choice)
    note = ("the reefs are laid in on a GPU; mappings_status says when the place is ready"
            if made.get("state") in ("laying", "recording", "ready") else
            "chosen; the reefs are laid in once every one has somewhere to go")
    return {**_mapping_summary(made), "note": note}


def mappings_drop(platform: Platform, mapping: str, asset: int) -> dict:
    """Take a reef out of a mapping before the reefs are laid in."""
    made = platform.request("POST", f"/api/v1/mappings/{mapping}/drop", {"asset": int(asset)})
    return {**_mapping_summary(made), "note": "dropped; the rest are laid in once each has somewhere to go"}


# ── the map store ────────────────────────────────────────────────────────────


def store_places(platform: Platform, near: list | None = None, across_m: float | None = None) -> dict:
    """The places iOcean builds and publishes, open to everybody."""
    query = ""
    if near is not None:
        if not isinstance(near, (list, tuple)) or len(near) != 2:
            raise Refused(400, "invalid", "near is [latitude, longitude] in degrees")
        query = f"?near={float(near[0])},{float(near[1])}"
        if across_m is not None:
            query += f"&acrossM={float(across_m)}"
    said_ = platform.request("GET", f"/api/v1/store/places{query}")
    places = []
    for one in said_.get("places") or []:
        source = f"the place {one.get('name')} as iOcean built it ({one.get('versionId')})"
        card: dict[str, Any] = {"place": one.get("id"), "slug": one.get("slug"), "name": one.get("name"),
                                "summary": one.get("summary"), "adopted": one.get("adopted", False)}
        for key in ("deepestM", "shallowestM"):
            if one.get(key) is not None:
                card[key] = said(one[key], DERIVED, source)
        if one.get("surveyedFraction") is not None:
            card["measuredShare"] = said(one["surveyedFraction"], DERIVED, source + ": how much of its depth was surveyed")
        elif one.get("surveyed") is not None:
            card["measured"] = "most of its depth was surveyed" if one["surveyed"] else \
                "its depth is estimated, not surveyed: " + (one.get("method") or "from public data")
        if one.get("colonies") is not None:
            card["colonies"] = said(one["colonies"], ASSUMED, source + ": grown, nobody counted them")
        if one.get("distanceM") is not None:
            card["distanceM"] = said(round(one["distanceM"]), DERIVED, "from the middle of the area asked about")
        card["picture"] = bool(one.get("picture"))
        places.append(card)
    note = ("store_adopt adds one to this institution's places; places_build with base_place builds on one "
            "with the institution's own data")
    if near is not None:
        note = (f"{len(places)} store places overlap that area, nearest first; use one rather than build it again. "
                + note)
    return {"places": places, "note": note}


def store_adopt(platform: Platform, place: str, org: str = "") -> dict:
    """Add a place from the map store to the institution's places."""
    org_id = _organisation(platform, org)
    binding = platform.request("POST", f"/api/v1/organisations/{org_id}/store/{place}/adopt")
    return {"place": place, "organisation": org_id, "adopted": True, "share": (binding or {}).get("id"),
            "note": "it is among this institution's places now; dives_start can fly in it"}


# ── a controller built from its source ───────────────────────────────────────


def controllers_build(platform: Platform, url: str = "", ref: str = "", path: str = "", zip_object: str = "",
                      zip_name: str = "", slug: str = "", name: str = "", controller: str = "",
                      org: str = "", controllers: list | None = None) -> dict:
    """Build the controllers in a GitHub repository or an uploaded zip."""
    if bool(url) == bool(zip_object):
        raise Refused(400, "invalid", "name a GitHub repository (url) or an uploaded zip (zip_object), one of them")
    if url:
        source: dict[str, Any] = {"kind": "git", "url": url}
        if ref:
            source["ref"] = ref
        if path:
            source["path"] = path
    else:
        source = {"kind": "zip", "objectId": zip_object, "name": zip_name or "controller.zip"}
    brief: dict[str, Any] = {"source": source}
    if controllers:
        brief["controllers"] = [str(one) for one in controllers]
    for key, value in (("slug", slug), ("name", name), ("controller", controller)):
        if value:
            brief[key] = value
    made = platform.request("POST", f"/api/v1/organisations/{_organisation(platform, org)}/controller-builds", brief)
    return {**_controller_build_summary(made),
            "note": "controllers_build_status says how it is going; a build takes minutes, its tank check one more"}


def _controller_build_summary(made: dict) -> dict:
    steps = made.get("steps") or []
    out: dict[str, Any] = {
        "build": made.get("id"), "source": (made.get("brief") or {}).get("source"),
        "state": made.get("state"),
        "steps": [(f"{s.get('say')} ({s['n']} of {s['of']})" if s.get("of") else s.get("say")) for s in steps][-12:],
    }
    report = made.get("report") or {}
    if report.get("source"):
        out["source"] = report["source"]
    built = []
    for one in made.get("controllers") or []:
        tank = (one.get("checks") or {}).get("tank") or {}
        entry: dict[str, Any] = {"slug": one.get("slug"), "ok": one.get("ok"), "controller": one.get("controller"),
                                 "commands": one.get("commands")}
        if tank:
            entry["tank"] = {"ok": tank.get("ok"), "said": tank.get("said")}
            if tank.get("seconds") is not None:
                entry["tank"]["seconds"] = said(tank["seconds"], MEASURED, "the build's tank check, timed")
        problems = ((one.get("checks") or {}).get("vehicle") or {}).get("problems")
        if problems:
            entry["problems"] = problems
        if one.get("failure"):
            entry["failure"] = one["failure"]
        if one.get("stackId"):
            entry["stack"] = one["stackId"]
        built.append(entry)
    if built:
        out["controllers"] = built
    for key in ("failure", "said"):
        if made.get(key):
            out[key] = made[key][-1500:] if key == "said" else made[key]
    if any(one.get("stack") for one in built):
        out["next"] = "dives_start with one of these controllers flies it; controllers_build_again rebuilds them"
    return out


def controllers_build_status(platform: Platform, build: str) -> dict:
    """How a controller build is going."""
    return _controller_build_summary(platform.request("GET", f"/api/v1/controller-builds/{build}"))


def controllers_build_again(platform: Platform, build: str) -> dict:
    """Build the same source again: from a repository, its newest commit."""
    made = platform.request("POST", f"/api/v1/controller-builds/{build}/again")
    return {**_controller_build_summary(made), "note": "a new build of the same source; the old one is unchanged"}


def controllers_look(platform: Platform, url: str, ref: str = "", path: str = "") -> dict:
    """Which controllers a public GitHub repository holds."""
    from urllib.parse import urlencode
    query = {"url": url}
    if ref:
        query["ref"] = ref
    if path:
        query["path"] = path
    said_ = platform.request("GET", "/api/v1/controller-sources/look?" + urlencode(query))
    return {**said_, "note": "controllers_build with controllers=[slugs] builds those; without, every one listed"}
