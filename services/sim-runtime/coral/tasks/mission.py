"""A dive made of several tasks, and a task this place cannot judge."""

from __future__ import annotations


import numpy as np

from .base import Task


class Mission(Task):
    """Several things, in order, as one dive.

    A dive stopped being one objective here. Each stage is a task in its own
    right, scored on its own terms and reported on its own line; the mission is
    over when the last one finishes or when one of them fails, because a
    mission that carries on after a failed dock is a mission pretending.
    """

    kind = "mission"
    name = "Mission"

    def __init__(self, objective, began_at, heading, make, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.make = make
        self.stages: list[Task] = []
        for stage in objective.get("stages", []):
            made = make(stage, began_at, heading)
            if made is not None:
                self.stages.append(made)
        self.at = 0
        self.finished: list[dict] = []
        self.stopped_early = False

    @property
    def stage(self) -> Task | None:
        return self.stages[self.at] if self.at < len(self.stages) else None

    def step(self, t, position, heading, floor, commands, believed=None) -> None:
        # The mission's own clock runs; the stage's clock starts when it does.
        if self.started_t is None:
            self.started_t = t
        self.t = t
        self.samples += 1
        self.effort += float(np.mean(np.abs(np.asarray(commands, dtype=float)))) if len(commands) else 0.0
        stage = self.stage
        if stage is None or self.done:
            self.done = True
            return
        # Handed down rather than dropped: a stage that models somebody doing
        # something needs to know when the vehicle *believed* it had arrived,
        # and a mission is only a way of running stages.
        stage.step(t, position, heading, floor, commands, believed=believed)
        if stage.done:
            self.finished.append(stage.result())
            if stage.failed() and stage.stops_a_mission:
                self.stopped_early = True
                self.done = True
                return
            self.at += 1
            if self.stage is None:
                self.done = True

    def judge(self, elapsed, position, heading, floor) -> None:      # pragma: no cover
        pass

    def score(self) -> float:
        scores = [one["score"] for one in self.finished]
        stage = self.stage
        if stage is not None and not self.done:
            scores.append(stage.score())
        if not self.stages:
            return 0.0
        # Stages never reached count as nothing, which is what they are.
        return float(sum(scores) / len(self.stages))

    def says(self) -> str:
        stage = self.stage
        where = f"{min(self.at + 1, len(self.stages))} of {len(self.stages)}"
        if stage is None:
            return f"all {len(self.stages)} stages done"
        return f"stage {where}: {stage.name} — {stage.says()}"

    def detail(self) -> dict:
        stage = self.stage
        return {"stage": self.at, "of": len(self.stages),
                "stageName": None if stage is None else stage.name,
                "stopped": self.stopped_early,
                "stages": self.finished + ([stage.progress()] if stage is not None else [])}

    def geometry(self) -> dict:
        stage = self.stage
        return {} if stage is None else stage.geometry()

    def goal(self) -> dict:
        stage = self.stage
        return {} if stage is None else stage.goal()

    def goal_id(self) -> str:
        return f"mission:{self.at}"

    def describe(self) -> dict:
        said = super().describe()
        said["stages"] = [{"kind": s.kind, "name": s.name} for s in self.stages]
        return said

    def failed(self) -> bool:
        return self.stopped_early or any(one.get("failed") for one in self.finished)


class Unavailable(Task):
    """A task the platform knows of and cannot yet judge here."""

    kind = "inspect"
    name = "Inspect"

    def __init__(self, objective, began_at, heading, why: str, **extra) -> None:
        super().__init__(objective, began_at, heading, **extra)
        self.why = why
        self.done = True

    def judge(self, elapsed, position, heading, floor) -> None:
        pass

    def says(self) -> str:
        return self.why

    def detail(self) -> dict:
        return {"unavailable": self.why}
