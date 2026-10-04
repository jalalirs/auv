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
    env = os.environ.get("IOCEAN_RUNTIME")
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
    raise ImportError("the tank needs the iocean runtime: pip install 'coral-city[tank]', "
                      "or set IOCEAN_RUNTIME to services/sim-runtime/coral")


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
        said = (f"score {self.score:.3f} over {self.seconds:.0f} s — ended at depth "
                f"{f['depthM']:.2f} m, heading {f['headingDeg']:.0f}°, "
                f"{f['offStartM']:.2f} m from where it began")
        # And what it believed, when that is a different story — which on a vehicle
        # with no bottom to lock to, in a current, it always is.
        drifted = f.get("believedOffStartM")
        if drifted is not None and abs(drifted - f["offStartM"]) > 0.5:
            said += f" (it believed {drifted:.2f} m)"
        return said


class Tank:
    def __init__(self, vehicle: str = "bluerov2", start=(0.0, 0.0, -7.0), seconds: float = 60.0,
                 task: dict | None = None, sensed: bool = True, hz: float = 20.0,
                 current: tuple[float, float] | None = None, latency_ticks: int = 0,
                 things: list[dict] | None = None) -> None:
        """`current` is (metres per second, heading in degrees the water flows
        towards, from north clockwise); None is still water. `latency_ticks`
        delays every command by that many ticks, as the live loop does — a
        policy that only holds with no delay will not hold on the platform.

        `things` puts obstacles in the water, each `{"kind":, "x":, "y":,
        "groundM":}` and optionally its own `radiusM` and `heightM` — a
        `nursery-frame`, a `mooring-block`, a `marker-post`. Without them a
        controller that avoids things has nothing to avoid, and a tank run says it
        avoided nothing, which is true and useless.
        """
        self.latency_ticks = int(latency_ticks)
        hydrodynamics, runner, Helm = _runtime()
        self.described = vehicles.load(vehicle)
        # The vehicle's package, kept as a directory for as long as the tank is.
        #
        # It used to be a temp file, read once and deleted — which meant the dive
        # had no `vehiclePath`, so `switch_on_the_sonar` and its siblings found no
        # package to read and **fitted no sensors at all**. A tank that fits none
        # cannot try the one kind of controller that most needs trying before it is
        # deployed: `coral-city tank` on a sonar controller reported it avoiding
        # nothing, in an empty sea, with no sonar, and nothing said so.
        import shutil
        import weakref

        kept = pathlib.Path(tempfile.mkdtemp(prefix="coral-city-tank-"))
        (kept / "dynamics.json").write_text(json.dumps(self.described.dynamics))
        weakref.finalize(self, shutil.rmtree, str(kept), True)
        self.vehicle_path = kept
        self.model = hydrodynamics.Hydrodynamics.from_package(kept / "dynamics.json")
        self.body = hydrodynamics.Body(self.model)
        self.allocator = hydrodynamics.Allocator(self.model)
        self.brief = {"durationSeconds": float(seconds),
                      "initialState": {"positionM": list(start)},
                      # So the dive fits what the vehicle declares it carries.
                      # A sonar costs about three times as much per step as a bare
                      # hull, which is the honest price of the vehicle being the
                      # vehicle: a controller that reads no sonar pays it and does
                      # not notice, and one that does could not be tried without it.
                      "vehiclePath": str(kept)}
        if things:
            # Something to run into. A tank with nothing in it cannot try a
            # controller whose whole job is not hitting things.
            self.brief["layout"] = {"things": list(things)}
        if current is not None:
            self.brief["conditions"] = {"kind": "constructed", "parameters": {
                "currentMetresPerSecond": float(current[0]), "currentHeadingDeg": float(current[1])}}
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
        self._pending: list = []
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
            # The dive's own observation is what the *vehicle believes*, not
            # what is true: that is the whole point of it, and it is what a
            # controller is handed on a real dive. So `sensed=False` cannot use
            # it — it took the believed position, called it the truth, and
            # handed a controller an estimate while telling it otherwise.
            #
            # In still water the two are the same and nothing showed. In a
            # current they are not: the vehicle is carried and its reckoning is
            # not, so the example hold sat there holding a position it was
            # eight metres away from, scoring perfectly against its own
            # estimate and failing the task. The test that caught it had been
            # failing for a long time and the suite had not been run.
            return Observation(t=truth.t,
                               position=self.dive.position.copy(),
                               velocity=self.dive.velocity.copy(),
                               rotation=self.dive.rotation.copy(),
                               floor=truth.floor,
                               on_the_bottom=truth.on_the_bottom,
                               # The sonar is not navigation: it is what the
                               # vehicle can see, and it is the same whether the
                               # position handed over is the truth or an estimate.
                               # Dropping it here meant a controller that avoids
                               # things could not be tried in the tank at all.
                               seen=truth.seen, sonar=truth.sonar,
                               estimated=False)
        # Through the sensors: pressure, attitude and rates, velocity over the ground.
        from .sensing import GRAVITY, SURFACE_PRESSURE_PA
        self.navigator.pressure(SURFACE_PRESSURE_PA + self.model.density * GRAVITY * truth.depth)
        self.navigator.imu(_quaternion(truth.rotation), truth.velocity[3:])
        self.navigator.dvl(truth.velocity[:3])
        if truth.floor is not None:
            # The Doppler log's range, through the log's own bounds, so the tank
            # loses bottom lock exactly where a vehicle would. The bounds come from
            # the dive's own navigation rather than from the vehicle, because that
            # is where the runtime keeps them — a log's reach belongs to the fit,
            # not to the hull.
            near, far = (0.05, 50.0)
            if getattr(self.dive, "navigation", None) is not None:
                near, far = self.dive.navigation.dvl_range
            self.navigator.bottom(float(truth.position[2]) - float(truth.floor),
                                  float(near), float(far))
        if truth.sonar is not None:
            # No `or []` anywhere near these: the runtime's fan holds numpy arrays,
            # and `array or []` raises "the truth value of an array with more than
            # one element is ambiguous" — which is how five tank tests went red.
            bearings = truth.sonar.get("bearingsRad")
            ranges = truth.sonar.get("rangesM")
            if bearings is not None and ranges is not None:
                self.navigator.sonar_fan(bearings, ranges)
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
            # A bare array is a wrench. It was two identical branches with a
            # condition between them — somebody's note to themselves about the
            # third command form, left in the first file an outside developer
            # reads and never finished.
            command = Command(wrench=np.asarray(asked, dtype=float))
        # Through a delay line when asked, so the vehicle acts on what the
        # controller said a few ticks ago, as it does live.
        self._pending.append(command)
        while len(self._pending) > self.latency_ticks + 1:
            self._pending.pop(0)
        acted = self._pending[0] if len(self._pending) > self.latency_ticks else Command.nothing()
        if acted.actuators is not None:
            # A vehicle that is not moved by thrust: the pump and the sliding
            # mass get a step towards what was asked for, and the water does
            # the rest. There is no wrench here and no thruster to allocate.
            self.dive.body.model.ask_actuators(acted.actuators, self.dive.dt)
            if len(self.model.thrusters):
                self.bridge.say(np.zeros(len(self.model.thrusters)))
        elif acted.thrusters is not None:
            self.bridge.say(acted.thrusters)
        elif len(self.model.thrusters) == 0:
            # Nothing to allocate to. A hull with no thrusters that is handed a
            # wrench is being flown by a controller written for another vehicle,
            # and saying so is better than quietly doing nothing.
            raise ValueError(
                "this vehicle has no thrusters: command its actuators instead, "
                "with Command.actuators_of(...). `coral-city vehicles` says which.")
        else:
            wrench = np.zeros(6) if acted.wrench is None else np.asarray(acted.wrench, dtype=float)
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
        # Only the instruments this controller reads.
        #
        # The vehicle carries a forward-looking sonar and that costs about four
        # times the rest of a step to ray-march — a 30-second rollout goes from
        # 1.16 s to 5.01 s — so a trainer flying three thousand of them pays hours
        # for a fan nobody looks at. What it does **not** touch is anything that
        # changes the vehicle: the tether still drags, because a tank without one
        # is easier than the platform and that is the mistake this just came out of.
        self.brief["fitSensors"] = sorted(set(type(controller).needs or ()))
        seen = self.reset()
        # What the dive is for, before it is engaged — the same order the platform
        # delivers it in, so a controller that reads the goal behaves the same here.
        controller.tasked(self.task or {})
        controller.engage(seen)
        until = self.seconds if seconds is None else float(seconds)
        while not self.done and self.t < until:
            seen, _, _, _ = self.step(controller.observe(seen))
        return self.report()

    def report(self) -> Report:
        # Where it is, and where it thinks it is, and they are not the same number.
        #
        # This called `dive.observation()` "truth" and it is not: with navigation
        # configured it hands back the vehicle's **belief**. The tank has no seabed,
        # so a Doppler log has no bottom to lock to and the reckoning integrates
        # through-water velocity — which in a current walks off at the current's own
        # speed. So a hold that truly sat 0.06 m from where it began was reported as
        # "11.68 m from where it began", and that sentence is the first thing anybody
        # reads after `coral-city tank`. It made a correct fix look like a broken one.
        believed = self.dive.observation()
        truly = self.dive.position
        final = {"depthM": round(float(-truly[2]), 3),
                 "headingDeg": round(float(np.degrees(believed.heading)), 1),
                 "x": round(float(truly[0]), 3), "y": round(float(truly[1]), 3),
                 "offStartM": round(float(np.hypot(*(truly[:2] - self.origin[:2]))), 3),
                 # What the vehicle would say, which is all a real one can tell you.
                 "believedOffStartM": round(
                     float(np.hypot(*(believed.position[:2] - self.origin[:2]))), 3)}
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
