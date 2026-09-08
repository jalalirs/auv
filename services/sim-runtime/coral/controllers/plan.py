"""Working out how to do what was asked. The platform's own planner.

A task says what it wants: cover this rectangle two metres up, hold this
station, come home to this dock. It does not say how, and until now it did —
every task carried the route that solved it, the runtime flew that route, and
what came out the other end was a measurement of a line we had supplied. No
controller was being compared to anything, and over thirty metres of water the
way a vehicle navigates could not show.

So the arithmetic that turns a goal into a path lives here, in a controller,
where somebody else's can stand beside it. It is deliberately plain — mow a
rectangle in lanes a swath apart, approach a dock down its own heading, circle
a thing while facing it — and being plain is the point: it is the floor a
written controller has to beat, and the reason a task can be flown at all by
somebody who has not written one.

Two things it does not do, deliberately. It does not look at the world: a plan
is made once from the goal, in the world's own coordinates, the way a mission
is loaded into a vehicle at the dock. And it never sees the truth — where the
vehicle actually is only matters to the follower, which is given what the
vehicle believes, like everything else.
"""

from __future__ import annotations

import math

import numpy as np

# What a plan document says it is, so that a file found on its own can be
# recognised, and so that the shape can change later without silence.
DESCRIBED_BY = "coral.city/plan/1"

# The manoeuvres this vehicle can fly. Named after IMC's, because that is the
# vocabulary the tooling in this field already speaks.
KINDS = ("goto", "follow-path", "station-keeping")


def plan_for(goal: dict, believed=None, camera_half_angle: float | None = None,
             named: str = "") -> dict:
    """A plan document for a goal: what this planner decided, written down.

    The document is the artefact, not the route. It is what a person could
    write by hand, what a model will be asked to emit, what is kept with the
    run so that a dive can be read a year later, and what two controllers can
    be compared through. Its shape is borrowed rather than invented — a graph
    of manoeuvres with parameters and a transition to the next, which is what
    an IMC plan is and what Neptus has flown for years.
    """
    legs = route_for(goal, believed=believed, camera_half_angle=camera_half_angle)
    kind = str(goal.get("kind", ""))
    manoeuvres: list[dict] = []
    if kind in ("cover", "work") and len(legs) > 1:
        # Lanes are one manoeuvre, not thirty: a survey is a path to follow,
        # and writing it out as thirty separate points would lose the fact
        # that they are one thing done at one altitude.
        manoeuvres.append({
            "id": "m1", "kind": "follow-path",
            "points": [{"x": leg["x"], "y": leg["y"]} for leg in legs],
            "altitudeM": legs[0].get("altitudeM"),
        })
    elif kind == "hold":
        at = goal.get("at") or [0.0, 0.0, 0.0]
        manoeuvres.append({
            "id": "m1", "kind": "station-keeping",
            "at": {"x": float(at[0]), "y": float(at[1]), "depthM": float(-at[2])},
            "radiusM": goal.get("radiusM"),
        })
    else:
        for i, leg in enumerate(legs, start=1):
            manoeuvre = {"id": f"m{i}", "kind": "goto",
                         "at": {"x": leg["x"], "y": leg["y"]}}
            for key in ("depthM", "altitudeM"):
                if leg.get(key) is not None:
                    manoeuvre["at"][key] = leg[key]
            for key in ("arriveM", "speedMs", "easeM", "holdS", "facing"):
                if leg.get(key) is not None:
                    manoeuvre[key] = leg[key]
            manoeuvres.append(manoeuvre)
    for one, following in zip(manoeuvres, manoeuvres[1:]):
        one["next"] = following["id"]
    return {
        "describedBy": DESCRIBED_BY,
        "plan": named or (kind or "plan"),
        "for": goal,
        "start": manoeuvres[0]["id"] if manoeuvres else None,
        "manoeuvres": manoeuvres,
    }


def legs_of(document: dict) -> list[dict]:
    """Compile a plan document into the legs a follower flies.

    Following the transitions rather than the order they were written in: a
    plan is a graph, and a document whose manoeuvres are listed out of order
    is still the same plan.
    """
    by_id = {str(m.get("id")): m for m in document.get("manoeuvres", [])}
    at = document.get("start") or (document.get("manoeuvres") or [{}])[0].get("id")
    legs: list[dict] = []
    seen: set[str] = set()
    while at is not None and str(at) in by_id and str(at) not in seen:
        seen.add(str(at))
        manoeuvre = by_id[str(at)]
        legs.extend(_legs_of_one(manoeuvre))
        at = manoeuvre.get("next")
    return legs


def _legs_of_one(manoeuvre: dict) -> list[dict]:
    kind = str(manoeuvre.get("kind", "goto"))
    if kind == "follow-path":
        common = {k: manoeuvre[k] for k in ("altitudeM", "depthM", "speedMs", "facing", "arriveM")
                  if manoeuvre.get(k) is not None}
        return [{"x": float(p["x"]), "y": float(p["y"]), **common}
                for p in manoeuvre.get("points", [])]
    if kind == "station-keeping":
        # Nothing to fly to: staying is what it asks for, and the follower
        # holds wherever it runs out of route.
        return []
    at = manoeuvre.get("at") or {}
    leg = {"x": float(at.get("x", 0.0)), "y": float(at.get("y", 0.0))}
    for key in ("depthM", "altitudeM"):
        if at.get(key) is not None:
            leg[key] = float(at[key])
    for key in ("arriveM", "speedMs", "easeM", "holdS"):
        if manoeuvre.get(key) is not None:
            leg[key] = float(manoeuvre[key])
    if manoeuvre.get("facing") is not None:
        leg["facing"] = manoeuvre["facing"]
    return [leg]


def what_is_wrong(document: dict) -> list[str]:
    """Everything wrong with a plan document, in sentences. Empty means fly it.

    Checked before a dive rather than discovered during one: a plan that names
    a manoeuvre which does not exist is a vehicle that stops in the water
    halfway through a mission for no reason a person could see.
    """
    wrong: list[str] = []
    manoeuvres = document.get("manoeuvres")
    if not isinstance(manoeuvres, list) or not manoeuvres:
        return ["the plan has no manoeuvres"]
    ids: set[str] = set()
    for i, manoeuvre in enumerate(manoeuvres):
        if not isinstance(manoeuvre, dict):
            wrong.append(f"manoeuvre {i + 1} is not a manoeuvre")
            continue
        name = str(manoeuvre.get("id", ""))
        if not name:
            wrong.append(f"manoeuvre {i + 1} has no id")
        elif name in ids:
            wrong.append(f"two manoeuvres are called {name}")
        ids.add(name)
        kind = str(manoeuvre.get("kind", ""))
        if kind not in KINDS:
            wrong.append(f"{name or i + 1} is a {kind or 'nameless'} manoeuvre, "
                         f"which this vehicle cannot fly")
        if kind == "follow-path" and not manoeuvre.get("points"):
            wrong.append(f"{name} is a path with no points")
        if kind in ("goto", "station-keeping") and not isinstance(manoeuvre.get("at"), dict):
            wrong.append(f"{name} does not say where")
    for manoeuvre in manoeuvres:
        if isinstance(manoeuvre, dict) and manoeuvre.get("next") is not None \
                and str(manoeuvre["next"]) not in ids:
            wrong.append(f"{manoeuvre.get('id')} hands over to {manoeuvre['next']}, "
                         f"which is not in this plan")
    start = document.get("start")
    if start is not None and str(start) not in ids:
        wrong.append(f"the plan starts at {start}, which is not in it")
    return wrong


def route_for(goal: dict, believed=None, camera_half_angle: float | None = None) -> list[dict]:
    """The path this planner would fly to satisfy a goal.

    `believed` is where the vehicle thinks it is, used only by the goals that
    are about where it already is. `camera_half_angle` is what the vehicle can
    see, in radians, which decides how far apart the lanes of a survey go —
    a fact about the vehicle rather than about the task, which is why the task
    does not state it.
    """
    kind = str(goal.get("kind", ""))
    if kind == "visit":
        return _visit(goal)
    if kind == "line":
        return _line(goal)
    if kind == "go":
        return _go(goal)
    if kind == "cover":
        return _cover(goal, camera_half_angle)
    if kind == "work":
        return _work(goal, camera_half_angle)
    if kind == "circle":
        return _circle(goal)
    if kind == "dock":
        return _dock(goal)
    # "hold", "wait", and anything this planner does not recognise: stay where
    # you are. A controller that does not know what it was asked should not
    # invent a direction to go in.
    return []


# ── the goals, one at a time ─────────────────────────────────────────────────

def _visit(goal: dict) -> list[dict]:
    """Points in the order given. A hold at each, when the goal asks for one."""
    hold = goal.get("holdS")
    arrive = goal.get("radiusM")
    route = []
    for p in goal.get("points", []):
        leg = {"x": float(p[0]), "y": float(p[1]), "depthM": float(-p[2])}
        if arrive is not None:
            leg["arriveM"] = max(0.25, float(arrive) * 0.6)
        if hold is not None:
            # A second more than asked: a sample taken to the last tenth is a
            # sample that fails on the clock.
            leg["holdS"] = float(hold) + 1.0
        route.append(leg)
    return route


def _line(goal: dict) -> list[dict]:
    """A straight run, flown at an altitude rather than a depth."""
    to = goal["to"]
    leg = {"x": float(to[0]), "y": float(to[1])}
    if goal.get("altitudeM") is not None:
        leg["altitudeM"] = float(goal["altitudeM"])
    elif goal.get("depthM") is not None:
        leg["depthM"] = float(goal["depthM"])
    return [leg]


def _go(goal: dict) -> list[dict]:
    """One place, and stop there."""
    to = goal["to"]
    leg = {"x": float(to[0]), "y": float(to[1])}
    if goal.get("depthM") is not None:
        leg["depthM"] = float(goal["depthM"])
    elif len(to) > 2:
        leg["depthM"] = float(-to[2])
    if goal.get("radiusM") is not None:
        leg["arriveM"] = max(0.3, float(goal["radiusM"]) * 0.5)
    return leg and [leg] or []


def _cover(goal: dict, half_angle: float | None) -> list[dict]:
    """Up and down a rectangle, the way a survey is actually flown.

    The lanes are a swath apart, and the swath is what the camera will see on
    the bottom from the altitude asked for — so the ground between lanes is
    covered rather than hoped over. A little overlap, because a vehicle that
    holds altitude to the centimetre is not one that exists.
    """
    altitude = float(goal.get("altitudeM", 2.0))
    if half_angle is not None:
        swath = 2.0 * max(0.25, altitude * math.tan(half_angle))
    else:
        swath = float(goal.get("swathM", 3.0))
    swath += float(goal.get("seeM", 0.0))          # a search sees wider than it photographs
    return _lawnmower(goal, max(1.0, swath * 0.85), altitude)


def _work(goal: dict, half_angle: float | None) -> list[dict]:
    """A patch of colonies, worked through in lanes as wide as the arm reaches."""
    centre = np.asarray(goal["centre"], dtype=float)
    radius = float(goal.get("radiusM", 5.0))
    along = np.asarray(goal.get("along", [1.0, 0.0]), dtype=float)
    across = np.array([along[1], -along[0]])
    corner = centre[:2] - along * radius - across * radius
    lanes = {"corner": [float(corner[0]), float(corner[1])],
             "along": [float(along[0]), float(along[1])],
             "widthM": 2.0 * radius, "heightM": 2.0 * radius}
    return _lawnmower(lanes, max(1.0, float(goal.get("reachM", 1.0)) * 1.6),
                      float(goal.get("altitudeM", 1.5)))


def _circle(goal: dict) -> list[dict]:
    """Round a thing, facing it the whole way.

    An inspection that looks where it is going has its back to what it came to
    see, which is how a lap of a structure returns one side of it.
    """
    at = np.asarray(goal["at"], dtype=float)
    radius = float(goal.get("radiusM", 3.0))
    sectors = int(goal.get("sectors", 12))
    looking = {"x": float(at[0]), "y": float(at[1])}
    route = []
    for sector in range(sectors * 2 + 1):
        angle = math.pi * sector / sectors
        route.append({"x": float(at[0] + radius * math.cos(angle)),
                      "y": float(at[1] + radius * math.sin(angle)),
                      "depthM": float(-at[2]),
                      "facing": looking, "arriveM": max(0.4, radius * 0.2)})
    return route


def _dock(goal: dict) -> list[dict]:
    """The gate first, on the station's own heading, then straight in.

    A vehicle that arrives from the side arrives across the cradle. The last
    leg is slower than the station will accept, because arriving fast is a
    miss even when the position is right.
    """
    station = np.asarray(goal["station"], dtype=float)
    facing = math.radians(float(goal.get("facingDeg", 0.0)))
    approach = float(goal.get("approachM", 6.0))
    tolerance = float(goal.get("toleranceM", 0.4))
    speed_limit = float(goal.get("speedLimitMs", 0.25))
    into = np.array([math.cos(facing), math.sin(facing)])
    gate = station[:2] - into * approach
    return [
        {"x": float(gate[0]), "y": float(gate[1]), "depthM": float(-station[2]),
         "arriveM": max(0.5, approach * 0.15)},
        {"x": float(station[0]), "y": float(station[1]), "depthM": float(-station[2]),
         "arriveM": max(0.08, tolerance * 0.5),
         "speedMs": max(0.05, speed_limit * 0.5),
         "easeM": max(1.0, approach * 0.6)},
    ]


def _lawnmower(area: dict, swath: float, altitude: float) -> list[dict]:
    """Lanes across a rectangle stated in the world's own coordinates.

    The rectangle is a near corner, a direction along it, and two lengths —
    which is all a plan needs to say, and says nothing about which way the
    vehicle happened to be pointing when the dive began.
    """
    corner = np.asarray(area["corner"], dtype=float)[:2]
    along = np.asarray(area.get("along", [1.0, 0.0]), dtype=float)[:2]
    across = np.array([along[1], -along[0]])
    width = float(area["widthM"])
    height = float(area["heightM"])
    legs = max(1, int(math.ceil(height / max(0.5, swath))))
    route = []
    for leg in range(legs + 1):
        out = min(height, leg * swath)
        ends = [0.0, width] if leg % 2 == 0 else [width, 0.0]
        for on in ends:
            point = corner + along * on + across * out
            route.append({"x": float(point[0]), "y": float(point[1]), "altitudeM": altitude})
    return route
