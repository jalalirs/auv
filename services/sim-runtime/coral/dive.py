"""Run one dive.

The agent hands over a brief — which place, which vehicle, what water, what
seed — and this loads the place, puts the vehicle in it, integrates the
hydrodynamics, and reports what happened.

Determinism is the property everything else rests on, so it is arranged here
rather than hoped for: a fixed timestep, every generator seeded from the seed
the run pinned, and no dependence on wall-clock time anywhere in the loop. Two
runs of the same brief produce the same trajectory, which is what makes a
replay a replay and a regression real rather than noise.
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import sys

# Fixed, and not negotiable: a variable timestep makes two runs of the same seed
# diverge, and everything the platform claims about a result rests on them not
# diverging. 200 Hz is comfortably above the vehicle's dynamics and cheap.
PHYSICS_HZ = 200.0
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
    print(json.dumps({"event": kind, **detail}), flush=True)


def main() -> int:
    brief = read_brief()
    seed = int(brief.get("seed", 0))

    # Every generator that could affect the trajectory, seeded from the one the
    # run pinned. Missing one of these is how a "deterministic" simulator
    # produces two different answers to the same question.
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed % (2**32))
    except ImportError:
        pass

    say("brief", runId=brief.get("runId"), seed=seed,
        mode=brief.get("mode"), rosDomain=brief.get("rosDomainId"))

    city = pathlib.Path(brief.get("cityPath", "/dive/city"))
    vehicle = pathlib.Path(brief.get("vehiclePath", "/dive/vehicle"))

    scene = find_scene(city)
    if scene is None:
        say("failed", why=f"no USD scene in the place at {city}")
        return 2

    dynamics_file = vehicle / "dynamics.json"
    say("packages", scene=str(scene.relative_to(city)),
        hasVehicleDynamics=dynamics_file.exists())

    # The hydrodynamics are loaded before Isaac Sim, so that a vehicle whose
    # parameters are wrong fails in a second rather than after a minute of
    # simulator startup.
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from hydrodynamics import Allocator, Body, Hydrodynamics

    if dynamics_file.exists():
        model = Hydrodynamics.from_package(dynamics_file)
    else:
        # The vehicle package carries its USD but not its parameters. That is a
        # vehicle that can be drawn and not flown, and saying so is better than
        # inventing numbers that would make the dive look like it worked.
        say("failed", why="the vehicle package states no dynamics, so it cannot be flown")
        return 2

    body = Body(model)
    allocator = Allocator(model)
    say("vehicle",
        massKg=model.mass_kg,
        buoyancyN=round(model.buoyancy_n, 2),
        weightN=round(model.weight_n, 2),
        netBuoyancyN=round(model.net_buoyancy_n, 3),
        thrusters=len(model.thrusters),
        effectiveMassKg=[round(m, 2) for m in body.effective_mass()[:3]])

    from isaacsim import SimulationApp

    headless = brief.get("mode") != "interactive"
    app = SimulationApp({"headless": headless})

    try:
        return fly(app, brief, scene, body, allocator)
    finally:
        app.close()


def find_scene(root: pathlib.Path) -> pathlib.Path | None:
    """The USD a place is loaded from.

    A place may carry several — a scene and a water surface, say — so the one
    that is not obviously a component is chosen, and the choice is reported so
    that nobody has to guess which was used.
    """
    candidates = sorted(root.rglob("*.usd")) + sorted(root.rglob("*.usda"))
    if not candidates:
        return None
    for candidate in candidates:
        name = candidate.stem.lower()
        if "water" not in name and "surface" not in name:
            return candidate
    return candidates[0]


def fly(app, brief: dict, scene: pathlib.Path, body, allocator) -> int:
    """Load the place, put the vehicle in it, and integrate."""
    import numpy as np
    import omni.usd
    from pxr import Gf, UsdGeom, UsdLux, UsdPhysics

    context = omni.usd.get_context()
    context.open_stage(str(scene))
    stage = context.get_stage()
    if stage is None:
        say("failed", why=f"the place at {scene} would not open")
        return 2

    prims = sum(1 for _ in stage.Traverse())
    say("place_open", scene=str(scene), prims=prims)

    # Gravity on, which is the whole point: OceanSim disables it and applies
    # damping instead, and a vehicle with no weight has nothing for buoyancy to
    # act against.
    physics = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
    physics.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
    physics.CreateGravityMagnitudeAttr().Set(9.80665)

    if not stage.GetPrimAtPath("/World/Sun"):
        UsdLux.DistantLight.Define(stage, "/World/Sun").CreateIntensityAttr(3000.0)

    initial = brief.get("initialState") or {}
    position = np.array(initial.get("positionM", [0.0, 0.0, -2.0]), dtype=float)

    # A body of the vehicle's actual mass, at the vehicle's actual place. The
    # visual hull is not loaded here: what is being integrated is the dynamics,
    # and a dive that reported a trajectory it had not computed would be worse
    # than one that reported no picture.
    vehicle_path = "/World/Vehicle"
    xform = UsdGeom.Xform.Define(stage, vehicle_path)
    xform.AddTranslateOp().Set(Gf.Vec3d(*position))

    say("vehicle_placed", position=[round(float(x), 3) for x in position])

    steps = int(brief.get("durationSeconds", 10.0) * PHYSICS_HZ)
    dt = 1.0 / PHYSICS_HZ
    # The boundary. If nothing is flying this vehicle the commands stay zero
    # and it drifts, which is what an untended ROV does.
    bridge = None
    if brief.get("autonomy", True):
        try:
            from bridge import Bridge
            bridge = Bridge(allocator.model, allocator,
                            int(brief.get("rosDomainId", 0)),
                            logger=lambda kind, **d: say(kind, **d))
            say("bridge_open", domain=brief.get("rosDomainId"),
                publishes=["/depth", "/imu/data", "/dvl/twist"],
                subscribes=["/thruster_cmd", "/cmd_vel"])
        except Exception as exc:
            say("bridge_unavailable", why=str(exc)[:200])

    commands = np.zeros(len(allocator.model.thrusters))

    velocity = np.zeros(6)
    effective = body.effective_mass()
    rotation = np.eye(3)
    simulated = 0.0
    reported = 0.0

    say("running", steps=steps, physicsHz=PHYSICS_HZ, seconds=steps * dt)

    for step in range(steps):
        if bridge is not None:
            commands = bridge.commands()

        wrench = body.step(rotation, velocity, commands, dt)

        # Semi-implicit Euler at a fixed step. Not because it is the best
        # integrator but because it is the same integrator every time, which
        # matters more than accuracy for a result two runs must agree on.
        velocity[:3] += (wrench[:3] / effective[:3]) * dt
        velocity[3:] += (wrench[3:] / effective[3:]) * dt
        position += rotation @ velocity[:3] * dt
        simulated += dt

        # Once a second of simulated time, not of wall-clock: the report is part
        # of the run, and a report that depended on how fast the machine was
        # would make two runs of the same seed produce different records.
        # Sensors at their own rate rather than every physics step: a real DVL
        # reports at tens of hertz, not two hundred, and a stack tuned against
        # a sensor that never lies about its rate will be surprised by one that
        # does.
        if bridge is not None and step % 10 == 0:
            bridge.publish(simulated, position, velocity, body.model.density)

        if simulated - reported >= 1.0:
            reported = simulated
            say("state",
                t=round(simulated, 3),
                depthM=round(float(-position[2]), 4),
                speedMs=round(float(np.linalg.norm(velocity[:3])), 4),
                commanded=bool(bridge.commanded) if bridge else False,
                thrust=[round(float(c), 3) for c in commands],
                position=[round(float(x), 4) for x in position])

        if step % 4 == 0:
            app.update()

    say("settled",
        t=round(simulated, 3),
        depthM=round(float(-position[2]), 4),
        speedMs=round(float(np.linalg.norm(velocity[:3])), 4))

    if bridge is not None:
        # Whether anything actually flew it. A dive that ran with nobody at the
        # controls is a valid result and a different one, and the difference
        # should not have to be inferred from the trajectory.
        say("autonomy",
            commanded=bool(bridge.commanded),
            commandsReceived=bridge.commands_seen)
        bridge.close()

    say("succeeded", simulatedSeconds=round(simulated, 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
