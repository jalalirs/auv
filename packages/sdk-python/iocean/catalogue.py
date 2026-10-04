"""Vehicles that are not ours.

The SDK's list of vehicles is generated from this repository's catalogue at
build time, which is right for the four hulls we publish and wrong for the
fifth. A customer can publish their own vehicle to the platform — that is
the whole point of a catalogue — and then be told by the SDK that there is
no such vehicle, because the SDK was built before their hull existed.

So a package can carry its own card. `vehicle.json`, written into the
package by `generate_vehicles.py --package`, holds what the SDK needs to
describe a hull: its mass, its trim, its thrusters and where they are, what
it carries, the topics it speaks, and **what it can actually produce on each
axis**. That last one is computed by the runtime's own allocator and not
here, deliberately: a capability the SDK worked out for itself would be a
second implementation of the arithmetic the runtime uses to fly the thing,
and two implementations of one idea agree until they do not.

Point `IOCEAN_VEHICLES` at a directory of packages and they load by
slug like any other — and if you are signed in to a platform that has the
hull, the card comes off its published package without your having the
package at all. That last part needed no new endpoint: the card is a file
in the package, and the platform already serves a version's files.
"""

from __future__ import annotations

import json
import os
import pathlib

from .vehicle import Sensor, Thruster, Topic, Vehicle


def a_vehicle(card: dict) -> Vehicle:
    """One hull, from the card its package carries."""
    capability = tuple(float(v) for v in card.get("capability") or ())
    if len(capability) != 6:
        raise ValueError(
            f"the card for '{card.get('slug', 'a vehicle')}' says nothing about what "
            f"it can produce on each axis. Write it with "
            f"`generate_vehicles.py --package <the package>`, which asks the runtime "
            f"— guessing it here would be a second answer to a question that has one.")
    return Vehicle(
        slug=str(card["slug"]),
        name=str(card.get("name") or card["slug"]),
        mass_kg=float(card["massKg"]),
        net_buoyancy_n=float(card.get("netBuoyancyN", 0.0)),
        thrusters=tuple(Thruster(one["name"], tuple(one["position"]),
                                 tuple(one["direction"]))
                        for one in card.get("thrusters") or ()),
        sensors=tuple(Sensor(one["kind"], one["name"])
                      for one in card.get("sensors") or ()),
        publishes=tuple(Topic(one["topic"], one["type"], one.get("note", ""))
                        for one in card.get("publishes") or ()),
        subscribes=tuple(Topic(one["topic"], one["type"], one.get("note", ""))
                         for one in card.get("subscribes") or ()),
        capability=capability,
        dynamics=card.get("dynamics") or {},
    )


def where_to_look() -> list[pathlib.Path]:
    """Directories of vehicle packages, from `IOCEAN_VEHICLES`."""
    said = os.environ.get("IOCEAN_VEHICLES", "")
    return [pathlib.Path(one).expanduser() for one in said.split(os.pathsep) if one]


def from_the_platform(slug: str) -> Vehicle | None:
    """A hull the platform has, by the card its published package carries.

    No new endpoint: the card is a file in the package, `tools/publish`
    uploads every file in the directory, and the platform already serves a
    version's files. So a hull somebody else published is describable
    without having their package on disk, which is the difference between
    "you can publish a vehicle" and "somebody else can fly it".

    Quietly nothing when there is no session or no such vehicle, because
    this is the third place looked and the error that matters is the one
    `from_a_package` raises after all three.
    """
    try:
        from .platform import Platform

        platform = Platform.from_session()
        vehicle = platform.vehicle(slug)
        versions = [one for one in platform.vehicle_versions(vehicle["id"])
                    if one.get("publishedAt")]
        if not versions:
            return None
        newest = max(versions, key=lambda one: one.get("ordinal", 0))
        files = platform.call("GET", f"/api/v1/versions/{newest['id']}/files")
        card = next((one for one in files.get("files", [])
                     if str(one.get("path", "")).endswith("vehicle.json")), None)
        if card is None:
            return None
        import urllib.request

        with urllib.request.urlopen(card["url"], timeout=30) as answer:
            return a_vehicle(json.loads(answer.read().decode("utf-8")))
    except SystemExit:
        return None
    except Exception:
        return None


def from_a_package(slug: str, known: dict) -> Vehicle:
    """A hull that is not ours, or the error that says what is.

    Raised rather than returned as None, because a controller that names a
    vehicle nobody has is a controller that must not be deployed — the
    check exists so that a hull missing a sensor is refused here rather
    than left waiting on a dive for a message that never comes.
    """
    for root in where_to_look():
        card = root / slug / "vehicle.json"
        if card.is_file():
            return a_vehicle(json.loads(card.read_text()))
        # A package handed over directly, rather than a directory of them.
        if root.name == slug and (root / "vehicle.json").is_file():
            return a_vehicle(json.loads((root / "vehicle.json").read_text()))
    # And the platform, when you are signed in to one that has it.
    theirs = from_the_platform(slug)
    if theirs is not None:
        return theirs
    ours = ", ".join(known) or "none"
    looked = ", ".join(str(one) for one in where_to_look())
    raise KeyError(
        f"no vehicle '{slug}'. Published with this SDK: {ours}."
        + (f" Looked for a package carrying its own vehicle.json in: {looked}."
           if looked else
           " A hull of your own is found by pointing IOCEAN_VEHICLES at the"
           " directory its package is in.")) from None
