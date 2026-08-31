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


def find_scene(root: pathlib.Path) -> pathlib.Path | None:
    """The USD a place is loaded from.

    A place may carry several — a scene and a water surface, say — so the one
    that is not obviously a component is chosen, and the choice is reported so
    that nobody has to guess which was used.
    """
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

        # What a person at the controls is asking for, as a body-frame wrench:
        # surge, sway, heave, roll, pitch, yaw. Held here rather than in the
        # shell so that flying it by hand goes through the same allocator and
        # the same thrusters as flying it by program. A pilot and a controller
        # should be able to do exactly the same things to this vehicle, and
        # neither should be able to do anything the other cannot.
        self.hand = np.zeros(6)
        self.flown_by_hand = False

        # What this vehicle can do on each axis, so that a fraction asked for by
        # a person can be turned into the force it meant.
        self.capability = allocator.capability()

        # Filled in when the place is opened: where its floor is, and where the
        # top of its water is. Both in metres, in the dive's own frame.
        self.floor = None
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

        if drawn:
            # Water. The fog that is the medium, the sun through the surface,
            # the surface seen from below, and the caustics it throws down.
            import water
            water.make(stage, self.say,
                       floor=self.floor if self.floor is not None else -20.0,
                       water_level=0.0,
                       across=float(extent[0]) if extent else 1000.0)
            self.water = water

        # A body of the vehicle's actual mass, at the vehicle's actual place.
        # What is being integrated is the dynamics; a dive that reported a
        # trajectory it had not computed would be worse than one that reported
        # no picture.
        self.vehicle_path = "/World/Vehicle"
        xform = UsdGeom.Xform.Define(stage, self.vehicle_path)
        self.placement = xform.AddTranslateOp()
        self._Gf = Gf
        self.placement.Set(self.drawn_at(self.position))

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

        self.say("vehicle_placed",
                 position=[round(float(x), 3) for x in self.position])
        return True

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
            self.bridge = Bridge(self.allocator.model, self.allocator,
                                 int(self.brief.get("rosDomainId", 0)),
                                 logger=lambda kind, **d: self.say(kind, **d))
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
                                self.body.model.density)

    # ── running ──────────────────────────────────────────────────────────────

    @property
    def done(self) -> bool:
        return self.taken >= self.steps

    def take_the_controls(self, asked) -> None:
        """A person is flying it. What they ask for is a fraction, not a force.

        Half ahead and full rise are fractions of what this vehicle can do, and
        turning them into a wrench is the vehicle's business — it is the only
        thing that knows what it can do. Handing the fraction straight to the
        allocator asks a hundred-newton vehicle for half a newton, which is
        exactly what happened: the keys arrived, the display said somebody was
        flying, and the vehicle sat there.

        Ends any deference to autonomy for as long as the hand is on the
        controls. There is no arbitration beyond that and there should not be:
        two things flying one vehicle is not a mode anybody wants, and a pilot
        who has taken hold of it has said which one wins.
        """
        fraction = np.clip(np.asarray(asked, dtype=float), -1.0, 1.0)
        self.hand = fraction * self.capability
        self.flown_by_hand = bool(np.any(fraction))

    def step(self) -> None:
        """One step of physics. Everything else is somebody else's schedule."""
        if self.flown_by_hand:
            self.commands = self.allocator.allocate(self.hand)
        elif self.bridge is not None:
            self.commands = self.bridge.commands()

        wrench = self.body.step(self.rotation, self.velocity, self.commands, self.dt)

        # Semi-implicit Euler at a fixed step. Not because it is the best
        # integrator but because it is the same integrator every time, which
        # matters more than accuracy for a result two runs must agree on.
        self.velocity[:3] += (wrench[:3] / self.effective[:3]) * self.dt
        self.velocity[3:] += (wrench[3:] / self.effective[3:]) * self.dt
        self.position += self.rotation @ self.velocity[:3] * self.dt
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
        if self.simulated - self.reported >= 1.0:
            self.reported = self.simulated
            self.say("state", **self.state())

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

    def stir(self) -> None:
        """Move the water. Still caustics are a painted floor."""
        if self.water is not None:
            self.water.drift(self.stage, self.simulated, follow=self.position)

    def show(self) -> None:
        """Move what is drawn to where the vehicle is.

        Separate from step() because it is not part of the dive: a headless run
        computes the same trajectory without ever doing this, and it must.
        """
        self.placement.Set(self.drawn_at(self.position))

    def state(self) -> dict:
        return {
            "t": round(self.simulated, 3),
            "depthM": round(float(-self.position[2]), 4),
            "speedMs": round(float(np.linalg.norm(self.velocity[:3])), 4),
            "commanded": bool(self.bridge.commanded) if self.bridge else False,
            "byHand": self.flown_by_hand,
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
        if self.bridge is not None:
            reading["topics"] = self.bridge.topics()
            reading["commandsReceived"] = self.bridge.commands_seen
        else:
            reading["topics"] = []
        return reading

    def model_net_buoyancy(self) -> float:
        return float(self.body.model.net_buoyancy_n)

    def close(self) -> None:
        self.say("settled",
                 t=round(self.simulated, 3),
                 depthM=round(float(-self.position[2]), 4),
                 speedMs=round(float(np.linalg.norm(self.velocity[:3])), 4))
        if self.bridge is not None:
            # Whether anything actually flew it. A dive that ran with nobody at
            # the controls is a valid result and a different one, and the
            # difference should not have to be inferred from the trajectory.
            self.say("autonomy",
                     commanded=bool(self.bridge.commanded),
                     commandsReceived=self.bridge.commands_seen)
            self.bridge.close()
            self.bridge = None
