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

# How far the camera can see, per leg. A dive sees fifteen metres, which is the
# truth about this water and useless for looking at a kilometre of reef: from
# any height that holds the whole site, fifteen metres of visibility is a blue
# rectangle. So the overview legs are flown in water that has been cleared —
# the same seabed, the same coral, the same light, with the scattering turned
# off — and the video says so. The last two legs are flown in the real water,
# which is what a vehicle will actually be looking through.
# From above, with the surface taken away. A kilometre of reef cannot be seen
# from inside water that is thirty metres deep — the only vantage that holds it
# is from the air, and from the air all there is to see is the surface, which
# from that side is opaque. So for this leg the surface is hidden.
PLAN = "from above, surface hidden"
# Under the water, with the scattering turned off. Same seabed, same coral,
# same light; what goes is the fifteen metres of visibility, which is the truth
# about this water and is also a blue wall at any useful height.
CLEARED = "cleared, to see the shape of the place"
# And the water as it is, which is what a vehicle will be looking through.
AS_DIVED = "as a dive sees it"

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
    """Camera position, target, and how far it can see, this far into the tour.

    Four legs: the whole map from above, a descent onto the reef, a run across
    it at the height a survey flies, and a low pass through the coral.

    Everything happens below the surface. The camera is in the water for the
    whole flight — from above the surface all there is to see is the surface,
    which is opaque from that side and is not the thing being looked at.
    """
    span = across / 2

    if at < 0.24:
        # The plan view: the whole site at once, turning slowly so the relief
        # reads. This is the view that shows where the coral is, which is the
        # one thing a frame taken from the seabed can never show.
        t = at / 0.24
        height = _lerp(across * 0.72, across * 0.52, t)
        turn = _lerp(-0.30, 0.30, t)
        eye = (math.sin(turn) * span * 0.30, math.cos(turn) * span * 0.30 - span * 0.30,
               height)
        target = (0.0, 0.0, -reef_depth)
        sees = PLAN

    elif at < 0.42:
        # Down through the surface and onto the reef, still cleared, so the
        # slope and the spur-and-groove stay readable the whole way in.
        t = (at - 0.24) / 0.18
        eye = (_lerp(span * 0.09, -span * 0.26, t),
               _lerp(-span * 0.21, -span * 0.30, t),
               _lerp(across * 0.52, -reef_depth + 26.0, t ** 1.7))
        target = (_lerp(0.0, -span * 0.10, t), _lerp(0.0, -span * 0.06, t), -reef_depth)
        sees = PLAN if t < 0.62 else CLEARED

    elif at < 0.78:
        # Across the reef at the height a survey flies, in the vehicle's own
        # water. Everything from here is what a dive will look like.
        t = (at - 0.42) / 0.36
        eye = (_lerp(-span * 0.26, span * 0.24, t),
               _lerp(-span * 0.30, span * 0.16, t),
               _lerp(-reef_depth + 26.0, -reef_depth + 9.0, t))
        target = (_lerp(-span * 0.10, span * 0.46, t),
                  _lerp(-span * 0.06, span * 0.30, t),
                  -reef_depth - 1.5)
        sees = AS_DIVED

    else:
        # And low through it, where the coral is taller than the vehicle.
        t = (at - 0.78) / 0.22
        eye = (_lerp(span * 0.24, span * 0.02, t),
               _lerp(span * 0.16, -span * 0.04, t),
               _lerp(-reef_depth + 9.0, -reef_depth + 2.6, t))
        target = (_lerp(span * 0.46, -span * 0.16, t),
                  _lerp(span * 0.30, -span * 0.10, t),
                  -reef_depth - 1.0)
        sees = AS_DIVED

    return eye, target, sees


class Tour:
    """Runs the camera along the path, one frame at a time."""

    def __init__(self, across: float, reef_depth: float, say) -> None:
        self.across = across
        self.reef_depth = reef_depth
        self.say = say
        self.frames = int(SECONDS * FRAMES_A_SECOND)
        self.taken = 0
        self.waiting = False
        self.seeing = None
        self.tidied = False

    @property
    def done(self) -> bool:
        return self.taken >= self.frames

    def _see_far(self) -> float:
        return max(400.0, self.across * 1.4)

    def _tidy(self, stage) -> None:
        """Take away everything that is about editing rather than looking.

        Kit draws a construction grid and an origin axis over the viewport,
        which in a video of a reef is a wireframe box over the whole ocean.
        """
        import carb

        settings = carb.settings.get_settings()
        for name in ("/app/viewport/grid/enabled",
                     "/app/viewport/show/axis",
                     "/app/viewport/outline/enabled",
                     "/persistent/app/viewport/displayOptions"):
            if name.endswith("displayOptions"):
                settings.set(name, 0)
            else:
                settings.set(name, False)
        self.tidied = True

    def _see(self, stage, sees: str) -> None:
        """Set how far the camera can see, and say so on the way past."""
        import carb

        if sees == self.seeing:
            return
        self.seeing = sees
        settings = carb.settings.get_settings()

        # The surface, which is only in the way when looking down at the site
        # from outside it.
        surface = stage.GetPrimAtPath("/World/Surface")
        if surface and surface.IsValid():
            from pxr import UsdGeom
            UsdGeom.Imageable(surface).MakeInvisible() if sees == PLAN \
                else UsdGeom.Imageable(surface).MakeVisible()

        if sees != AS_DIVED:
            # Not "no fog": a haze that reaches for hundreds of metres still
            # reads as water and still puts distance in the picture. What goes
            # is the fifteen metres, which is what makes a survey height look
            # like a wall.
            settings.set("/rtx/fog/fogDistance", self._see_far())
            settings.set("/rtx/fog/fogStartDistance", 40.0)
            settings.set("/rtx/fog/fogColorIntensity", 0.75)
        else:
            settings.set("/rtx/fog/fogDistance", 15.0)
            settings.set("/rtx/fog/fogStartDistance", 3.0)
            settings.set("/rtx/fog/fogColorIntensity", 1.35)
        self.say("tour_sees", how=sees, atFrame=self.taken)

    def place(self, stage, viewport) -> None:
        """Point the camera wherever this frame wants it."""
        from pxr import Gf, UsdGeom

        if not self.tidied:
            self._tidy(stage)

        eye, target, sees = where_to_look(self.taken / max(1, self.frames),
                                          self.across, self.reef_depth)
        self._see(stage, sees)
        camera_path = "/World/TourCamera"
        camera = UsdGeom.Camera.Define(stage, camera_path)
        camera.CreateFocalLengthAttr(18.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 12000.0))

        look = Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()
        moving = UsdGeom.Xformable(camera.GetPrim())
        moving.ClearXformOpOrder()
        moving.AddTransformOp().Set(look)
        if str(viewport.camera_path) != camera_path:
            viewport.camera_path = camera_path
