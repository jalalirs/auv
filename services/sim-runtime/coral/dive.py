"""Run one dive, headless.

The agent hands over a brief — which place, which vehicle, what water, what
seed — and this loads the place, puts the vehicle in it, integrates the
hydrodynamics, and reports what happened.

The dive itself is in runner.py, because the client runs the same one and two
implementations of the same physics would eventually disagree. What is here is
only the part that is particular to nobody watching: run as fast as the machine
allows, report to stdout, exit with a status.

Determinism is the property everything else rests on, so it is arranged here
rather than hoped for: a fixed timestep, every generator seeded from the seed
the run pinned, and no dependence on wall-clock time anywhere in the loop. Two
runs of the same brief produce the same trajectory, which is what makes a replay
a replay and a regression real rather than noise.
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import sys

RENDER_HZ = 60.0

# How often a dive with nothing to record pumps the app anyway, in steps.
EVERY_SO_OFTEN = 2000


def read_brief() -> dict:
    """What the agent asked for."""
    path = os.environ.get("CORAL_CITY_BRIEF", "/dive/dive.json")
    return json.loads(pathlib.Path(path).read_text())


def say(kind: str, **detail) -> None:
    """Report an event.

    Written to stdout as one JSON object per line rather than posted to the
    control plane: the agent is already reading this process's output, it
    already holds the run's lease, and a simulator that had to authenticate
    would be a simulator that could be locked out of reporting its own results.
    """
    # Spaced separators so that the agent, which reads this output to know when
    # the vehicle is publishing, can look for a stable marker rather than a
    # shape json.dumps might render differently.
    print(json.dumps({"event": kind, **detail}, separators=(", ", ": ")), flush=True)


def say_what_computed_this(say) -> None:
    """Declare the physics: written beside the brief, and said aloud.

    Both, because they are for two different readers. The file is for the
    agent, which has to put it on the run record: a file is there whether or
    not anything was watching, whatever a log driver is doing, and however much
    Isaac Sim said on the way up. The event is for a person reading the record
    afterwards.

    Said here, in `prepare`, because there are two ways into a dive and this is
    where they meet. A dive that renders — anything with a task, and anything
    somebody is watching — is started as a Kit application and never runs
    `main` at all, so a declaration made there was made on the one path that
    almost nothing takes. Both paths prepare, and both prepare before they open
    anything: a run that fails while loading a scene is exactly the run
    somebody is trying to compare against a working one, and it still says what
    it would have been computed by.
    """
    from runner import PHYSICS, PHYSICS_IS

    say("physics", version=PHYSICS, is_=PHYSICS_IS)
    try:
        beside = pathlib.Path(os.environ.get("CORAL_CITY_BRIEF", "/dive/dive.json")).parent
        (beside / "computed.json").write_text(json.dumps(
            {"physicsVersion": PHYSICS, "is": PHYSICS_IS}))
    except OSError as trouble:
        say("could_not_say_what_computed_it", why=str(trouble)[:160])


def prepare(brief: dict, say):
    """Everything that can be got wrong before a simulator is started.

    Loaded first so that a vehicle whose parameters are wrong fails in a second
    rather than after a minute of simulator startup. Returns the scene, the
    body and the allocator, or None with the reason already reported.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from hydrodynamics import Allocator, Body, Hydrodynamics
    from runner import find_scene

    say_what_computed_this(say)

    city = pathlib.Path(brief.get("cityPath", "/dive/city"))
    vehicle = pathlib.Path(brief.get("vehiclePath", "/dive/vehicle"))

    scene = find_scene(city)
    if scene is None:
        say("failed", why=f"no USD scene in the place at {city}")
        return None

    dynamics_file = vehicle / "dynamics.json"
    say("packages", scene=str(scene.relative_to(city)),
        hasVehicleDynamics=dynamics_file.exists())

    if not dynamics_file.exists():
        # The vehicle package carries its USD but not its parameters. That is a
        # vehicle that can be drawn and not flown, and saying so is better than
        # inventing numbers that would make the dive look like it worked.
        say("failed", why="the vehicle package states no dynamics, so it cannot be flown")
        return None

    model = Hydrodynamics.from_package(dynamics_file)
    body = Body(model)
    allocator = Allocator(model)
    say("vehicle",
        massKg=model.mass_kg,
        buoyancyN=round(model.buoyancy_n, 2),
        weightN=round(model.weight_n, 2),
        netBuoyancyN=round(model.net_buoyancy_n, 3),
        thrusters=len(model.thrusters),
        effectiveMassKg=[round(m, 2) for m in body.effective_mass()[:3]])
    return scene, body, allocator


def seed_everything(seed: int) -> None:
    """Every generator that could affect the trajectory.

    Missing one of these is how a "deterministic" simulator produces two
    different answers to the same question.
    """
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed % (2**32))
    except ImportError:
        pass


def main() -> int:
    brief = read_brief()
    seed = int(brief.get("seed", 0))
    seed_everything(seed)

    say("brief", runId=brief.get("runId"), seed=seed,
        mode=brief.get("mode"), rosDomain=brief.get("rosDomainId"))

    prepared = prepare(brief, say)
    if prepared is None:
        return 2
    scene, body, allocator = prepared

    # A dive nobody is going to look at does not need a renderer.
    #
    # Measured on the box, all four on the same brief and the same card: the
    # shell extension the agent normally launches runs at 0.17x real time, this
    # runner at 3.3x, this runner rendering only when the recording wants a
    # frame at 5.2x, and this runner with no renderer started at all at 19.6x.
    # The trajectories are the same file — identical md5 — because the
    # dynamics come from the vehicle's parameters and not from its triangles,
    # and nothing a step does asks the stage a question.
    #
    # That is the difference between benching a controller in an hour and
    # benching it in a day, and it also means a bench needs no GPU. The default
    # is still drawn, because a dive somebody asked to watch must be watchable;
    # a bench asks for dry.
    if not brief.get("drawn", True):
        return fly_dry(brief, scene, body, allocator)

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": brief.get("mode") != "interactive"})

    try:
        return fly(app, brief, scene, body, allocator)
    finally:
        app.close()


def fly_dry(brief: dict, scene, body, allocator) -> int:
    """Fly it with nothing to see: no Kit, no stage, no frames.

    The same Dive, the same fixed step, the same record — poses, sensors, task,
    manifest — short only a video, which the manifest says it is short of.
    """
    import time as wallclock

    from runner import Dive

    dive = Dive(brief, body, allocator, scene, say)
    if not dive.open_dry():
        return 2
    dive.connect()

    waited = wait_for_autonomy(dive, brief, update=None)

    # What paces it.
    #
    # Nothing, when the vehicle is flown by something in this process: the
    # physics is deterministic and a fixed step, so running flat out and running
    # slowly produce the same trajectory. But a controller in another container
    # publishes on the clock on the wall, and a dive that outran it would hand
    # the vehicle one command every two simulated seconds instead of ten a
    # second — which is not this controller being tested, it is a starved one.
    paced = dive.bridge is not None and dive.bridge.commanded
    say("running", steps=dive.steps, physicsHz=1.0 / dive.dt,
        seconds=dive.steps * dive.dt, realTime=paced, drawn=False,
        waitedSeconds=waited)
    began = wallclock.monotonic()

    # Nothing here paces a controller that thinks, and that is deliberate.
    #
    # The runtime already charges thinking, and charges it in the **dive's** clock
    # rather than the machine's: `Thinking._deliver` holds a thought until
    # `simulated >= asked_at + took`, so a decision that took a second and a half
    # in reality costs a second and a half of the dive whatever rate the dive is
    # running at. Its own words: "otherwise the same controller on a quicker
    # computer would appear to think for free, and every benchmark would be
    # measuring the machine."
    #
    # A guard was added here on 27 September 2026 believing that charge was
    # missing. It was not, and the coarse version of the guard — hold the whole
    # dive to real time whenever a controller *could* think slowly — moved
    # `ponder`'s quick suite from 48.8% to **23.3%**, a twenty-five point change
    # to a result that was already right. Three runs of the same brief agree to
    # every printed digit, so the determinism the module promises does hold; what
    # broke it was the fix.
    while not dive.done:
        dive.step()
        if paced:
            # A controller in another container publishes on the clock on the
            # wall, so the whole dive is held to it. This one is real: it is about
            # a process outside the dive, not about thinking.
            ahead = began + dive.simulated - wallclock.monotonic()
            if ahead > 0:
                wallclock.sleep(min(ahead, 0.05))

    dive.close()
    ran = wallclock.monotonic() - began
    say("succeeded", simulatedSeconds=round(dive.simulated, 3),
        wallSeconds=round(ran, 1),
        timesRealTime=round(dive.simulated / ran, 2) if ran > 0 else None)
    return 0


def wait_for_autonomy(dive, brief: dict, update) -> float:
    """Give a controller in another container wall-clock time to appear.

    Publishing while it waits, because otherwise neither side can go first: this
    was waiting for a command, the controller was waiting for a depth reading to
    respond to, and each was the other's precondition.
    """
    import time as wallclock

    waited = float(brief.get("autonomyWaitSeconds", 60.0))
    if dive.bridge is None:
        return 0.0
    deadline = wallclock.monotonic() + waited
    while not dive.bridge.commanded and wallclock.monotonic() < deadline:
        dive.publish()
        if update is not None:
            update()
        wallclock.sleep(0.05)
    took = round(waited - (deadline - wallclock.monotonic()), 2)
    if dive.bridge.commanded:
        say("autonomy_ready", waitedSeconds=took)
    else:
        # Not a failure. A vehicle nobody commands drifts, and a dive that
        # recorded that is a real result — it is simply a different one, and
        # the record says which.
        say("autonomy_absent", waitedSeconds=waited)
    return took


def fly(app, brief: dict, scene, body, allocator) -> int:
    """Step the dive as fast as the machine allows, or as fast as a controller."""
    import time as wallclock

    from runner import Dive

    dive = Dive(brief, body, allocator, scene, say)
    if not dive.open():
        return 2
    dive.connect()

    # A controller needs wall-clock time to exist in: left to itself the
    # physics runs two thousand steps in well under a second, and a stack
    # that takes five to start its node would find the dive already over —
    # reporting, correctly and uselessly, that nothing flew the vehicle.
    wait_for_autonomy(dive, brief, update=app.update)

    paced = dive.bridge is not None and dive.bridge.commanded
    say("running", steps=dive.steps, physicsHz=1.0 / dive.dt,
        seconds=dive.steps * dive.dt, realTime=paced)
    began = wallclock.monotonic()

    while not dive.done:
        dive.step()
        # Rendered when the recording wants a frame, not every fourth step.
        # A frame costs upwards of half a second and a step costs a quarter of a
        # millisecond, so updating every four steps was rendering two hundred
        # times a second to keep a recording that asked for eight: measured, the
        # same brief ran 3.3x real time that way and 5.2x this way, and produced
        # the same poses file to the byte. A dive with no recording still gets
        # an occasional update, because an app that is never pumped is an app
        # that looks hung to anything watching the process.
        wants_a_frame = (dive.recorder is not None
                         and dive.recorder.owes_a_picture(float(dive.simulated)))
        if wants_a_frame or dive.taken % EVERY_SO_OFTEN == 0:
            app.update()
        # Paced only when something is flying it. Running ahead of the
        # controller would mean the vehicle experienced a command issued for
        # where it used to be, which is a lag no real vehicle has and no
        # controller should be tuned against.
        if paced:
            ahead = began + dive.simulated - wallclock.monotonic()
            if ahead > 0:
                wallclock.sleep(min(ahead, 0.05))

    dive.close()
    say("succeeded", simulatedSeconds=round(dive.simulated, 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
