"""iocean over MCP, on stdio.

Speaks the protocol directly rather than through a framework. There is not much
of it — initialize, tools/list, tools/call — and a dependency that has to be
installed before a customer's assistant can reach the platform is a dependency
between us and the sale.

    IOCEAN_PLATFORM=http://... IOCEAN_EMAIL=... IOCEAN_SECRET=... \
        python -m coral_city_mcp

Credentials come from the environment and never from a tool argument: an agent
that can be told a password in a prompt is an agent that can be told somebody
else's.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

from .platform import Platform, Refused
from . import tools

VERSION = "2024-11-05"

# name -> (what it does, what it takes, the function)
TOOLS: dict[str, tuple[str, dict, Callable[..., Any]]] = {
    "places_list": (
        "Every place this session has been granted, with its name and summary.",
        {"type": "object", "properties": {}},
        tools.places_list),
    "places_get": (
        "One place in full: what its ground came from, how deep it is, how deep "
        "that depth is actually calibrated to, its reef and its water. Every "
        "number comes back marked measured, derived, chosen or assumed.",
        {"type": "object",
         "properties": {"place": {"type": "string",
                                  "description": "the place's id or slug"}},
         "required": ["place"]},
        lambda p, place: tools.places_get(p, place)),
    "vehicles_list": (
        "Every vehicle, and whether it can actually fly. Read `flyable`: a "
        "package with dynamics and no hull cannot be put in the water however "
        "complete it looks.",
        {"type": "object", "properties": {}},
        tools.vehicles_list),
    "controllers_list": (
        "The autonomy deployed to this institution.",
        {"type": "object", "properties": {}},
        tools.controllers_list),
    "layouts_list": (
        "Every arrangement of a place: where transponders, moorings, plots and "
        "lines have been laid out on it.",
        {"type": "object",
         "properties": {"place": {"type": "string", "description": "id or slug"}},
         "required": ["place"]},
        lambda p, place: tools.layouts_list(p, place)),
    "layouts_create": (
        "Start your own arrangement of a place. Anybody who can look at a "
        "place can have their own scenarios over it; you can only change the "
        "ones you made.",
        {"type": "object",
         "properties": {"place": {"type": "string"}, "name": {"type": "string"},
                        "slug": {"type": "string"}},
         "required": ["place", "name"]},
        lambda p, place, name, slug="": tools.layouts_create(p, place, name, slug)),
    "layouts_get": (
        "What is in the water, as one arrangement says: every thing, its kind "
        "and where it is in site metres.",
        {"type": "object", "properties": {"layout": {"type": "string"}},
         "required": ["layout"]},
        lambda p, layout: tools.layouts_get(p, layout)),
    "layouts_add_line": (
        "Put a row of marks along a line, evenly spaced, and save it as a new "
        "version. Coordinates are [x, y] in site metres: origin at the middle "
        "of the site, +x east, +y north. Returns the arrangement, NOT a "
        "picture — ask layouts_chart to look at it. Depth is the place's "
        "business: a transponder lands on the ground, a buoy floats.",
        {"type": "object",
         "properties": {
             "layout": {"type": "string"},
             "start": {"type": "array", "items": {"type": "number"},
                       "description": "[x, y] in site metres"},
             "end": {"type": "array", "items": {"type": "number"},
                     "description": "[x, y] in site metres"},
             "spacing_m": {"type": "number"},
             "kind": {"type": "string",
                      "description": "transponder, buoy, block, post, ship",
                      "default": "transponder"},
             "name": {"type": "string"}},
         "required": ["layout", "start", "end", "spacing_m"]},
        lambda p, layout, start, end, spacing_m, kind="transponder", name="":
            tools.layouts_add_line(p, layout, start, end, spacing_m, kind, name)),
    "layouts_chart": (
        "A plan view of the place with the arrangement drawn on it, as a PNG. "
        "North up, shaded by depth from the place's own heightfield, with a "
        "scale bar. Cheap: no scene, no camera, no GPU. It answers where "
        "things are, and cannot answer what they look like — a camera view is "
        "a separate operation.",
        {"type": "object", "properties": {"layout": {"type": "string"}},
         "required": ["layout"]},
        lambda p, layout: tools.layouts_chart(p, layout)),
    "dives_list": (
        "Dives this institution has defined, newest first.",
        {"type": "object",
         "properties": {"limit": {"type": "integer", "default": 20}}},
        lambda p, limit=20: tools.dives_list(p, limit)),
    "dives_start": (
        "Put a dive in the water. THIS SPENDS TIME ON A MACHINE — everything "
        "else here only reads. A dive names a place, a vehicle, the sea it was "
        "flown in and what it is for; the sea is required, because a dive whose "
        "water nobody stated cannot be compared with another. `pictures` "
        "renders every frame: a drawn dive runs at about a sixth of real time "
        "and an undrawn one at fifteen times it on the same trajectory, so ask "
        "for pictures only when somebody is going to look.",
        {"type": "object",
         "properties": {
             "place": {"type": "string"},
             "vehicle": {"type": "string",
                         "description": "must have a hull; see vehicles_list"},
             "objective": {"type": "object",
                           "description": "what it is for, e.g. "
                                          "{\"kind\": \"hold-station\", \"seconds\": 120}. It may also say "
                                          "when the dive is — \"day\": {\"localTimeH\": 20, \"dayLengthS\": 300} "
                                          "(fish keep that day; a tank's lights follow it) — and, for a "
                                          "vehicle with no thrusters such as edgetech-2300, the tow that flies "
                                          "it: \"tow\": {\"speedKn\": 4, \"headingDeg\": 90, \"cableOutM\": 300, "
                                          "\"frequencykHz\": 120}"},
             "water": {"type": "string",
                       "enum": ["still", "gentle", "half-knot", "one-knot",
                                "tank-still", "fan-low", "fan-high", "pump", "fan-and-pump"],
                       "description": "the sea; in a tank, the fan blows across the surface and the pump makes a current",
                       "default": "still"},
             "pictures": {"type": "boolean", "default": False},
             "views": {"type": "array", "items": {"type": "string"},
                       "description": "cycle the camera through these, e.g. "
                                      "[\"room\", \"chase\", \"front\", \"overhead\"]; "
                                      "places_get lists a place's own views"},
             "view_every_s": {"type": "number", "default": 4.0,
                              "description": "seconds of dive on each view"},
             "name": {"type": "string"}},
         "required": ["place", "vehicle", "objective"]},
        lambda p, place, vehicle, objective, water="still", pictures=False,
               name="", controller="", views=None, view_every_s=4.0:
            tools.dives_start(p, place, vehicle, objective, water, controller,
                              name, pictures, views, view_every_s)),
    "dives_film": (
        "The path-traced film of a run already flown — one watched live, or "
        "flown by a controller, or flown undrawn for its numbers. THIS SPENDS "
        "TIME ON A MACHINE. The run is flown again from the commands it "
        "recorded, on its seed: the same dive, tick for tick, with pictures. "
        "Only a run that succeeded and kept its commands (flown on or after "
        "4 October 2026) can be filmed.",
        {"type": "object",
         "properties": {"dive": {"type": "string"},
                        "run": {"type": "string",
                                "description": "the run to film; the dive's latest when left out"},
                        "views": {"type": "array", "items": {"type": "string"}},
                        "view_every_s": {"type": "number", "default": 6.0},
                        "film": {"type": "object",
                                 "description": "{fps, width, height, spp, bitrate}; 24 fps 1280x720 16 spp when left out"}},
         "required": ["dive"]},
        lambda p, dive, run=None, views=None, view_every_s=6.0, film=None:
            tools.dives_film(p, dive, run, views, view_every_s, film)),
    "dives_frame": (
        "What the camera saw at a moment of a dive, as an image — and from "
        "where: the position, heading and camera it was seen from come back "
        "beside the picture, because a picture an agent cannot place is one it "
        "will describe as though it knew. Only a dive flown with pictures=true "
        "has frames.",
        {"type": "object",
         "properties": {"dive": {"type": "string"},
                        "at_seconds": {"type": "number",
                                       "description": "seconds into the dive"},
                        "run": {"type": "string"}},
         "required": ["dive", "at_seconds"]},
        lambda p, dive, at_seconds, run=None: tools.dives_frame(p, dive, at_seconds, run)),
    "missions_list": (
        "A place's plans of work. A sweep flies a mission, not a place.",
        {"type": "object", "properties": {"place": {"type": "string"}},
         "required": ["place"]},
        lambda p, place: tools.missions_list(p, place)),
    "sweeps_run": (
        "Fly one mission against every combination of the doubts named, each "
        "several times. THIS SPENDS A LOT: scenarios x repeats dives. Doubts "
        "are named by the app's own catalogue, e.g. "
        "{\"current\": [\"still\", \"one knot\"], "
        "\"the mooring\": [\"as drawn\", \"thirty metres off\"]}. "
        "Dimensions: current, fix, water clarity, trouble, the array, "
        "the mooring, how long.",
        {"type": "object",
         "properties": {"mission": {"type": "string"},
                        "vehicle": {"type": "string"},
                        "doubts": {"type": "object"},
                        "repeats": {"type": "integer", "default": 2},
                        "name": {"type": "string"}},
         "required": ["mission", "vehicle", "doubts"]},
        lambda p, mission, vehicle, doubts, repeats=2, name="":
            tools.sweeps_run(p, mission, vehicle, doubts, repeats, name)),
    "sweeps_findings": (
        "What breaks the mission and the one change that saves the most of it, "
        "ranked by how much each doubt changes the outcome. Readable before "
        "the sweep finishes.",
        {"type": "object", "properties": {"sweep": {"type": "string"}},
         "required": ["sweep"]},
        lambda p, sweep: tools.sweeps_findings(p, sweep)),
    "dives_result": (
        "What a run scored. A run that did not finish comes back as unknown "
        "rather than as a score of zero.",
        {"type": "object",
         "properties": {"dive": {"type": "string"}, "run": {"type": "string"}},
         "required": ["dive"]},
        lambda p, dive, run=None: tools.dives_result(p, dive, run)),
    "dives_deliverables": (
        "The geometry a run produced, with the files' contents inline: "
        "track.geojson (where it was AND where it believed it was, as separate "
        "features), coverage.geojson (what was actually seen), planting.geojson, "
        "and provenance.json (what each of those numbers is). Read the contents, "
        "not the links — the links point inside the platform's network.",
        {"type": "object",
         "properties": {"dive": {"type": "string"}, "run": {"type": "string"}},
         "required": ["dive"]},
        lambda p, dive, run=None: tools.dives_deliverables(p, dive, run)),
}


def answer(said: dict, result: Any = None, error: dict | None = None) -> dict:
    out: dict[str, Any] = {"jsonrpc": "2.0", "id": said.get("id")}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    return out


def handle(said: dict, platform: Platform | None,
           no_session: Refused | None = None) -> dict | None:
    method = said.get("method")

    if method == "initialize":
        return answer(said, {
            "protocolVersion": VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "coral-city", "version": "0.1.0"},
            "instructions": (
                "iocean: underwater vehicles, real reefs, and dives whose "
                "every number says who measured it. Values arrive as "
                "{value, kind, from} where kind is measured, derived, chosen or "
                "assumed. Report the kind with the number — a derived figure "
                "stated as a measurement is wrong even when the figure is right."),
        })

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "tools/list":
        return answer(said, {"tools": [
            {"name": name, "description": about, "inputSchema": schema}
            for name, (about, schema, _) in TOOLS.items()]})

    if method == "tools/call":
        asked = said.get("params") or {}
        name = asked.get("name")
        if name not in TOOLS:
            return answer(said, error={"code": -32601,
                                       "message": f"no tool called {name!r}"})
        if platform is None:
            # Why there is no session, not a recital of what to set.
            #
            # This said "set IOCEAN_PLATFORM and either IOCEAN_TOKEN or
            # IOCEAN_EMAIL/SECRET" whatever had happened — including when
            # all three were set and the platform had rejected them, which
            # tells an agent to do the thing it already did. The same failure
            # as a vehicle line reading "0 to choose from".
            return answer(said, {"isError": True, "content": [{
                "type": "text",
                "text": json.dumps({"refused": no_session.code,
                                    "why": no_session.message}, indent=1)}]}
                          ) if no_session is not None else answer(said, {
                "isError": True, "content": [{
                    "type": "text",
                    "text": "not signed in: set IOCEAN_PLATFORM and either "
                            "IOCEAN_TOKEN or IOCEAN_EMAIL/SECRET"}]})
        _, _, run = TOOLS[name]
        try:
            got = run(platform, **(asked.get("arguments") or {}))
        except Refused as no:
            # A refusal is the platform working. It comes back as content
            # rather than a protocol error so the agent reads the reason and
            # asks for something else, instead of treating it as a crash.
            return answer(said, {"isError": True, "content": [{
                "type": "text",
                "text": json.dumps({"refused": no.code, "why": no.message},
                                   indent=1)}]})
        except Exception as problem:
            return answer(said, {"isError": True, "content": [{
                "type": "text", "text": f"{type(problem).__name__}: {problem}"}]})
        # An image comes back as an image. MCP carries pictures, and a chart
        # handed over as a base64 string inside a JSON blob is a chart nothing
        # will look at.
        content: list[dict] = []
        if isinstance(got, dict) and "image" in got:
            picture = got.pop("image")
            content.append({"type": "image", "data": picture,
                            "mimeType": "image/png"})
        content.append({"type": "text",
                        "text": json.dumps(got, indent=1, ensure_ascii=False)})
        return answer(said, {"content": content})

    return answer(said, error={"code": -32601, "message": f"no method {method!r}"})


def main() -> int:
    if "--http" in sys.argv:
        at = sys.argv[sys.argv.index("--http") + 1]
        host, _, port = at.rpartition(":")
        serve_http(host or "0.0.0.0", int(port))
        return 0
    no_session: Refused | None = None
    try:
        platform: Platform | None = Platform.from_environment()
    except Refused as why:
        # Serve anyway: an agent listing the tools should see what is here even
        # when nobody has configured a session yet, and be told plainly on the
        # first call rather than watching the server fail to start. The reason
        # is kept, because "not configured" and "the platform rejected those
        # credentials" are different problems with different fixes.
        platform, no_session = None, why

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            said = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(said, platform, no_session)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


# ── over HTTP, for an agent that is not on this machine ──────────────────────
#
# MCP's streamable HTTP transport, the part of it a tool server needs: one
# endpoint, a JSON-RPC message posted to it, the answer in the response. No
# event stream, because nothing here pushes — every tool answers when asked.
#
# The server holds no credential. Each caller sends its own — `Service
# <principal>:<secret>` or `Bearer <session>` — and it is forwarded to the
# platform untouched, so every agent acts as the principal it was issued as and
# the platform's grants decide what it may do. A shared credential baked into a
# server reachable from the whole tailnet would make every agent the same agent,
# and the audit log would say so.

def _platform_for(header: str | None) -> tuple[Platform | None, Refused | None]:
    base = os.environ.get("IOCEAN_PLATFORM", "http://control-plane:8080")
    if not header:
        return None, Refused(401, "unauthenticated",
                             "send your own credential: make a token in the Coral "
                             "City application under Profile → Tokens for your "
                             "assistant, and send it as Authorization: Bearer cc_…")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() == "service" and credential:
        return Platform(base, service=credential), None
    if scheme.lower() == "bearer" and credential:
        return Platform(base, token=credential), None
    return None, Refused(401, "unauthenticated",
                         "Authorization must be `Service <principal>:<secret>` "
                         "or `Bearer <session>`")


def serve_http(host: str, port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class One(BaseHTTPRequestHandler):
        def _send(self, status: int, body: object | None) -> None:
            raw = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            if body is not None:
                self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"ok": True, "tools": len(TOOLS)})
                return
            # Nothing is pushed, so there is no stream to open.
            self._send(405, {"error": "POST a JSON-RPC message to /mcp"})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/mcp":
                self._send(404, {"error": "the endpoint is /mcp"})
                return
            length = int(self.headers.get("content-length") or 0)
            try:
                said = json.loads(self.rfile.read(length) or b"null")
            except json.JSONDecodeError:
                self._send(400, {"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32700, "message": "not JSON"}})
                return
            platform, why = _platform_for(self.headers.get("authorization"))
            batch = said if isinstance(said, list) else [said]
            replies = [r for r in (handle(one, platform, why) for one in batch
                                   if isinstance(one, dict)) if r is not None]
            if not replies:
                self._send(202, None)       # notifications only
            elif isinstance(said, list):
                self._send(200, replies)
            else:
                self._send(200, replies[0])

        def log_message(self, *_):        # one line per call, not per header
            pass

    print(f"coral-city MCP on http://{host}:{port}/mcp, {len(TOOLS)} tools",
          flush=True)
    ThreadingHTTPServer((host, port), One).serve_forever()
