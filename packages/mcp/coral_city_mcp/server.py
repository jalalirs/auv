"""Coral City over MCP, on stdio.

Speaks the protocol directly rather than through a framework. There is not much
of it — initialize, tools/list, tools/call — and a dependency that has to be
installed before a customer's assistant can reach the platform is a dependency
between us and the sale.

    CORAL_CITY_PLATFORM=http://... CORAL_CITY_EMAIL=... CORAL_CITY_SECRET=... \
        python -m coral_city_mcp

Credentials come from the environment and never from a tool argument: an agent
that can be told a password in a prompt is an agent that can be told somebody
else's.
"""

from __future__ import annotations

import json
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
    "dives_list": (
        "Dives this institution has defined, newest first.",
        {"type": "object",
         "properties": {"limit": {"type": "integer", "default": 20}}},
        lambda p, limit=20: tools.dives_list(p, limit)),
    "dives_result": (
        "What a run scored. A run that did not finish comes back as unknown "
        "rather than as a score of zero.",
        {"type": "object",
         "properties": {"dive": {"type": "string"}, "run": {"type": "string"}},
         "required": ["dive"]},
        lambda p, dive, run=None: tools.dives_result(p, dive, run)),
    "dives_deliverables": (
        "The geometry a run produced: track.geojson (where it was AND where it "
        "believed it was, as separate features), coverage.geojson (what was "
        "actually seen), planting.geojson, and provenance.json.",
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
                "Coral City: underwater vehicles, real reefs, and dives whose "
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
            # This said "set CORAL_CITY_PLATFORM and either CORAL_CITY_TOKEN or
            # CORAL_CITY_EMAIL/SECRET" whatever had happened — including when
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
                    "text": "not signed in: set CORAL_CITY_PLATFORM and either "
                            "CORAL_CITY_TOKEN or CORAL_CITY_EMAIL/SECRET"}]})
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
        except Exception as problem:                      # noqa: BLE001
            return answer(said, {"isError": True, "content": [{
                "type": "text", "text": f"{type(problem).__name__}: {problem}"}]})
        return answer(said, {"content": [
            {"type": "text", "text": json.dumps(got, indent=1, ensure_ascii=False)}]})

    return answer(said, error={"code": -32601, "message": f"no method {method!r}"})


def main() -> int:
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
