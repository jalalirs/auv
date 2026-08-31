"""Coral City, running.

The application starts, this reads the brief the agent wrote, opens the place,
puts the vehicle in it and steps the same dive the headless runner steps. The
difference is only in the schedule: here it advances by wall-clock time, because
a person is watching and a controller is flying, and a dive that ran two
thousand steps in half a second would be over before either noticed.

Nothing about the physics is decided here. If it were, an interactive dive and a
batch dive of the same brief could disagree, and the whole claim that a replay
is a replay would be worth nothing.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import carb
import omni.ext
import omni.kit.app
import omni.usd

from .controls import Controls
from .hud import Hud

# Where the runtime keeps the dive: the physics, the boundary, and the loader
# the headless runner uses too.
CORAL = pathlib.Path("/isaac-sim/coral")

# How far behind wall-clock time the physics is allowed to fall before it stops
# trying to catch up. Without a bound, one slow frame makes the next frame ask
# for more steps, which makes it slower still.
MOST_CATCHUP_SECONDS = 0.25

# When to photograph the dive, in simulated seconds. Early, so that a run that
# went wrong still left a picture of the place it went wrong in, and at the end,
# so there is something to look at afterwards.
#
# A dive should leave more than numbers. Somebody reading a run a week later can
# tell from one frame whether the vehicle was in the water it was meant to be in,
# and no amount of telemetry says that as quickly.
PHOTOGRAPH_AT = (2.0, 30.0)


def _inherit_pythonpath() -> None:
    """Put PYTHONPATH on the path, which Kit's interpreter does not do itself.

    Isaac Sim ships a complete ROS 2 Jazzy Python stack and leaves it off the
    interpreter's path; the image says where it is, and python.sh honours that.
    Kit embeds its own interpreter and builds sys.path itself, so inside the
    application the same import fails and the vehicle comes up with no way for
    anything to fly it — reported, quietly, as one line about rclpy.

    The image remains the one place that says where ROS is. This only makes the
    embedded interpreter believe it.
    """
    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if entry and entry not in sys.path:
            sys.path.append(entry)


class CoralCityShell(omni.ext.IExt):
    """The dive, and everything a person sees of it."""

    def on_startup(self, extension_id: str) -> None:
        self.dive = None
        self.hud = None
        self.update = None
        self.began = None
        self.waiting_until = None
        self.finished = False
        self.photographs = list(PHOTOGRAPH_AT)
        self.controls = None
        self.watch = None
        self._frames = None
        self._product = None
        self._every = 3
        self._since = 0
        self._capturing = False
        self._complained = False
        self._latest_state = {}
        self._alone_since = None
        self._watch_port = int(os.environ.get("CORAL_CITY_WATCH_PORT", "18102"))

        if str(CORAL) not in sys.path:
            sys.path.insert(0, str(CORAL))
        _inherit_pythonpath()

        self.hud = Hud()
        self.hud.opened("opening the place…", "")
        try:
            self.controls = Controls()
        except Exception as exc:
            # A dive nobody can fly by hand is still a dive. Autonomy does not
            # need a keyboard.
            carb.log_warn(f"Coral City has no keyboard: {exc}")

        # Subscribed before anything is loaded, so that a failure to open has
        # somewhere to be reported rather than a black window.
        self.update = (omni.kit.app.get_app().get_update_event_stream()
                       .create_subscription_to_pop(self._frame, name="coral.city.dive"))

        try:
            self._open()
        except Exception as exc:  # a shell that dies silently is worse than one that says so
            carb.log_error(f"Coral City could not open the dive: {exc}")
            self.hud.opened("this dive would not open", str(exc)[:120])

    # ── opening ──────────────────────────────────────────────────────────────

    def _open(self) -> None:
        from dive import prepare, seed_everything
        from runner import Dive

        brief_path = os.environ.get("CORAL_CITY_BRIEF", "/dive/dive.json")
        brief = json.loads(pathlib.Path(brief_path).read_text())
        seed_everything(int(brief.get("seed", 0)))
        self.brief = brief

        prepared = prepare(brief, self._say)
        if prepared is None:
            self.hud.opened("this dive is not runnable", "")
            return
        scene, body, allocator = prepared

        dive = Dive(brief, body, allocator, scene, self._say)
        if not dive.open(drawn=True):
            self.hud.opened("the place would not open", str(scene))
            return
        dive.connect()
        self.dive = dive

        self.hud.opened(
            brief.get("cityName") or scene.stem,
            brief.get("vehicleName") or f"{body.model.mass_kg:g} kg, "
                                        f"{len(body.model.thrusters)} thrusters")
        self._watch_from(dive)

        if dive.bridge is not None:
            self.waiting_until = time.monotonic() + float(
                brief.get("autonomyWaitSeconds", 60.0))
        else:
            self.began = time.monotonic()

    def _watch_from(self, dive) -> None:
        """Put the camera where the vehicle can be seen from.

        Behind, above, and looking down slightly — the view you would want from
        a chase boat. It does not follow: a camera that chases the vehicle makes
        the vehicle look still and the water look moving, which is exactly
        backwards for judging whether a controller is holding depth.
        """
        try:
            from omni.kit.viewport.utility import get_active_viewport
            from pxr import Gf, UsdGeom

            viewport = get_active_viewport()
            if viewport is None:
                return
            stage = omni.usd.get_context().get_stage()
            camera_path = "/World/CoralCityCamera"
            camera = UsdGeom.Camera.Define(stage, camera_path)
            camera.CreateFocalLengthAttr(24.0)
            near = 0.02 * dive.units_per_metre
            camera.CreateClippingRangeAttr(Gf.Vec2f(near, near * 500000.0))

            # In the stage's units and the stage's idea of up, not ours. Four
            # and a half metres behind the vehicle is four and a half metres
            # whatever the author of the place measured in.
            x, y, z = dive.position
            at = dive.drawn_at((x, y, z))
            # Kept well under the surface. The first attempt sat twenty
            # centimetres below it, and the underside of the water filled the
            # frame — a convincing picture of nothing.
            from_ = dive.drawn_at((x - 3.4, y - 3.4, z + 0.9))
            up = Gf.Vec3d(0.0, 1.0, 0.0) if dive.up_axis == "Y" else Gf.Vec3d(0.0, 0.0, 1.0)
            # Aimed rather than angled. The first attempt set pitch and yaw by
            # hand, which is a guess that happens to be right for one starting
            # depth and wrong for every other; this is right for all of them.
            look = Gf.Matrix4d().SetLookAt(from_, at, up).GetInverse()
            transform = UsdGeom.Xformable(camera.GetPrim())
            transform.ClearXformOpOrder()
            transform.AddTransformOp().Set(look)
            viewport.camera_path = camera_path
            self._open_the_window(camera_path)
            # Read back rather than assumed. Setting it is one line and failing
            # to set it looks exactly the same from here — you get a picture
            # either way, just not of what you aimed at.
            self._say("camera", wanted=camera_path,
                      looking_through=str(viewport.camera_path),
                      eye=[round(float(v), 2) for v in from_])
        except Exception as exc:
            carb.log_warn(f"Coral City could not place the camera: {exc}")

    # ── running ──────────────────────────────────────────────────────────────

    def _frame(self, event) -> None:
        dive = self.dive
        if dive is None or self.finished:
            return

        # Waiting for somebody to take the controls. The vehicle publishes while
        # it waits, because a vehicle sitting in the water still has a depth,
        # and saying nothing until commanded deadlocks against a controller
        # waiting for a reading to respond to.
        if self.waiting_until is not None:
            if self.controls is not None and self.controls.flying:
                # Somebody has taken hold of it. There is nothing left to wait
                # for — the vehicle is being flown, which is what the wait was
                # for.
                self._say("pilot_took_the_controls")
                self.waiting_until = None
                self.began = time.monotonic()
            elif dive.bridge is not None and dive.bridge.commanded:
                self._say("autonomy_ready", waitedSeconds=0.0)
                self.waiting_until = None
                self.began = time.monotonic()
            elif time.monotonic() >= self.waiting_until:
                self._say("autonomy_absent",
                          waitedSeconds=float(self.brief.get("autonomyWaitSeconds", 60.0)))
                self.hud.untended()
                self.waiting_until = None
                self.began = time.monotonic()
            else:
                dive.publish()
                self.hud.waiting(self.waiting_until - time.monotonic())
                self.hud.show(dive.state())
                return

        if self.controls is not None:
            dive.take_the_controls(self.controls.wrench())

        # Advance to where wall-clock time says the vehicle should be. The
        # physics step is fixed; what varies is how many of them a frame is
        # worth, which is the only way a fixed-step integrator and a variable
        # frame rate can both be true.
        behind = min((time.monotonic() - self.began) - dive.simulated,
                     MOST_CATCHUP_SECONDS)
        steps = int(behind / dive.dt)
        for _ in range(steps):
            if dive.done:
                break
            dive.step()

        dive.show()
        self.hud.show(dive.state())
        if self.photographs and dive.simulated >= self.photographs[0]:
            self._photograph(round(self.photographs.pop(0), 1))
        self._send_a_frame(dive.state())
        if dive.flown_by_hand:
            self.hud.by_hand()
        elif dive.bridge is not None and dive.bridge.commanded:
            self.hud.flying(dive.bridge.commands_seen)

        if dive.done:
            self.finished = True
            dive.close()
            self._say("succeeded", simulatedSeconds=round(dive.simulated, 3))
            self.hud.finished()

    def _open_the_window(self, camera_path: str) -> None:
        """Start sending frames to whoever is watching from elsewhere.

        Through the viewport's own capture rather than Replicator. Replicator is
        the documented way to render headlessly and it does not load in this
        application — its plugin wants a PhysX symbol that is not there — while
        the viewport capture is already proven here, because it is what takes
        the photographs a dive leaves behind.
        """
        try:
            from .watch import FRAMES_PER_SECOND, Watch

            self.watch = Watch(self._watch_port, self.controls, self._say)
            self._every = max(1, int(round(60.0 / FRAMES_PER_SECOND)))
        except Exception as exc:
            carb.log_warn(f"Coral City cannot be watched from elsewhere: {exc}")
            self._say("watch_unavailable", why=str(exc)[:200])

    def _send_a_frame(self, state: dict) -> None:
        """One frame to the watchers, if anybody is there and it is time.

        Asked for, not waited on. The capture arrives on a later frame through a
        callback, and blocking the simulation until a picture is ready would
        make how fast the vehicle flies depend on how fast somebody's screen
        draws.
        """
        if self.watch is None or not self.watch.watched:
            return
        self._since += 1
        if self._since < self._every or self._capturing:
            return
        self._since = 0

        try:
            from omni.kit.viewport.utility import capture_viewport_to_buffer, get_active_viewport

            viewport = get_active_viewport()
            if viewport is None:
                return
            self._latest_state = state
            self._capturing = True
            capture_viewport_to_buffer(viewport, self._encode)
        except Exception as exc:
            self._capturing = False
            carb.log_warn(f"Coral City could not ask for a frame: {exc}")

    def _encode(self, buffer, size, wide, tall, fmt=None) -> None:
        """Turn a captured frame into something a socket can carry."""
        self._capturing = False
        try:
            import ctypes

            import cv2
            import numpy as np

            # The capture hands back an address, not a pointer. Casting an
            # integer as though it were already one fails with "argument 1:
            # wrong type" — fifty times a second, in a warning nobody reads,
            # while the screen stays black and everything else looks correct.
            held = buffer if not isinstance(buffer, int) else ctypes.c_void_p(buffer)
            pointer = ctypes.cast(held, ctypes.POINTER(ctypes.c_ubyte * size))
            frame = np.frombuffer(pointer.contents, dtype=np.uint8)
            frame = frame.reshape(tall, wide, 4)
            # The capture is RGBA and the encoder wants BGR. Getting that
            # backwards produces a picture correct in every respect except that
            # the water is orange.
            ok, jpeg = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR),
                                    [int(cv2.IMWRITE_JPEG_QUALITY), 72])
            if ok:
                self.watch.send(jpeg.tobytes(), self._latest_state)
        except Exception as exc:
            # Once, not once per frame. A fault in a loop that runs twenty times
            # a second writes its own haystack.
            if not self._complained:
                self._complained = True
                carb.log_error(f"Coral City could not encode a frame: {exc}")
                self._say("frames_unavailable", why=str(exc)[:200])

    def _photograph(self, at: float) -> None:
        """Write out what the dive looks like.

        Beside the brief, which is a directory the agent already mounted and
        already reads — so a picture needs no new path, no new permission and no
        way out of the container that did not already exist.
        """
        try:
            from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport

            viewport = get_active_viewport()
            if viewport is None:
                return
            where = pathlib.Path(
                os.environ.get("CORAL_CITY_BRIEF", "/dive/dive.json")).parent
            path = where / f"frame-{at:g}s.png"
            capture_viewport_to_file(viewport, str(path))
            self._say("photograph", at=at, path=str(path))
        except Exception as exc:
            carb.log_warn(f"Coral City could not photograph the dive: {exc}")

    # ── reporting ────────────────────────────────────────────────────────────

    def _say(self, kind: str, **detail) -> None:
        """The same line the headless runner writes.

        One format, whoever is watching: the agent reads this output to know
        what happened, and a dive that reported differently depending on whether
        somebody was looking at it would be two dives.
        """
        print(json.dumps({"event": kind, **detail}, separators=(", ", ": ")),
              flush=True)

    def on_shutdown(self) -> None:
        if self.update is not None:
            self.update = None
        if self.dive is not None and not self.finished:
            self.dive.close()
            self.dive = None
        if self.watch is not None:
            self.watch.close()
            self.watch = None
        if self.controls is not None:
            self.controls.close()
            self.controls = None
        if self.hud is not None:
            self.hud.close()
            self.hud = None
