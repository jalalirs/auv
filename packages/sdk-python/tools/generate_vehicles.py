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
OUT = ROOT / "packages" / "sdk-python" / "coral_city" / "vehicles"

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


def main() -> int:
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
    for slug, module in written:
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
        "        raise KeyError(f\"no vehicle '{slug}' in the catalogue; there are {', '.join(ALL)}\") from None",
        "",
        "",
        "def all() -> list[Vehicle]:  # noqa: A001 — reads well at the call site",
        "    return list(ALL.values())",
        "",
    ]
    (OUT / "__init__.py").write_text("\n".join(index))
    for slug, module in written:
        print(f"{slug} -> coral_city/vehicles/{module}.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
