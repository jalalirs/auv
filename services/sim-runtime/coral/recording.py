"""What a dive leaves behind.

A survey's product is the data, so a dive that is for something records as it
goes: where the vehicle was and which way it pointed, what its sensors said,
how its task was going, and the frames it saw — written beside the brief, in a
directory the agent already mounts and already reads, and put into storage by
the agent when the dive is over. Lines of JSON rather than a database, because
a recording is something a person should be able to open with nothing.

Poses and sensors at a steady rate of simulated time, not wall-clock: two runs
of the same seed leave the same recording.
"""

from __future__ import annotations

import json
import math
import pathlib

import numpy as np


class Recorder:
    def __init__(self, into: pathlib.Path, hz: float = 5.0, frames_hz: float = 1.0) -> None:
        self.into = into
        self.frames = into / "frames"
        self.every = 1.0 / hz
        self.frame_every = 1.0 / frames_hz
        self.into.mkdir(parents=True, exist_ok=True)
        self.frames.mkdir(parents=True, exist_ok=True)
        # Line-buffered, so a dive that is stopped without ceremony still
        # leaves every line it wrote; a manifest is rewritten as it goes for
        # the same reason.
        self._poses = (self.into / "poses.jsonl").open("w", buffering=1)
        self._sensors = (self.into / "sensors.jsonl").open("w", buffering=1)
        self._task = (self.into / "task.jsonl").open("w", buffering=1)
        self.last_manifest = -1e9
        self.camera: dict | None = None
        self.last_pose = -1e9
        self.last_task = -1e9
        self.last_frame = -1e9
        self.poses = 0
        self.frames_taken = 0
        self.frame_name: str | None = None
        self._site: dict | None = None

    def due_frame(self, t: float) -> str | None:
        """The frame file to write now, or None; the caller captures it."""
        if t - self.last_frame < self.frame_every:
            return None
        self.last_frame = t
        self.frames_taken += 1
        self.frame_name = f"frames/{self.frames_taken:06d}.jpg"
        return str(self.into / self.frame_name)

    def step(self, dive) -> None:
        t = float(dive.simulated)
        if t - self.last_pose < self.every:
            return
        self.last_pose = t
        R = dive.rotation
        pose = {
            "t": round(t, 3),
            "position": [round(float(v), 4) for v in dive.position],
            "quaternion": [round(float(v), 5) for v in _quaternion(R)],
            "headingDeg": round(math.degrees(math.atan2(float(R[1, 0]), float(R[0, 0]))), 2),
            "depthM": round(float(-dive.position[2]), 4),
            "velocity": [round(float(v), 4) for v in dive.velocity[:3]],
            "rates": [round(float(v), 4) for v in dive.velocity[3:]],
            "view": dive.view,
            "frame": self.frame_name,
        }
        floor = dive.floor
        if dive.seabed is not None:
            floor = dive.seabed.under(float(dive.position[0]), float(dive.position[1]))
        pose["altitudeM"] = None if floor is None else round(float(dive.position[2]) - floor, 4)
        self._poses.write(json.dumps(pose) + "\n")
        self._sensors.write(json.dumps({"t": round(t, 3), **dive.samples()}) + "\n")
        self.poses += 1
        if dive.task is not None and t - self.last_task >= 1.0:
            self.last_task = t
            self._task.write(json.dumps({"t": round(t, 3), **dive.task.progress()}) + "\n")
        if t - self.last_manifest >= 5.0:
            self.last_manifest = t
            (self.into / "manifest.json").write_text(json.dumps(self.manifest(dive, self.camera, closed=False), indent=2))

    def close(self, dive, camera: dict | None) -> dict:
        for handle in (self._poses, self._sensors, self._task):
            handle.flush()
            handle.close()
        manifest = self.manifest(dive, camera, closed=True)
        (self.into / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest

    def manifest(self, dive, camera: dict | None, closed: bool) -> dict:
        # The chart a replay draws needs what a console is handed on arrival:
        # the bottom as a coarse grid, the coral, and what the task asked for.
        # Kept in the recording, so a replay stands on its own — the site may
        # have a newer version by then, and this is the one it was flown on.
        if self._site is None:
            try:
                self._site = dive.hello().get("site") or {}
            except Exception:
                self._site = {}
        geometry = None
        if dive.task is not None:
            try:
                geometry = dive.task.geometry()
            except Exception:
                geometry = None
        manifest = {
            "site": self._site or None,
            "geometry": geometry,
            "poses": self.poses,
            "frames": self.frames_taken,
            "posesHz": round(1.0 / self.every, 2),
            "framesHz": round(1.0 / self.frame_every, 2),
            "seconds": round(float(dive.simulated), 3),
            "beganAt": [round(float(v), 3) for v in dive.began_at],
            "camera": camera,
            "task": None if dive.task is None else dive.task.result(),
            "files": ["poses.jsonl", "sensors.jsonl", "task.jsonl", "manifest.json"],
            "closed": closed,
        }
        return manifest


def _quaternion(m: np.ndarray) -> tuple[float, float, float, float]:
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        s = (trace + 1.0) ** 0.5 * 2.0
        return (0.25 * s, float(m[2, 1] - m[1, 2]) / s, float(m[0, 2] - m[2, 0]) / s, float(m[1, 0] - m[0, 1]) / s)
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = (1.0 + m[0, 0] - m[1, 1] - m[2, 2]) ** 0.5 * 2.0
        return (float(m[2, 1] - m[1, 2]) / s, 0.25 * s, float(m[0, 1] + m[1, 0]) / s, float(m[0, 2] + m[2, 0]) / s)
    if m[1, 1] > m[2, 2]:
        s = (1.0 + m[1, 1] - m[0, 0] - m[2, 2]) ** 0.5 * 2.0
        return (float(m[0, 2] - m[2, 0]) / s, float(m[0, 1] + m[1, 0]) / s, 0.25 * s, float(m[1, 2] + m[2, 1]) / s)
    s = (1.0 + m[2, 2] - m[0, 0] - m[1, 1]) ** 0.5 * 2.0
    return (float(m[1, 0] - m[0, 1]) / s, float(m[0, 2] + m[2, 0]) / s, float(m[1, 2] + m[2, 1]) / s, 0.25 * s)
