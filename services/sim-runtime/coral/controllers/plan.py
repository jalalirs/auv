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
