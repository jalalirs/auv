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
                pictures: bool = False) -> dict:
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
    """
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
            "objective": {**objective, "pictures": bool(pictures)},
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
    runtime = os.environ.get("CORAL_CITY_RUNTIME_VERSION", RUNTIME)
    run = platform.request("POST", f"/api/v1/dives/{dive['id']}/runs", {
        "queueId": queues[0]["id"], "mode": "batch",
        "runtimeVersion": runtime})

    return {
        "dive": dive["id"], "run": run["id"], "state": run.get("state"),
        "place": found.get("name"), "vehicle": machine.get("name"),
        "water": water, "drawn": bool(pictures), "runtime": runtime,
        "note": ("queued. dives_result says how it went; a drawn dive runs at "
                 "about a sixth of real time and an undrawn one at fifteen "
                 "times it, on the same trajectory"),
    }


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


# ── what the camera saw ──────────────────────────────────────────────────────

def _cached(run_id: str, name: str, url: str) -> pathlib.Path:
    """A run's file, fetched once. Recordings are immutable: a run that has
    ended never changes, so asking for six frames of one dive should download
    its video once and not six times."""
    import tempfile
    import urllib.request

    where = pathlib.Path(tempfile.gettempdir()) / "coral-city-mcp" / run_id
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
            "runtimeVersion": os.environ.get("CORAL_CITY_RUNTIME_VERSION", RUNTIME),
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
