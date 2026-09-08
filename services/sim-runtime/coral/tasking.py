"""Turning what somebody said into a plan the vehicle can fly.

This is the layer that has to be last. A sentence is worth nothing until there
is a plan format to turn it into, a planner that knows what the vehicle can
do, and a way of flying a document that somebody else wrote — and once those
exist, this is a small thing rather than a large one.

Where it happens matters. It happens at the dock, or at the surface, over a
link with bandwidth: the acoustic channel a vehicle has underwater is
JANUS-shaped, a few hundred bits a second with seconds of latency and losses,
and sending prose down it is not physics. What goes down is the compiled plan,
or a short code that selects one already aboard.

Two readers, one interface. The built-in one understands the vocabulary this
platform actually has — surveys, transects, stations, docks, colonies — and
runs anywhere with nothing configured. The other asks a model, and is used
when one is configured; what it returns is checked against the same rules as
any other plan before anything is flown, because a plan from a model is a plan
from a stranger.

Either way the reading is reported back with the plan: what it understood, in
its own words, and what it could not. A person who cannot see what the machine
heard cannot tell a good plan from a lucky one.
"""

from __future__ import annotations

import math
import os
import re

from controllers import plan as planning

# What the built-in reader understands. Not a natural language — the vocabulary
# of this vehicle's actual work, which is what a person asking for a dive
# writes anyway.
VERBS = {
    "survey": ("cover", ("survey", "cover", "mow", "map")),
    "search": ("cover", ("search", "find", "look for", "hunt")),
    "transect": ("line", ("transect", "straight line", "fly a line")),
    "go": ("go", ("go", "run", "head", "transit", "reach", "travel")),
    "hold": ("hold", ("hold", "stay", "station", "sit", "keep station")),
    "home": ("go", ("come home", "return", "go home", "come back")),
    "dock": ("dock", ("dock", "come alongside", "onto the station")),
    "inspect": ("circle", ("inspect", "circle", "look at", "orbit")),
    "treat": ("work", ("treat", "work through", "dose")),
}

BEARINGS = {"north": 0.0, "south": 180.0, "east": 90.0, "west": 270.0,
            "northeast": 45.0, "northwest": 315.0, "southeast": 135.0, "southwest": 225.0}


def understand(said: str, at, heading: float = 0.0,
               camera_half_angle: float | None = None) -> dict:
    """What somebody asked for, as a plan, with the reading that produced it.

    Answers a dict of `plan`, `read` — sentences saying what was understood —
    and `missed`, which is everything in the sentence that meant nothing here.
    Never raises on nonsense: a reader that guesses when it did not understand
    is worse than one that says so.
    """
    asked = " ".join(str(said or "").split())
    if not asked:
        return {"plan": None, "read": [], "missed": ["nothing was asked for"]}

    by_model = _ask_a_model(asked, at, heading)
    if by_model is not None:
        return by_model

    read, missed, goals = [], [], []
    for clause in _clauses(asked):
        goal, saying = _goal_of(clause, at, heading)
        if goal is None:
            missed.append(clause)
        else:
            goals.append(goal)
            read.append(saying)
    if not goals:
        return {"plan": None, "read": [], "missed": missed or [asked],
                "why": "nothing in that is something this vehicle can do"}
    documents = [planning.plan_for(goal, believed=at, camera_half_angle=camera_half_angle)
                 for goal in goals]
    return {"plan": _joined(documents, asked), "read": read, "missed": missed}


# ── reading a sentence ───────────────────────────────────────────────────────

def _clauses(asked: str) -> list[str]:
    """One instruction at a time. "then" is how people join them."""
    parts = re.split(r"\bthen\b|\band then\b|;|\.\s+", asked, flags=re.I)
    return [p.strip(" ,.") for p in parts if p and p.strip(" ,.")]


def _numbers(clause: str) -> list[float]:
    return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", clause)]


def _dimensions(clause: str) -> tuple[float, float] | None:
    """"sixty by thirty", "60 x 30" — an area, in that order."""
    found = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|metres?|meters?)?\s*(?:by|x|×)\s*"
                      r"(\d+(?:\.\d+)?)", clause, flags=re.I)
    return (float(found.group(1)), float(found.group(2))) if found else None


def _after(clause: str, *words: str) -> float | None:
    """The number that follows one of these words, if any."""
    for word in words:
        found = re.search(word + r"\D{0,12}?(\d+(?:\.\d+)?)", clause, flags=re.I)
        if found:
            return float(found.group(1))
    return None


def _altitude(clause: str) -> float | None:
    found = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|metres?|meters?)?\s*(?:up|above|off the bottom|"
                      r"altitude)", clause, flags=re.I)
    if found:
        return float(found.group(1))
    return _after(clause, r"at an altitude of", r"altitude of", r"altitude")


def _minutes(clause: str) -> float | None:
    found = re.search(r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|seconds?|secs?)", clause, flags=re.I)
    if not found:
        return None
    said = float(found.group(1))
    return said * 60.0 if found.group(2).lower().startswith(("min", "m")) else said


def _bearing(clause: str, heading: float) -> float:
    """Which way, in radians of our world, where north is x and 90 is east."""
    for word, degrees in BEARINGS.items():
        if re.search(rf"\b{word}\b", clause, flags=re.I):
            return math.radians(degrees)
    found = re.search(r"\bon\s+(\d{1,3})\b|\bbearing\s+(\d{1,3})\b", clause, flags=re.I)
    if found:
        return math.radians(float(found.group(1) or found.group(2)))
    if re.search(r"\bback\b|\bastern\b|\bbehind\b", clause, flags=re.I):
        return heading + math.pi
    return heading                                        # "ahead", and by default


def _verb(clause: str) -> tuple[str, str] | None:
    for name, (kind, words) in VERBS.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", clause, flags=re.I):
                return name, kind
    return None


def _goal_of(clause: str, at, heading: float):
    """One clause, as a goal in the world's own coordinates."""
    found = _verb(clause)
    if found is None:
        return None, ""
    name, kind = found
    x, y, z = float(at[0]), float(at[1]), float(at[2])
    towards = _bearing(clause, heading)
    ahead = (math.cos(towards), math.sin(towards))
    far = _numbers(clause)

    if name in ("survey", "search"):
        wide, tall = _dimensions(clause) or (60.0, 30.0)
        up = _altitude(clause) or 5.0
        goal = {"kind": "cover", "corner": [x, y], "along": list(ahead),
                "widthM": wide, "heightM": tall, "altitudeM": up}
        if name == "search":
            goal["seeM"] = _after(clause, r"see|seeing|sight") or 8.0
        return goal, (f"{name} a {wide:g} by {tall:g} metre area "
                      f"{_which_way(towards)}, {up:g} m above the bottom")

    if name == "transect":
        length = _after(clause, r"for|of") or (far[0] if far else 200.0)
        up = _altitude(clause) or 3.0
        end = [x + ahead[0] * length, y + ahead[1] * length]
        return ({"kind": "line", "from": [x, y], "to": end, "altitudeM": up},
                f"fly {length:g} m {_which_way(towards)}, {up:g} m above the bottom")

    if name == "go":
        length = far[0] if far else 100.0
        to = [x + ahead[0] * length, y + ahead[1] * length]
        goal = {"kind": "go", "to": to, "radiusM": 3.0, "depthM": -z}
        return goal, f"go {length:g} m {_which_way(towards)}"

    if name == "home":
        deep = 0.5 if re.search(r"surface", clause, flags=re.I) else -z
        length = far[0] if far else 0.0
        to = [x - ahead[0] * length, y - ahead[1] * length] if length else [x, y]
        return ({"kind": "go", "to": to, "depthM": deep, "radiusM": 3.0},
                "come home" + (" and surface" if deep <= 1.0 else ""))

    if name == "hold":
        seconds = _minutes(clause) or 300.0
        return ({"kind": "hold", "at": [x, y, z], "radiusM": 0.5, "seconds": seconds},
                f"hold station here for {seconds / 60:g} minutes")

    if name == "dock":
        length = far[0] if far else 80.0
        station = [x + ahead[0] * length, y + ahead[1] * length, z]
        return ({"kind": "dock", "station": station, "facingDeg": math.degrees(towards),
                 "approachM": 8.0, "toleranceM": 0.4, "speedLimitMs": 0.25},
                f"dock at the station {length:g} m {_which_way(towards)}")

    if name == "inspect":
        length = far[0] if far else 60.0
        radius = _after(clause, r"at|from|within") or 6.0
        target = [x + ahead[0] * length, y + ahead[1] * length, z]
        return ({"kind": "circle", "at": target, "radiusM": radius, "sectors": 12},
                f"circle the mark {length:g} m {_which_way(towards)} at {radius:g} m")

    if name == "treat":
        radius = _after(clause, r"within|inside|radius of") or (far[0] if far else 15.0)
        return ({"kind": "work", "centre": [x, y, z], "along": list(ahead),
                 "radiusM": radius, "reachM": 1.5, "altitudeM": 1.5},
                f"work through the colonies within {radius:g} m")
    return None, ""


def _which_way(towards: float) -> str:
    degrees = math.degrees(towards) % 360.0
    for word, at in BEARINGS.items():
        if abs((degrees - at + 180) % 360 - 180) < 22.5:
            return word
    return f"on {degrees:.0f}"


def _joined(documents: list[dict], asked: str) -> dict:
    """Several plans, one after another, as one document.

    Ids are made unique and the last manoeuvre of each hands over to the first
    of the next — which is all "then" means.
    """
    manoeuvres: list[dict] = []
    for at, document in enumerate(documents, start=1):
        by_id = {}
        for manoeuvre in document.get("manoeuvres", []):
            renamed = dict(manoeuvre)
            renamed["id"] = f"s{at}{manoeuvre['id']}"
            by_id[manoeuvre["id"]] = renamed["id"]
            manoeuvres.append(renamed)
        for manoeuvre in manoeuvres:
            if manoeuvre.get("next") in by_id:
                manoeuvre["next"] = by_id[manoeuvre["next"]]
    for one, following in zip(manoeuvres, manoeuvres[1:]):
        one["next"] = following["id"]
    if manoeuvres:
        manoeuvres[-1].pop("next", None)
    return {"describedBy": planning.DESCRIBED_BY, "plan": asked[:80],
            "by": "read from what was asked", "start": manoeuvres[0]["id"] if manoeuvres else None,
            "manoeuvres": manoeuvres}


# ── the other reader ─────────────────────────────────────────────────────────

def _ask_a_model(asked: str, at, heading: float):
    """Ask a model for a plan, when one is configured. Otherwise nothing.

    Deliberately the same interface as the reader above and deliberately not
    trusted more: whatever comes back is checked against the same rules before
    it is flown, and a plan that fails them is dropped rather than repaired,
    because a plan nobody can read is worse than no plan.

    Configured with CORAL_CITY_MODEL_URL and CORAL_CITY_MODEL_KEY. Untested
    against a live model — there is no key on this platform yet — so it is
    written to fail quietly back to the reader that always works.
    """
    url, key = os.environ.get("CORAL_CITY_MODEL_URL"), os.environ.get("CORAL_CITY_MODEL_KEY")
    if not url or not key:
        return None
    import json
    import urllib.request

    told = (
        "You are planning one dive for an underwater vehicle. Answer with JSON only: "
        f'{{"plan": "a short name", "start": "m1", "manoeuvres": [...]}}. '
        f'A manoeuvre is {{"id", "kind", "next"}} where kind is one of {planning.KINDS}. '
        'A "goto" has {"at": {"x", "y", "depthM" or "altitudeM"}, "arriveM"}. '
        'A "follow-path" has {"points": [{"x","y"}], "altitudeM"}. '
        'A "station-keeping" has {"at": {...}, "radiusM"}. '
        f"The vehicle is at x={at[0]:.1f}, y={at[1]:.1f}, depth {-at[2]:.1f} m, "
        f"heading {math.degrees(heading):.0f} degrees, where x is north and y is east. "
        "Metres throughout. Say nothing but the JSON."
    )
    body = json.dumps({"model": os.environ.get("CORAL_CITY_MODEL", "claude-sonnet-5"),
                       "max_tokens": 2000,
                       "system": told,
                       "messages": [{"role": "user", "content": asked}]}).encode()
    ask = urllib.request.Request(url, data=body, headers={
        "content-type": "application/json", "x-api-key": key,
        "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(ask, timeout=60) as answered:
            said = json.loads(answered.read())
        text = said.get("content", [{}])[0].get("text") or said.get("completion") or ""
        document = json.loads(re.search(r"\{.*\}", text, flags=re.S).group(0))
    except Exception as trouble:
        return {"plan": None, "read": [], "missed": [asked],
                "why": f"the model did not answer with a plan: {str(trouble)[:120]}"}
    document.setdefault("describedBy", planning.DESCRIBED_BY)
    document["by"] = f"a model: {os.environ.get('CORAL_CITY_MODEL', 'unnamed')}"
    wrong = planning.what_is_wrong(document)
    if wrong:
        return {"plan": None, "read": [], "missed": [asked],
                "why": "the model's plan cannot be flown: " + "; ".join(wrong[:3])}
    return {"plan": document, "read": [f"a model read this as {document.get('plan')}"],
            "missed": []}
