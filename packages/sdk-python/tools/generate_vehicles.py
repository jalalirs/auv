#!/usr/bin/env python3
"""Write the SDK's vehicle descriptions from the catalogue.

Run from the repository root whenever a vehicle's dynamics change:

    python3 packages/sdk-python/tools/generate_vehicles.py

The capability numbers come from the runtime's own allocator, so what the SDK
says a vehicle can do is what the runtime will let it do.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
CATALOG = ROOT / "catalog" / "vehicles"
RUNTIME = ROOT / "services" / "sim-runtime" / "coral"
OUT = ROOT / "packages" / "sdk-python" / "iocean" / "vehicles"

sys.path.insert(0, str(RUNTIME))
from hydrodynamics import Allocator, Hydrodynamics  # noqa: E402


def title_of(readme: pathlib.Path, slug: str) -> str:
    if readme.exists():
        for line in readme.read_text().splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return slug


def module_name(slug: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")


def card_of(dynamics: pathlib.Path) -> dict:
    """A vehicle package, reduced to what the SDK needs to describe it.

    The capability numbers come from the runtime's own allocator, which is
    the whole point: what the SDK says a vehicle can do is what the runtime
    will let it do, and there is one implementation of that arithmetic.

    Written into a package so that a hull somebody else published can be
    flown by an SDK controller. Until now the SDK's list of vehicles was
    generated from *our* catalogue at build time, so a customer could
    publish a hull to the platform and then be told by the SDK that there
    was no such vehicle.
    """
    slug = dynamics.parent.name
    document = json.loads(dynamics.read_text())
    model = Hydrodynamics.from_package(dynamics)
    contract = document.get("topicContract", {})
    return {
        "slug": slug,
        "name": title_of(dynamics.parent / "README.md", slug),
        "massKg": float(document["massKg"]),
        "netBuoyancyN": round(float(model.net_buoyancy_n), 3),
        "capability": [round(float(v), 3) for v in Allocator(model).capability()],
        "thrusters": [{"name": one["name"],
                       "position": [float(v) for v in one["position"]],
                       "direction": [float(v) for v in one["direction"]]}
                      for one in document.get("thrusters", {}).get("units", [])],
        "sensors": [{"kind": one["kind"], "name": one["name"]}
                    for one in document.get("sensors", [])],
        "publishes": [{"topic": one["topic"], "type": one["type"],
                       "note": one.get("note", "")}
                      for one in contract.get("publishes", [])],
        "subscribes": [{"topic": one["topic"], "type": one["type"],
                        "note": one.get("note", "")}
                       for one in contract.get("subscribes", [])],
        "dynamics": document,
    }


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--package":
        # One package, carded in place, for a hull that is not ours.
        package = pathlib.Path(sys.argv[2]).expanduser()
        dynamics = package / "dynamics.json"
        if not dynamics.is_file():
            print(f"no dynamics.json in {package}", file=sys.stderr)
            return 1
        (package / "vehicle.json").write_text(
            json.dumps(card_of(dynamics), indent=2) + "\n")
        print(f"{package.name} -> {package / 'vehicle.json'}")
        return 0

    written = []
    for dynamics in sorted(CATALOG.glob("*/dynamics.json")):
        slug = dynamics.parent.name
        document = json.loads(dynamics.read_text())
        model = Hydrodynamics.from_package(dynamics)
        capability = [round(float(v), 3) for v in Allocator(model).capability()]
        contract = document.get("topicContract", {})
        units = document.get("thrusters", {}).get("units", [])
        lines = [
            f'"""{title_of(dynamics.parent / "README.md", slug)}, as the catalogue describes it. Generated; do not edit."""',
            "",
            "from ..vehicle import Sensor, Thruster, Topic, Vehicle",
            "",
            f"DYNAMICS = {json.dumps(document, indent=4)}",
            "",
            "VEHICLE = Vehicle(",
            f"    slug={slug!r},",
            f"    name={title_of(dynamics.parent / 'README.md', slug)!r},",
            f"    mass_kg={float(document['massKg'])!r},",
            f"    net_buoyancy_n={round(float(model.net_buoyancy_n), 3)!r},",
            "    thrusters=(",
        ]
        for unit in units:
            lines.append(f"        Thruster({unit['name']!r}, {tuple(float(v) for v in unit['position'])!r}, "
                         f"{tuple(float(v) for v in unit['direction'])!r}),")
        lines += ["    ),", "    sensors=("]
        for sensor in document.get("sensors", []):
            lines.append(f"        Sensor({sensor['kind']!r}, {sensor['name']!r}),")
        lines += ["    ),", "    publishes=("]
        for topic in contract.get("publishes", []):
            lines.append(f"        Topic({topic['topic']!r}, {topic['type']!r}, {topic.get('note', '')!r}),")
        lines += ["    ),", "    subscribes=("]
        for topic in contract.get("subscribes", []):
            lines.append(f"        Topic({topic['topic']!r}, {topic['type']!r}, {topic.get('note', '')!r}),")
        lines += ["    ),", f"    capability={tuple(capability)!r},", "    dynamics=DYNAMICS,", ")", ""]
        (OUT / f"{module_name(slug)}.py").write_text("\n".join(lines))
        written.append((slug, module_name(slug)))

    index = [
        '"""Every vehicle the catalogue describes. Generated; do not edit."""',
        "",
        "from __future__ import annotations",
        "",
        "from ..vehicle import Vehicle",
        "",
    ]
    for _, module in written:
        index.append(f"from .{module} import VEHICLE as _{module}")
    index += ["", "ALL: dict[str, Vehicle] = {"]
    for slug, module in written:
        index.append(f"    {slug!r}: _{module},")
    index += [
        "}",
        "",
        "",
        "def load(slug: str) -> Vehicle:",
        "    try:",
        "        return ALL[slug]",
        "    except KeyError:",
        "        # Not one of ours. A customer's own hull is found by the",
        "        # card its package carries; see iocean/catalogue.py.",
        "        from ..catalogue import from_a_package",
        "",
        "        return from_a_package(slug, ALL)",
        "",
        "",
        "def all() -> list[Vehicle]:  # noqa: A001 — reads well at the call site",
        "    return list(ALL.values())",
        "",
    ]
    (OUT / "__init__.py").write_text("\n".join(index))
    for slug, module in written:
        print(f"{slug} -> iocean/vehicles/{module}.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
