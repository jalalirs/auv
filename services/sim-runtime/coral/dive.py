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


def prepare(brief: dict, say):
    """Everything that can be got wrong before a simulator is started.

    Loaded first so that a vehicle whose parameters are wrong fails in a second
    rather than after a minute of simulator startup. Returns the scene, the
    body and the allocator, or None with the reason already reported.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from hydrodynamics import Allocator, Body, Hydrodynamics
    from runner import find_scene

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

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": brief.get("mode") != "interactive"})

    try:
        return fly(app, brief, scene, body, allocator)
    finally:
        app.close()


def fly(app, brief: dict, scene, body, allocator) -> int:
    """Step the dive as fast as the machine allows, or as fast as a controller."""
    import time as wallclock

    from runner import Dive

    dive = Dive(brief, body, allocator, scene, say)
    if not dive.open():
        return 2
    dive.connect()

    # A controller needs wall-clock time to exist in.
    #
    # Left to itself the physics runs two thousand steps in well under a second,
    # and a stack that takes five to start its node would find the dive already
    # over — reporting, correctly and uselessly, that nothing flew the vehicle.
    # So a dive with autonomy attached waits for it to appear and then runs at
    # real time; one without runs as fast as the machine allows, which is the
    # whole point of batch.
    waited = float(brief.get("autonomyWaitSeconds", 60.0))
    if dive.bridge is not None:
        # Publishing while it waits, because otherwise neither side can go
        # first: this was waiting for a command, the controller was waiting for
        # a depth reading to respond to, and each was the other's precondition.
        deadline = wallclock.monotonic() + waited
        while not dive.bridge.commanded and wallclock.monotonic() < deadline:
            dive.publish()
            app.update()
            wallclock.sleep(0.05)
        if dive.bridge.commanded:
            say("autonomy_ready",
                waitedSeconds=round(waited - (deadline - wallclock.monotonic()), 2))
        else:
            # Not a failure. A vehicle nobody commands drifts, and a dive that
            # recorded that is a real result — it is simply a different one, and
            # the record says which.
            say("autonomy_absent", waitedSeconds=waited)

    paced = dive.bridge is not None and dive.bridge.commanded
    say("running", steps=dive.steps, physicsHz=1.0 / dive.dt,
        seconds=dive.steps * dive.dt, realTime=paced)
    began = wallclock.monotonic()

    while not dive.done:
        dive.step()
        if dive.taken % 4 == 0:
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
