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
    of it; nothing here needs USD to be loaded to answer a chart."""
    import json
    import re

    try:
        named = json.loads((city / "site.json").read_text()).get("layers", {}).get("coral", "coral.usda")
        text = (city / named).read_text(errors="ignore")
    except Exception:
        return []
    found = re.search(r"positions\s*=\s*\[([^\]]*)\]", text)
    if not found:
        return []
    points = re.findall(r"\(\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*[-0-9.eE+]+\s*\)", found.group(1))
    if not points:
        return []
    step = max(1, len(points) // at_most)
    return [[round(float(x), 1), round(float(y), 1)] for x, y in points[::step]]


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
        self.coral: list[list[float]] = []
        self.view = "chase"
        self.began_at = np.zeros(3)
        # The water's own motion, in the world frame, metres per second. Read
        # from the dive's conditions: still unless they say otherwise. Drag
        # acts on the vehicle's motion through the water, not over the ground,
        # so a vehicle doing nothing in a current is carried by it.
        self.current = np.zeros(3)
        self.visibility_m = None
        self.read_conditions(brief.get("conditions"))
        # What the dive is for, judged as it runs. None when it is only flown.
        self.task = None
        # What it leaves behind. Opened with the task, beside the brief.
        self.recorder = None
        self.water_level = None
        self.water = None
        self.on_the_bottom = False

        # How far the vehicle's middle is from its bottom. Taken from the hull
        # when one is drawn, and a guess otherwise — a vehicle resting exactly
        # on the floor with its centre on the floor is half buried.
        self.half_height = 0.15

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
        self.coral = coral_positions(pathlib.Path(self.brief.get("cityPath", "/dive/city")))
        if self.coral:
            self.say("coral_charted", colonies=len(self.coral))
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
                self.say("hull_drawn", file=hull.name, metresAcross=size)

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
        return self.taken >= self.steps

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

    def conditions_said(self) -> dict:
        speed = float(np.hypot(self.current[0], self.current[1]))
        heading = (90.0 - np.degrees(np.arctan2(self.current[1], self.current[0]))) % 360.0 if speed > 1e-9 else 0.0
        return {"currentMetresPerSecond": round(speed, 3), "currentHeadingDeg": round(float(heading), 1),
                "current": [round(float(v), 4) for v in self.current[:2]],
                "visibilityM": self.visibility_m}

    def begin_task(self, objective) -> None:
        """Where the dive begins is where its task is measured from.

        Called once the vehicle is placed; the tank calls it itself, since it
        never opens a scene.
        """
        from tasks import task_for

        self.began_at = self.position.copy()
        self.task = task_for(objective, self.began_at,
                             float(np.arctan2(self.rotation[1, 0], self.rotation[0, 0])),
                             camera=self.camera())
        if self.task is not None:
            self.say("task_set", task=self.task.describe())
            # A dive that is for something records; a survey looks down, since
            # what it records is what it sees. A console may look elsewhere.
            if self.task.kind == "survey":
                self.view = "down"
            try:
                from recording import Recorder
                self.recorder = Recorder(pathlib.Path(self.brief.get("recordInto",
                                         str(pathlib.Path(self.brief.get("cityPath", "/dive/city")).parent / "recording"))))
                self.recorder.camera = self.camera()
                self.say("recording", into=str(self.recorder.into))
            except Exception as exc:
                self.say("recording_unavailable", why=str(exc)[:160])

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
                        "capabilityN": [round(float(v), 1) for v in self.capability]},
            "views": list(VIEWS),
            "view": self.view,
            "beganAt": [round(float(v), 3) for v in self.began_at],
            "task": None if self.task is None else self.task.describe(),
            "conditions": self.conditions_said(),
        }

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
        return said

    def observation(self):
        from controllers import Observation

        floor = self.floor
        if self.seabed is not None:
            floor = self.seabed.under(float(self.position[0]), float(self.position[1]))
        return Observation(t=self.simulated, position=self.position, velocity=self.velocity,
                           rotation=self.rotation, floor=floor, on_the_bottom=self.on_the_bottom)

    def step(self) -> None:
        """One step of physics. Everything else is somebody else's schedule."""
        self.commands = self.helm.command(self.observation())

        # Drag is on the motion through the water. The current, in the body
        # frame, is taken off the ground velocity before the water sees it.
        through_water = self.velocity.copy()
        through_water[:3] -= self.rotation.T @ self.current
        wrench = self.body.step(self.rotation, through_water, self.commands, self.dt)

        # Semi-implicit Euler at a fixed step. Not because it is the best
        # integrator but because it is the same integrator every time, which
        # matters more than accuracy for a result two runs must agree on.
        self.velocity[:3] += (wrench[:3] / self.effective[:3]) * self.dt
        self.velocity[3:] += (wrench[3:] / self.effective[3:]) * self.dt
        self.position += self.rotation @ self.velocity[:3] * self.dt
        # Attitude from the body rates, so that yaw is a heading somebody can
        # hold and roll and pitch are what the righting moment acts against.
        # Rodrigues on the small rotation this step; renormalised so a long
        # dive does not drift off orthonormal.
        self.rotation = self.rotation @ _turn(self.velocity[3:] * self.dt)
        self.simulated += self.dt
        self.taken += 1
        self.land()

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
        """Stop the vehicle at the bottom, and at the surface.

        Not a collision solver — a floor and a ceiling. It resolves by putting
        the vehicle back where it was allowed to be and taking away the velocity
        that carried it out, which is what a hard stop against a tank floor
        does: it does not bounce and it does not keep pushing.

        A vehicle held down by its thrusters stays down, because the thrust is
        still applied; it simply cannot go through. That is the behaviour worth
        having before a real height query exists, and it is the difference
        between a dive that ends on the bottom and one that leaves the world.
        """
        floor = self.floor
        if self.seabed is not None:
            floor = self.seabed.under(float(self.position[0]), float(self.position[1]))

        if floor is not None:
            bottom = floor + self.half_height
            if self.position[2] < bottom:
                self.position[2] = bottom
                if self.velocity[2] < 0.0:
                    self.velocity[2] = 0.0
                    self.on_the_bottom = True
                return
            self.on_the_bottom = False

        # The surface is a lid for the same reason. A vehicle that rises through
        # it is a vehicle in the air, which this simulator has nothing true to
        # say about.
        if self.water_level is not None:
            top = self.water_level - self.half_height
            if self.position[2] > top:
                self.position[2] = top
                if self.velocity[2] > 0.0:
                    self.velocity[2] = 0.0

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
            "commanded": bool(self.bridge.commanded) if self.bridge else False,
            "byHand": self.flown_by_hand,
            "flying": self.helm.flying.name,
            "onTheBottom": self.on_the_bottom,
            "thrust": [round(float(c), 3) for c in self.commands],
            "position": [round(float(x), 4) for x in self.position],
        }

    def instruments(self) -> dict:
        """Everything an operator's panels want, in one reading.

        More than state() carries, because state() goes into the run's record
        and this goes onto somebody's screen twenty times a second. The record
        should stay small; a screen can afford the whole vehicle.
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
        reading["controller"] = self.helm.describe()
        reading["samples"] = self.samples()
        reading["view"] = self.view
        reading["task"] = None if self.task is None else self.task.progress()
        if self.bridge is not None:
            reading["topics"] = self.bridge.topics()
            reading["commandsReceived"] = self.bridge.commands_seen
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
        self.say("settled",
                 t=round(self.simulated, 3),
                 depthM=round(float(-self.position[2]), 4),
                 speedMs=round(float(np.linalg.norm(self.velocity[:3])), 4),
                 **({} if self.task is None else {"task": self.task.result()}))
        if self.bridge is not None:
            # Whether anything actually flew it. A dive that ran with nobody at
            # the controls is a valid result and a different one, and the
            # difference should not have to be inferred from the trajectory.
            self.say("autonomy",
                     commanded=bool(self.bridge.commanded),
                     commandsReceived=self.bridge.commands_seen)
            self.bridge.close()
            self.bridge = None
