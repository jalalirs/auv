"""A dive's world and the systems that run it, put together.

`the_ocean` makes every part of the world a dive has, empty, with its owner;
the dive fills them in as it opens the place, the vehicle and the conditions.
`the_systems` makes the systems. The engine orders them from their
declarations — the list here is only the tie-break where the declarations
leave the order open.
"""

from __future__ import annotations

import numpy as np

from engine import Clock, World
from engine.engine import Tick
from systems.faults import Faults, FaultsSystem
from systems.contact import Contacts
from systems.helm import Asked, HelmSystem, Orders
from systems.instruments import Ctd, CtdSystem, Fresh, MultibeamSystem, SonarSystem
from systems.navigation import NavigationSystem
from systems.outputs import BridgeSystem, RecordSystem
from systems.place import Place
from systems.tasking import Task, TaskingSystem
from systems.thrusters import Power, Thrust, ThrustersSystem
from systems.vehicle import Vehicle, VehicleSystem
from systems.wash import Wash, WashSystem
from systems.views import Camera, ViewsSystem
from systems.water import Water, WaterSystem


def the_ocean(body, thrusters: int, dt: float) -> World:
    """Every part of a dive's world, and which system writes it."""
    world = World()
    world.put("clock", Clock(dt), owner="clock")
    world.put("place", Place())
    world.put("faults", Faults(), owner="faults")
    world.put("water", Water(), owner="water")
    world.put("camera", Camera(), owner="views")
    world.put("navigation", None, owner="navigation")
    world.put("ctd", Ctd(), owner="ctd")
    world.put("multibeam", None, owner="multibeam")
    world.put("swath", Fresh(), owner="multibeam")
    world.put("sonar", None, owner="sonar")
    world.put("ping", Fresh(), owner="sonar")
    world.put("helm", None, owner="helm")
    world.put("asked", Asked(np.zeros(int(thrusters))), owner="helm")
    world.put("orders", Orders(), owner="tasking")
    world.put("thrust", Thrust(thrusters), owner="thrusters")
    world.put("power", Power(), owner="thrusters")
    world.put("vehicle", Vehicle(body, np.zeros(3)), owner="vehicle")
    world.put("contacts", Contacts(), owner="vehicle")
    world.put("cable", None, owner="vehicle")
    world.put("wash", Wash(), owner="wash")
    world.put("task", Task(), owner="tasking")
    world.put("bridge", None, owner="bridge")
    world.put("record", None, owner="record")
    return world


def the_systems(dive) -> list:
    """The systems a dive runs, built from what the dive says about itself."""
    brief, say, dt = dive.brief, dive.say, dive.dt
    objective = brief.get("objective") if isinstance(brief.get("objective"), dict) else None
    return [
        FaultsSystem(len(dive.allocator.model.thrusters), say),
        WaterSystem(say),
        ViewsSystem(objective, dive.views, say),
        NavigationSystem(dt),
        CtdSystem(),
        MultibeamSystem(),
        SonarSystem(),
        HelmSystem(say),
        ThrustersSystem(dt, float(brief.get("dockWatts", 120.0))),
        VehicleSystem(dt, say),
        WashSystem(dive.allocator.model.thrusters),
        # The clock moves on once the vehicle has: what runs after it judges
        # the state the tick produced, at the time it was produced.
        Tick(after=("vehicle",)),
        TaskingSystem(brief, say, dive.who_should_fly, dive.envelope, dive.camera_half_angle),
        BridgeSystem(dive.publish),
        RecordSystem(dive, say),
    ]
