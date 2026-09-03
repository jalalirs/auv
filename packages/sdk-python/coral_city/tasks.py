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


# For the command line: `--task hold`, `--task reach-depth=9` is gone; a depth
# is a hold at another depth, which is a controller's business.
TASKS = {"hold": hold_station, "hold-station": hold_station, "waypoints": waypoints,
         "transect": transect, "survey": survey, "return": come_home}
