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
    # How many pictures a second of the dive the recording keeps.
    #
    # It was one, which is a slideshow: four hundred seconds of dive came back
    # as three hundred and seventy stills, and no amount of downloading them
    # first makes one picture a second look like movement. Eight is a dive
    # somebody can watch, and as video rather than as eight files a second it
    # is smaller than the stills were.
    FRAMES_HZ = 8.0

    def __init__(self, into: pathlib.Path, hz: float = 5.0, frames_hz: float = FRAMES_HZ) -> None:
        self.into = into
        self.frames = into / "frames"
        self.every = 1.0 / hz
        self.frame_every = 1.0 / frames_hz
        self.into.mkdir(parents=True, exist_ok=True)
        # The dive as one video, whose clock is the dive's clock: a frame is
        # captured every eighth of a simulated second and encoded at eight a
        # second, so a moment in the recording is at that many seconds in the
        # video and a player can simply be told where to go.
        self.video = None
        self.video_name = "dive.mp4"
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

    def due(self, t: float) -> bool:
        """Whether a picture is owed at this moment of the dive."""
        if t - self.last_frame < self.frame_every:
            return False
        self.last_frame = t
        return True

    def captured(self) -> None:
        """A frame has actually been written into the video.

        Counted here rather than when one is owed, because the two are not the
        same: a capture that was still in flight when the next was due is a
        frame the video does not have, and a pose pointing at a frame that was
        never written is a replay showing the wrong moment. The pose points at
        the frame's place in the video, and the video is played by going to it.
        """
        self.frames_taken += 1
        self.frame_name = f"{self.video_name}#{self.frames_taken - 1}"

    def video_wanted(self) -> tuple[int, str]:
        """What an encoder for this recording should be: its rate, and where.

        The encoder itself belongs to whoever can capture a frame — the shell
        extension — because it is the only thing that knows how big a frame is
        until one arrives. This says what it should be told.
        """
        return int(round(1.0 / self.frame_every)), str(self.into / self.video_name)

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
            # Where this frame was seen from, so a replay can paint the world
            # back onto it. Absent on a dive nobody rendered, which is fine:
            # there is no picture to paint on either.
            "camera": getattr(dive, "looking", None),
        }
        floor = dive.floor
        if dive.seabed is not None:
            floor = dive.seabed.under(float(dive.position[0]), float(dive.position[1]))
        pose["altitudeM"] = None if floor is None else round(float(dive.position[2]) - floor, 4)
        # Where the vehicle believes it is, beside where it is. The gap between
        # those two is the whole of what a positioning technology buys, and it
        # is worth having on the frame rather than only in a plot.
        navigation = getattr(dive, "navigation", None)
        if navigation is not None:
            pose["believed"] = [round(float(v), 3) for v in navigation.believed]
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
        if self.video:
            # Finished rather than killed: the index at the front of a video is
            # written as the encoder closes, and without it nothing will play.
            self.video.stop()
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
        # What was deployed in this water to give fixes, and where it sits:
        # the array's transponders, the ship overhead, the beacon on the dock.
        # A replay that draws the vehicle believing itself somewhere it is not
        # should be able to draw what would have told it otherwise.
        positioning = None
        try:
            positioning = dive.positioning_said()
        except Exception:
            positioning = None
        manifest = {
            "site": self._site or None,
            "geometry": geometry,
            "positioning": positioning,
            "vehicle": {"halfWidthM": round(float(getattr(dive, "half_width", 0.25)), 3),
                        "halfHeightM": round(float(getattr(dive, "half_height", 0.15)), 3),
                        "offsetM": list(getattr(dive, "hull_offset", [0.0, 0.0, 0.0]))},
            "poses": self.poses,
            "frames": self.frames_taken,
            "posesHz": round(1.0 / self.every, 2),
            "framesHz": round(1.0 / self.frame_every, 2),
            "seconds": round(float(dive.simulated), 3),
            "beganAt": [round(float(v), 3) for v in dive.began_at],
            "camera": camera,
            "task": None if dive.task is None else dive.task.result(),
            "video": {"file": self.video_name,
                       "framesPerSecond": round(1.0 / self.frame_every, 2),
                       "frames": self.frames_taken} if self.video else None,
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
