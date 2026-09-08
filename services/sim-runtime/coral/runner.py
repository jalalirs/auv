"""One dive, stepped by whoever is running it.

This exists because a dive has two audiences and must not have two
implementations. Run headless, it is stepped as fast as the machine allows and
nobody watches. Run in the client, it is stepped once per rendered frame and
somebody is flying it. If those were two loops they would drift, and the first
time they disagreed would be the first time somebody trusted a batch result that
the interactive run had contradicted.

So the loop lives here and the callers differ only in how often they call it and
what they do between calls.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np

# Fixed, and not negotiable: a variable timestep makes two runs of the same seed
# diverge, and everything the platform claims about a result rests on them not
# diverging. 200 Hz is comfortably above the vehicle's dynamics and cheap.
PHYSICS_HZ = 200.0


def find_hull(root: pathlib.Path) -> pathlib.Path | None:
    """The vehicle's own geometry, if the package carries any.

    The lighter of the two where a package ships both. A hull is looked at, not
    collided with — the dynamics are integrated from the vehicle's parameters,
    not from its triangles — so the three hundred megabyte version buys nothing
    but a slower start.
    """
    candidates = sorted(root.glob("*.usd")) + sorted(root.glob("*.usda"))
    if not candidates:
        return None
    for candidate in candidates:
        if "low" in candidate.stem.lower():
            return candidate
    return min(candidates, key=lambda c: c.stat().st_size)


def find_water(root: pathlib.Path) -> pathlib.Path | None:
    """The place's water surface, which find_scene deliberately skips."""
    for candidate in sorted(root.rglob("*.usd")) + sorted(root.rglob("*.usda")):
        name = candidate.stem.lower()
        if "water" in name or "surface" in name:
            return candidate
    return None


def _turn(small: np.ndarray) -> np.ndarray:
    """The rotation matrix for a small rotation vector, Rodrigues' formula."""
    angle = float(np.linalg.norm(small))
    if angle < 1e-12:
        return np.eye(3)
    k = small / angle
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    R = np.eye(3) + np.sin(angle) * K + (1.0 - np.cos(angle)) * (K @ K)
    # Renormalise: one Gram-Schmidt pass keeps it orthonormal over a long dive.
    u, _, vt = np.linalg.svd(R)
    return u @ vt


# The cameras a console may look through. Rendered one at a time: the large
# pane is whichever was asked for, and the other panes are drawn from the pose.
VIEWS = ("chase", "front", "down", "top", "orbit")

# How coarse the map handed to a console is, per side.
MAP_CELLS = 64


def coral_positions(city: pathlib.Path, at_most: int = 2000) -> list[list[float]]:
    """Where the coral is, read off the place's point instancer, thinned to
    what a chart can draw. The file is text, and the positions are one line
    of it; nothing here needs USD to be loaded to answer a chart.

    Written to never hold the interpreter for long, which is not a detail:
    a tenth of a second of uninterrupted Python anywhere near this
    application's renderer leaves every frame it draws pure white, with no
    error and everything else working (4 September). So the bytes are never
    decoded, only every nth colony is parsed rather than all eighty thousand
    of them, and the loop sleeps every so often — sleeping is free, because
    what the renderer cannot survive is the interpreter being held, not time
    passing.
    """
    import json
    import time

    try:
        named = json.loads((city / "site.json").read_text()).get("layers", {}).get("coral", "coral.usda")
        raw = (city / named).read_bytes()
    except Exception:
        return []
    at = raw.find(b"positions")
    if at < 0:
        return []
    opened = raw.find(b"[", at)
    closed = raw.find(b"]", opened + 1)
    if opened < 0 or closed < 0:
        return []
    # Split at the C level, parse at the Python level — and only the ones we
    # are going to draw.
    colonies = raw[opened + 1:closed].split(b"(")[1:]
    if not colonies:
        return []
    step = max(1, len(colonies) // at_most)
    found: list[list[float]] = []
    for i in range(0, len(colonies), step):
        if len(found) % 250 == 249:
            time.sleep(0.001)          # let go of the interpreter
        try:
            x, y = colonies[i].split(b",")[:2]
            found.append([round(float(x), 1), round(float(y.strip(b" )")), 1)])
        except (ValueError, IndexError):
            continue
    return found


class Seabed:
    """How deep the bottom is, anywhere in a site.

    Read from the numbers the site carries rather than from its mesh. A ray cast
    into the geometry would only work when the geometry is loaded, which is only
    when somebody is watching — and a batch dive has to land in exactly the same
    place as one being flown or nothing they say about each other means anything.

    Sampled with bilinear interpolation, because a vehicle held two metres above
    a reef by a controller reading a staircase will chase the steps.
    """

    def __init__(self, heights, across: float) -> None:
        self.heights = heights
        self.across = across
        self.rows, self.columns = heights.shape

    @classmethod
    def of(cls, site: pathlib.Path, city: pathlib.Path):
        """The heightfield a place carries, or nothing if it carries none."""
        import json

        try:
            described = json.loads((city / "site.json").read_text())
            field = described["mesh"]["heightfield"]
            raw = np.fromfile(city / field["file"], dtype="<f4")
            heights = raw.reshape(field["rows"], field["columns"])
            return cls(heights, float(described["from"]["acrossMetres"]))
        except Exception:
            return None

    def under(self, x: float, y: float) -> float:
        """The height of the bottom at a point, in metres."""
        # Into grid coordinates, clamped: outside the site the nearest edge is
        # the honest answer, and it keeps a vehicle that wandered off from
        # falling through the world.
        u = (x / self.across + 0.5) * (self.columns - 1)
        v = (y / self.across + 0.5) * (self.rows - 1)
        u = min(max(u, 0.0), self.columns - 1.0001)
        v = min(max(v, 0.0), self.rows - 1.0001)

        column, row = int(u), int(v)
        fu, fv = u - column, v - row
        h = self.heights
        return float(
            h[row, column] * (1 - fu) * (1 - fv)
            + h[row, column + 1] * fu * (1 - fv)
            + h[row + 1, column] * (1 - fu) * fv
            + h[row + 1, column + 1] * fu * fv
        )


    def normal(self, x: float, y: float) -> np.ndarray:
        """Which way the bottom faces at a point: a unit vector, z up.

        From the slope of the height field over one cell either side, which is
        as fine as the field is. A flat bottom returns straight up; the wall of
        a spur returns something nearly horizontal, and that is the difference
        between ground a vehicle settles onto and ground it runs into.
        """
        step = self.across / max(1, self.columns - 1)
        east = self.under(x + step, y) - self.under(x - step, y)
        north = self.under(x, y + step) - self.under(x, y - step)
        normal = np.array([-east, -north, 2.0 * step])
        length = float(np.linalg.norm(normal))
        return np.array([0.0, 0.0, 1.0]) if length < 1e-9 else normal / length


def _mentions(objective, kind: str) -> bool:
    """Whether an objective, or any stage of it, is of this kind."""
    if not isinstance(objective, dict):
        return False
    if str(objective.get("kind", "")) == kind:
        return True
    return any(_mentions(stage, kind) for stage in objective.get("stages", []))


def _find_dock(objective):
    """Where a dive says its dock is, wherever in the objective it says it."""
    if not isinstance(objective, dict):
        return None
    if str(objective.get("kind", "")) == "dock":
        return objective.get("dock") or objective.get("station") or objective
    for stage in objective.get("stages", []):
        found = _find_dock(stage)
        if found is not None:
            return found
    return None


def layers_of(root: pathlib.Path) -> dict:
    """What a place says it is made of.

    Named by the place rather than guessed at from filenames. A rule like "the
    first USD that is not obviously water" loads a reef's coral as its world,
    because c sorts before s — and it fails silently, with a dive apparently
    running in a place made entirely of coral and no seabed at all.
    """
    import json

    try:
        return json.loads((root / "site.json").read_text()).get("layers", {})
    except Exception:
        return {}


def find_scene(root: pathlib.Path) -> pathlib.Path | None:
    """The USD a place is loaded from.

    What the place says, where it says anything. Otherwise the old rule: a place
    may carry several files, so the one that is not obviously a component wins,
    and the choice is reported so nobody has to guess which was used.
    """
    named = layers_of(root).get("terrain")
    if named and (root / named).exists():
        return root / named
    candidates = sorted(root.rglob("*.usd")) + sorted(root.rglob("*.usda"))
    if not candidates:
        return None
    for candidate in candidates:
        name = candidate.stem.lower()
        if "water" not in name and "surface" not in name:
            return candidate
    return candidates[0]


class Dive:
    """A vehicle, in a place, being integrated.

    Construct it with the brief; call open() once, then step() as often as you
    like. Nothing here knows whether a human is watching, and nothing here
    updates the application — whoever is running it decides when to draw.
    """

    def __init__(self, brief: dict, body, allocator, scene: pathlib.Path,
                 say) -> None:
        self.brief = brief
        self.body = body
        self.allocator = allocator
        self.scene = scene
        self.say = say

        self.dt = 1.0 / PHYSICS_HZ
        self.steps = int(brief.get("durationSeconds", 10.0) * PHYSICS_HZ)
        self.taken = 0
        self.simulated = 0.0
        self.reported = 0.0

        self.velocity = np.zeros(6)
        self.rotation = np.eye(3)
        self.effective = body.effective_mass()
        # Why the dive stopped, in one word, decided by whatever stopped it. A
        # dive whose clock ran out and a dive that finished its work are two
        # different results, and used to be the same one.
        self.ended = ""
        # The battery the vehicle package declares, and whether a dock is
        # putting charge back into it.
        self.battery = None
        self.charging = False
        # How many times a hand picked the vehicle up and put it somewhere.
        self.carried = 0
        self.route_flying = ""
        # Who worked out the path being flown, once something has, and the
        # plan document it is flying — kept so that a dive can be read back a
        # year later and two plans for one task can be held side by side.
        self.planned_by = ""
        self.document: dict | None = None
        # How many times somebody has asked to start the task over.
        self.attempts = 1
        self.objective = None
        # Where the vehicle believes it is. Built when the dive is placed,
        # because a navigator has to start from somewhere known — which for a
        # vehicle is wherever it was last on the surface.
        self.navigation = None
        # Whether the task has finished on an interactive dive, where finishing
        # says so rather than ending the dive.
        self.task_over = False
        self.began_rotation = np.eye(3)
        self.began_with_wh = 0.0
        self.commands = np.zeros(len(allocator.model.thrusters))
        self.position = np.array(
            (brief.get("initialState") or {}).get("positionM", [0.0, 0.0, -2.0]),
            dtype=float)
        self.bridge = None

        # Who flies. A helm decides every step whether the thrusters follow a
        # hand on the controls, a stack talking over ROS 2, or the hold that
        # keeps the vehicle where it was left. All three go through the same
        # allocator and the same thrusters: a pilot and a program can do
        # exactly the same things to this vehicle, and neither can do anything
        # the other cannot.
        from controllers import Helm
        self.helm = Helm(allocator, self.dt)
        self.capability = self.helm.capability

        # Filled in when the place is opened: where its floor is, and where the
        # top of its water is. Both in metres, in the dive's own frame.
        self.floor = None
        self.seabed = None
        self.bounds = (None, None)
        self._coral: list[list[float]] | None = None   # read when a chart first asks
        self.view = "chase"
        self.began_at = np.zeros(3)
        # The water's own motion, in the world frame, metres per second. Read
        # from the dive's conditions: still unless they say otherwise. Drag
        # acts on the vehicle's motion through the water, not over the ground,
        # so a vehicle doing nothing in a current is carried by it.
        self.current = np.zeros(3)
        self.visibility_m = None
        self.read_conditions(brief.get("conditions"))
        # The battery the vehicle package declares. A vehicle that declares
        # none flies as everything did before: for as long as it is asked to.
        try:
            from energy import Battery
            self.battery = Battery.of(pathlib.Path(brief.get("vehiclePath", "/dive/vehicle")))
            charge = brief.get("batteryCharge")
            if self.battery is not None and charge is not None:
                self.battery.remaining_wh = self.battery.capacity_wh * float(charge)
            if self.battery is not None:
                say("battery", **self.battery.said())
        except Exception as exc:
            say("battery_unavailable", why=str(exc)[:160])
        # What the dive is for, judged as it runs. None when it is only flown.
        self.task = None
        # What it leaves behind. Opened with the task, beside the brief.
        self.recorder = None
        # Where the water stops. Depth is measured from z = 0 everywhere, so
        # that is the waterline unless a place ships a surface of its own and
        # says otherwise. It used to be None until a place shipped one, which
        # meant that on every place that does not — Looe Key among them — the
        # surface was a picture with nothing behind it, and a vehicle could
        # rise straight out of the sea and keep going.
        self.water_level = 0.0
        self.water = None
        self.on_the_bottom = False

        # How far the vehicle's middle is from its bottom. Taken from the hull
        # when one is drawn, and a guess otherwise — a vehicle resting exactly
        # on the floor with its centre on the floor is half buried.
        self.half_height = 0.15
        # How far the drawn hull sits from the origin the physics uses. Nothing
        # until a hull is loaded and measured; nothing at all on a dive that
        # draws nothing.
        self.hull_offset = [0.0, 0.0, 0.0]
        # And how wide, which is how far ahead of itself it meets a wall.
        self.half_width = 0.3
        # Whether it is up against ground it cannot ride over.
        self.against_the_ground = False

    # ── setting up ───────────────────────────────────────────────────────────

    def open(self, drawn: bool = False) -> bool:
        """Load the place and put the vehicle in it. False if it would not open.

        Drawn only when somebody is watching. The hull and the water surface are
        tens of megabytes that no batch dive has any use for: the dynamics come
        from the vehicle's parameters and not from its triangles, so nothing
        loaded here changes the trajectory by so much as a millimetre. What it
        changes is whether there is anything to see.
        """
        import omni.usd
        from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics

        context = omni.usd.get_context()
        context.open_stage(str(self.scene))
        stage = context.get_stage()
        if stage is None:
            self.say("failed", why=f"the place at {self.scene} would not open")
            return False
        self.stage = stage

        prims = sum(1 for _ in stage.Traverse())

        # What the place is measured in, and how big it is.
        #
        # The physics here is in metres and always will be. A USD stage is in
        # whatever its author chose — centimetres are common — and a scene in
        # centimetres drawn as though it were metres puts the camera four
        # centimetres from the vehicle, inside the tank wall. That is what the
        # first photograph of a lit dive turned out to be. Nothing about the
        # trajectory changes; only where things are drawn.
        self.units_per_metre = 1.0 / (UsdGeom.GetStageMetersPerUnit(stage) or 1.0)
        self.up_axis = UsdGeom.GetStageUpAxis(stage)

        bounds = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
        ).ComputeWorldBound(stage.GetPseudoRoot()).ComputeAlignedRange()
        extent = corner = far = None
        if not bounds.IsEmpty():
            metres = lambda v: [round(float(c) / self.units_per_metre, 2) for c in v]
            extent, corner, far = (metres(bounds.GetSize()),
                                   metres(bounds.GetMin()), metres(bounds.GetMax()))
        self.bounds = (corner, far)

        self.say("place_open", scene=str(self.scene), prims=prims,
                 metresAcross=extent, from_=corner, to=far,
                 upAxis=str(self.up_axis),
                 unitsPerMetre=round(self.units_per_metre, 4))

        # The floor.
        #
        # The site's own heightfield where it has one, so the bottom is the
        # bottom under this vehicle rather than the deepest point in the place.
        # On a reef with four metres of relief the difference is a vehicle
        # resting on the coral and a vehicle four metres inside it.
        self.seabed = Seabed.of(self.scene, pathlib.Path(
            self.brief.get("cityPath", "/dive/city")))
        self.floor = None if corner is None else float(corner[2])
        if self.seabed is not None:
            self.say("seabed_known",
                     samples=[self.seabed.rows, self.seabed.columns],
                     acrossM=self.seabed.across)

        # Where a dive begins.
        #
        # The middle of the water, a couple of metres under its surface, unless
        # the dive says otherwise. A dive that starts wherever the origin happens
        # to fall cannot be compared with another that also started nowhere in
        # particular — and in this tank the origin is at one end.
        asked = (self.brief.get("initialState") or {}).get("positionM")
        if asked is None:
            # What the place says, if it says anything. The middle of a site is
            # only the right answer when the site is uniform, and a reef is the
            # opposite of uniform: its parts are different on purpose, and
            # starting on the wave-scoured flat looking out at the reef is not
            # the same dive as starting over the slope in the middle of it.
            said = self._site_says()
            if said is not None:
                self.position = np.array(said[0], dtype=float)
                self.say("spawned",
                         at=[round(float(v), 2) for v in self.position],
                         why=said[1])
                asked = said[0]
        if asked is None:
            where, why = self.spawn(corner, far)
            if where is not None:
                self.position = np.array(where, dtype=float)
                self.say("spawned",
                         at=[round(float(v), 2) for v in self.position], why=why)
        elif corner is not None:
            inside = all(corner[i] <= self.position[i] <= far[i] for i in range(3))
            if not inside:
                # A vehicle placed outside its own tank is a dive definition
                # that is wrong, and saying so beats discovering it by looking
                # at a photograph of a wall.
                self.say("vehicle_outside_the_place",
                         position=[round(float(v), 2) for v in self.position],
                         from_=corner, to=far)

        # Gravity on, which is the whole point: OceanSim disables it and applies
        # damping instead, and a vehicle with no weight has nothing for buoyancy
        # to act against.
        physics = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
        physics.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        physics.CreateGravityMagnitudeAttr().Set(9.80665)

        city = pathlib.Path(self.brief.get("cityPath", "/dive/city"))

        if drawn:
            # Water. The fog that is the medium, the sun through the surface,
            # the surface seen from below, and the caustics it throws down.
            import water
            water.make(stage, self.say,
                       floor=self.floor if self.floor is not None else -20.0,
                       water_level=0.0,
                       across=float(extent[0]) if extent else 1000.0,
                       working_depth=abs(float(self.position[2])),
                       visibility_m=self.visibility_m)
            self.water = water

        # A body of the vehicle's actual mass, at the vehicle's actual place.
        # What is being integrated is the dynamics; a dive that reported a
        # trajectory it had not computed would be worse than one that reported
        # no picture.
        self.vehicle_path = "/World/Vehicle"
        xform = UsdGeom.Xform.Define(stage, self.vehicle_path)
        # One transform for where it is and which way it points. A translate
        # alone drew the hull level and facing the same way whatever the
        # physics did with it: the dials said it rolled and turned, the
        # picture said it did not, and a chase camera bolted to the heading
        # made every yaw look like the camera circling a still vehicle.
        xform.ClearXformOpOrder()
        self.placement = xform.AddTransformOp()
        self._Gf = Gf
        self.placement.Set(self.pose())

        if drawn:
            # The hull hangs under our own transform rather than being it, so
            # that whatever the vehicle package does to place itself cannot
            # fight with where the dive says the vehicle is.
            hull = find_hull(pathlib.Path(
                self.brief.get("vehiclePath", "/dive/vehicle")))
            if hull is not None:
                prim = stage.DefinePrim(self.vehicle_path + "/Hull")
                prim.GetReferences().AddReference(str(hull))
                # How big it came out. A vehicle package is authored by
                # somebody else, in units of their choosing, and a BlueROV2
                # drawn fifty metres long looks exactly like a wall.
                drawn = UsdGeom.BBoxCache(
                    Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
                ).ComputeWorldBound(prim).ComputeAlignedRange()
                size = None
                if not drawn.IsEmpty():
                    size = [round(float(v) / self.units_per_metre, 3)
                            for v in drawn.GetSize()]
                if size is not None:
                    self.half_height = max(0.05, size[2] / 2.0)
                    self.half_width = max(0.1, max(size[0], size[1]) / 2.0)
                # And where it sits relative to the vehicle. The physics has
                # its origin at the centre of gravity; the geometry has its
                # origin wherever whoever modelled it put one, and for this
                # hull that is a fifth of a metre below what is drawn. Nothing
                # about the dive depends on this — but a marker drawn around
                # the vehicle on the picture does, and one drawn at the origin
                # sits visibly under the thing it is marking.
                #
                # Taken as a local bound so it is the offset within our own
                # transform rather than a position in the world, then turned
                # back into our metres and our idea of up.
                self.hull_offset = [0.0, 0.0, 0.0]
                if not drawn.IsEmpty():
                    local = UsdGeom.BBoxCache(
                        Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
                    ).ComputeLocalBound(prim).ComputeAlignedRange()
                    if not local.IsEmpty():
                        middle = local.GetMidpoint()
                        ours = [float(v) / self.units_per_metre for v in middle]
                        if self.up_axis == "Y":
                            ours = [ours[0], -ours[2], ours[1]]
                        self.hull_offset = [round(v, 4) for v in ours]
                self.say("hull_drawn", file=hull.name, metresAcross=size,
                         drawnAboveOriginM=self.hull_offset)

            # The reef. Referenced rather than merged, so the seabed stays one
            # file and the coral stays another — a place is layers, and a
            # thousand colonies is not something to paste into a terrain.
            reef = layers_of(city).get("coral")
            if reef and (city / reef).exists() and not stage.GetPrimAtPath("/World/Coral"):
                stage.DefinePrim("/World/Coral").GetReferences() \
                    .AddReference(str(city / reef))
                self.say("coral_drawn", file=reef)

            water = find_water(pathlib.Path(
                self.brief.get("cityPath", "/dive/city")))
            if water is not None and not stage.GetPrimAtPath("/World/Water"):
                surface = stage.DefinePrim("/World/Water")
                surface.GetReferences().AddReference(str(water))
                # Where the top of the water is, which is where depth is
                # measured from and where a dive starts two metres below.
                wet = UsdGeom.BBoxCache(
                    Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
                ).ComputeWorldBound(surface).ComputeAlignedRange()
                if not wet.IsEmpty():
                    self.water_level = float(wet.GetMax()[2]) / self.units_per_metre
                self.say("water_drawn", file=water.name,
                         surfaceAtM=None if self.water_level is None
                         else round(self.water_level, 2))

        self.begin_task(self.brief.get("objective"))
        self.say("vehicle_placed",
                 position=[round(float(x), 3) for x in self.position])
        return True

    def _site_says(self):
        """Where this place says a dive should begin, if it says."""
        import json

        try:
            city = pathlib.Path(self.brief.get("cityPath", "/dive/city"))
            described = json.loads((city / "site.json").read_text())
            begin = described.get("beginAt")
            if begin and len(begin) == 3:
                return list(begin), described.get(
                    "beginBecause", "where the place says a dive begins")
        except Exception:
            pass
        return None

    def spawn(self, corner, far):
        """The middle of the water, two metres down.

        The water, not the scene. A scene's bounding box is inflated by whatever
        is furthest from the origin in it — one stray prim makes a tow tank
        ninety-five metres long — and the middle of that box can be a place with
        nothing in it, which is what the first attempt produced: a vehicle
        correctly centred in the frame, in an empty blue nowhere, with the tank
        somewhere off to one side.

        The water layer is the volume a dive happens in. It is read here rather
        than measured from the drawn scene, because it is only drawn when
        somebody is watching, and where a dive begins must not depend on whether
        anybody is looking at it — a batch run and an interactive run of one
        definition have to start in the same place or nothing about comparing
        them means anything.

        Two metres down because that is where an ROV goes in from a boat: one
        that begins on the bottom cannot be seen to sink, and one that begins at
        the surface is in the waves.
        """
        from pxr import Usd, UsdGeom

        water = find_water(pathlib.Path(self.brief.get("cityPath", "/dive/city")))
        if water is not None:
            try:
                layer = Usd.Stage.Open(str(water))
                per_metre = 1.0 / (UsdGeom.GetStageMetersPerUnit(layer) or 1.0)
                wet = UsdGeom.BBoxCache(
                    Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
                ).ComputeWorldBound(layer.GetPseudoRoot()).ComputeAlignedRange()
                if not wet.IsEmpty():
                    low = [float(v) / per_metre for v in wet.GetMin()]
                    high = [float(v) / per_metre for v in wet.GetMax()]
                    return ([(low[0] + high[0]) / 2.0,
                             (low[1] + high[1]) / 2.0,
                             high[2] - 2.0], "the middle of the water")
            except Exception as exc:
                self.say("water_unreadable", why=str(exc)[:160])

        if corner is None:
            return (None, "")
        return ([(corner[0] + far[0]) / 2.0, (corner[1] + far[1]) / 2.0,
                 max(corner[2] + 0.5, min(far[2], 0.0) - 2.0)],
                "the middle of the place, which has no water layer")

    def connect(self) -> None:
        """Open the boundary somebody else's autonomy talks across."""
        if not self.brief.get("autonomy", True):
            return
        try:
            from bridge import Bridge
            from controllers import Helm
            self.bridge = Bridge(self.allocator.model, self.allocator,
                                 int(self.brief.get("rosDomainId", 0)),
                                 logger=lambda kind, **d: self.say(kind, **d))
            # The helm learns of the stack the moment the boundary opens, and
            # keeps whatever a hand has already tuned.
            self.helm = Helm(self.allocator, self.dt, bridge=self.bridge)
            self.say("bridge_open", domain=self.brief.get("rosDomainId"),
                     publishes=["/depth", "/imu/data", "/dvl/twist"],
                     subscribes=["/thruster_cmd", "/cmd_vel"])
        except Exception as exc:
            self.say("bridge_unavailable", why=str(exc)[:200])

    def publish(self) -> None:
        """What the vehicle's sensors report, without advancing anything.

        Used while waiting for autonomy to appear. A vehicle sitting in the
        water still has a depth and still reports it; saying nothing until
        commanded is the simulator behaving in a way no vehicle does, and it
        deadlocks exactly as that deserves.
        """
        if self.bridge is not None:
            self.bridge.publish(self.simulated, self.position, self.velocity,
                                self.body.model.density, self.rotation)

    # ── running ──────────────────────────────────────────────────────────────

    @property
    def done(self) -> bool:
        return bool(self.ended) or self.taken >= self.steps

    def finish(self, why: str) -> None:
        """End the dive, for a reason worth recording."""
        if not self.ended:
            self.ended = why
            self.say("ending", why=why, t=round(self.simulated, 2))

    @property
    def flown_by_hand(self) -> bool:
        return self.helm.flying is self.helm.manual

    def take_the_controls(self, asked) -> None:
        """A person is flying it. What they ask for is a fraction, not a force.

        Half ahead and full rise are fractions of what this vehicle can do, and
        turning them into a wrench is the vehicle's business — it is the only
        thing that knows what it can do. Handing the fraction straight to the
        allocator asks a hundred-newton vehicle for half a newton, which is
        exactly what happened once: the keys arrived, the display said somebody
        was flying, and the vehicle sat there.

        While any key is down the hand has the vehicle; the moment all are up
        the hold takes it back where it is. There is no arbitration beyond
        that and there should not be.
        """
        self.helm.hands(asked)

    def message(self, said: dict) -> None:
        """Something the person watching asked for, other than steering.

        `tune` moves a controller's parameter; `hold` re-engages the hold where
        the vehicle is. Anything else is ignored rather than guessed at.
        """
        view = said.get("view")
        if isinstance(view, str) and view in VIEWS:
            self.view = view
            self.say("view", view=view)
        engage = said.get("engage")
        if isinstance(engage, str):
            if self.helm.engage(engage, self.observation()):
                self.say("engaged", controller=engage, flying=self.helm.flying.name)
        tune = said.get("tune")
        if isinstance(tune, dict):
            if self.helm.tune(str(tune.get("controller", "")), str(tune.get("name", "")),
                              float(tune.get("value", 0.0))):
                self.say("tuned", controller=tune.get("controller"),
                         parameter=tune.get("name"), value=tune.get("value"))
        if said.get("hold") == "here":
            self.helm.hold_here(self.observation())
            self.say("hold_engaged", **self.helm.hold.status())
        place = said.get("place")
        if isinstance(place, dict):
            self.carry_to(place)
        if said.get("reset") or said.get("retry"):
            self.start_again()
        found = said.get("found")
        if isinstance(found, (list, tuple)) and len(found) >= 2:
            self.report_a_find(found)

    def carry_to(self, where: dict) -> None:
        """Pick the vehicle up and put it somewhere. A hand of God.

        Flying a kilometre at a quarter of a metre a second to reach the thing
        you wanted to look at is forty minutes of nothing, so a person watching
        may click the chart and be there. It is not flying and is not pretended
        to be: the vehicle arrives stopped, the hold takes the new pose, and
        the number of times it happened goes into the state, the recording and
        the run — so a controller that did the work is never quietly compared
        with one that was carried.
        """
        x = float(where.get("x", self.position[0]))
        y = float(where.get("y", self.position[1]))
        floor = self.floor if self.seabed is None else self.seabed.under(x, y)
        if where.get("depthM") is not None:
            z = -float(where["depthM"])
        elif floor is not None:
            # A sensible height over whatever is there, rather than the depth
            # it happened to be at somewhere else entirely.
            z = floor + max(self.half_height + 0.2, float(where.get("altitudeM", 2.0)))
        else:
            z = float(self.position[2])
        if floor is not None:
            z = max(z, floor + self.half_height + 0.05)
        if self.water_level is not None:
            z = min(z, self.water_level - self.half_height)
        self.position = np.array([x, y, z])
        self.velocity = np.zeros(6)
        self.carried += 1
        self.helm.hold_here(self.observation())
        self.helm.failsafe.stand_down()
        if self.task is not None:
            # The route is flown from where the vehicle is now: carrying it
            # past three waypoints does not reach them.
            self.route_flying = ""
            self.steer_to_the_task()
        if self.navigation is not None:
            # It was picked up and put somewhere; it did not swim there, and
            # nothing it carries could have told it. A hand of God knows where
            # it put the thing.
            self.navigation.believed = self.position.copy()
        self.say("carried", to=[round(float(v), 2) for v in self.position], times=self.carried)

    def start_again(self) -> None:
        """Put it back where the dive began and try the task again.

        A person who wants another go at a task should not have to surface,
        hand the machine back, define a new dive and wait for a scene to open
        — the vehicle is right here and the task is a thing that can start
        over. The vehicle goes back to where it began, stopped and level, the
        battery back to the charge it began with, and the task is built again
        from the same objective, so its score and its clock start from
        nothing. The attempt is counted and the run remembers how many there
        were, because a score on the fourth try is not a score on the first.
        """
        self.position = self.began_at.copy()
        self.rotation = self.began_rotation.copy()
        self.velocity = np.zeros(6)
        self.commands = np.zeros_like(self.commands)
        self.against_the_ground = False
        self.on_the_bottom = False
        self.ended = ""
        self.attempts += 1
        if self.battery is not None:
            self.battery.remaining_wh = self.began_with_wh
            self.battery.spent_wh = 0.0
            self.battery.flat = False
        self.dead_thrusters.clear()
        self.sensors_out_until = 0.0
        for failure in self.failures:
            failure.pop("done", None)
        self.route_flying = ""
        # It is back where it was deployed, so its navigator starts from there
        # too: the drift it accumulated belonged to the attempt that is over.
        self.begin_navigating()
        self.helm.failsafe.stand_down()
        self.helm.hold_here(self.observation())
        self.begin_task(self.objective, again=True)
        self.say("started_again", attempt=self.attempts,
                 at=[round(float(v), 2) for v in self.position])

    def report_a_find(self, where) -> None:
        """Somebody saying they have found the thing they were sent to find."""
        from tasks import Mission, Search

        task = self.task.stage if isinstance(self.task, Mission) else self.task
        if isinstance(task, Search):
            task.report(where)
            self.say("reported", where=[round(float(v), 2) for v in where[:3]],
                     right=task.detail()["found"])

    def read_conditions(self, conditions) -> None:
        """What the water is doing, from the conditions the dive was defined with."""
        parameters = {}
        if isinstance(conditions, dict):
            parameters = conditions.get("parameters") or {}
        speed = float(parameters.get("currentMetresPerSecond", 0.0) or 0.0)
        # The heading a current is named by is where it flows towards, from
        # north, clockwise — the way a current is written on a chart.
        heading = float(parameters.get("currentHeadingDeg", 0.0) or 0.0)
        angle = np.radians(90.0 - heading)
        self.current = np.array([speed * np.cos(angle), speed * np.sin(angle), 0.0])
        visibility = parameters.get("visibilityM")
        self.visibility_m = None if visibility in (None, "", 0) else float(visibility)
        # What is deployed in this water to fix a position with, if anything.
        # The vehicle's instruments are the vehicle's; this is the water's, and
        # a dive is one crossed with the other.
        aiding = parameters.get("positioning")
        self.aiding = dict(aiding) if isinstance(aiding, dict) else {"kind": "none"}
        # What of the vehicle's own suite is fitted for this dive. The same
        # hull with and without a Doppler log is two different problems, and
        # saying so should not need a second vehicle in the catalogue.
        fitted = parameters.get("fitted")
        self.fitted = dict(fitted) if isinstance(fitted, dict) else {}
        # Things that go wrong, on purpose and on the clock. A controller that
        # has only ever flown a healthy vehicle in still water has not been
        # tested, and a failure that happens at a stated second happens at the
        # same second on a re-run — which is the only kind worth having.
        self.failures = []
        for said in (parameters.get("failures") or []):
            if not isinstance(said, dict):
                continue
            self.failures.append({"kind": str(said.get("kind", "")),
                                  "at": float(said.get("atS", 0.0)),
                                  "which": said.get("which"),
                                  "forS": said.get("forS")})
        self.dead_thrusters: set[int] = set()
        self.sensors_out_until = 0.0

    def things_go_wrong(self) -> None:
        """Apply whatever the conditions said would fail, when it said."""
        for failure in self.failures:
            if failure.get("done") or self.simulated < failure["at"]:
                continue
            failure["done"] = True
            kind = failure["kind"]
            if kind == "thruster":
                which = failure.get("which")
                dead = (list(range(len(self.commands))) if which is None
                        else [int(which)] if not isinstance(which, list) else [int(w) for w in which])
                for one_of_them in dead:
                    if 0 <= one_of_them < len(self.commands):
                        self.dead_thrusters.add(one_of_them)
                self.say("thruster_failed", which=sorted(self.dead_thrusters))
            elif kind == "sensors":
                self.sensors_out_until = self.simulated + float(failure.get("forS") or 5.0)
                self.say("sensors_out", untilS=round(self.sensors_out_until, 1))
            elif kind == "current":
                speed = float(failure.get("which") or 0.5)
                self.current = self.current + np.array([speed, 0.0, 0.0])
                self.say("gust", currentMs=round(float(np.hypot(*self.current[:2])), 3))

    @property
    def sensors_are_out(self) -> bool:
        return self.simulated < self.sensors_out_until

    def conditions_said(self) -> dict:
        speed = float(np.hypot(self.current[0], self.current[1]))
        heading = (90.0 - np.degrees(np.arctan2(self.current[1], self.current[0]))) % 360.0 if speed > 1e-9 else 0.0
        return {"currentMetresPerSecond": round(speed, 3), "currentHeadingDeg": round(float(heading), 1),
                "current": [round(float(v), 4) for v in self.current[:2]],
                "visibilityM": self.visibility_m}

    def begin_task(self, objective, again: bool = False) -> None:
        """Where the dive begins is where its task is measured from.

        Called once the vehicle is placed; the tank calls it itself, since it
        never opens a scene.
        """
        from tasks import task_for

        # Kept, so that starting again asks for the same thing. Reading it
        # back off the brief was a second copy of the truth, and on a dive
        # whose objective was handed in rather than briefed it was empty.
        self.objective = objective
        if not again:
            self.began_at = self.position.copy()
            self.began_rotation = self.rotation.copy()
            self.begin_navigating()
            self.began_with_wh = (0.0 if self.battery is None else self.battery.remaining_wh)
        wants_coral = _mentions(objective, "treat")
        self.task = task_for(objective, self.began_at,
                             float(np.arctan2(self.rotation[1, 0], self.rotation[0, 0])),
                             camera=self.camera(),
                             colonies=self.colonies_here() if wants_coral else None)
        if self.task is not None:
            self.task_over = False
            self.say("task_set", task=self.task.describe(), attempt=self.attempts)
            # The platform flies what it can, so that choosing a task on the
            # dive page and pressing Dive does the thing rather than watching
            # the vehicle sit where it started. A stack or a hand still wins.
            self.steer_to_the_task()
            self.watch_the_energy()
            # A dive that is for something records; a survey looks down, since
            # what it records is what it sees. A console may look elsewhere.
            if self.task.kind == "survey":
                self.view = "down"
            try:
                from recording import Recorder

                # How long this is expected to take decides how often it is
                # filmed, so that a mission of a kilometre and a task of thirty
                # metres leave recordings of about the same size.
                expected = None
                if isinstance(self.objective, dict):
                    expected = self.objective.get("timeLimitS") or self.objective.get("seconds")
                self.recorder = Recorder(pathlib.Path(self.brief.get("recordInto",
                                         str(pathlib.Path(self.brief.get("cityPath", "/dive/city")).parent / "recording"))),
                                         frames_hz=Recorder.rate_for(expected))
                self.recorder.camera = self.camera()
                self.say("recording", into=str(self.recorder.into))
            except Exception as exc:
                self.say("recording_unavailable", why=str(exc)[:160])

    @property
    def coral(self) -> list[list[float]]:
        if self._coral is None:
            self._coral = coral_positions(pathlib.Path(self.brief.get("cityPath", "/dive/city")))
            if self._coral:
                self.say("coral_charted", colonies=len(self._coral))
        return self._coral

    def begin_navigating(self) -> None:
        """Give the vehicle its own idea of where it is, starting from here.

        Two separate declarations, belonging to two different people: the
        instruments are the vehicle's, stated by whoever published it, and
        anything deployed in the water — an LBL array, a ship with a USBL,
        nothing at all — is the water's, stated by whoever defined the
        conditions. Keeping them apart is what lets one task be flown on four
        different technologies.
        """
        try:
            from navigation import Navigation

            self.navigation = Navigation(suite={**self.navigation_suite(), **self.fitted},
                                         aiding=self.aiding,
                                         began_at=self.position,
                                         seed=int(self.seed()))
            self.say("navigating", **self.navigation.said(self.position, self.simulated))
        except Exception as exc:
            self.navigation = None
            self.say("navigation_unavailable", why=str(exc)[:160])

    def navigation_suite(self) -> dict:
        """What this vehicle has to navigate with, from its own package.

        A package may state it outright; otherwise it is read off the sensors
        the package lists, because a vehicle that carries a Doppler log has one
        whether or not anybody wrote down its accuracy.
        """
        import json

        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
        except Exception:
            return {}
        stated = described.get("navigation")
        if isinstance(stated, dict):
            return stated
        kinds = {str(one_of_them.get("kind", "")) for one_of_them in described.get("sensors", [])}
        return {"dvl": "dvl" in kinds}

    def colonies_here(self):
        """Every colony in the place, for a task that is about the coral.

        Unthinned, unlike the chart's copy: a patch fifteen metres across holds
        a handful of the two thousand a chart draws and thousands of the real
        ones, and a treatment score has to be a share of the real population.
        """
        return coral_positions(pathlib.Path(self.brief.get("cityPath", "/dive/city")),
                               at_most=200000)

    def steer_to_the_task(self) -> None:
        """Plan a way of doing what the task asks, and fly that.

        The task states a goal and the planner works out a path — which is the
        line that matters, because until it was drawn the task carried its own
        solution and every dive measured a route we had supplied. What is here
        is the platform's own planner (controllers/plan.py); somebody else's
        controller ignores all of it and is handed the goal and the sensors.

        Re-planned when the goal changes, which for a mission is when its
        stage does.
        """
        if self.task is None:
            return
        which = self.task.goal_id()
        if which == self.route_flying:
            return
        from controllers import plan

        goal = self.task.goal()
        # Every controller is told what the dive is for. One that plans for
        # itself needs the goal and not a route — that is the whole of the
        # difference between a vehicle being asked and one being driven.
        self.helm.tasked(goal)
        named = self.who_should_fly()
        if named and named != getattr(self, "_asked_for", None):
            self._asked_for = named
            if self.helm.engage(named, self.observation()):
                self.say("flying_with", controller=named)
            else:
                self.say("no_such_controller", asked=named)
        # A plan given to the dive is flown as given. Nothing here works out
        # what to do: the document says, and where it came from — a person, a
        # model, another planner — is not this code's business. It is checked
        # first, because a plan that names a manoeuvre which does not exist is
        # a vehicle that stops in the water for no reason anyone can see.
        # A plan may come with the dive, or ride inside the objective it
        # satisfies — which is how one reaches a vehicle without the platform
        # needing a second field for it: the dive says what it wants and how
        # it means to go about it, together.
        given = self.brief.get("plan")
        if not isinstance(given, dict):
            given = (self.brief.get("objective") or {}).get("plan") \
                if isinstance(self.brief.get("objective"), dict) else None
        if isinstance(given, dict) and given.get("manoeuvres"):
            wrong = plan.what_is_wrong(given)
            if wrong:
                self.say("plan_refused", why=wrong[:4])
                given = None
            else:
                self.document = given
                self.planned_by = str(given.get("by") or "the plan it was given")
        if not isinstance(getattr(self, "document", None), dict) or given is None:
            self.document = plan.plan_for(goal, believed=self.believed(),
                                          camera_half_angle=self.camera_half_angle(),
                                          named=self.task.kind)
            self.planned_by = "the platform's planner"
        route = plan.legs_of(self.document)
        self.route_flying = which
        self.helm.fly(route)
        if route or self.document:
            self.say("planned", legs=len(route),
                     manoeuvres=len(self.document.get("manoeuvres", [])),
                     forTask=self.task.kind, goal=goal.get("kind"),
                     stage=which, by=self.planned_by)

    def seed(self) -> int:
        """What makes two dives comparable: the same water, wrong the same way.

        A benchmark that gives one controller a favourable draw of compass
        error is not a benchmark. The seed may be stated by the dive, or ride
        with the objective — which is where a bench puts it, so that the same
        task set is identically wrong for everyone flying it.
        """
        objective = self.brief.get("objective")
        if isinstance(objective, dict) and objective.get("seed") is not None:
            return int(objective["seed"])
        return int(self.brief.get("seed", 0))

    def who_should_fly(self) -> str:
        """Which controller this dive asked for, if it asked for one.

        A dive that names a controller is how a bench flies the same task set
        with two different ones. Nothing else changes — same water, same fit,
        same seed — so the difference in what comes back is attributable.
        """
        objective = self.brief.get("objective")
        named = self.brief.get("controller")
        if not named and isinstance(objective, dict):
            named = objective.get("controller")
        return str(named or "")

    def believed(self):
        """Where the vehicle thinks it is. What a controller is allowed to use."""
        if self.navigation is not None:
            return np.asarray(self.navigation.believed, dtype=float)
        return np.asarray(self.position, dtype=float)

    def camera_half_angle(self) -> float | None:
        """Half the camera's horizontal field of view, radians, if it has one.

        A fact about the vehicle, which is why a planner is told it and a task
        is not: how far apart to fly the lanes of a survey depends on what the
        thing can see.
        """
        described = self.camera()
        if described is None:
            return None
        wide = described.get("horizontalFovDeg")
        return None if wide is None else math.radians(float(wide) / 2.0)

    def watch_the_energy(self) -> None:
        """Tell the failsafe what it is watching and where home is."""
        if self.battery is None:
            return
        home = None
        objective = self.brief.get("objective") or {}
        said = _find_dock(objective)
        if said is not None and self.task is not None:
            home = self.task.somewhere(said)
        self.helm.watch_the_battery(self.battery, home)

    def hello(self) -> dict:
        """What somebody arriving at the console needs once: the site as a
        coarse height grid to draw a map from, the vehicle, and the views."""
        site = None
        if self.seabed is not None:
            rows, columns = self.seabed.rows, self.seabed.columns
            step = max(1, max(rows, columns) // MAP_CELLS)
            coarse = self.seabed.heights[::step, ::step]
            site = {
                "acrossM": self.seabed.across,
                "rows": int(coarse.shape[0]), "columns": int(coarse.shape[1]),
                "heights": [round(float(h), 2) for h in coarse.ravel()],
                "deepestM": round(float(-self.seabed.heights.min()), 2),
                "shallowestM": round(float(-self.seabed.heights.max()), 2),
                "coral": self.coral,
            }
        elif self.bounds[0] is not None:
            corner, far = self.bounds
            site = {"acrossM": float(max(far[0] - corner[0], far[1] - corner[1])),
                    "rows": 0, "columns": 0, "heights": [],
                    "deepestM": round(float(-corner[2]), 2), "shallowestM": round(float(-far[2]), 2)}
        return {
            "kind": "hello",
            "site": site,
            "vehicle": {"thrusters": len(self.allocator.model.thrusters),
                        "capabilityN": [round(float(v), 1) for v in self.capability],
                        # How big it is, for a bracket drawn around it on the
                        # picture: a marker the size of the thing it marks.
                        "halfWidthM": round(float(self.half_width), 3),
                        "halfHeightM": round(float(self.half_height), 3),
                        "offsetM": list(self.hull_offset)},
            "views": list(VIEWS),
            "view": self.view,
            "beganAt": [round(float(v), 3) for v in self.began_at],
            "task": None if self.task is None else self.task.describe(),
            "conditions": self.conditions_said(),
            # What is deployed in this water and where, so a chart can draw it.
            # A console that shows a vehicle navigating and not what it is
            # navigating by is showing half of it.
            "positioning": self.positioning_said(),
        }

    def positioning_said(self) -> dict:
        """The technology this dive is navigating by, for the chart and the panel."""
        said = {"kind": str(self.aiding.get("kind", "none")),
                "fitted": dict(self.fitted),
                "suite": {**self.navigation_suite(), **self.fitted}}
        # Where the fixes actually come from, which is not always what the dive
        # was asked for: an array with no stated position is laid around the
        # start. What is drawn should be what is used.
        where = self.aiding.get("at")
        if where is None and self.navigation is not None and self.navigation.at is not None:
            where = [float(v) for v in self.navigation.at]
        # A transceiver with nowhere stated is a ship keeping station over the
        # vehicle — which is what the fix model does, taking the slant range as
        # the depth — so it is drawn above the vehicle rather than at a place.
        if said["kind"] == "usbl" and self.aiding.get("at") is None:
            said["overhead"] = True
        if where is not None:
            said["at"] = [round(float(v), 2) for v in where]
        for key in ("rangeM", "everyS", "accuracyM", "accuracyPercent"):
            if self.aiding.get(key) is not None:
                said[key] = self.aiding[key]
        # An array is three transponders in a triangle around its middle, and
        # that is how it is laid: a chart should show where they are rather
        # than a circle standing in for them.
        if said["kind"] == "lbl" and where is not None:
            import math as _math

            reach = float(self.aiding.get("rangeM", 150.0))
            laid = [
                [round(float(where[0]) + reach * 0.8 * _math.cos(a), 2),
                 round(float(where[1]) + reach * 0.8 * _math.sin(a), 2)]
                for a in (_math.radians(90), _math.radians(210), _math.radians(330))
            ]
            # On the bottom, where a transponder is: the array's stated depth
            # is the depth of the middle of it, and the seabed is not flat.
            for anchor in laid:
                floor = None if self.seabed is None else self.seabed.under(anchor[0], anchor[1])
                anchor.append(round(float(floor if floor is not None
                                          else (where[2] if len(where) > 2 else -10.0)) + 0.5, 2))
            said["anchors"] = laid
        return said

    def samples(self) -> dict:
        """The latest value on each topic, for a console plotting one.

        What the sensors would say, worked out from the state the same way the
        bridge works it out, so a plot of /depth is a plot of pressure whether
        or not a stack is listening to it.
        """
        depth = max(float(-self.position[2]), 0.0)
        R = self.rotation
        roll = float(np.arctan2(R[2, 1], R[2, 2]))
        pitch = float(-np.arcsin(max(-1.0, min(1.0, float(R[2, 0])))))
        yaw = float(np.arctan2(R[1, 0], R[0, 0]))
        said = {
            "/depth": {"fluidPressurePa": round(101325.0 + self.body.model.density * 9.80665 * depth, 1)},
            "/imu/data": {"rollDeg": round(np.degrees(roll), 2), "pitchDeg": round(np.degrees(pitch), 2),
                          "yawDeg": round(np.degrees(yaw), 2),
                          "p": round(float(self.velocity[3]), 4), "q": round(float(self.velocity[4]), 4),
                          "r": round(float(self.velocity[5]), 4)},
            "/dvl/twist": {"u": round(float(self.velocity[0]), 4), "v": round(float(self.velocity[1]), 4),
                           "w": round(float(self.velocity[2]), 4)},
            "/thruster_cmd": {f"t{i + 1}": round(float(c), 3) for i, c in enumerate(self.commands)},
        }
        if self.sensors_are_out:
            # Quiet, not zero. A sensor that has dropped out publishes nothing,
            # and a controller that treats missing as zero is the bug this is
            # here to find.
            return {"/thruster_cmd": said["/thruster_cmd"]}
        if self.navigation is not None:
            # What a stack subscribes to for its own position: the estimate,
            # never the truth. The truth is not on any topic, here or in the sea.
            said["/navigation"] = {
                "x": round(float(self.navigation.believed[0]), 3),
                "y": round(float(self.navigation.believed[1]), 3),
                "z": round(float(self.navigation.believed[2]), 3),
                "bottomLock": 1.0 if self.navigation.bottom_lock else 0.0,
                "sinceFixS": -1.0 if self.navigation.last_fix_t is None
                             else round(self.simulated - self.navigation.last_fix_t, 1),
            }
        if self.battery is not None:
            said["/battery"] = {"percentage": round(self.battery.fraction * 100.0, 2),
                                "voltage": round(self.battery.voltage * (0.85 + 0.15 * self.battery.fraction), 2),
                                "watts": round(self.battery.watts, 1),
                                "remainingWh": round(self.battery.remaining_wh, 2)}
        return said

    def observation(self):
        """What the vehicle knows about itself — not what is true about it.

        The difference is the whole of underwater navigation. A controller is
        handed where the vehicle believes it is, worked out from its log, its
        compass and its pressure sensor, and where it believes it is pointing,
        which is out by whatever the compass is out by. What is actually true
        stays here, for the tasks to score against and for the console to draw
        beside it.
        """
        from controllers import Observation

        floor = self.floor
        if self.seabed is not None:
            floor = self.seabed.under(float(self.position[0]), float(self.position[1]))
        if self.navigation is None:
            return Observation(t=self.simulated, position=self.position, velocity=self.velocity,
                               rotation=self.rotation, floor=floor, on_the_bottom=self.on_the_bottom)
        believed_floor = None if floor is None else floor + (self.navigation.believed[2] - float(self.position[2]))
        return Observation(t=self.simulated,
                           position=self.navigation.believed.copy(),
                           velocity=self.velocity,
                           rotation=self.navigation.believed_rotation(self.rotation),
                           floor=believed_floor,
                           on_the_bottom=self.on_the_bottom)

    def step(self) -> None:
        """One step of physics. Everything else is somebody else's schedule."""
        self.things_go_wrong()
        # Where it thinks it is, before anything is asked of it: a controller
        # commands on the estimate it had at the start of the step, which is
        # what one on a real vehicle does.
        if self.navigation is not None:
            floor = self.floor
            if self.seabed is not None:
                floor = self.seabed.under(float(self.position[0]), float(self.position[1]))
            self.navigation.step(self.simulated, self.position, self.velocity,
                                 self.rotation, floor, self.dt)
        self.commands = self.helm.command(self.observation())
        if self.dead_thrusters:
            # A thruster that has failed produces nothing, whatever it is
            # asked for. The allocator does not know, which is the point: the
            # vehicle is now asymmetric and the controller has to cope.
            for one_of_them in self.dead_thrusters:
                if one_of_them < len(self.commands):
                    self.commands[one_of_them] = 0.0

        # How much of the hull is under the surface. Everything the water does
        # — hold it up, slow it down, give the thrusters something to push
        # against, come along with it — is only true of the part that is in it.
        submerged = self.submerged()

        # What it cost. A flat battery is a vehicle with no thrusters, which
        # is a hull doing whatever its buoyancy says.
        if self.battery is not None:
            self.battery.draw(self.commands if not self.battery.flat else np.zeros_like(self.commands), self.dt)
            if self.battery.flat:
                self.commands = np.zeros_like(self.commands)

        # Drag is on the motion through the water. The current, in the body
        # frame, is taken off the ground velocity before the water sees it.
        through_water = self.velocity.copy()
        through_water[:3] -= self.rotation.T @ self.current
        wrench = self.body.step(self.rotation, through_water, self.commands, self.dt, submerged)
        effective = self.effective if submerged >= 1.0 else self.body.effective_mass(submerged)

        # Semi-implicit Euler at a fixed step. Not because it is the best
        # integrator but because it is the same integrator every time, which
        # matters more than accuracy for a result two runs must agree on.
        self.velocity[:3] += (wrench[:3] / effective[:3]) * self.dt
        self.velocity[3:] += (wrench[3:] / effective[3:]) * self.dt
        self.position += self.rotation @ self.velocity[:3] * self.dt
        # Attitude from the body rates, so that yaw is a heading somebody can
        # hold and roll and pitch are what the righting moment acts against.
        # Rodrigues on the small rotation this step; renormalised so a long
        # dive does not drift off orthonormal.
        self.rotation = self.rotation @ _turn(self.velocity[3:] * self.dt)
        self.simulated += self.dt
        self.taken += 1
        self.against_the_ground = False
        self.land()
        self.charge_at_the_dock()
        self.steer_to_the_task()
        self.consider_the_end()

        # Sensors at their own rate rather than every physics step: a real DVL
        # reports at tens of hertz, not two hundred, and a stack tuned against a
        # sensor that never lies about its rate will be surprised by one that
        # does.
        if self.bridge is not None and self.taken % 10 == 0:
            self.publish()

        # Once a second of simulated time, not of wall-clock: the report is part
        # of the run, and a report that depended on how fast the machine was
        # would make two runs of the same seed produce different records.
        if self.task is not None:
            floor = self.floor
            if self.seabed is not None:
                floor = self.seabed.under(float(self.position[0]), float(self.position[1]))
            self.task.step(self.simulated, self.position,
                           float(np.arctan2(self.rotation[1, 0], self.rotation[0, 0])), floor, self.commands)
        if self.recorder is not None:
            self.recorder.step(self)
        # Every five seconds of simulated time. One a second put four hundred
        # lines on a five-minute run's record that nobody reads one by one;
        # the console gets twenty a second over its own channel regardless.
        if self.simulated - self.reported >= 5.0:
            self.reported = self.simulated
            self.say("state", **self.state())

    def pose(self):
        """The hull's transform on this stage: its attitude and its position,
        in the stage's units and the stage's idea of up."""
        Gf = self._Gf
        R = self.rotation
        if self.up_axis == "Y":
            # Our z is the stage's y, our y the stage's -z: P maps a vector of
            # ours onto the stage, and the attitude becomes P R Pᵀ.
            P = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
            R = P @ R @ P.T
        # USD multiplies row vectors, so the matrix it wants is the transpose
        # of the one that turns a column vector.
        rows = R.T
        matrix = Gf.Matrix4d(
            float(rows[0, 0]), float(rows[0, 1]), float(rows[0, 2]), 0.0,
            float(rows[1, 0]), float(rows[1, 1]), float(rows[1, 2]), 0.0,
            float(rows[2, 0]), float(rows[2, 1]), float(rows[2, 2]), 0.0,
            0.0, 0.0, 0.0, 1.0)
        matrix.SetTranslateOnly(self.drawn_at(self.position))
        return matrix

    def drawn_at(self, position):
        """Where a point in metres falls on this stage.

        Two conversions, both the stage's business and neither the physics's:
        the unit it is measured in, and which way is up. A vehicle two metres
        down is drawn two metres down whether the author wrote centimetres and
        called Y the sky or not.
        """
        x, y, z = (float(v) * self.units_per_metre for v in position)
        if self.up_axis == "Y":
            return self._Gf.Vec3d(x, z, -y)
        return self._Gf.Vec3d(x, y, z)

    def land(self) -> None:
        """Stop the vehicle where the ground is: under it, and ahead of it.

        Not a collision solver. Two constraints, resolved by putting the
        vehicle back where it was allowed to be and taking away the velocity
        that carried it out, which is what a hard stop against ground does: it
        does not bounce and it does not keep pushing. A vehicle held down by
        its thrusters stays down, because the thrust is still applied; it
        simply cannot go through.

        The floor alone was not enough. Clamping depth and nothing else means
        a vehicle driven at the rising face of a spur is lifted up it a
        centimetre at a time — it crosses ground no vehicle could cross,
        silently, and a controller that did that in the sea would be in
        pieces. So ground too steep to ride over now stops it.
        """
        floor = self.floor
        if self.seabed is not None:
            floor = self.seabed.under(float(self.position[0]), float(self.position[1]))

        if floor is not None:
            bottom = floor + self.half_height
            if self.position[2] < bottom:
                self.position[2] = bottom
                self.settle()
            else:
                self.on_the_bottom = False

        self.strike()

        # There is no lid on the surface. There used to be, and it was never
        # reached, because it was only built for places that ship a water
        # layer. It is not wanted either: a vehicle that breaks the surface
        # loses its buoyancy and its thrust as it emerges and falls back on
        # its own, which is what a real one does and is worth being able to
        # see happen.

    # Ground steeper than this is a wall rather than a slope: a vehicle rides
    # over what it can and is stopped by what it cannot. Fifty degrees is well
    # past anything a reef's sand or rubble holds, and short of the near
    # vertical faces of a spur, which is exactly the line worth drawing.
    CLIMBS_UP_TO = math.cos(math.radians(50.0))

    def settle(self) -> None:
        """Take away the motion going into the ground, and leave the rest.

        The ground is a surface, not a lift. Clamping depth and zeroing the
        descent — which is all this used to do — meant a vehicle pressed onto a
        slope was carried up it at no cost, gaining height it never worked for.
        Removing the part of the motion that goes into the surface gives the
        right answer at every angle without a special case: on a flat bottom
        the descent stops, on a slope the push turns into travel along the
        slope and the vehicle keeps only what it did not spend climbing, and
        on a face near vertical almost nothing of it is left.
        """
        facing = (np.array([0.0, 0.0, 1.0]) if self.seabed is None
                  else self.seabed.normal(float(self.position[0]), float(self.position[1])))
        moving = self.rotation @ self.velocity[:3]
        into = float(np.dot(moving, facing))
        if into < 0.0:
            self.velocity[:3] = self.rotation.T @ (moving - facing * into)
        # Ground it is resting on, or a face it is up against. The two mean
        # different things to whoever is reading: one is a dive that has
        # landed, the other is a dive that is stuck.
        self.on_the_bottom = bool(facing[2] > 0.7)
        if facing[2] <= 0.7:
            self.against_the_ground = True

    def strike(self) -> None:
        """Stop the vehicle against ground it cannot ride over.

        It looks its own half-width ahead along the way it is actually moving,
        which is where it will meet something before its centre does. If the
        ground there stands above its keel and faces too steeply to be a slope,
        the part of its motion going into that face is taken away — the rest is
        left alone, so a vehicle stopped by a wall still slides along it, which
        is what happens and what a pilot expects.
        """
        if self.seabed is None:
            return
        moving = self.rotation @ self.velocity[:3]
        flat = moving[:2]
        speed = float(np.linalg.norm(flat))
        if speed < 1e-4:
            return
        ahead = self.position[:2] + (flat / speed) * self.half_width
        there = self.seabed.under(float(ahead[0]), float(ahead[1]))
        keel = float(self.position[2]) - self.half_height
        if there <= keel:
            return
        facing = self.seabed.normal(float(ahead[0]), float(ahead[1]))
        if facing[2] >= self.CLIMBS_UP_TO:
            return                      # a slope, not a wall: it may ride up
        into = facing[:2]
        length = float(np.linalg.norm(into))
        if length < 1e-9:
            return
        into = into / length
        going = float(np.dot(flat, into))
        if going >= 0.0:
            return                      # already leaving the face
        moving[:2] = flat - into * going
        self.velocity[:3] = self.rotation.T @ moving
        self.against_the_ground = True

    def charge_at_the_dock(self) -> None:
        """On the station, the battery fills. That is what a dock is for."""
        self.charging = False
        if self.battery is None or self.task is None:
            return
        from tasks import Dock, Mission, Wait

        stage = self.task.stage if isinstance(self.task, Mission) else self.task
        docked = False
        if isinstance(self.task, Mission):
            docked = any(one.get("kind") == "dock" and one.get("achieved", {}).get("docked")
                         for one in self.task.finished)
        if isinstance(stage, Wait) and docked:
            self.charging = True
            self.battery.charge(float(self.brief.get("dockWatts", 120.0)), self.dt)
        elif isinstance(stage, Dock) and stage.docked:
            self.charging = True
            self.battery.charge(float(self.brief.get("dockWatts", 120.0)), self.dt)

    def consider_the_end(self) -> None:
        """Every way a dive can be over other than its clock running out.

        A task that is done is a dive that is done: the machine goes back
        rather than holding station for the rest of an hour somebody asked for
        because they did not know how long the job would take.
        """
        if self.ended:
            return
        if self.task is not None and self.task.done:
            if str(self.brief.get("mode", "batch")) == "interactive":
                # Somebody is watching. Ending here would take the water away
                # from them at the exact moment there is something to look at,
                # and asking for another go would mean another dive and
                # another scene. The vehicle holds where it is, the console
                # says how it went, and they can try again or surface.
                if not self.task_over:
                    self.task_over = True
                    self.say("task_over", result=self.task.result(), attempt=self.attempts)
                return
            self.finish("failed" if self.task.failed() else "achieved")
            return
        if self.battery is not None and self.battery.flat:
            self.finish("battery")
            return
        # The failsafe has taken the vehicle and got it there.
        decided = self.helm.failsafe.decided
        if decided == "surface" and self.submerged() < 1.0:
            self.finish("surfaced")
        elif decided == "dock" and self.helm.failsafe.pursue.holding:
            self.finish("home")

    def submerged(self) -> float:
        """The share of the hull under the surface, from one to nothing.

        The hull is treated as a box of its own height, so it goes from wholly
        under to wholly out over its own depth rather than all at once. Sudden
        is what makes a surface model unusable: a vehicle that loses all its
        buoyancy in one step leaves at speed.
        """
        if self.water_level is None:
            return 1.0
        top_of_hull = float(self.position[2]) + self.half_height
        if top_of_hull <= self.water_level:
            return 1.0
        under = self.water_level - (float(self.position[2]) - self.half_height)
        return float(max(0.0, min(1.0, under / max(1e-6, 2.0 * self.half_height))))

    def across_metres(self) -> float:
        """How wide this place is, in metres."""
        corner, far = self.bounds
        if corner is None:
            return 1000.0
        return max(float(far[0] - corner[0]), float(far[1] - corner[1]))

    def stir(self) -> None:
        """Move the water. Still caustics are a painted floor."""
        if self.water is not None:
            self.water.drift(self.stage, self.simulated, follow=self.position)
            self.water.light_for(self.stage, float(-self.position[2]))

    def show(self) -> None:
        """Move what is drawn to where the vehicle is.

        Separate from step() because it is not part of the dive: a headless run
        computes the same trajectory without ever doing this, and it must.
        """
        self.placement.Set(self.pose())

    def state(self) -> dict:
        return {
            "t": round(self.simulated, 3),
            "depthM": round(float(-self.position[2]), 4),
            "headingDeg": round(float(np.degrees(np.arctan2(self.rotation[1, 0], self.rotation[0, 0]))), 2),
            "pitchDeg": round(float(np.degrees(-np.arcsin(max(-1.0, min(1.0, float(self.rotation[2, 0])))))), 2),
            "rollDeg": round(float(np.degrees(np.arctan2(self.rotation[2, 1], self.rotation[2, 2]))), 2),
            "speedMs": round(float(np.linalg.norm(self.velocity[:3])), 4),
            "submerged": round(self.submerged(), 3),
            "surfaced": self.submerged() < 1.0,
            "againstTheGround": self.against_the_ground,
            "carried": self.carried,
            **({} if self.navigation is None
               else {"navigation": self.navigation.said(self.position, self.simulated)}),
            "attempt": self.attempts,
            "taskOver": self.task_over,
            **({"sensorsOut": True} if self.sensors_are_out else {}),
            **({"deadThrusters": sorted(self.dead_thrusters)} if self.dead_thrusters else {}),
            **({} if self.battery is None else {"battery": self.battery.said(),
                                                "charging": self.charging}),
            "commanded": bool(self.bridge.commanded) if self.bridge else False,
            "byHand": self.flown_by_hand,
            "flying": self.helm.flying.name,
            "onTheBottom": self.on_the_bottom,
            "thrust": [round(float(c), 3) for c in self.commands],
            "position": [round(float(x), 4) for x in self.position],
        }

    def instruments(self, whole: bool = True) -> dict:
        """Everything an operator's panels want, in one reading.

        More than state() carries, because state() goes into the run's record
        and this goes onto somebody's screen twenty times a second. The record
        should stay small; a screen can afford the whole vehicle.

        Not all of it every frame, though. The topic tree, every controller's
        every declared parameter and the vehicle's fixed numbers do not change
        between one twentieth of a second and the next, and sending them
        anyway cost as much as the picture did — a megabit and a half of the
        same JSON, twenty times a second. They go once a second; the numbers
        that move go every frame, and a console keeps what it was last told.
        """
        reading = self.state()
        reading["velocity"] = [round(float(v), 4) for v in self.velocity[:3]]
        reading["rates"] = [round(float(v), 4) for v in self.velocity[3:]]
        reading["thrusters"] = len(self.allocator.model.thrusters)
        floor = self.floor
        if self.seabed is not None:
            floor = self.seabed.under(float(self.position[0]), float(self.position[1]))
        reading["floorM"] = None if floor is None else round(floor, 2)
        reading["altitudeM"] = (None if floor is None
                                else round(float(self.position[2]) - floor, 3))
        reading["netBuoyancyN"] = round(self.model_net_buoyancy(), 3)
        reading["samples"] = self.samples()
        reading["view"] = self.view
        reading["task"] = None if self.task is None else self.task.progress()
        if self.bridge is not None:
            reading["commandsReceived"] = self.bridge.commands_seen
        if not whole:
            return reading
        reading["controller"] = self.helm.describe()
        if self.bridge is not None:
            reading["topics"] = self.bridge.topics()
        else:
            # Nobody is listening, so nothing crosses — but the vehicle still
            # carries these, and a console should be able to plot what its
            # sensors would say. The contract, marked as not open.
            reading["topics"] = self.contract_topics()
        return reading

    def contract_topics(self) -> list[dict]:
        """The vehicle's topic contract as a tree with nothing crossing it."""
        if not hasattr(self, "_contract"):
            self._contract = []
            try:
                import json
                described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                        / "dynamics.json").read_text())
                contract = described.get("topicContract", {})
                for topic in contract.get("publishes", []):
                    self._contract.append({"name": topic["topic"], "type": topic["type"], "way": "from"})
                for topic in contract.get("subscribes", []):
                    self._contract.append({"name": topic["topic"], "type": topic["type"], "way": "to"})
            except Exception:
                pass
        return [{**topic, "messages": 0, "rateHz": 0.0, "open": False} for topic in self._contract]

    def model_net_buoyancy(self) -> float:
        return float(self.body.model.net_buoyancy_n)

    def camera(self) -> dict | None:
        """The vehicle's camera, as the catalogue describes it, for whoever
        turns poses into coverage."""
        try:
            import json
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
            for sensor in described.get("sensors", []):
                if sensor.get("kind") == "underwater_camera":
                    return {k: sensor[k] for k in ("name", "focalLengthMm", "widthPx", "heightPx",
                                                    "horizontalFovDeg", "verticalFovDeg") if k in sensor}
        except Exception:
            pass
        return None

    def close(self) -> None:
        if self.recorder is not None:
            try:
                manifest = self.recorder.close(self, self.camera())
                self.say("recorded", poses=manifest["poses"], frames=manifest["frames"])
            except Exception as exc:
                self.say("recording_failed", why=str(exc)[:160])
            self.recorder = None
        result = None if self.task is None else self.task.result()
        if result is not None:
            # Which controller had the vehicle, and who worked out the path it
            # was following. A result without these is a number nobody can
            # attribute, which is what every dive in the record was until now.
            result["flownBy"] = self.helm.who_flew()
            result["plannedBy"] = self.planned_by or None
            # What the slow loops did, when anything used one: how many
            # thoughts, how long they took, and how many failed. A controller
            # that scores well by thinking for four seconds a step is not
            # obviously the better controller, and this is where that shows.
            thought = self.helm.thought()
            if thought:
                result["thought"] = thought
        if result is not None and self.battery is not None:
            # A controller that does the job on half the charge is the better
            # controller, and until now there was no way to say so.
            result["energyWh"] = round(self.battery.spent_wh, 3)
        self.say("settled",
                 t=round(self.simulated, 3),
                 depthM=round(float(-self.position[2]), 4),
                 speedMs=round(float(np.linalg.norm(self.velocity[:3])), 4),
                 ended=self.ended or "time",
                 carried=self.carried,
                 attempts=self.attempts,
                 **({} if self.navigation is None
                    else {"navigation": self.navigation.said(self.position, self.simulated)}),
                 **({} if self.battery is None else {"battery": self.battery.said()}),
                 **({} if result is None else {"task": result}))
        if self.bridge is not None:
            # Whether anything actually flew it. A dive that ran with nobody at
            # the controls is a valid result and a different one, and the
            # difference should not have to be inferred from the trajectory.
            self.say("autonomy",
                     commanded=bool(self.bridge.commanded),
                     commandsReceived=self.bridge.commands_seen)
            self.bridge.close()
            self.bridge = None
