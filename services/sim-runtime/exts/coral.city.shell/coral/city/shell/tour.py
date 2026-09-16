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


def where_to_look(at: float, across: float, anchor, downhill):
    """Where the camera is and what it looks at, this far into the flight.

    The path is hung off two facts about the ground rather than off fractions
    of the site: where the reef is at the depth a vehicle works at, and which
    way the bottom falls away from there.

    The first version used fractions, which was right for a site built to a
    plan with its shore on a known edge and wrong for every surveyed one. On
    Looe Key it flew the reef flat: the survey leg finished in one metre of
    water and the low pass ended on ground with eighteen per cent cover, while
    the fore reef the vehicle would actually be deployed on — eight to twenty
    metres, sixty per cent cover, a third of the site — never appeared.

    Heights are metres above the seabed, except the plan view, which is above
    the sea and says so.
    """
    span = across / 2
    ax, ay = anchor
    dx, dy = downhill
    # Across the slope, for the legs that run along a contour rather than down.
    sx, sy = -dy, dx

    if at < 0.14:
        # The plan view: the whole site at once, turning slowly so the relief
        # reads. The one view that shows where the reef is, which is the one
        # thing a frame from the seabed can never show.
        t = at / 0.14
        turn = _lerp(-0.30, 0.30, t)
        eye = (math.sin(turn) * span * 0.30,
               math.cos(turn) * span * 0.30 - span * 0.30,
               _lerp(across * 0.72, across * 0.52, t))
        return eye, (0.0, 0.0, 0.0), PLAN, "sea"

    if at < 0.30:
        # Down through the surface and onto the reef, arriving above the ground
        # the site says a dive begins on.
        t = (at - 0.14) / 0.16
        up = _lerp(across * 0.52, 16.0, t ** 1.9)
        eye = (_lerp(ax - dx * span * 0.55, ax - dx * 210.0, t),
               _lerp(ay - dy * span * 0.55, ay - dy * 210.0, t), up)
        target = _ahead(eye, (dx, dy), max(30.0, up * 1.4))
        return eye, target, PLAN if t < 0.45 else CLEARED, "sea" if t < 0.45 else "bottom"

    if at < 0.62:
        # Down the slope, from the shallow reef out over the drop, at the height
        # a survey flies and looking at the ground rather than the horizon.
        # This is the leg that shows the zonation: what grows at five metres,
        # what grows at twenty, and where the coral gives out.
        t = (at - 0.30) / 0.32
        up = _lerp(15.0, 11.0, t)
        eye = (ax + dx * _lerp(-210.0, 240.0, t) + sx * _lerp(-40.0, 40.0, t),
               ay + dy * _lerp(-210.0, 240.0, t) + sy * _lerp(-40.0, 40.0, t),
               up)
        target = _ahead(eye, (dx, dy), up * 1.5)
        return eye, target, CLEARED, "bottom"

    # And low through the reef itself, in the vehicle's own water, at the depth
    # it will be deployed at.
    t = (at - 0.62) / 0.38
    up = _lerp(11.0, 2.6, min(1.0, t * 2.2))
    eye = (ax + dx * _lerp(120.0, -70.0, t) + sx * _lerp(30.0, -30.0, t),
           ay + dy * _lerp(120.0, -70.0, t) + sy * _lerp(30.0, -30.0, t), up)
    target = _ahead(eye, (-dx, -dy), max(9.0, up * 2.4))
    return eye, target, CLEARED if t < 0.18 else AS_DIVED, "bottom"


class Tour:
    """Runs the camera along the path, one frame at a time."""

    def __init__(self, across: float, floor_at, say, begin=None) -> None:
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

        # Where the reef is, and which way the bottom falls away from it. Both
        # read off the ground: the site says where a dive begins, and the floor
        # around that point says where the deep water is.
        self.anchor = (float(begin[0]), float(begin[1])) if begin is not None else (0.0, 0.0)
        self.downhill = self._which_way_is_deep()
        self.say("tour_aimed", anchor=[round(v, 1) for v in self.anchor],
                 downhill=[round(v, 2) for v in self.downhill],
                 floorAtAnchorM=round(float(self.floor_at(*self.anchor) or 0.0), 1))

    def _which_way_is_deep(self):
        """The compass direction the seabed falls away in, from the anchor.

        Sampled over a couple of hundred metres rather than differentiated at a
        point, because at a point the answer is whichever boulder the anchor
        happens to sit beside.
        """
        ax, ay = self.anchor
        best, deepest = (0.0, -1.0), None
        for step in range(16):
            angle = 2 * math.pi * step / 16
            dx, dy = math.cos(angle), math.sin(angle)
            drop = 0.0
            for reach in (80.0, 160.0, 240.0):
                floor = self.floor_at(ax + dx * reach, ay + dy * reach)
                if floor is None:
                    drop = None
                    break
                drop += float(floor)
            if drop is None:
                continue
            if deepest is None or drop < deepest:
                deepest, best = drop, (dx, dy)
        return best

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
            settings.set("/rtx/fog/fogDistance", 30.0)
            settings.set("/rtx/fog/fogStartDistance", 11.0)
            settings.set("/rtx/fog/fogColorIntensity", 0.55)

        self.say("tour_sees", how=sees, atFrame=self.taken)

    def place(self, stage, viewport) -> None:
        """Point the camera wherever this frame wants it."""
        from pxr import Gf, UsdGeom

        if not self.tidied:
            self._tidy()

        eye, target, sees, above = where_to_look(
            self.taken / max(1, self.frames), self.across,
            self.anchor, self.downhill)
        self._see(stage, sees)

        eye = (eye[0], eye[1], self._height(eye[0], eye[1], eye[2], above))
        target = (target[0], target[1],
                  self._height(target[0], target[1], target[2], "bottom"))

        camera_path = "/World/TourCamera"
        camera = UsdGeom.Camera.Define(stage, camera_path)
        camera.CreateFocalLengthAttr(18.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 12000.0))

        # Which way is up for this view. Straight down with up as z is a
        # degenerate basis and SetLookAt hands back nonsense for it: the
        # looking-down frame came back an empty rectangle and was read as the
        # water being too thick, which it was not. When the view is within a
        # few degrees of vertical, north does the job instead.
        way = (target[0] - eye[0], target[1] - eye[1], target[2] - eye[2])
        flat = math.hypot(way[0], way[1])
        up = Gf.Vec3d(1, 0, 0) if flat < 0.05 * abs(way[2]) else Gf.Vec3d(0, 0, 1)

        look = Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(*eye), Gf.Vec3d(*target), up).GetInverse()
        moving = UsdGeom.Xformable(camera.GetPrim())
        moving.ClearXformOpOrder()
        moving.AddTransformOp().Set(look)
        if str(viewport.camera_path) != camera_path:
            viewport.camera_path = camera_path


# ── the exposure ladder ──────────────────────────────────────────────────────
#
# Every judgement about how this reef is lit has been one setting, one flight,
# five minutes, look, guess again. That is a bad loop, and it is why the reef
# spent a week the colour of marzipan: the palette was brown the whole time and
# nobody could tell, because checking cost a render.
#
# So: hold the camera still and step the exposure instead. One container open,
# a dozen frames, every one of them the same reef under a different setting,
# side by side.

# Stops of aperture, and how much of the caustic light to keep. Caustics are a
# modulation of sunlight and not a second sun, so the question of how strong
# they should be is asked here alongside the exposure rather than after it.
# What to try. Each rung is a name and the settings that make it, so the ladder
# can ask any question rather than only "which aperture" — which was the wrong
# question the first time it was asked: the reef was not clipping at any
# aperture, it was being veiled by something additive, and only turning the
# candidates off one at a time says which.
#
# "fog" and "aperture" are read here; anything beginning with a slash is set on
# carb directly; a light name sets that light's intensity.
LOOKS = (
    ("as-is", {}),
    # How much veiling light. The whole frame goes the colour of the water at
    # the strength this sets, so it is the difference between a reef in water
    # and a reef behind a sheet of coloured glass.
    ("veil-05", {"/rtx/fog/fogColorIntensity": 0.05}),
    ("veil-10", {"/rtx/fog/fogColorIntensity": 0.10}),
    ("veil-15", {"/rtx/fog/fogColorIntensity": 0.15}),
    ("veil-35", {"/rtx/fog/fogColorIntensity": 0.35}),
    # And how far it takes to get there.
    ("far-8", {"/rtx/fog/fogDistance": 8.0}),
    ("far-35", {"/rtx/fog/fogDistance": 35.0}),
    ("far-70", {"/rtx/fog/fogDistance": 70.0}),
    # A veil that is less of a hue and more of a haze. The derived colour is
    # normalised to its strongest channel, which makes it fully saturated, and
    # multiple scattering in real water does not leave it that way.
    ("veil-pale", {"/rtx/fog/fogColor": [0.45, 0.72, 0.78]}),
    ("veil-pale-10", {"/rtx/fog/fogColor": [0.45, 0.72, 0.78],
                      "/rtx/fog/fogColorIntensity": 0.10}),
    ("veil-blue-10", {"/rtx/fog/fogColor": [0.18, 0.45, 0.62],
                      "/rtx/fog/fogColorIntensity": 0.10}),
)
# Frames to wait before keeping one. Changing a render setting rebuilds the
# pipeline, which takes a while on a scene this size — so a setting is applied
# once when the rung changes and never again, and the wait is for the rebuild.
SETTLE = 8


class Ladder:
    """The same view of the same reef, under each look worth trying."""

    def __init__(self, floor_at, say, begin=None) -> None:
        self.floor_at = floor_at
        self.say = say
        # Where the reef is. It used to stand at the middle of the site and
        # look north, which at Al Fahal is eight hundred metres of sand: every
        # rung of a light ladder was a picture of the wrong place.
        self.anchor = (float(begin[0]), float(begin[1])) if begin is not None else (0.0, 0.0)
        self.frames = len(LOOKS) * SETTLE
        self.taken = 0
        self.waiting = False
        self.tidied = False
        self.was = {}
        self.set_for = None

    @property
    def done(self) -> bool:
        return self.taken >= self.frames

    @property
    def rung(self):
        return LOOKS[min(self.taken // SETTLE, len(LOOKS) - 1)]

    def name(self) -> str:
        return self.rung[0]

    def keep(self) -> bool:
        """Only the last frame of each rung; the rest are Kit catching up."""
        return self.taken % SETTLE == SETTLE - 1

    def _remember(self, stage) -> None:
        import carb

        settings = carb.settings.get_settings()
        for _, changes in LOOKS:
            for what in changes:
                if what in self.was:
                    continue
                if what.startswith("/rtx") or what.startswith("/app"):
                    self.was[what] = settings.get(what)
                else:
                    prim = stage.GetPrimAtPath(what)
                    attribute = prim.GetAttribute("inputs:intensity") if prim else None
                    self.was[what] = float(attribute.Get()) if attribute else None
        settings.set("/app/viewport/grid/enabled", False)
        settings.set("/app/viewport/show/axis", False)
        settings.set("/persistent/app/viewport/displayOptions", 0)
        self.tidied = True

    def _wear(self, stage, say: bool = True) -> None:
        """Put everything back, then apply this rung."""
        import carb

        settings = carb.settings.get_settings()
        for what, before in self.was.items():
            if what.startswith("/rtx") or what.startswith("/app"):
                if before is not None:
                    settings.set(what, before)
            elif before is not None:
                prim = stage.GetPrimAtPath(what)
                attribute = prim.GetAttribute("inputs:intensity") if prim else None
                if attribute:
                    attribute.Set(before)

        for what, value in self.rung[1].items():
            if what.startswith("/rtx") or what.startswith("/app"):
                settings.set(what, value)
            else:
                prim = stage.GetPrimAtPath(what)
                attribute = prim.GetAttribute("inputs:intensity") if prim else None
                if attribute:
                    attribute.Set(float(value))
        if say:
            self.say("ladder_rung", at=self.name(), atFrame=self.taken)

    def place(self, stage, viewport) -> None:
        from pxr import Gf, UsdGeom

        if not self.tidied:
            self._remember(stage)
        # Applied every frame, not only when the rung changes. The water resets
        # every light to what is left at the vehicle's depth on each stir, so a
        # rung set once is a rung undone one frame later — which is why two
        # ladders of light changes came back with eight identical frames.
        told = self.rung != self.set_for
        self.set_for = self.rung
        self._wear(stage, say=told)

        # A low pass over the reef, standing still. Two and a half metres up and
        # looking slightly down, which is where a vehicle works and so is the
        # view any of this has to be right for.
        ax, ay = self.anchor
        floor = self.floor_at(ax, ay)
        floor = -20.0 if floor is None else float(floor)
        eye = (ax, ay - 14.0, floor + 2.6)
        target = (ax, ay + 4.0, floor + 1.2)

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


# ── the same four frames, everywhere ─────────────────────────────────────────
#
# Every judgement in the look plan is a judgement about an image, and a
# judgement made against memory is not a judgement. The tour flies a path and
# hands back whatever it passed: two runs are not comparable, and neither is a
# before and an after.
#
# So: named viewpoints, the same in every place, held still. What changes
# between two sheets is what somebody changed.

# Where to stand, relative to where the place says a dive begins. Each is a
# question somebody actually asks about a reef.
VIEWS = (
    # What a vehicle sees doing the work: three metres up, looking along.
    ("at-work", dict(from_anchor=(-14.0, 0.0), above=3.0,
                     at=(10.0, 0.0), at_above=2.0,
                     says="at the work site, three metres up, looking along")),
    # On the bottom, looking horizontally — the view that shows whether the
    # water has any depth to it and whether the coral has any form.
    ("on-the-bottom", dict(from_anchor=(-8.0, -3.0), above=0.8,
                           at=(14.0, 2.0), at_above=1.0,
                           says="a metre off the bottom, looking along it")),
    # From mid-water looking down, which is how cover is judged.
    ("looking-down", dict(from_anchor=(0.0, 0.0), above=12.0,
                          at=(0.01, 0.0), at_above=0.0,
                          says="twelve metres up, looking straight down")),
    # And out into open water, which is where the visibility lives and where
    # a water model is either right or obviously wrong.
    ("into-the-blue", dict(from_anchor=(0.0, 0.0), above=6.0,
                           at=(60.0, 0.0), at_above=5.0,
                           says="six metres up, looking out into open water")),
    # Where the pilot sits: just behind the vehicle, low, looking where it
    # looks. The only view that shows what the lamps do, because the lamps are
    # on the vehicle and a camera fourteen metres away sees their edge.
    ("by-the-lamps", dict(from_anchor=(-1.2, 0.0), above=1.4,
                          at=(9.0, 0.0), at_above=0.6,
                          says="just behind the vehicle, where its lamps point")),
)
# Frames to let Kit settle before one is kept. The same reason the ladder
# waits: moving a camera on a scene this size is not instant.
STILL_SETTLE = 10


class Stills:
    """The same four views of every place, held still, for comparing."""

    def __init__(self, across: float, floor_at, say, begin=None,
                 water_level: float | None = None) -> None:
        self.across = across
        self.floor_at = floor_at
        self.say = say
        self.frames = len(VIEWS) * STILL_SETTLE
        self.taken = 0
        self.waiting = False
        self.tidied = False
        self.anchor = (float(begin[0]), float(begin[1])) if begin is not None else (0.0, 0.0)
        # Where the top of the water is, because a view is measured up from the
        # bottom and the bottom is not always deep enough to hold it. Twelve
        # metres over a nine-metre reef puts the camera three metres into the
        # air, looking down at a surface that from that side is opaque — which
        # came back as a flat green rectangle and was read as the water being
        # too thick. It was the sky.
        self.water_level = 0.0 if water_level is None else float(water_level)
        self.placed_for = None
        self.say("stills_begin", views=[name for name, _ in VIEWS],
                 anchor=[round(v, 1) for v in self.anchor],
                 floorAtAnchorM=round(float(self.floor_at(*self.anchor) or 0.0), 1))

    @property
    def done(self) -> bool:
        return self.taken >= self.frames

    @property
    def view(self):
        return VIEWS[min(self.taken // STILL_SETTLE, len(VIEWS) - 1)]

    def name(self) -> str:
        return self.view[0]

    def keep(self) -> bool:
        """Only the last frame of each view; the rest are Kit catching up."""
        return self.taken % STILL_SETTLE == STILL_SETTLE - 1

    def _tidy(self) -> None:
        import carb

        settings = carb.settings.get_settings()
        settings.set("/app/viewport/grid/enabled", False)
        settings.set("/app/viewport/show/axis", False)
        settings.set("/persistent/app/viewport/displayOptions", 0)
        self.tidied = True

    # How far under the surface a camera must stay. Half a metre, because at
    # less than that the lens is in the chop and looking at nothing.
    UNDER = 0.5

    def _height(self, x: float, y: float, above: float) -> float:
        """A height above the bottom here, kept under the water.

        A view says how far off the bottom it wants to be; the water says how
        far off the bottom there is. In shallow water the water wins, and the
        view says so rather than quietly going outside.
        """
        floor = 0.0 if (got := self.floor_at(x, y)) is None else float(got)
        return min(floor + above, self.water_level - self.UNDER)

    def place(self, stage, viewport) -> None:
        from pxr import Gf, UsdGeom

        if not self.tidied:
            self._tidy()
        name, how = self.view
        if name != self.placed_for:
            self.placed_for = name
            self.say("stills_view", at=name, says=how["says"], atFrame=self.taken)

        ex, ey = (self.anchor[0] + how["from_anchor"][0],
                  self.anchor[1] + how["from_anchor"][1])
        tx, ty = self.anchor[0] + how["at"][0], self.anchor[1] + how["at"][1]
        eye = (ex, ey, self._height(ex, ey, how["above"]))
        target = (tx, ty, self._height(tx, ty, how["at_above"]))

        camera_path = "/World/LookCamera"
        camera = UsdGeom.Camera.Define(stage, camera_path)
        # Twenty-four millimetres, which is about what a vehicle's camera is —
        # wide, because everything underwater is close.
        camera.CreateFocalLengthAttr(24.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 12000.0))
        look = Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()
        moving = UsdGeom.Xformable(camera.GetPrim())
        moving.ClearXformOpOrder()
        moving.AddTransformOp().Set(look)
        if str(viewport.camera_path) != camera_path:
            viewport.camera_path = camera_path
