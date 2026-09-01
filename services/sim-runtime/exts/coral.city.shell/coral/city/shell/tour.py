"""Flying over a place to see what it is.

Every judgement about this map so far has been made from a single frame, three
metres off the bottom, pointing one way. That is the worst possible view for
the questions that actually matter — is the coral in the right places, is the
cover right, does the shore look like a shore — and it is why those questions
kept being answered wrong.

So: a camera on a path. Straight down from high enough to see the whole
kilometre, then down onto the reef, then across it at working height. What
comes back is a video somebody can criticise.

Nothing here touches the dive. The place, the water and the light are exactly
what a dive gets; only the camera is different, and no physics runs at all.
"""

from __future__ import annotations

import math

# The path, as a sequence of legs. Each says how long it lasts, where the camera
# is, and where it looks — both as functions of how far through the leg it is.
#
# Heights are metres above the water, so they are positive going up and the
# seabed is somewhere below zero.
SECONDS = 26.0
FRAMES_A_SECOND = 24


def _lerp(a, b, t):
    return a + (b - a) * t


def where_to_look(at: float, across: float, reef_depth: float):
    """Camera position and target, this far into the tour.

    Four legs: the whole map from above, a slow descent onto the reef, a run
    across it at working height, and a low pass through the coral.
    """
    span = across / 2

    if at < 0.24:
        # Straight down from high enough to hold the whole site. This is the
        # view that shows where the reef actually is, which is the one thing a
        # frame from the seabed can never show.
        t = at / 0.24
        height = _lerp(across * 0.95, across * 0.62, t)
        turn = _lerp(0.0, 0.28, t)
        eye = (math.sin(turn) * span * 0.10, math.cos(turn) * span * 0.10 - 1.0, height)
        target = (0.0, 0.0, -reef_depth)

    elif at < 0.50:
        # Down onto the reef, tilting from looking down to looking along.
        t = (at - 0.24) / 0.26
        height = _lerp(across * 0.62, 26.0, t ** 1.4)
        eye = (_lerp(0.0, -span * 0.34, t), _lerp(-span * 0.10, -span * 0.30, t), height)
        target = (_lerp(0.0, -span * 0.10, t), 0.0, -reef_depth)

    elif at < 0.78:
        # Across the reef at the height an ROV surveys from, which is the view
        # the vehicle's own camera will have.
        t = (at - 0.50) / 0.28
        eye = (_lerp(-span * 0.34, span * 0.30, t), _lerp(-span * 0.30, span * 0.18, t),
               _lerp(26.0, 14.0, t))
        target = (_lerp(-span * 0.10, span * 0.55, t), _lerp(0.0, span * 0.35, t),
                  -reef_depth - 2.0)

    else:
        # And low through it, where the coral is taller than the vehicle.
        t = (at - 0.78) / 0.22
        eye = (_lerp(span * 0.30, span * 0.02, t), _lerp(span * 0.18, -span * 0.05, t),
               _lerp(14.0, -reef_depth + 4.0, t))
        target = (_lerp(span * 0.55, -span * 0.20, t), _lerp(span * 0.35, -span * 0.12, t),
                  -reef_depth - 1.0)

    return eye, target


class Tour:
    """Runs the camera along the path, one frame at a time."""

    def __init__(self, across: float, reef_depth: float, say) -> None:
        self.across = across
        self.reef_depth = reef_depth
        self.say = say
        self.frames = int(SECONDS * FRAMES_A_SECOND)
        self.taken = 0
        self.waiting = False

    @property
    def done(self) -> bool:
        return self.taken >= self.frames

    def place(self, stage, viewport) -> None:
        """Point the camera wherever this frame wants it."""
        from pxr import Gf, UsdGeom

        eye, target = where_to_look(self.taken / max(1, self.frames),
                                    self.across, self.reef_depth)
        camera_path = "/World/TourCamera"
        camera = UsdGeom.Camera.Define(stage, camera_path)
        camera.CreateFocalLengthAttr(20.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 12000.0))

        look = Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()
        moving = UsdGeom.Xformable(camera.GetPrim())
        moving.ClearXformOpOrder()
        moving.AddTransformOp().Set(look)
        if str(viewport.camera_path) != camera_path:
            viewport.camera_path = camera_path
