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

        if str(CORAL) not in sys.path:
            sys.path.insert(0, str(CORAL))
        _inherit_pythonpath()

        self.hud = Hud()
        self.hud.opened("opening the place…", "")

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
            camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 5000.0))

            x, y, z = (float(v) for v in dive.position)
            eye = Gf.Vec3d(x - 4.5, y - 4.5, z + 1.8)
            # Aimed rather than angled. The first attempt set pitch and yaw by
            # hand, which is a guess that happens to be right for one starting
            # depth and wrong for every other; this is right for all of them.
            look = Gf.Matrix4d().SetLookAt(eye, Gf.Vec3d(x, y, z),
                                           Gf.Vec3d(0.0, 0.0, 1.0)).GetInverse()
            transform = UsdGeom.Xformable(camera.GetPrim())
            transform.ClearXformOpOrder()
            transform.AddTransformOp().Set(look)
            viewport.camera_path = camera_path
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
            if dive.bridge is not None and dive.bridge.commanded:
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
        if dive.bridge is not None and dive.bridge.commanded:
            self.hud.flying(dive.bridge.commands_seen)

        if dive.done:
            self.finished = True
            dive.close()
            self._say("succeeded", simulatedSeconds=round(dive.simulated, 3))
            self.hud.finished()

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
        if self.hud is not None:
            self.hud.close()
            self.hud = None
