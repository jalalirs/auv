"""What a dive is for, evaluated as it runs.

A module per family rather than one file of seventeen hundred lines, because
the families barely touch: everything here is a `Task` and nothing here knows
about any other task. What they are grouped by is what the score means —

  `going`      getting somewhere and staying there: a position and a tolerance
  `covering`   covering ground or water: a fraction of something
  `working`    doing something to something: a count of things
  `mission`    several of the above in sequence

This module is the only thing outside the package anyone imports: the names,
the table from a kind to a class, and the one function that turns an objective
into the task it asks for.
"""

from __future__ import annotations

from .base import Task, footprint_half_angle, wrap
from .covering import Profile, Search, Section, Survey
from .going import Dock, HoldStation, Reach, Return, Transect, Waypoints, Wait
from .mission import Mission, Unavailable
from .working import Inspect, Monitor, Outplant, Revisit, Treat

TASKS = {
    "hold-station": HoldStation, "waypoints": Waypoints, "transect": Transect,
    "reach": Reach, "return": Return, "dock": Dock, "wait": Wait,
    "survey": Survey, "search": Search, "profile": Profile, "section": Section,
    "treat": Treat, "outplant": Outplant, "monitor": Monitor,
    "inspect": Inspect, "revisit": Revisit,
}
KINDS = tuple(TASKS) + ("mission",)

__all__ = ["KINDS", "TASKS", "Task", "footprint_half_angle", "task_for", "wrap",
           "Dock", "HoldStation", "Inspect", "Mission", "Monitor", "Outplant",
           "Profile", "Reach", "Return", "Revisit", "Search", "Section",
           "Survey", "Transect", "Treat", "Unavailable", "Wait", "Waypoints"]


def task_for(objective, began_at, heading: float, camera: dict | None = None,
             colonies=None, world=None) -> Task | None:
    """The task an objective asks for, or None when the dive is only flown.

    `camera` and `colonies` are handed to the tasks that say they want them —
    said by each class rather than tested for here, because a chain of `if made
    is Survey` is a chain somebody adding the eighteenth task has to find and
    add to.

    `world` is what somebody arranged this place with, for a task pointed at
    something drawn. A task given no world can still be flown; a task pointed
    at a thing in a world it was not given says so in its score rather than
    quietly scoring against nothing.
    """
    if not isinstance(objective, dict) or not objective:
        return None
    kind = str(objective.get("kind", ""))
    if kind == "mission":
        def stage(said, began, heading_):
            return task_for(said, began, heading_, camera=camera,
                            colonies=colonies, world=world)
        return Mission(objective, began_at, heading, stage)
    made = TASKS.get(kind)
    if made is None:
        return None
    spare = {"camera": camera, "colonies": colonies}
    return made(objective, began_at, heading, world=world,
                **{name: spare[name] for name in made.wants})
