"""Bring today's ocean observations into the platform.

Reads the National Data Buoy Center's real-time feed for a set of stations,
takes each station's most recent complete report, and writes them as one
observation set with a description of what it is.

This is the platform's heartbeat: it runs on a schedule, nobody triggers it, and
each run supersedes the last. It uses nothing but the standard library, because
a text feed does not need more.

This program writes files. It holds no credential and reaches nothing but the
feed it reads.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FEED = os.environ.get("CORAL_NDBC_FEED", "https://www.ndbc.noaa.gov/data/realtime2")
STATION_TABLE = os.environ.get(
    "CORAL_NDBC_STATIONS", "https://www.ndbc.noaa.gov/data/stations/station_table.txt"
)
# Which stations to read. Given as identifiers so that what this version covers
# is a decision recorded in the schedule rather than something the program chose.
STATIONS = [
    station.strip()
    for station in os.environ.get(
        "CORAL_NDBC_STATION_IDS", "41047,41049,44008,46006,51000,42001,44011,46059"
    ).split(",")
    if station.strip()
]

OUTPUTS = Path(os.environ.get("CORAL_OUTPUTS", "/work/outputs"))
OBSERVATIONS = OUTPUTS / "observations.json"
DESCRIPTOR = OUTPUTS / "version.json"

# The columns of the standard meteorological feed that this reads. Everything
# else the feed carries is left alone rather than guessed at.
MEASUREMENTS = {
    "WDIR": ("windDirectionDegreesTrue", float),
    "WSPD": ("windSpeedMetresPerSecond", float),
    "GST": ("gustMetresPerSecond", float),
    "WVHT": ("significantWaveHeightMetres", float),
    "DPD": ("dominantWavePeriodSeconds", float),
    "APD": ("averageWavePeriodSeconds", float),
    "MWD": ("waveDirectionDegreesTrue", float),
    "PRES": ("pressureHectopascals", float),
    "ATMP": ("airTemperatureCelsius", float),
    "WTMP": ("waterTemperatureCelsius", float),
    "DEWP": ("dewPointCelsius", float),
}

COORDINATE = re.compile(r"([\d.]+)\s*([NS])\s+([\d.]+)\s*([EW])")


def log(message: str) -> None:
    print(message, flush=True)


def read(url: str) -> str:
    with urllib.request.urlopen(url, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} answered {response.status}")
        return response.read().decode("utf-8", errors="replace")


def station_positions() -> dict[str, dict[str, float]]:
    """Read where the stations are, from the operator's own table."""
    positions: dict[str, dict[str, float]] = {}
    for line in read(STATION_TABLE).splitlines():
        if line.startswith("#") or "|" not in line:
            continue
        fields = line.split("|")
        if len(fields) < 7:
            continue
        identifier = fields[0].strip().lower()
        found = COORDINATE.search(fields[6])
        if not found:
            continue
        latitude = float(found.group(1)) * (1 if found.group(2) == "N" else -1)
        longitude = float(found.group(3)) * (1 if found.group(4) == "E" else -1)
        positions[identifier] = {
            "latitude": latitude,
            "longitude": longitude,
            "name": fields[4].strip(),
            "owner": fields[1].strip(),
        }
    log(f"read {len(positions)} station positions")
    return positions


def latest_report(station: str) -> dict[str, object] | None:
    """Take a station's most recent report.

    A missing measurement is reported as missing rather than as a number, which
    is the whole reason this reads the feed rather than averaging it.
    """
    try:
        feed = read(f"{FEED}/{station.upper()}.txt")
    except Exception as failure:  # noqa: BLE001 — one station's silence is not a failure
        log(f"station {station}: {failure}")
        return None

    lines = [line for line in feed.splitlines() if line and not line.startswith("#")]
    header = [line for line in feed.splitlines() if line.startswith("#")]
    if not lines or not header:
        log(f"station {station}: the feed carried no report")
        return None

    columns = header[0].lstrip("#").split()
    values = lines[0].split()
    if len(values) != len(columns):
        log(f"station {station}: the report does not match its own header")
        return None

    row = dict(zip(columns, values))
    try:
        observed = datetime(
            int(row["YY"]), int(row["MM"]), int(row["DD"]),
            int(row["hh"]), int(row["mm"]), tzinfo=timezone.utc,
        )
    except (KeyError, ValueError) as failure:
        log(f"station {station}: the report has no usable time: {failure}")
        return None

    measurements: dict[str, float] = {}
    missing: list[str] = []
    for column, (name, convert) in MEASUREMENTS.items():
        raw = row.get(column, "MM")
        if raw == "MM":
            missing.append(name)
            continue
        try:
            measurements[name] = convert(raw)
        except ValueError:
            missing.append(name)

    return {
        "station": station.lower(),
        "observedAt": observed.isoformat().replace("+00:00", "Z"),
        "measurements": measurements,
        # What the station did not report, named. An absent measurement that is
        # merely absent from the output is indistinguishable from one nobody
        # asked for.
        "notReported": missing,
    }


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    positions = station_positions()

    reports = []
    for station in STATIONS:
        report = latest_report(station)
        if report is None:
            continue
        position = positions.get(station.lower())
        if position is None:
            log(f"station {station}: reported, but the operator's table does not place it")
            continue
        report["latitude"] = position["latitude"]
        report["longitude"] = position["longitude"]
        report["name"] = position["name"]
        report["owner"] = position["owner"]
        reports.append(report)

    if not reports:
        log("no station reported; there is nothing to record")
        return 1

    times = sorted(report["observedAt"] for report in reports)
    latitudes = [report["latitude"] for report in reports]
    longitudes = [report["longitude"] for report in reports]

    OBSERVATIONS.write_text(json.dumps({
        "source": "NOAA National Data Buoy Center real-time feed",
        "retrievedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stations": reports,
    }, indent=2) + "\n")
    log(f"recorded {len(reports)} stations from {times[0]} to {times[-1]}")

    descriptor = {
        # Measurements of the world, made by instruments, reported unaltered.
        "truthClass": "observation",
        "crsEpsg": 4326,
        # These are surface measurements: a wave height is measured from the sea
        # surface at the buoy, not from a geodetic datum.
        "verticalDatum": "instantaneous sea surface at the reporting station",
        "extent": {
            # A degree of margin, because a set of points is not a region and an
            # extent of zero width is not one either.
            "west": max(min(longitudes) - 1.0, -180.0),
            "south": max(min(latitudes) - 1.0, -90.0),
            "east": min(max(longitudes) + 1.0, 180.0),
            "north": min(max(latitudes) + 1.0, 90.0),
        },
        "observedFrom": times[0],
        "observedTo": times[-1],
        "uncertainty": {
            "kind": "described",
            "note": (
                "Accuracy differs by measurement, sensor, and station, and the "
                "real-time feed carries no per-measurement figure. The operator "
                "documents sensor accuracies separately. Measurements a station "
                "did not report are named in each station's notReported list "
                "rather than omitted."
            ),
        },
        "rights": (
            "US Government work, in the public domain. NOAA asks that the "
            "National Data Buoy Center be credited."
        ),
        "attribution": "NOAA National Data Buoy Center",
    }
    DESCRIPTOR.write_text(json.dumps(descriptor, indent=2) + "\n")
    log(f"described this version as observation over {times[0]} to {times[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
