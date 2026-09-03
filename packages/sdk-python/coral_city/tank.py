"""A tank on your own machine.

The runtime's own hydrodynamics and helm, stepped headless with nothing drawn,
as fast as the machine allows. A controller that holds station here holds it
on the platform, because it is the same integrator — the platform's tests run
this loop too.

Two uses. Run a controller and get a score:

    report = Tank("bluerov2", task=hold_station()).run(MyController())

Or step it yourself, the way a learner does:

    tank = Tank("bluerov2", task=waypoints([{"dx": 5, "dy": 0}]))
    seen = tank.reset()
    while not tank.done:
        seen, reward, done, info = tank.step(policy(seen))

`sensed=True` (the default) hands the controller what the vehicle's sensors
would give it — dead-reckoned position, depth from pressure — through the same
navigator the live node uses. `sensed=False` hands it the truth, which is a
kindness the sea will not extend.

Needs the runtime installed (`pip install coral-city[tank]`), or the repository
checked out beside this package.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from dataclasses import dataclass, field

import numpy as np

from .controller import Command, Controller, Observation
from .sensing import Navigator
from . import vehicles


def _runtime():
    """The runtime's modules, found where they are and put on the path."""
    here = pathlib.Path(__file__).resolve()
    candidates = []
    for up in here.parents:
        candidates.append(up / "services" / "sim-runtime" / "coral")
    env = os.environ.get("CORAL_CITY_RUNTIME")
    if env:
        candidates.insert(0, pathlib.Path(env))
    try:
        import coral  # the installed runtime package
        candidates.insert(0, pathlib.Path(coral.__file__).parent)
    except ImportError:
        pass
    for candidate in candidates:
        if (candidate / "runner.py").exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            import hydrodynamics
            import runner
            from controllers import Helm
            return hydrodynamics, runner, Helm
    raise ImportError("the tank needs the Coral City runtime: pip install 'coral-city[tank]', "
                      "or set CORAL_CITY_RUNTIME to services/sim-runtime/coral")


class _Bridge:
    """Stands where the ROS 2 bridge stands, so the helm sees the controller
    as a stack that is talking."""

    def __init__(self, thrusters: int) -> None:
        self._commands = np.zeros(thrusters)
        self.commanded = False
        self.commands_seen = 0
        self.declared: list[dict] = []

    def say(self, commands: np.ndarray) -> None:
        self._commands = np.clip(np.asarray(commands, dtype=float), -1.0, 1.0)
        self.commanded = True
        self.commands_seen += 1

    def commands(self) -> np.ndarray:
        return self._commands.copy()

    def parameters(self) -> list[dict]:
        return self.declared

    def set_parameter(self, name: str, value: float) -> bool:
        return False

    stack_node = "tank"


@dataclass
class Report:
    """How a run in the tank went."""

    score: float
    seconds: float
    task: dict
    final: dict
    trace: list[dict] = field(default_factory=list)
    events: list[tuple[str, dict]] = field(default_factory=list)

    def __str__(self) -> str:
        f = self.final
        return (f"score {self.score:.3f} over {self.seconds:.0f} s — ended at depth {f['depthM']:.2f} m, "
                f"heading {f['headingDeg']:.0f}°, {f['offStartM']:.2f} m from where it began")


class Tank:
    def __init__(self, vehicle: str = "bluerov2", start=(0.0, 0.0, -7.0), seconds: float = 60.0,
                 task: dict | None = None, sensed: bool = True, hz: float = 20.0) -> None:
        hydrodynamics, runner, Helm = _runtime()
        self.described = vehicles.load(vehicle)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(self.described.dynamics, handle)
            path = handle.name
        try:
            self.model = hydrodynamics.Hydrodynamics.from_package(path)
        finally:
            os.unlink(path)
        self.body = hydrodynamics.Body(self.model)
        self.allocator = hydrodynamics.Allocator(self.model)
        self.brief = {"durationSeconds": float(seconds), "initialState": {"positionM": list(start)}}
        self._Dive, self._Helm = runner.Dive, Helm
        self.task = task
        self.sensed = sensed
        self.hz = hz
        self.seconds = float(seconds)
        self.events: list[tuple[str, dict]] = []
        self.dive = None
        self.reset()

    # ── stepping it yourself ─────────────────────────────────────────────────

    def reset(self) -> Observation:
        self.events.clear()
        self.dive = self._Dive(self.brief, self.body, self.allocator, pathlib.Path("nowhere.usda"),
                               lambda kind, **d: self.events.append((kind, d)))
        self.bridge = _Bridge(len(self.model.thrusters))
        self.dive.helm = self._Helm(self.allocator, self.dive.dt, bridge=self.bridge)
        # The task is judged by the runtime's own code, from where the dive began.
        self.dive.begin_task(self.task)
        self._scored = 0.0
        self.navigator = Navigator(density=self.model.density)
        self.steps_per_tick = max(1, int(round(1.0 / (self.hz * self.dive.dt))))
        self.tick_dt = self.steps_per_tick * self.dive.dt
        self.started = False
        self.trace: list[dict] = []
        self.origin = np.array(self.brief["initialState"]["positionM"], dtype=float)
        return self.observe()

    @property
    def done(self) -> bool:
        return self.dive.done

    @property
    def t(self) -> float:
        return float(self.dive.simulated)

    def observe(self) -> Observation:
        truth = self.dive.observation()
        if not self.sensed:
            return Observation(t=truth.t, position=truth.position.copy(), velocity=truth.velocity.copy(),
                               rotation=truth.rotation.copy(), floor=truth.floor,
                               on_the_bottom=truth.on_the_bottom, estimated=False)
        # Through the sensors: pressure, attitude and rates, velocity over the ground.
        from .sensing import GRAVITY, SURFACE_PRESSURE_PA
        self.navigator.pressure(SURFACE_PRESSURE_PA + self.model.density * GRAVITY * truth.depth)
        self.navigator.imu(_quaternion(truth.rotation), truth.velocity[3:])
        self.navigator.dvl(truth.velocity[:3])
        seen = self.navigator.observation(truth.t)
        # The navigator starts its reckoning at zero; the tank knows where the
        # vehicle was put, as a real one knows where it was launched.
        seen.position[:2] += self.origin[:2]
        return seen

    def step(self, asked: Command | np.ndarray | None):
        """Apply a command for one tick. Returns (observation, reward, done, info)."""
        if isinstance(asked, Command):
            command = asked
        elif asked is None:
            command = Command.nothing()
        else:
            asked = np.asarray(asked, dtype=float)
            command = Command(wrench=asked) if asked.shape[0] == 6 and len(self.model.thrusters) != 6 \
                else Command(wrench=asked)
        if command.thrusters is not None:
            self.bridge.say(command.thrusters)
        else:
            wrench = np.zeros(6) if command.wrench is None else np.asarray(command.wrench, dtype=float)
            self.bridge.say(self.allocator.allocate(self.dive.helm.guard(wrench)))
        for _ in range(self.steps_per_tick):
            if self.dive.done:
                break
            self.dive.step()
        seen = self.observe()
        reward = 0.0
        if self.dive.task is not None:
            # The reward is the score earned this tick: dense where the task
            # is (time on station, ground covered), and zero where it is not.
            score = self.dive.task.score()
            reward = float(score - self._scored)
            self._scored = score
        self.trace.append({"t": round(seen.t, 3), "depthM": round(seen.depth, 4),
                           "headingDeg": round(float(np.degrees(seen.heading)), 2),
                           "x": round(float(seen.position[0]), 4), "y": round(float(seen.position[1]), 4),
                           "reward": round(reward, 4)})
        return seen, reward, self.dive.done, {"flying": self.dive.helm.flying.name}

    # ── running a controller ─────────────────────────────────────────────────

    def run(self, controller: Controller, seconds: float | None = None) -> Report:
        problems = self.described.check(type(controller))
        if problems:
            raise ValueError("this controller cannot fly this vehicle: " + "; ".join(problems))
        seen = self.reset()
        controller.engage(seen)
        until = self.seconds if seconds is None else float(seconds)
        while not self.done and self.t < until:
            seen, _, _, _ = self.step(controller.observe(seen))
        return self.report()

    def report(self) -> Report:
        truth = self.dive.observation()
        final = {"depthM": round(truth.depth, 3), "headingDeg": round(float(np.degrees(truth.heading)), 1),
                 "x": round(float(truth.position[0]), 3), "y": round(float(truth.position[1]), 3),
                 "offStartM": round(float(np.hypot(*(truth.position[:2] - self.origin[:2]))), 3)}
        task = self.dive.task
        score = task.score() if task is not None else float("nan")
        return Report(score=score, seconds=self.t, task=task.result() if task is not None else {},
                      final=final, trace=list(self.trace), events=list(self.events))


def _quaternion(rotation: np.ndarray) -> tuple[float, float, float, float]:
    m = rotation
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        s = (trace + 1.0) ** 0.5 * 2.0
        return (0.25 * s, float(m[2, 1] - m[1, 2]) / s, float(m[0, 2] - m[2, 0]) / s, float(m[1, 0] - m[0, 1]) / s)
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = (1.0 + m[0, 0] - m[1, 1] - m[2, 2]) ** 0.5 * 2.0
        return (float(m[2, 1] - m[1, 2]) / s, 0.25 * s, float(m[0, 1] + m[1, 0]) / s, float(m[0, 2] + m[2, 0]) / s)
    if m[1, 1] > m[2, 2]:
        s = (1.0 + m[1, 1] - m[0, 0] - m[2, 2]) ** 0.5 * 2.0
        return (float(m[0, 2] - m[2, 0]) / s, float(m[0, 1] + m[1, 0]) / s, 0.25 * s, float(m[1, 2] + m[2, 1]) / s)
    s = (1.0 + m[2, 2] - m[0, 0] - m[1, 1]) ** 0.5 * 2.0
    return (float(m[1, 0] - m[0, 1]) / s, float(m[0, 2] + m[2, 0]) / s, float(m[1, 2] + m[2, 1]) / s, 0.25 * s)
