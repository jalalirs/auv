"""What a controller is scored on.

A task is an objective: a small document a dive is defined with, judged by the
runtime as the dive runs — on the platform and in the tank alike, by the same
code, so a controller that scores well on a laptop scores the same there. These
are the objectives, written as functions so the fields are spelled once.
Everything is measured from where the dive began.
"""

from __future__ import annotations


def hold_station(seconds: float = 60.0, radius_m: float = 0.5, depth_band_m: float = 0.3) -> dict:
    """Stay where the dive began, within a radius and a depth band, for a time."""
    return {"kind": "hold-station", "seconds": seconds, "radiusM": radius_m, "depthBandM": depth_band_m}


def waypoints(points: list[dict] | None = None, radius_m: float = 1.0, time_limit_s: float = 300.0) -> dict:
    """Visit points in order: each {dx, dy, depthM?} ahead and to starboard of the start."""
    made = {"kind": "waypoints", "radiusM": radius_m, "timeLimitS": time_limit_s}
    if points is not None:
        made["points"] = points
    return made


def transect(length_m: float = 20.0, altitude_m: float = 2.0, altitude_band_m: float = 0.5,
             heading_tolerance_deg: float = 10.0, heading_deg: float | None = None,
             time_limit_s: float = 180.0) -> dict:
    """Fly a line along the heading at a fixed altitude above the bottom."""
    made = {"kind": "transect", "lengthM": length_m, "altitudeM": altitude_m,
            "altitudeBandM": altitude_band_m, "headingToleranceDeg": heading_tolerance_deg,
            "timeLimitS": time_limit_s}
    if heading_deg is not None:
        made["headingDeg"] = heading_deg
    return made


def survey(width_m: float = 20.0, height_m: float = 10.0, altitude_m: float = 2.0,
           swath_m: float = 3.0, altitude_band_m: float = 1.0, time_limit_s: float = 600.0) -> dict:
    """Cover a rectangle ahead of the start in passes, at an altitude, with a swath."""
    return {"kind": "survey", "widthM": width_m, "heightM": height_m, "altitudeM": altitude_m,
            "swathM": swath_m, "altitudeBandM": altitude_band_m, "timeLimitS": time_limit_s}


def come_home(home_radius_m: float = 2.0, surface_depth_m: float = 0.5, time_limit_s: float = 300.0) -> dict:
    """Come back to where the dive began and surface."""
    return {"kind": "return", "homeRadiusM": home_radius_m, "surfaceDepthM": surface_depth_m,
            "timeLimitS": time_limit_s}


def reach(dx: float = 25.0, dy: float = 0.0, radius_m: float = 1.5,
          depth_m: float | None = None, time_limit_s: float = 600.0) -> dict:
    """Get to a point, and be judged on going there directly."""
    made = {"kind": "reach", "dx": dx, "dy": dy, "radiusM": radius_m, "timeLimitS": time_limit_s}
    if depth_m is not None:
        made["depthM"] = depth_m
    return made


def search(width_m: float = 30.0, height_m: float = 20.0, altitude_m: float = 2.5,
           see_m: float = 6.0, target: dict | None = None, time_limit_s: float = 900.0) -> dict:
    """Find something in a patch, without being told where it is.

    A controller that recognises what it sees says so with `found`; one that
    does not can still fly the pattern until the thing is in front of it.
    """
    return {"kind": "search", "widthM": width_m, "heightM": height_m,
            "altitudeM": altitude_m, "seeM": see_m, "timeLimitS": time_limit_s,
            "target": target or {"dx": width_m * 0.7, "dy": height_m * 0.6}}


def treat(radius_m: float = 12.0, reach_m: float = 1.2, altitude_m: float = 1.5,
          speed_ms: float = 0.35, centre: dict | None = None, time_limit_s: float = 1800.0) -> dict:
    """Pass within reach of every colony in a patch, low and slow."""
    made = {"kind": "treat", "radiusM": radius_m, "reachM": reach_m, "altitudeM": altitude_m,
            "speedMs": speed_ms, "timeLimitS": time_limit_s}
    if centre is not None:
        made["centre"] = centre
    return made


def inspect(dx: float = 10.0, dy: float = 0.0, radius_m: float = 4.0, band_m: float = 2.0,
            time_limit_s: float = 900.0) -> dict:
    """Circle a thing, keeping it in frame: every side of it counts."""
    return {"kind": "inspect", "dx": dx, "dy": dy, "radiusM": radius_m, "bandM": band_m,
            "timeLimitS": time_limit_s}


def revisit(marks: list[dict] | None = None, reach_m: float = 1.0, hold_s: float = 10.0,
            time_limit_s: float = 1200.0) -> dict:
    """Visit each marked colony and hold there long enough to sample."""
    return {"kind": "revisit", "reachM": reach_m, "holdS": hold_s, "timeLimitS": time_limit_s,
            "marks": marks or [{"dx": 8, "dy": 0}, {"dx": 16, "dy": 6}, {"dx": 10, "dy": -8}]}


def dock(dx: float = 15.0, dy: float = 0.0, approach_m: float = 6.0, tolerance_m: float = 0.4,
         heading_tolerance_deg: float = 20.0, speed_ms: float = 0.25,
         time_limit_s: float = 900.0) -> dict:
    """Get onto the station: slowly, straight, and inside the tolerance."""
    return {"kind": "dock", "dx": dx, "dy": dy, "approachM": approach_m,
            "toleranceM": tolerance_m, "headingToleranceDeg": heading_tolerance_deg,
            "speedMs": speed_ms, "timeLimitS": time_limit_s}


def wait(seconds: float = 300.0, reason: str = "charging", drift_m: float = 1.0) -> dict:
    """Stay put for a while: charging, or handing over what was recorded."""
    return {"kind": "wait", "seconds": seconds, "reason": reason, "driftM": drift_m}


def mission(*stages: dict) -> dict:
    """Several things in order, as one dive.

    Each stage is scored on its own terms and the mission on all of them; a
    stage that fails ends it, because a mission that carries on after a failed
    dock is a mission pretending.
    """
    return {"kind": "mission", "stages": list(stages)}


def failures(*said: dict) -> list[dict]:
    """Things that go wrong on purpose, for the conditions a dive is defined with.

    `failures(thruster_dies(at_s=120), sensors_drop(at_s=200, for_s=5))`
    """
    return list(said)


def thruster_dies(at_s: float, which: int | list[int] | None = None) -> dict:
    return {"kind": "thruster", "atS": at_s, "which": which}


def sensors_drop(at_s: float, for_s: float = 5.0) -> dict:
    return {"kind": "sensors", "atS": at_s, "forS": for_s}


def gust(at_s: float, metres_per_second: float = 0.5) -> dict:
    return {"kind": "current", "atS": at_s, "which": metres_per_second}


# For the command line: `--task hold`, `--task reach-depth=9` is gone; a depth
# is a hold at another depth, which is a controller's business.
TASKS = {"hold": hold_station, "hold-station": hold_station, "waypoints": waypoints,
         "transect": transect, "survey": survey, "return": come_home,
         "reach": reach, "search": search, "treat": treat, "inspect": inspect,
         "revisit": revisit, "dock": dock, "wait": wait}
