"""Flying over a place to see what it is.

Every judgement about this reef was being made from a single frame, three metres
off the bottom, pointing one way. That is the worst possible view for the
questions that actually matter — is the coral in the right places, is the cover
right, does the shore look like a shore — and it is why those questions kept
being answered wrong.

So: a camera on a path. The whole site from above, a descent onto the reef, a
run across it, and a low pass through the coral. What comes back is a video
somebody can criticise.

Nothing here touches the dive. The place, the water and the light are exactly
what a dive gets; only the camera is different, and no physics runs at all.
"""

from __future__ import annotations

import math

# A fifth of the flight is out of the water, which is enough to read the layout
# and no more. The rest is in it, because the water is the thing being built and
# a video that is mostly a map is a video of the wrong subject.
SECONDS = 30.0
FRAMES_A_SECOND = 24

# From above, with the surface taken away. A kilometre of reef cannot be seen
# from inside water that is thirty metres deep — the only vantage that holds it
# is from the air, and from the air all there is to see is the surface, which
# from that side is opaque.
PLAN = "from above, surface hidden"
# Under the water, with the scattering turned off. Same seabed, same coral, same
# light; what goes is the fifteen metres of visibility, which is the truth about
# this water and is also a blue wall at any height worth surveying from.
CLEARED = "cleared, to see the shape of the place"
# And the water as it is, which is what a vehicle will be looking through. Only
# the last leg, and only close to the bottom: at any altitude the fog is the
# whole picture, which is true and is not worth twenty seconds of video.
AS_DIVED = "as a dive sees it"


def _lerp(a, b, t):
    return a + (b - a) * t


def _ahead(eye, heading, lead: float):
    """A point on the bottom, that far in front of the camera.

    Aiming at a fixed landmark makes the camera swing wildly as it passes it,
    and aiming at the horizon aims through the whole site. Aiming a fixed
    distance ahead keeps the pitch steady and the subject close.
    """
    length = math.hypot(*heading) or 1.0
    return (eye[0] + heading[0] / length * lead,
            eye[1] + heading[1] / length * lead,
            1.0)


def where_to_look(at: float, across: float):
    """Where the camera is and what it looks at, this far into the flight.

    Heights are given as metres above the seabed rather than as depths, because
    a fringing reef runs from ankle-deep to forty metres across one site and a
    fixed depth is either buried at one end or in the air at the other. The one
    exception is the plan view, which is above the water and says so.

    Returns the eye, the target, how far the camera can see, and whether the
    heights are above the bottom or above the sea.
    """
    span = across / 2

    if at < 0.14:
        # The plan view: the whole site at once, turning slowly so the relief
        # reads. This is the view that shows where the coral is, which is the
        # one thing a frame taken from the seabed can never show.
        t = at / 0.14
        turn = _lerp(-0.30, 0.30, t)
        eye = (math.sin(turn) * span * 0.30,
               math.cos(turn) * span * 0.30 - span * 0.30,
               _lerp(across * 0.72, across * 0.52, t))
        target = (0.0, 0.0, 0.0)
        return eye, target, PLAN, "sea"

    if at < 0.30:
        # Down through the surface and onto the reef. Cleared for the second
        # half, so the slope and the spur-and-groove stay readable all the way.
        t = (at - 0.14) / 0.16
        eye = (_lerp(span * 0.09, -span * 0.26, t),
               _lerp(-span * 0.21, -span * 0.30, t),
               _lerp(across * 0.52, 14.0, t ** 1.9))
        target = (_lerp(0.0, -span * 0.10, t), _lerp(0.0, -span * 0.06, t), 0.0)
        return eye, target, PLAN if t < 0.45 else CLEARED, "sea" if t < 0.45 else "bottom"

    if at < 0.62:
        # Across the reef from the crest to the terrace, at the height a survey
        # flies — and looking down at it rather than along it. A camera at that
        # height aimed at the horizon is aimed through four hundred metres of
        # water, and four hundred metres of any water is a flat wash. What is
        # wanted is the ground, so the camera looks at the ground.
        t = (at - 0.30) / 0.32
        up = _lerp(15.0, 11.0, t)
        eye = (_lerp(-span * 0.26, span * 0.24, t),
               _lerp(-span * 0.30, span * 0.16, t), up)
        target = _ahead(eye, (span * 0.50, span * 0.46), up * 1.5)
        return eye, target, CLEARED, "bottom"

    # And low through it, in the vehicle's own water, where the coral is taller
    # than the vehicle and fifteen metres is all anybody gets.
    t = (at - 0.62) / 0.38
    up = _lerp(11.0, 2.6, min(1.0, t * 2.2))
    eye = (_lerp(span * 0.24, -span * 0.06, t),
           _lerp(span * 0.16, -span * 0.10, t), up)
    target = _ahead(eye, (-span * 0.30, -span * 0.26), max(9.0, up * 2.4))
    return eye, target, CLEARED if t < 0.18 else AS_DIVED, "bottom"


class Tour:
    """Runs the camera along the path, one frame at a time."""

    def __init__(self, across: float, floor_at, say) -> None:
        self.across = across
        # Where the bottom is, anywhere in the site. The same sampler a dive
        # flies over, so a height in this flight means what it means in a dive.
        self.floor_at = floor_at
        self.say = say
        self.frames = int(SECONDS * FRAMES_A_SECOND)
        self.taken = 0
        self.waiting = False
        self.seeing = None
        self.tidied = False

    @property
    def done(self) -> bool:
        return self.taken >= self.frames

    def _height(self, x: float, y: float, up: float, above: str) -> float:
        if above == "sea":
            return up
        floor = self.floor_at(x, y)
        if floor is None:
            floor = -20.0
        return float(floor) + up

    def _far(self) -> float:
        return max(400.0, self.across * 1.4)

    def _tidy(self) -> None:
        """Take away everything that is about editing rather than looking.

        Kit draws a construction grid and an origin axis over the viewport,
        which in a video of a reef is a wireframe box over the whole ocean.
        """
        import carb

        settings = carb.settings.get_settings()
        settings.set("/app/viewport/grid/enabled", False)
        settings.set("/app/viewport/show/axis", False)
        settings.set("/app/viewport/outline/enabled", False)
        settings.set("/persistent/app/viewport/displayOptions", 0)
        self.tidied = True

    def _see(self, stage, sees: str) -> None:
        """Set how far the camera can see, and say so on the way past."""
        import carb
        from pxr import UsdGeom

        if sees == self.seeing:
            return
        self.seeing = sees
        settings = carb.settings.get_settings()

        # Two things are only in the way when looking down at the site from
        # outside it: the surface, which from above is opaque, and the caustics
        # light, whose rectangular footprint from seven hundred metres up is a
        # hard-edged bright panel across a third of the reef.
        for path in ("/World/Surface", "/World/Caustics"):
            prim = stage.GetPrimAtPath(path)
            if prim and prim.IsValid():
                shown = UsdGeom.Imageable(prim)
                shown.MakeInvisible() if sees == PLAN else shown.MakeVisible()

        if sees == PLAN:
            # No haze at all. Seven hundred metres of even a very long fog is
            # still seven hundred metres of it, and the plan view exists to
            # show the ground rather than the water over it.
            settings.set("/rtx/fog/enabled", False)
        elif sees == CLEARED:
            settings.set("/rtx/fog/enabled", True)
            # Not "no fog": a haze reaching for hundreds of metres still reads
            # as water and still puts distance in the picture. What goes is the
            # fifteen metres.
            settings.set("/rtx/fog/fogDistance", self._far())
            settings.set("/rtx/fog/fogStartDistance", 40.0)
            settings.set("/rtx/fog/fogColorIntensity", 0.75)
        else:
            settings.set("/rtx/fog/enabled", True)
            settings.set("/rtx/fog/fogDistance", 15.0)
            settings.set("/rtx/fog/fogStartDistance", 3.0)
            settings.set("/rtx/fog/fogColorIntensity", 1.35)

        self.say("tour_sees", how=sees, atFrame=self.taken)

    def place(self, stage, viewport) -> None:
        """Point the camera wherever this frame wants it."""
        from pxr import Gf, UsdGeom

        if not self.tidied:
            self._tidy()

        eye, target, sees, above = where_to_look(
            self.taken / max(1, self.frames), self.across)
        self._see(stage, sees)

        eye = (eye[0], eye[1], self._height(eye[0], eye[1], eye[2], above))
        target = (target[0], target[1],
                  self._height(target[0], target[1], target[2], "bottom"))

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
