"""What every task is, and the arithmetic they share.

A task is given the dive's objective — a small JSON document the dive was
defined with — and where the vehicle began, and is then told where the vehicle
is on every step. It keeps a score in [0, 1] as it goes, says how far along it
is for the console, and reduces itself to a result at the end: what was
achieved, how closely, how long it took, how much was asked of the thrusters.
A result rather than a pass mark.

Everything is relative to where the dive began unless the objective says
otherwise, because a task defined on a composer before the dive cannot know the
site's coordinates and should not have to: "hold here", "eight metres ahead
and back", "twenty metres along your heading". The exception is a task pointed
at something somebody drew, which knows exactly where it is.

The same code scores the SDK's tank, so a controller that scores well on a
laptop scores the same on the platform.
"""

from __future__ import annotations

import math

import numpy as np


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class Task:
    kind = "task"
    name = "Task"
    # What this task needs besides the objective, said by the task rather than
    # tested for by whoever builds it. "camera" for anything scored on what was
    # seen, "colonies" for anything scored on coral.
    wants: tuple[str, ...] = ()
    # Whether this asks the vehicle to stop. Most tasks do somewhere — arrive,
    # hold, work, dock — and a vehicle that cannot stop cannot be asked. A
    # glider is the reason the question exists: it does not hover badly, it
    # falls out of the water column, and a dive that lets it try is a dive
    # that has wasted somebody's day proving something arithmetic.
    needs_hover = True

    def __init__(self, objective: dict, began_at, heading: float,
                 world=None, **ignored) -> None:
        self.objective = objective
        self.began_at = np.array(began_at, dtype=float)
        self.began_heading = float(heading)
        # What somebody arranged this place with, and the one thing in it this
        # task was pointed at, if it was pointed at anything.
        #
        # This is what makes a drawn site worth drawing. Until now a task
        # carried its own geometry as offsets from wherever the vehicle
        # happened to start, because there was nowhere else for geometry to
        # live — so "survey the plot" meant "survey a sixty-metre box ahead of
        # you and hope somebody aimed the vehicle". Now the plot is a thing
        # with corners and the task can be pointed at it.
        self.world = world
        self.over = None
        self.missing = ""
        named = objective.get("over")
        if named:
            self.over = None if world is None else world.by_id(str(named))
            if self.over is None:
                # Said rather than ignored. A task pointed at something that is
                # not in the water is a task that would otherwise score against
                # nothing and read as a task that was simply done badly.
                self.missing = str(named)
        self.started_t: float | None = None
        self.t = 0.0
        self.effort = 0.0
        self.samples = 0
        self.done = False
        self.believed: np.ndarray | None = None

    # ── what every task shares ───────────────────────────────────────────────

    def step(self, t: float, position, heading: float, floor: float | None, commands,
             believed=None) -> None:
        if self.started_t is None:
            self.started_t = t
        self.t = t
        self.samples += 1
        self.effort += float(np.mean(np.abs(np.asarray(commands, dtype=float)))) if len(commands) else 0.0
        # Where the vehicle thinks it is, for the few tasks that need to know.
        # Kept on the task rather than added to every `judge` signature: a task
        # is scored against the truth and that is the rule, but a task that
        # models somebody *doing* something has to know when the vehicle
        # believed it had arrived, because that is when the work happens. The
        # gap between the two is then the finding rather than the error.
        self.believed = None if believed is None else np.asarray(believed, dtype=float)
        if not self.done:
            self.judge(t - self.started_t, np.asarray(position, dtype=float), float(heading), floor)

    def judge(self, elapsed: float, position: np.ndarray, heading: float, floor: float | None) -> None:
        raise NotImplementedError

    def score(self) -> float:
        return 0.0

    def says(self) -> str:
        return ""

    def detail(self) -> dict:
        return {}

    def geometry(self) -> dict:
        """What to draw on the chart: points, a line, a rectangle, in world xy."""
        return {}

    def goal(self) -> dict:
        """What this task wants, in the world's own coordinates. Not how.

        A task used to carry the route that solved it, and the runtime flew
        that route — so what was being measured was a line we had supplied,
        and no controller was compared to anything. What a task says now is
        the specification: cover this rectangle at this altitude, hold this
        station, come home to this dock. Working out a path that satisfies it
        is a controller's job, and the platform's own planner is one of those
        (controllers/plan.py) rather than a privilege of the task.

        Stated absolutely, never relative to where the vehicle happens to be,
        because that is what a plan is: the same document whether it was
        written by a person, emitted by a model, or worked out here.
        """
        return {}

    def goal_id(self) -> str:
        """Changes when the goal changes, so a controller can be told again."""
        return self.kind

    def failed(self) -> bool:
        """Whether this ended badly. Done and failed are different things."""
        return False

    def elapsed(self) -> float:
        return 0.0 if self.started_t is None else self.t - self.started_t

    def progress(self) -> dict:
        return {"kind": self.kind, "name": self.name, "score": round(self.score(), 3),
                "done": self.done, "says": self.says(), "elapsedS": round(self.elapsed(), 1),
                "detail": self.detail()}

    def result(self) -> dict:
        said = {"kind": self.kind, "name": self.name, "score": round(self.score(), 3),
                "done": self.done, "failed": self.failed(), "seconds": round(self.elapsed(), 1),
                "thrusterEffort": round(self.effort / max(1, self.samples), 3),
                "achieved": self.detail()}
        # Pointed at something: which thing, so a result can be read against
        # the arrangement it was flown in rather than against a bare score.
        if self.over is not None:
            said["over"] = {"id": self.over.id, "kind": self.over.kind,
                            "is": self.over.spec.what}
        if self.missing:
            said["pointedAtNothing"] = self.missing
        return said

    def describe(self) -> dict:
        return {"kind": self.kind, "name": self.name, "objective": self.objective,
                "geometry": self.geometry()}

    # ── helpers ──────────────────────────────────────────────────────────────

    def ahead(self) -> tuple[float, float]:
        heading = self.objective.get("headingDeg")
        angle = self.began_heading if heading is None else math.radians(float(heading))
        return math.cos(angle), math.sin(angle)

    def start_depth(self) -> float:
        return float(-self.began_at[2])

    def out_from_start(self, dx: float, dy: float, depth=None) -> np.ndarray:
        """A point the objective gave as ahead-and-to-starboard of the start."""
        ahead = self.ahead()
        right = (ahead[1], -ahead[0])
        z = -float(depth) if depth is not None else float(self.began_at[2])
        return np.array([self.began_at[0] + dx * ahead[0] + dy * right[0],
                         self.began_at[1] + dx * ahead[1] + dy * right[1], z])

    def somewhere(self, said, fallback=None) -> np.ndarray | None:
        """A place named either by the world or by the start.

        `{"x": .., "y": .., "depthM": ..}` is a point in the place — where a
        thing planted in the place is. `{"dx": .., "dy": ..}` is relative to
        where this dive began, which is what a composer can say before the
        dive exists. `{"over": "cell-b7"}` is the middle of something somebody
        drew, which is what a person means when they point at a chart.
        """
        # `[x, y, z]` is the same point written the way the rest of the record
        # writes positions. Taken rather than ignored: a target written as a
        # list used to fall through to the fallback, which flew a different
        # dive and said nothing about it.
        if isinstance(said, (list, tuple)) and len(said) == 3:
            return np.asarray(said, dtype=float)
        if not isinstance(said, dict):
            return None if fallback is None else np.asarray(fallback, dtype=float)
        if said.get("over") is not None:
            thing = None if self.world is None else self.world.by_id(str(said["over"]))
            if thing is None:
                self.missing = str(said["over"])
                return None if fallback is None else np.asarray(fallback, dtype=float)
            middle = self.middle_of(thing)
            depth = said.get("depthM")
            if depth is not None:
                middle = np.array([middle[0], middle[1], -float(depth)])
            return middle
        if said.get("x") is not None and said.get("y") is not None:
            depth = said.get("depthM")
            z = -float(depth) if depth is not None else float(self.began_at[2])
            return np.array([float(said["x"]), float(said["y"]), z])
        if said.get("dx") is not None or said.get("dy") is not None:
            return self.out_from_start(float(said.get("dx", 0.0)), float(said.get("dy", 0.0)),
                                       said.get("depthM"))
        return None if fallback is None else np.asarray(fallback, dtype=float)

    @staticmethod
    def middle_of(thing) -> np.ndarray:
        """Where a drawn thing is, whatever shape it is.

        A thing standing at a point is at that point; a line is at the middle
        of its run; a plot is at the middle of its outline. A task pointed at
        one should not have to know which of the three it got.
        """
        corners = getattr(thing, "corners", None)
        if corners:
            xs = [float(c[0]) for c in corners]
            ys = [float(c[1]) for c in corners]
            deep = float(getattr(thing, "said", {}).get("groundM") or 0.0)
            return np.array([(min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, -deep])
        curve = getattr(thing, "curve", None)
        if curve is not None and len(curve):
            return np.asarray(curve[len(curve) // 2], dtype=float)
        return np.asarray(getattr(thing, "at", (0.0, 0.0, 0.0)), dtype=float)

    @staticmethod
    def box_of(thing):
        """The rectangle a drawn plot bounds, or nothing if it is not a plot.

        Answers the middle, how far it runs east, and how far it runs north.
        Axis-aligned because that is what the editor draws and what a lane plan
        can actually fly; a plot at an angle is a later problem and pretending
        otherwise here would score a survey against a box nobody drew.
        """
        corners = getattr(thing, "corners", None)
        if not corners:
            return None
        xs = [float(c[0]) for c in corners]
        ys = [float(c[1]) for c in corners]
        return (np.array([(min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0]),
                max(xs) - min(xs), max(ys) - min(ys))


def footprint_half_angle(camera: dict | None) -> float | None:
    """Half the camera's horizontal field of view, in radians, or None.

    From the catalogue's field of view where it states one, else from the
    focal length as a 36 mm-equivalent — which is what a focal length on its
    own means to anybody reading it.
    """
    if not camera:
        return None
    fov = camera.get("horizontalFovDeg")
    if fov:
        return math.radians(float(fov)) / 2.0
    focal = camera.get("focalLengthMm")
    if focal:
        return math.atan(18.0 / float(focal))
    return None
