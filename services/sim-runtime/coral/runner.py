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

import json
import math
import os
import pathlib

import numpy as np

from engine import Engine
from systems import contact
from systems.build import the_ocean, the_systems
from systems.helm import observe

# Fixed, and not negotiable: a variable timestep makes two runs of the same seed
# diverge, and everything the platform claims about a result rests on them not
# diverging. 200 Hz is comfortably above the vehicle's dynamics and cheap.
PHYSICS_HZ = 200.0

# What computed this, as a number that changes when the answer would.
#
# The record pins the place, the vehicle, the water and the seed, and pinned
# none of that mattered while the simulator itself was moving under it: the
# physics changed six times in one day and every result from before became
# incomparable with every result after, silently. A runtime version tag does
# not help — the tag stayed `r1` through all six.
#
# So: a plain integer, bumped by hand, here, whenever a change would move a
# number somebody might put in a table. It does not need to be clever. It
# needs to change when the answer would. Say what changed in the list below so
# that two versions can be told apart by somebody reading the record rather
# than by reading the diff.
#
#   1  where this began: thruster geometry, the depth loop, the EOS-80 water,
#      the glider's flight model, navigation from a laid array, a world with
#      things in it to run into.
#   2  the tether. Every tethered dive before this flew as though the umbilical
#      were not there, and a working scope in half a knot pulls three times
#      what the hull's own drag costs — so no result from either side of this
#      line belongs in a table with the other. It also puts a hard limit on
#      reach: a vehicle on a hundred metres of cable cannot get to a point a
#      hundred and twenty metres away, which it could the day before.
PHYSICS = 2
PHYSICS_IS = ("thruster geometry at the centre of gravity, EOS-80 water, "
              "Eriksen flight for a glider, LBL from the transponders that "
              "were laid, a world a vehicle can run into, and the cable it "
              "is on")


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

    def under_many(self, x, y) -> np.ndarray:
        """`under` for many points at once: a cable's nodes, a school's fish."""
        u = np.clip((np.asarray(x, dtype=float) / self.across + 0.5) * (self.columns - 1), 0.0, self.columns - 1.0001)
        v = np.clip((np.asarray(y, dtype=float) / self.across + 0.5) * (self.rows - 1), 0.0, self.rows - 1.0001)
        column, row = u.astype(int), v.astype(int)
        fu, fv = u - column, v - row
        h = self.heights
        return (h[row, column] * (1 - fu) * (1 - fv) + h[row, column + 1] * fu * (1 - fv)
                + h[row + 1, column] * (1 - fu) * fv + h[row + 1, column + 1] * fu * fv).astype(float)

    def normal_many(self, x, y) -> np.ndarray:
        """`normal` for many points at once, (n, 3)."""
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        step = self.across / max(1, self.columns - 1)
        east = self.under_many(x + step, y) - self.under_many(x - step, y)
        north = self.under_many(x, y + step) - self.under_many(x, y - step)
        normal = np.column_stack([-east, -north, np.full_like(east, 2.0 * step)])
        return normal / np.linalg.norm(normal, axis=1, keepdims=True)

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


# What a lumen is worth to the renderer.
#
# A subsea lamp is rated in lumens and USD wants an intensity, and there is no
# clean conversion: it depends on the light's area, whether it is normalised,
# and what the camera is exposed for. Read off a ladder rather than derived,
# and named so the next person knows it was measured and not calculated.
# Lumens to whatever the renderer means by intensity.
#
# A rect light with normalize off emits radiance, so what arrives is intensity
# times area — and a lamp is eight centimetres across while the caustic sheet
# it was measured against is ninety metres. Eight thousand times less area.
#
# Measured rather than derived: two rect lights of the same kind were put at
# the same place, one at ninety metres and 5200 and one at the lamp's size and
# brightness, and the first moved the frame by twenty points and the second by
# nothing. This is the number that makes their totals match. It is a unit
# conversion and nothing else; the fifteen watts and fifteen hundred lumens in
# the vehicle's package are the real quantities.
#
# Set at six hundred metres, where the lamps are the only light there is, and
# then brought down because at six metres in daylight they burned the near
# ground to white. That they need one number for both is the camera's fault
# rather than the lamp's: the exposure is computed from depth by a formula
# instead of from what is actually in front of the lens, so the deep frame is
# metered eight times more sensitively than the shallow one and a lamp correct
# in one is wrong in the other. When the camera meters properly this becomes a
# real photometric conversion and stops being a compromise.
LAMP_SCALE = 70_000.0


def lamp_nits(lumens: float, across_m: float) -> float:
    """What a rect light has to be set to for a lamp of this many lumens.

    The compromise above is over. It said, in as many words, that when the
    camera metered properly this would become a real photometric conversion —
    and the camera does now, and the lamps now point where they are aimed
    rather than behind the vehicle, which is the other half of why seventy
    thousand was ever needed. A number tuned to make a light that was facing
    the wrong way show up at all is not a unit conversion.

    A Lambertian emitter of area A radiating a luminous flux into the
    hemisphere in front of it has luminance

        L = flux / (A x pi)

    and that is what a rect light's intensity is in. Fifteen hundred lumens
    across the eight centimetres of a Lumen Subsea's face is about seventy-four
    thousand candela a square metre — which is a bright lamp, and is four
    orders of magnitude below the hundred million the old scale produced.
    """
    area = max(float(across_m) * float(across_m), 1e-9)
    return float(lumens) / (area * math.pi)


def asked_for(name: str, fallback=None):
    """A number from the environment, where unset and empty mean the same.

    Docker passes an unset variable through as an empty string, so
    `os.environ.get(name, default)` hands back `""` rather than the default and
    `float("")` raises. That exception happened inside opening a dive, so the
    dive failed, no frames were written, and the previous run's frames and log
    were left sitting where the next comparison would read them. Several hours
    of "this change did nothing" were that.
    """
    said = os.environ.get(name, "")
    if said is None or said == "":
        return fallback
    try:
        return float(said)
    except ValueError:
        return fallback


def aiming(towards):
    """A rotation that takes a rect light's own -Z round to point at `towards`.

    Row-vector convention, which is USD's: a direction d is sent to d @ R. So
    what this has to satisfy is `(0, 0, -1) @ aiming(t) == t`, and that is
    exactly what it is tested against — for level aims, for straight down, for
    straight up, and for a bearing off to one side, which is the case the
    old swing-then-tip ordering silently dropped.
    """
    import numpy as _np

    towards = _np.asarray(towards, dtype=float)
    towards = towards / max(float(_np.linalg.norm(towards)), 1e-12)
    down = _np.array([0.0, 0.0, -1.0])
    axis = _np.cross(down, towards)
    length = float(_np.linalg.norm(axis))
    if length < 1e-9:
        # Parallel or opposite: no unique axis, so pick one and turn a half
        # turn if it is opposite.
        if float(_np.dot(down, towards)) > 0.0:
            return _np.eye(3)
        return _np.diag([1.0, -1.0, -1.0])
    axis = axis / length
    angle = math.acos(max(-1.0, min(1.0, float(_np.dot(down, towards)))))
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    # Rodrigues, written out already transposed for the row-vector
    # convention — so no `.T` on the end. Putting one there as well turns it
    # back into the column-vector form, which sends every aim to its mirror.
    return _np.array([
        [c + x * x * (1 - c), x * y * (1 - c) + z * s, x * z * (1 - c) - y * s],
        [y * x * (1 - c) - z * s, c + y * y * (1 - c), y * z * (1 - c) + x * s],
        [z * x * (1 - c) + y * s, z * y * (1 - c) - x * s, c + z * z * (1 - c)],
    ])


def _kept(part: str, field: str | None = None):
    """An attribute of the dive whose value lives in its world.

    The dive's state used to be the dive's attributes, and three thousand
    lines read and write them by those names: the console, the drawing, the
    reports, the tests. The state now lives in the world, owned by the system
    that writes it (systems/), and these are the old names for the new
    places, so that everything outside the tick keeps working while it is
    moved out of here a piece at a time.
    """
    if field is None:
        return property(lambda self: self.ocean[part],
                        lambda self, value: self.ocean.replace(part, value))
    return property(lambda self: getattr(self.ocean[part], field),
                    lambda self, value: setattr(self.ocean[part], field, value))


class Dive:
    """A vehicle, in a place, being integrated.

    Construct it with the brief; call open() once, then step() as often as you
    like. Nothing here knows whether a human is watching, and nothing here
    updates the application — whoever is running it decides when to draw.
    """

    # Where each piece of the dive's state lives now: (part, field) of its
    # world. See `_kept`.
    simulated = _kept("clock", "simulated")
    taken = _kept("clock", "taken")
    position = _kept("vehicle", "position")
    velocity = _kept("vehicle", "velocity")
    rotation = _kept("vehicle", "rotation")
    effective = _kept("vehicle", "effective")
    half_width = _kept("vehicle", "half_width")
    half_height = _kept("vehicle", "half_height")
    on_the_bottom = _kept("vehicle", "on_the_bottom")
    against_the_ground = _kept("vehicle", "against_the_ground")
    last_wrench = _kept("vehicle", "wrench")
    _struck = _kept("contacts", "struck")
    _grounded = _kept("contacts", "grounded")
    _glass_strikes = _kept("contacts", "glass")
    _on_the_glass = _kept("contacts", "on_the_glass")
    tether = _kept("cable")
    current = _kept("water", "current")
    wind = _kept("water", "wind")
    water = _kept("water", "sea")
    water_level = _kept("water", "level")
    salinity_psu = _kept("water", "salinity")
    seabed = _kept("place", "seabed")
    floor = _kept("place", "floor")
    interior = _kept("place", "interior")
    world = _kept("place", "things")
    failures = _kept("faults", "failures")
    dead_thrusters = _kept("faults", "dead")
    sensors_out_until = _kept("faults", "sensors_out_until")
    view = _kept("camera", "view")
    navigation = _kept("navigation")
    ctd = _kept("ctd", "config")
    profile = _kept("ctd", "profile")
    ctd_last_t = _kept("ctd", "last_t")
    multibeam = _kept("multibeam")
    sonar = _kept("sonar")
    helm = _kept("helm")
    commands = _kept("thrust", "commands")
    battery = _kept("power", "battery")
    charging = _kept("power", "charging")
    task = _kept("task", "task")
    ended = _kept("task", "ended")
    task_over = _kept("task", "task_over")
    attempts = _kept("task", "attempts")
    route_flying = _kept("task", "route_flying")
    document = _kept("task", "document")
    planned_by = _kept("task", "planned_by")
    _asked_for = _kept("task", "asked_for")
    _tuned_from_objective = _kept("task", "tuned_from_objective")
    recorder = _kept("record")
    bridge = _kept("bridge")
    shoal = _kept("fish")

    def __init__(self, brief: dict, body, allocator, scene: pathlib.Path,
                 say) -> None:
        self.brief = brief
        self.body = body
        self.allocator = allocator
        self.scene = scene
        self.say = say
        # Everything the dive is, in the parts its systems own. First, because
        # every assignment below lands in it.
        self.ocean = the_ocean(body, len(allocator.model.thrusters), 1.0 / PHYSICS_HZ)
        self.ocean.thrust.read_the_package(
            pathlib.Path(brief.get("vehiclePath", "/dive/vehicle")) / "dynamics.json")

        self.dt = 1.0 / PHYSICS_HZ
        self.steps = int(brief.get("durationSeconds", 10.0) * PHYSICS_HZ)
        self.taken = 0
        self.simulated = 0.0

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
        # A wind over the surface, in the world frame, metres per second. In a
        # tank it is a fan; it ripples the surface and drags the top of the
        # water with it, and nothing below a few centimetres feels it.
        self.wind = np.zeros(3)
        # What a place that is a room says about itself: how its cameras sit
        # and the box of water a vehicle is kept inside. Empty for a reef.
        self.place_cameras: dict = {}
        self.interior = None
        self.lamp_intensity = 0.0
        self.lamp_lumens = 0.0
        # How far the snow box reaches from the camera. Four metres: past
        # that a two-millimetre aggregate is under a pixel and the lamp has
        # nothing left to give it, so drawing more is cost without picture.
        self.snow = None
        self.visibility_m = None
        # Which of Jerlov's waters this is. Named by the conditions, because
        # "clear Red Sea" and "the Keys in August" are selections a person
        # makes and not numbers they should have to supply.
        self.water_type = None
        # And what the sea on top of it is doing. The two numbers a wave buoy
        # reports, which is what an observed condition carries.
        self.sea_height_m = None
        self.sea_period_s = None
        self.sea_heading_deg = None
        self.read_conditions(brief.get("conditions"))
        # What somebody put in the water here. Empty when the dive was flown
        # over bare ground, which most are and always will be.
        from world import World

        self.world = World(brief.get("layout"))
        self._struck: set[str] = set()   # said once each, not once a step
        # And the seabed, separately, because they are different mistakes. A
        # vehicle that clips a nursery frame has hit something somebody put
        # there; one that flies into a spur has hit the place.
        self._grounded = 0
        # The cable, if this vehicle is on one. Set up once the vehicle has
        # been placed, because a tether is a line between two points and one of
        # them is the vehicle.
        self.tether = None
        # The sonar, if the vehicle carries one. Built once the packages are
        # read, because it is described by the vehicle's own package.
        self.sonar = None
        self.multibeam = None
        # The thin pipe to the surface, if the vehicle carries one.
        self.modem = None
        # And the instrument that reads the water it is flying in.
        self.ctd = None
        self.profile = []
        self.ctd_last_t = None
        self.world.version = str(brief.get("layoutVersionId") or "")
        # And the world not being as drawn, which is a scenario's business
        # rather than a layout's: the mooring thirty metres from where it was
        # laid, a transponder down, a net where the chart says clear water.
        for one in self.world.not_as_drawn(brief.get("layoutChanges")):
            self.say("not_as_drawn", what=one)
        # The battery the vehicle package declares. A vehicle that declares
        # none flies as everything did before: for as long as it is asked to.
        try:
            from energy import Battery
            self.battery = Battery.of(pathlib.Path(brief.get("vehiclePath", "/dive/vehicle")))
            # What it carries draws whether or not it has been given anything
            # to do. This was under `begin_task` at first, so a dive with no
            # task carried nothing and drew nothing, which is not a vehicle.
            self.add_up_what_it_carries()

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
        # No stage until somebody opens one, and a dive nobody is watching
        # never does. None rather than absent, so asking is allowed.
        self.stage = None
        # Where the water stops. Depth is measured from z = 0 everywhere, so
        # that is the waterline unless a place ships a surface of its own and
        # says otherwise. It used to be None until a place shipped one, which
        # meant that on every place that does not — Looe Key among them — the
        # surface was a picture with nothing behind it, and a vehicle could
        # rise straight out of the sea and keep going.
        self.water_level = 0.0
        self.water = None
        self.shoal = None
        self._rooted = None
        self._rooted_orientations = None
        self._life_cost = [0.0, 0.0, 0]
        self.last_wrench = None
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

        # What the water is at a depth, which is the conditions' business and
        # read by whatever needs it.
        self.ocean.water.temperature_at = self.temperature_at
        self.ocean.water.density_at = self.density_at
        # And the systems that step it. Built now, not when the place opens,
        # because opening already asks the task to plan.
        self.engine = Engine(self.ocean, the_systems(self))
        self.tasking = next(s for s in self.engine.systems if s.name == "tasking")
        self.helming = next(s for s in self.engine.systems if s.name == "helm")

    # ── setting up ───────────────────────────────────────────────────────────

    def open_dry(self) -> bool:
        """Load the place without drawing it. False if it has no description.

        A dive is renderered because somebody wants to watch it, not because the
        physics needs it: nothing a step does asks the stage a question, and both
        the multibeam and the imaging sonar march their rays against the place's
        heightfield rather than against its triangles. Measured on the box, the
        same dive steps 3,900 times a second with no renderer and 33 with one.
        That is the difference between benching a controller in an hour and
        benching it in a day, and a bench nobody runs twice is not a bench.

        What the stage was being asked for was the size of the place, and the
        place already says: its description carries how far across it is and its
        heightfield carries how deep. Those are better answers than the bounding
        box, which also enclosed the water plane and every coral.
        """
        city = pathlib.Path(self.brief.get("cityPath", "/dive/city"))
        described = self.the_place_describes_itself(city)
        if described is None:
            self.say("failed", why=f"the place at {city} does not describe itself, "
                                   "and a dive with nothing to see has nothing "
                                   "else to go on")
            return False
        corner, far, extent = described
        self.units_per_metre = 1.0
        self.up_axis = "Z"
        self.bounds = (corner, far)
        self.say("place_open", scene=str(city), prims=0,
                 metresAcross=extent, from_=corner, to=far,
                 upAxis=self.up_axis, unitsPerMetre=1.0, drawn=False)
        # How big the vehicle is, from its package, since there is no hull
        # drawn to measure. The default was 0.6 m across, which in a tank a
        # metre wide is a vehicle that cannot pass anything.
        try:
            import json
            hull = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                               / "dynamics.json").read_text()).get("hull") or {}
            size = hull.get("dimensionsM")
            if size and len(size) == 3:
                self.half_width = max(0.1, max(float(size[0]), float(size[1])) / 2.0)
                self.half_height = max(0.05, float(size[2]) / 2.0)
                self.ocean.vehicle.footprint = (float(size[0]) / 2.0, float(size[1]) / 2.0)
        except Exception:
            pass
        self.put_the_vehicle_in_the_place(corner, far, extent)
        # The fish are in the water whether or not anybody draws them.
        self.stock_the_place(city)
        # The same two things a drawn dive ends its opening with. Without the
        # first there is no task, no recorder and no score: the dive flies, the
        # vehicle holds where it was put, and the record is a vehicle doing
        # nothing — which is what the first dry dive produced.
        self.begin_task(self.brief.get("objective"))
        self.say("vehicle_placed",
                 position=[round(float(x), 3) for x in self.position])
        return True

    def the_place_describes_itself(self, city: pathlib.Path):
        """How big the place is, from the place rather than from its geometry."""
        import json

        try:
            said = json.loads((city / "site.json").read_text())
            across = float(said["from"]["acrossMetres"])
            field = said["mesh"]["heightfield"]
            heights = np.fromfile(city / field["file"], dtype="<f4")
            if heights.size == 0:
                return None
        except Exception:
            return None
        # The water column is part of the place: a vehicle at the surface is
        # inside it, so the top is the surface and not the shallowest rock.
        deep, shallow = float(heights.min()), max(0.0, float(heights.max()))
        half = across / 2.0
        corner = [-half, -half, deep]
        far = [half, half, shallow]
        return corner, far, [across, across, round(shallow - deep, 2)]

    def read_the_room(self) -> None:
        """A tank's cameras and walls, from the place.

        Asked of the place, never inferred: a reef has no walls and its views
        are sized for a reef, and a one-metre tank has glass a vehicle stops
        at and views that would all be outside it at a reef's distances.
        """
        import json

        try:
            said = json.loads((pathlib.Path(self.brief.get("cityPath", "/dive/city"))
                               / "site.json").read_text())
        except Exception:
            return
        cameras = said.get("cameras")
        self.place_cameras = dict(cameras) if isinstance(cameras, dict) else {}
        inside = said.get("interior")
        if isinstance(inside, dict) and "min" in inside and "max" in inside:
            self.interior = (np.array(inside["min"], dtype=float), np.array(inside["max"], dtype=float))
        if self.place_cameras or self.interior is not None:
            self.say("room_is", views=self.views(),
                     interior=None if self.interior is None else
                     [[round(float(v), 3) for v in self.interior[0]], [round(float(v), 3) for v in self.interior[1]]])

    def views(self) -> list:
        """The views this dive offers: the built-in ones and the place's own."""
        fixed = (self.place_cameras.get("fixed") or {}) if self.place_cameras else {}
        return list(VIEWS) + [name for name in fixed if name not in VIEWS]

    def put_the_vehicle_in_the_place(self, corner, far, extent) -> None:
        """The bottom under the vehicle and where the vehicle starts.

        Shared by a dive somebody is watching and a dive nobody is: none of
        it asks the renderer anything. The place's own heightfield says
        where the bottom is, and the brief or the place says where to begin.
        """
        # The floor.
        #
        # The site's own heightfield where it has one, so the bottom is the
        # bottom under this vehicle rather than the deepest point in the place.
        # On a reef with four metres of relief the difference is a vehicle
        # resting on the coral and a vehicle four metres inside it.
        self.seabed = Seabed.of(self.scene, pathlib.Path(
            self.brief.get("cityPath", "/dive/city")))
        self.floor = None if corner is None else float(corner[2])
        self.read_the_room()
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

        # Where the plan of work says the vehicle goes in.
        #
        # This is the first thing a real dive has and the last thing this one
        # got. Without it the *place* chose the spot, by coral cover, out of a
        # number its own survey later disproved — so a mission could not say
        # "we launch from the ship" with a ship drawn on the layout, and the
        # transit out to the work and back was neither flown nor counted.
        if asked is None:
            asked = self.launch_from((self.brief.get("initialState") or {}).get("launch"))

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
        if asked is None and not self.body.model.can_hover:
            # A vehicle that cannot hold a depth is not lowered to one. A
            # glider goes over the side of a ship and starts by falling, and
            # where it starts falling from is the surface.
            #
            # The default is the middle of the water, which is right for
            # something that can stop there and wrong for something that
            # cannot: this put a Seaglider on the seabed of a six-hundred-metre
            # site and then asked it to profile the top three hundred, so it
            # spent the whole dive climbing and never flew the task at all.
            top = 0.0 if self.water_level is None else float(self.water_level)
            self.position = np.array([float(self.position[0]), float(self.position[1]),
                                      top - self.half_height - 0.5])
            self.say("spawned", at=[round(float(v), 2) for v in self.position],
                     why="launched from the surface: this vehicle cannot hold a depth")
            asked = [float(v) for v in self.position]
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

    def open(self, drawn: bool = False) -> bool:
        """Load the place and put the vehicle in it. False if it would not open.

        Drawn only when somebody is watching. The hull and the water surface are
        tens of megabytes that no batch dive has any use for: the dynamics come
        from the vehicle's parameters and not from its triangles, so nothing
        loaded here changes the trajectory by so much as a millimetre. What it
        changes is whether there is anything to see.
        """
        import omni.usd
        from pxr import Gf, Usd, UsdGeom, UsdPhysics

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

        self.put_the_vehicle_in_the_place(corner, far, extent)

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
                       # A tank's water is its interior, not the room the
                       # scene's bounds take in: a 7.9 m caustic patch over a
                       # 2 m tank was one cell of net across the whole floor.
                       across=(float(self.interior[1][0] - self.interior[0][0]) if self.interior is not None
                               else float(extent[0]) if extent else 1000.0),
                       working_depth=abs(float(self.position[2])),
                       visibility_m=self.visibility_m,
                       water_type=self.water_type,
                       significant_height_m=self.sea_height_m,
                       wave_period_s=self.sea_period_s,
                       wave_heading_deg=self.sea_heading_deg,
                       seed=int(self.brief.get("seed", 0)),
                       # Where the dive starts, so the medium is baked
                       # measuring from there rather than from the middle of
                       # the site.
                       begins_at=tuple(float(v) for v in self.position),
                       # A tank, not an ocean. The place says so; nothing
                       # here guesses it from the size, because a small
                       # site is not a building.
                       enclosed=bool(self._site_is_enclosed()))
            self.water = water

            # And what lives in it: stocked as in every dive, then drawn.
            self.stock_the_place(city)
            if self.shoal is not None:
                import life
                try:
                    life.put_them_in(stage, self.shoal)
                except Exception as bad:
                    # Said, not swallowed: a dive that cannot draw its fish is
                    # still a dive; one that cannot say why is not worth running.
                    import traceback
                    self.say("life_failed", why=str(bad)[:200],
                             where=traceback.format_exc().strip().splitlines()[-2][:160])

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

        self.switch_on_the_lamps(stage)

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
                    self.ocean.vehicle.footprint = (float(size[0]) / 2.0, float(size[1]) / 2.0)
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

            # Its propellers, when the package says how big they are, turned
            # each frame to where they are in their turn. See draw/propellers.py.
            self._propellers = None
            thrust = self.ocean.thrust
            if thrust.diameter_m and self.up_axis == "Z":
                from draw import propellers
                self._propellers = propellers.put_in(stage, self.vehicle_path,
                                                     self.allocator.model.thrusters,
                                                     thrust.diameter_m, self.units_per_metre)
                self.say("propellers_drawn", count=len(self._propellers),
                         diameterM=thrust.diameter_m, fullRpm=float(thrust.max_rpm.max()),
                         rpmFrom=thrust.rpm_from)

            # The reef. Referenced rather than merged, so the seabed stays one
            # file and the coral stays another — a place is layers, and a
            # thousand colonies is not something to paste into a terrain.
            reef = layers_of(city).get("coral")
            if reef and (city / reef).exists() and not stage.GetPrimAtPath("/World/Coral"):
                stage.DefinePrim("/World/Coral").GetReferences() \
                    .AddReference(str(city / reef))
                self.say("coral_drawn", file=reef)
                # And find the rooted colonies, now that there are some.
                #
                # This used to run beside the water, which is before the reef
                # is referenced in: it looked for a coral instancer in an empty
                # stage, said honestly that there wasn't one, and the
                # gorgonians never moved.
                self._rooted = self._root_the_gorgonians(stage, city)
                # And put the water on the colonies, now that there are some.
                #
                # Exactly the same reason the line above it is here. The water
                # is worked out and applied before this reference exists, and
                # an MDL parameter takes the value it compiled with — so every
                # coral material compiled with the `veil = 0` sitting in its
                # USD, which means no medium at all. A colony at the horizon
                # was lit like a colony at arm's length for as long as the
                # medium has existed.
                import water as water_module
                water_module.put_the_water_in_whatever_arrived_since(
                    stage, self.say)

            # And the marine snow, which is the water's and not the reef's.
            #
            # Made after the water because how much of it there is comes off
            # the water type: the same suspended particles that shorten the
            # attenuation length are the ones a lamp finds.
            try:
                import snow as marine_snow

                # `water_module`, not `water`: fifteen lines below, `water`
                # is rebound to a file path, which makes it a local for the
                # whole function and unbound here. And `seed` is a method on
                # this class, not a number. Both would have been swallowed by
                # the catch below into "snow_not_drawn", and the dive would
                # have rendered with no snow and no reason given.
                # How deep the dive is, because marine snow is made at the
                # top of the ocean and eaten on the way down. Without it
                # Thuwal Deep rendered a snowstorm at the density of a reef
                # at fifteen metres.
                how_deep = float(-self.position[2])
                self.snow = marine_snow.Snow(
                    reaches_m=self.SNOW_REACHES_M, most=self.SNOW_MOST,
                    lengths=water_module.water_of(self.water_type),
                    seed=int(self.seed()), depth_m=how_deep)
                self.snow.follow(self.position)
                drawn = marine_snow.draw(stage, self.snow)
                self.say("snow_is", drawn=self.snow.count,
                         askedFor=self.snow.asked,
                         perCubicMetre=round(self.snow.per_cubic_metre(), 1),
                         atDepthM=round(how_deep, 1),
                         ofTheUpperOcean=round(
                             marine_snow.how_much_gets_this_deep(how_deep), 3),
                         reachesM=self.SNOW_REACHES_M, inScene=bool(drawn))
            except Exception as exc:
                # Loud, because a silent fallback here is a dive that looks
                # finished and is missing the thing that makes the footage
                # read as footage.
                self.snow = None
                self.say("snow_not_drawn", why=f"{type(exc).__name__}: {exc}"[:240])

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

    def launch_from(self, said):
        """Where a mission's launch point puts the vehicle, or nothing.

        `from` names something drawn — a ship, a dock, a marker. `at` gives
        site metres when nothing drawn is the right answer. Depth is the
        surface unless it says otherwise, because a vehicle put over the side
        starts at the surface and everything after that is the dive.
        """
        if not isinstance(said, dict) or not said:
            return None
        where = None
        named = said.get("from")
        if named:
            thing = self.world.by_id(str(named)) if self.world is not None else None
            if thing is None:
                self.say("launch_missing", wanted=str(named),
                         why="nothing drawn under that name; the place will choose")
                return None
            at = np.asarray(thing.at, dtype=float)
            where = [float(at[0]), float(at[1]), float(at[2])]
        elif said.get("at"):
            given = [float(v) for v in said["at"]]
            where = given if len(given) == 3 else [given[0], given[1], 0.0]
        if where is None:
            return None

        top = 0.0 if self.water_level is None else float(self.water_level)
        depth = said.get("depthM")
        where[2] = (top - self.half_height - 0.2) if depth is None else (top - float(depth))
        # Never through the bottom: a ship moored in four metres does not
        # launch a vehicle into the sand.
        floor = self.floor
        if self.seabed is not None:
            floor = self.seabed.under(where[0], where[1])
        if floor is not None:
            where[2] = max(where[2], float(floor) + self.half_height + 0.3)
        self.say("launched_from",
                 what=str(named) if named else "a point",
                 at=[round(v, 2) for v in where])
        return where

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

    def _site_is_enclosed(self) -> bool:
        """Whether this place is a tank rather than an ocean.

        Asked of the place and never inferred from its size. A hundred-metre
        site is not a building — Looe Key's layout plot is smaller than the
        MHL tank is long — and a medium that decided for itself would be a
        medium nobody could argue with.
        """
        import json

        try:
            city = pathlib.Path(self.brief.get("cityPath", "/dive/city"))
            return bool(json.loads((city / "site.json").read_text())
                        .get("enclosed", False))
        except Exception:
            return False

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
            self.helm = Helm(self.allocator, self.dt, bridge=self.bridge,
                             deployed=str(self.brief.get("autonomyName") or ""),
                             slug=str(self.brief.get("autonomySlug") or ""))
            # And what the dive is for, latched, so a controller that starts
            # afterwards still hears it.
            self.bridge.publish_task(self.objective)
            self.say("bridge_open", domain=self.brief.get("rosDomainId"),
                     publishes=["/depth", "/imu/data", "/dvl/twist",
                                "/dvl/range", "/sonar/scan", "/task"],
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
            # The range to the bottom goes over with the rest of it: the same
            # floor the observation is built from, so what a controller outside
            # this process is told and what one inside it sees cannot disagree.
            floor = self.floor
            if self.seabed is not None:
                floor = self.seabed.under(float(self.position[0]),
                                          float(self.position[1]))
            altitude = None if floor is None else float(self.position[2]) - floor
            self.bridge.publish(self.simulated, self.position, self.velocity,
                                self.body.model.density, self.rotation,
                                altitude=altitude,
                                dvl_range=(self.navigation.dvl_range
                                           if self.navigation is not None
                                           else (0.05, 50.0)))

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
        if isinstance(view, str) and view in self.views():
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
        # Where each of these numbers came from, kept before anything is
        # defaulted. The control plane has always known that conditions are
        # either observed at an instant or constructed by somebody, and it
        # refuses the ones that claim the wrong thing — but the runtime read
        # only `parameters` and threw the claim away, so a dive record showed
        # 1025 kg/m3 whether a CTD measured it or the runtime made it up.
        # Those are not the same dive and the record should not say they are.
        said = conditions if isinstance(conditions, dict) else {}
        self.conditions_kind = str(said.get("kind") or "constructed")
        self.observed_at = said.get("observedAt") or None
        self.condition_sources = [one for one in (said.get("sources") or [])
                                  if isinstance(one, dict)]
        # Stated means somebody put a number there. An empty string is the
        # form a blank field arrives in and is not a statement.
        self.stated = {key for key, value in parameters.items()
                       if value not in (None, "")}
        # Nothing measures a current: not a satellite, not a wave buoy. When
        # the conditions say so out loud, an observed set still does not get
        # to call its current measured.
        self.current_measured = bool(parameters.get("currentMetresPerSecond")) and \
            not parameters.get("currentNotMeasured")
        speed = float(parameters.get("currentMetresPerSecond", 0.0) or 0.0)
        # The heading a current is named by is where it flows towards, from
        # north, clockwise — the way a current is written on a chart.
        heading = float(parameters.get("currentHeadingDeg", 0.0) or 0.0)
        angle = np.radians(90.0 - heading)
        self.current = np.array([speed * np.cos(angle), speed * np.sin(angle), 0.0])
        # Wind, named like the current by where it blows towards.
        blows = float(parameters.get("windMetresPerSecond", 0.0) or 0.0)
        towards = np.radians(90.0 - float(parameters.get("windHeadingDeg", 0.0) or 0.0))
        self.wind = np.array([blows * np.cos(towards), blows * np.sin(towards), 0.0])
        visibility = parameters.get("visibilityM")
        self.visibility_m = None if visibility in (None, "", 0) else float(visibility)
        named = parameters.get("waterType") or parameters.get("jerlov")
        self.water_type = None if named in (None, "") else str(named)

        def number(key):
            got = parameters.get(key)
            return None if got in (None, "") else float(got)

        self.sea_height_m = number("significantWaveHeightM")
        self.sea_period_s = number("waveMeanPeriodS") or number("wavePeakPeriodS")
        self.sea_heading_deg = number("waveHeadingDeg")
        # A fan over a tank makes ripples, not a sea: centimetres high and a
        # third of a second apart, running the way it blows. Used only where
        # the conditions did not state a wave of their own.
        if blows > 0 and self.sea_height_m is None and self._site_is_enclosed():
            self.sea_height_m = round(min(0.02, 0.0016 * blows ** 2), 4)
            self.sea_period_s = round(0.25 + 0.04 * blows, 3)
            self.sea_heading_deg = float(parameters.get("windHeadingDeg", 0.0) or 0.0)
        self.read_the_water(parameters)
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
        # Said once, at the top of the log, because a reader who scrolls past
        # `water_is` should not have to guess whether anybody measured it.
        # Both halves in one event: the numbers the dive was flown in, and
        # where each of them came from. Apart, a reader has to join them by
        # hand, and the second half is the half that gets dropped.
        were = self.conditions_said()
        self.say("conditions_from", were=were, cameFrom=were.pop("cameFrom"))


    @property
    def sensors_are_out(self) -> bool:
        return self.simulated < self.sensors_out_until

    def read_the_water(self, parameters: dict) -> None:
        """How dense this water is, and what the depth gauge was set for.

        Density belonged to the vehicle: it was an argument to the model's
        constructor with a constant behind it, so a dive could not ask for
        different water and Florida and the Red Sea were the same sea. It is
        the water's property and it belongs here, beside the current.

        Stated either way round. `salinityPsu` and `temperatureC` are what an
        oceanographer has and what a CTD reads, and the equation of state turns
        them into a density; `densityKgM3` is for when somebody has measured
        the answer directly and would rather not be second-guessed. Water that
        says nothing keeps the constant, so every dive already in the record
        still means what it meant.
        """
        from hydrodynamics import DENSITY_SEAWATER, density_of

        self.salinity_psu = parameters.get("salinityPsu")
        self.temperature_c = parameters.get("temperatureC")
        stated = parameters.get("densityKgM3")
        self.stated_density = None if stated in (None, "") else float(stated)
        if self.stated_density is not None:
            self.density = self.stated_density
        elif self.salinity_psu not in (None, "") and self.temperature_c not in (None, ""):
            self.salinity_psu = float(self.salinity_psu)
            self.temperature_c = float(self.temperature_c)
            self.density = density_of(self.salinity_psu, self.temperature_c)
        else:
            self.density = DENSITY_SEAWATER
        # The water the vehicle is actually floating in. Buoyancy, the pressure
        # the depth gauge feels, and everything downstream of both follow this
        # rather than a constant compiled into the runtime.
        if self.body is not None and getattr(self.body, "model", None) is not None:
            self.body.model.density = self.density
        # What the depth gauge was calibrated against. A pressure gauge is a
        # density and a multiplication, so one set for ordinary seawater and
        # flown in the Red Sea reads deep — by four tenths of a metre at a
        # hundred, which is a navigation error and not a rounding one. Unstated
        # means a gauge that happens to be right for the water it is in, which
        # is the assumption every dive so far has quietly made.
        calibrated = parameters.get("depthGaugeDensityKgM3")
        self.depth_gauge_density = (self.density if calibrated in (None, "")
                                    else float(calibrated))
        # How the temperature goes down the water column, as depth-temperature
        # pairs. A single number is a column all one temperature, which is what
        # a reef in ten metres of water effectively is and what every dive so
        # far has assumed. It stops being true for anything that profiles: the
        # Red Sea is famously warm at depth, holding around 21.5 °C below the
        # surface layer, and a hull that shrinks when it is cold notices.
        profile = parameters.get("temperatureProfile")
        self.temperature_profile = None
        if isinstance(profile, (list, tuple)) and len(profile) >= 2:
            pairs = sorted((float(d), float(c)) for d, c in profile)
            self.temperature_profile = pairs
            if self.temperature_c is None:
                self.temperature_c = pairs[0][1]

    def ballasted_for_this_water(self) -> dict | None:
        """Whether this hull can be trimmed neutral in the water it is in.

        Only a question for a vehicle whose propulsion *is* its buoyancy. An
        ROV that is a newton or two out flies through it on the thrusters and
        never notices; a glider that is a newton out has spent its engine
        before it starts, because displacing a little more or less water than
        it weighs is the only thing it can do.

        And the Red Sea is where it bites. A hull ballasted in ordinary
        seawater is buoyant here — forty and a half parts per thousand against
        thirty-five — and cancelling that comes out of the same few hundred
        cubic centimetres that were supposed to fly the mission. It is a known
        way to lose a deployment, it is arithmetic, and it should be arithmetic
        somebody does on shore rather than a discovery made at sea.
        """
        model = self.body.model
        actuators = model.actuators or {}
        if model.can_hover or "vbdCcRange" not in actuators:
            return None
        low, high = actuators["vbdCcRange"]
        here = self.density_at(0.0)
        # What the hull would have to displace, or stop displacing, to hang
        # still in this water.
        surplus_kg = model.displaced_volume_m3 * here - model.mass_kg
        needed_cc = -surplus_kg / here * 1e6
        working = max(abs(float(low)), abs(float(high)))
        return {"waterDensityKgM3": round(here, 2),
                "outOfTrimKg": round(surplus_kg, 3),
                "toCancelCc": round(needed_cc, 1),
                "engineRangeCc": round(working, 1),
                "shareOfEngine": round(abs(needed_cc) / max(1e-9, working), 3),
                "enough": abs(needed_cc) < working}

    def temperature_at(self, depth_m: float) -> float | None:
        """How warm the water is at that depth, straight-line between the
        stated points and flat above the first and below the last."""
        if self.temperature_profile is None:
            return None if self.temperature_c is None else float(self.temperature_c)
        pairs = self.temperature_profile
        depth = max(0.0, float(depth_m))
        if depth <= pairs[0][0]:
            return pairs[0][1]
        for (shallow, warm), (deep, cold) in zip(pairs, pairs[1:]):
            if depth <= deep:
                share = (depth - shallow) / max(1e-9, deep - shallow)
                return warm + share * (cold - warm)
        return pairs[-1][1]

    def density_at(self, depth_m: float) -> float:
        """The water's density where the vehicle is.

        Salinity and temperature give it at the surface; the weight of the
        water above does the rest. It is not a small correction — a thousand
        metres down, water is 0.4% denser than the same water at the top, which
        is four kilos a cubic metre, as much as the whole difference between a
        Florida reef and the Red Sea.

        Water that was handed a density outright is taken at its word at every
        depth: somebody who measured it did not ask to be extrapolated.
        """
        from hydrodynamics import density_of

        if self.salinity_psu is None or self.stated_density is not None:
            return self.density
        warm = self.temperature_at(depth_m)
        if warm is None:
            return self.density
        return density_of(float(self.salinity_psu), float(warm), max(0.0, float(depth_m)))

    # What each field of the conditions would have been if nobody had said.
    # Named, because "assumed" on its own tells you a number is not yours
    # without telling you what stood in for it.
    INSTEAD = {"currentMetresPerSecond": "still water",
               "currentHeadingDeg": "still water",
               "visibilityM": "whatever the water type gives",
               "waterType": "the place's own water",
               "significantWaveHeightM": "a quiet day, 0.4 m",
               # Not "flat": a dive that states a height and no period still
               # gets a sea, built on the runtime's own quiet-day period.
               "waveMeanPeriodS": "the quiet-day period, 6 s",
               "temperatureC": "unstated, so the density constant stands",
               "salinityPsu": "unstated, so the density constant stands",
               "densityKgM3": "ordinary seawater",
               "depthGaugeDensityKgM3": "a gauge right for the water it is in"}

    def where_conditions_came_from(self) -> dict:
        """Which of this dive's conditions were measured, and which were chosen.

        The same discipline the place pages apply to a reef, applied to a run.
        Four words, and the fourth is the one that matters: *measured* is an
        instrument reading with an instant on it, *derived* is computed from
        measured things, *chosen* is a person putting a number in a field, and
        *assumed* is nobody saying anything and the runtime's default standing
        in unannounced. A dive that reads as still water because the sea was
        calm and one that reads as still water because the current box was
        empty are different claims, and only this tells them apart.
        """
        observed = self.conditions_kind == "observed"
        # An instrument per field, where the conditions named one. Sources
        # written before this existed name a field in prose rather than by
        # key; those still count as measured, they just cannot say by what.
        instrument = {}
        for one in self.condition_sources:
            key = one.get("parameter")
            if isinstance(key, str) and key:
                instrument[key] = {k: one[k] for k in ("at", "from", "through")
                                   if one.get(k)}

        def how(key: str) -> dict:
            if key not in self.stated:
                return {"how": "assumed", "instead": self.INSTEAD.get(key, "the runtime's default")}
            if not observed:
                return {"how": "chosen"}
            told = {"how": "measured"}
            if self.observed_at:
                told["at"] = self.observed_at
            told.update(instrument.get(key, {}))
            return told

        fields = {key: how(key) for key in
                  ("currentMetresPerSecond", "currentHeadingDeg", "visibilityM",
                   "waterType", "significantWaveHeightM", "waveMeanPeriodS",
                   "temperatureC", "salinityPsu")}
        # A current is the one thing nothing in the water measures. An
        # observed set that says so is still telling the truth about the rest.
        for key in ("currentMetresPerSecond", "currentHeadingDeg"):
            if fields[key]["how"] == "measured" and not self.current_measured:
                fields[key] = {"how": "chosen"}
        # Density is the whole argument in one field: stated outright, worked
        # out of a CTD's two numbers, or the constant nobody asked for.
        if "densityKgM3" in self.stated:
            fields["densityKgM3"] = how("densityKgM3")
        elif self.salinity_psu is not None and self.temperature_c is not None:
            fields["densityKgM3"] = {"how": "derived", "fromFields": ["salinityPsu", "temperatureC"],
                                     "by": "the equation of state"}
        else:
            fields["densityKgM3"] = how("densityKgM3")
        fields["depthGaugeDensityKgM3"] = (how("depthGaugeDensityKgM3")
                                           if "depthGaugeDensityKgM3" in self.stated
                                           else {"how": "assumed",
                                                 "instead": self.INSTEAD["depthGaugeDensityKgM3"]})
        counted = {"measured": 0, "derived": 0, "chosen": 0, "assumed": 0}
        for told in fields.values():
            counted[told["how"]] = counted[told["how"]] + 1
        return {"kind": self.conditions_kind,
                **({} if self.observed_at is None else {"observedAt": self.observed_at}),
                "fields": fields, "counted": counted}

    def conditions_said(self) -> dict:
        speed = float(np.hypot(self.current[0], self.current[1]))
        heading = (90.0 - np.degrees(np.arctan2(self.current[1], self.current[0]))) % 360.0 if speed > 1e-9 else 0.0
        said = {"currentMetresPerSecond": round(speed, 3), "currentHeadingDeg": round(float(heading), 1),
                "current": [round(float(v), 4) for v in self.current[:2]],
                "visibilityM": self.visibility_m,
                **({} if self.water_type is None else {"waterType": self.water_type}),
                **({} if self.sea_height_m is None
                   else {"significantWaveHeightM": self.sea_height_m,
                         "waveMeanPeriodS": self.sea_period_s}),
                "densityKgM3": round(float(self.density), 3)}
        if self.salinity_psu is not None:
            said["salinityPsu"] = round(float(self.salinity_psu), 2)
        if self.temperature_c is not None:
            said["temperatureC"] = round(float(self.temperature_c), 2)
        if abs(self.depth_gauge_density - self.density) > 1e-9:
            said["depthGaugeDensityKgM3"] = round(float(self.depth_gauge_density), 3)
        said["cameFrom"] = self.where_conditions_came_from()
        return said

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
        # And said again across the boundary, because a mission's stages change
        # what the dive is for while it is flying. A controller told the first
        # stage and nothing after would fly the whole mission as its opening leg.
        if self.bridge is not None:
            self.bridge.publish_task(objective)
        if not again:
            self.began_at = self.position.copy()
            self.began_rotation = self.rotation.copy()
            self.begin_navigating()
            self.switch_on_the_ctd()
            self.switch_on_the_modem()
            self.switch_on_the_sonar()
            self.switch_on_the_sidescan()
            self.switch_on_the_sonde()
            self.switch_on_the_multibeam()
            self.run_out_the_tether()
            self.began_with_wh = (0.0 if self.battery is None else self.battery.remaining_wh)
        # Every task that is about the coral rather than about the ground.
        wants_coral = any(_mentions(objective, kind) for kind in ("treat", "monitor"))
        self.task = task_for(objective, self.began_at,
                             float(np.arctan2(self.rotation[1, 0], self.rotation[0, 0])),
                             camera=self.camera(),
                             colonies=self.colonies_here() if wants_coral else None,
                             world=self.world)
        # Pointed at something that is not in the water. Refused rather than
        # flown: a survey over "cell-b7" in a place where nobody drew cell-b7
        # would otherwise fall back to a box ahead of the vehicle and come back
        # as a mediocre score, which reads as a controller that flew badly.
        if self.task is not None and getattr(self.task, "missing", ""):
            self.say("task_refused", task=self.task.kind,
                     why=(f"this dive is pointed at {self.task.missing}, which is not "
                          "in the layout it was flown in"),
                     instead=sorted({one.id for one in self.world.things}))
            self.task = None
            return
        # A task this vehicle has no way of doing is refused here rather than
        # flown badly. A glider asked to hold station does not hold it poorly;
        # it falls out of the water column while the clock runs, and the result
        # is a score nobody can read and a day nobody gets back.
        if self.task is not None and getattr(self.task, "needs_hover", False) \
                and not self.body.model.can_hover:
            self.say("task_refused", task=self.task.kind,
                     why=("this vehicle has no thrusters and cannot hold a position "
                          "or a depth; it is flown by buoyancy and wings"),
                     instead=["profile", "section"])
            self.task = None
            return
        # Before anything else: can this hull even be made neutral here?
        trim = self.ballasted_for_this_water()
        if trim is not None and trim["shareOfEngine"] > 0.05:
            self.say("ballast", **trim,
                     why=("this hull was not ballasted for this water; cancelling "
                          "the difference costs part of the only propulsion it has"))
            if not trim["enough"]:
                self.say("task_refused", task=getattr(self.task, "kind", "?"),
                         why=("this vehicle cannot be trimmed neutral in this water: "
                              f"{abs(trim['toCancelCc']):.0f} cc against an engine "
                              f"of {trim['engineRangeCc']:.0f} cc"),
                         instead=["ballast it for this sea before the dive"])
                self.task = None
                return
        if self.task is not None:
            self.task_over = False
            self.say("task_set", task=self.task.describe(), attempt=self.attempts)
            # Who flies it, when the dive asked for somebody in particular.
            # Carried on the objective because the objective is the one part of
            # a dive definition that travels to the simulator untouched — and
            # because which controller flew it is part of what a dive *was*,
            # the same way the vehicle and the water are.
            named = str((objective or {}).get("flyWith") or "")
            if named and self.helm.engage(named, self.observation()):
                self.say("flying_with", controller=named)
            elif named:
                self.say("cannot_fly_with", controller=named,
                         have=sorted(self.helm.controllers))
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
                                         frames_hz=float(self.film().get("fps") or 0) or Recorder.rate_for(expected))
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

            # Pressure is the water's; what the gauge makes of it is the
            # vehicle's. The ratio of the two is the error, and it is one the
            # water can cause on its own.
            gauge = {"depthGaugeScale": float(self.density) / float(self.depth_gauge_density)}
            self.navigation = Navigation(suite={**self.navigation_suite(), **gauge, **self.fitted},
                                         aiding=self.aiding,
                                         began_at=self.position,
                                         seed=int(self.seed()))
            # An array somebody laid out is the array. A layout that put
            # transponders in the water replaces "a circle around roughly
            # here" with the things themselves, and where a fix can be had
            # follows from how many of them are in range.
            # Where the lines actually are, in this water. A line drawn on a
            # chart is where somebody put its two ends; a current moves it by
            # metres, and a vehicle flying under the chart's line meets
            # something else entirely.
            self.world.in_this_water(self.current)
            for one in self.world.of_kind("mooring-line"):
                if getattr(one, "leaned_by", 0.0) > 0.5:
                    self.say("a_line_leaned", which=one.id,
                             byM=round(one.leaned_by, 1),
                             lowestM=round(-min(float(p[2]) for p in one.curve), 1))
            laid = [one.at for one in self.world.of_kind("transponder")]
            if laid and self.navigation.kind == "lbl":
                self.navigation.transponders = laid
                self.say("array_laid", transponders=len(laid),
                         from_="the layout this dive was flown in")
            # And the surface asset a USBL fix comes from. The default is a
            # transceiver straight overhead, which is the best case and never
            # quite true: a ship holds station where the weather lets it, and a
            # fix whose error is a share of slant range is worse the further
            # off to one side that is. When somebody drew the ship, the ship is
            # where it is.
            ships = self.world.of_kind("ship") + self.world.of_kind("buoy")
            if ships and self.navigation.kind == "usbl":
                self.navigation.at = ships[0].at
                self.say("surface_asset",
                         at=[round(float(v), 1) for v in ships[0].at],
                         is_=ships[0].spec.what,
                         from_="the layout this dive was flown in")
            self.say("navigating", **self.navigation.said(self.position, self.simulated))
        except Exception as exc:
            self.navigation = None
            self.say("navigation_unavailable", why=str(exc)[:160])

    def switch_on_the_lamps(self, stage) -> None:
        """Hang the vehicle's own lights on it, as its package describes them.

        Nothing on this platform has ever carried a light. Every dive has been
        lit by the sun, which is true down to about thirty metres and is a lie
        everywhere else: at six hundred there is no sun at all, and the deep
        site rendered black in every frame because that is what it is.

        The lamps hang under the vehicle's transform, so they go where it goes
        and point where it points without anybody moving them. They also cost
        what they cost — a Lumen is fifteen watts, two of them is thirty, and
        on a vehicle whose whole hotel load is twenty-five that is a number a
        dive plan has to know.
        """
        import json

        from pxr import Gf, Usd, UsdGeom, UsdLux

        self.lamps = []
        self.lamp_watts = 0.0
        self.lamp_places = {}
        self.lamp_rig = {}
        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
            fitted = ((described.get("lights") or {}).get("fitted")) or []
        except Exception:
            fitted = []
        if not fitted:
            return
        # A dive may unship them, the same way it can unship a Doppler log.
        # Lights off is a real choice: it is half an hour of battery.
        if getattr(self, "fitted", {}).get("lights") is False:
            self.say("lamps_off", why="this dive is not carrying them")
            return

        for one in fitted:
            name = str(one.get("name", "lamp"))
            at = [float(v) for v in (one.get("position") or [0.0, 0.0, 0.0])]
            aim = [float(v) for v in (one.get("aim") or [1.0, 0.0, 0.0])]
            watts = float(one.get("watts", 0.0))
            # A rectangle rather than a sphere, and not for looks.
            #
            # A sphere light here renders nothing at all: created, placed
            # correctly, switched on at sixty times a sensible brightness, and
            # not one pixel changes. A rectangle at the same place lights the
            # scene, which is how the caustics have always worked. Whatever the
            # reason, this is the light this renderer has.
            #
            # Small, because a subsea lamp is a bright source behind a dome and
            # the shadow it throws has a soft edge, which is most of what makes
            # a lit frame look lit rather than traced.
            # A direct child of /World, with no scope between.
            #
            # Under /World/Lamps/<name> the light renders nothing at all, at
            # any size or brightness, while the caustics — a rect light at
            # /World/Caustics — light the scene from 71 to 207. The only thing
            # left between them was the implicitly created scope in the middle,
            # which is a typeless prim this renderer's traversal apparently
            # does not go through.
            light = UsdLux.RectLight.Define(stage, f"/World/Lamp_{name}")
            across = asked_for("CORAL_CITY_LAMP_SIZE", 0.08)
            light.CreateWidthAttr(across)
            light.CreateHeightAttr(across)
            lumens = float(one.get("lumens", 1500.0))
            nits = asked_for("CORAL_CITY_LAMP_INTENSITY",
                             lamp_nits(lumens, across))
            light.CreateIntensityAttr(nits)
            self.lamp_intensity, self.lamp_lumens = float(nits), lumens
            light.CreateColorAttr(Gf.Vec3f(1.0, 0.98, 0.95))
            light.CreateNormalizeAttr(False)
            # No shaping cone.
            #
            # This is what stopped the lamps working, and it cost most of a
            # day. A rect light emits from one face already, so the cone was
            # belt and braces on top of a direction the light had anyway — and
            # with it applied the lamps emitted nothing at all, at any size and
            # any brightness, while an identical light beside them lit the
            # scene. Off, the deep site goes from a mean of 26 to 40 and from a
            # peak of 44 to 137.
            #
            # The declared beam angle is still in the vehicle's package and is
            # still the truth about the lamp. When there is a way to apply it
            # that this renderer honours, it goes back — behind this switch, so
            # that the next person can tell in one run whether it is the cone
            # again.
            if os.environ.get("CORAL_CITY_LAMP_CONE", "0") == "1":
                shaping = UsdLux.ShapingAPI.Apply(light.GetPrim())
                shaping.CreateShapingConeAngleAttr(float(one.get("coneDeg", 120.0)) / 2.0)
                shaping.CreateShapingConeSoftnessAttr(0.45)

            # At world level, and moved every step, which is how the caustics
            # have always worked and is the only way a light works here.
            #
            # Hung under the vehicle's own transform — which is the obvious
            # place for a thing bolted to a vehicle — the light is created,
            # sits at exactly the right world position, and emits nothing at
            # any brightness between a hundred thousand and ten billion. The
            # caustics, a rect light of the same kind at world level, change
            # the frame from 71 to 207 across the same test. So: world level,
            # and the pose is applied here rather than inherited.
            moving = UsdGeom.Xformable(light.GetPrim())
            moving.ClearXformOpOrder()
            # One matrix, not a translate and two rotations.
            #
            # The three-op version was wrong twice and the two faults hid each
            # other. A rect light faces its own -Z; the tip was `90 + asin(z)`,
            # which for a lamp aimed level swings -Z round to *-X* — the lamps
            # pointed behind the vehicle. And the ops were ordered swing-then-
            # tip, so the swing acted on a vector still pointing straight down
            # and did nothing at all, which meant every lamp came out aimed the
            # same way whatever bearing it was given.
            #
            # For a lamp aimed straight down both faults cancel and the answer
            # is right, which is why the caustics — a rect light pointed at the
            # seabed — have worked all along while the lamps never have.
            #
            # A rotation that takes -Z to the aim has no order and no sign to
            # get wrong, and `aiming` below is checked against the four
            # directions that matter.
            self.lamp_places[name] = moving.AddTransformOp()
            self.lamp_rig[name] = (at, [float(v) for v in aim])
            self.aim_the_lamps()
            self.lamps.append(name)
            self.lamp_watts += watts

        # And they are part of the hotel load while they are on. Two Lumens is
        # thirty watts against a hotel load of twenty-five, so a vehicle with
        # its lights on draws more than twice what one with them off draws
        # before it has moved at all. A dive that did not count them would
        # promise an endurance nobody gets.
        if self.battery is not None and self.lamp_watts:
            self.battery.hotel_w += float(self.lamp_watts)

        # Where they actually ended up, not where they were asked to go. A
        # light hung under a transform that is not what you think it is lights
        # somewhere nobody is looking, and the way that presents is a scene
        # that is simply dark.
        where = []
        for name in self.lamps:
            prim = stage.GetPrimAtPath(f"/World/Lamp_{name}")
            if prim:
                box = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                    Usd.TimeCode.Default())
                at = box.ExtractTranslation()
                where.append([round(float(at[i]) / self.units_per_metre, 2)
                              for i in range(3)])
            else:
                where.append(None)
        # What was set, not what a second copy of the formula says.
        #
        # This line worked the intensity out again from `1500 * LAMP_SCALE`
        # while the light itself had been given something else, so after the
        # lamps became a real photometric conversion the log went on
        # reporting a hundred and five million — four orders of magnitude
        # above the value in the scene. A readback that recomputes is not a
        # readback.
        self.say("lamps_made",
                 acrossM=asked_for("CORAL_CITY_LAMP_SIZE", 0.08),
                 intensity=round(float(self.lamp_intensity), 1),
                 lumensEach=round(float(self.lamp_lumens), 1))
        self.say("lamps_at", where=where,
                 vehicleAt=[round(float(v), 2) for v in self.position])

        # The same light again, at the same place, hung at world level instead
        # of on the vehicle. The vehicle's lamps are created, positioned and
        # switched on and no frame gets brighter; either the renderer does not
        # light from a local source here, or something about hanging one under
        # the vehicle stops it. One of those is a five-minute fix and this says
        # which.
        if asked_for("CORAL_CITY_TEST_LAMP") is not None:
            probe = UsdLux.RectLight.Define(stage, "/World/TestLamp")
            probe.CreateWidthAttr(0.3)
            probe.CreateHeightAttr(0.3)
            probe.CreateIntensityAttr(asked_for("CORAL_CITY_TEST_LAMP", 0.0))
            probe.CreateColorAttr(Gf.Vec3f(1.0, 0.35, 0.35))
            probe.CreateNormalizeAttr(False)
            UsdGeom.Xformable(probe.GetPrim()).AddTranslateOp().Set(
                self.drawn_at([float(self.position[0]) + 0.4,
                               float(self.position[1]),
                               float(self.position[2]) + 0.3]))
            self.say("test_lamp",
                     at=[round(float(self.position[0]) + 0.4, 2),
                         round(float(self.position[1]), 2),
                         round(float(self.position[2]) + 0.3, 2)],
                     intensity=asked_for("CORAL_CITY_TEST_LAMP", 0.0))

        self.say("lamps_on", lamps=self.lamps,
                 watts=round(self.lamp_watts, 1),
                 lumens=sum(float(one.get("lumens", 0.0)) for one in fitted),
                 hotelNowW=None if self.battery is None
                 else round(self.battery.hotel_w, 1))

    def aim_the_lamps(self) -> None:
        """Put each lamp where the vehicle carries it, pointing where it points.

        Called every step, because the lights are at world level and nothing
        else moves them.
        """
        if not self.lamp_places:
            return
        from pxr import Gf

        R = np.asarray(self.rotation, dtype=float)
        for name, place in self.lamp_places.items():
            at, aim = self.lamp_rig[name]
            world = np.asarray(self.position, dtype=float) + R @ np.asarray(at, dtype=float)
            towards = R @ np.asarray(aim, dtype=float)
            if np.linalg.norm(towards) < 1e-9:
                continue
            spun = aiming(towards / np.linalg.norm(towards))
            matrix = Gf.Matrix4d(
                float(spun[0][0]), float(spun[0][1]), float(spun[0][2]), 0.0,
                float(spun[1][0]), float(spun[1][1]), float(spun[1][2]), 0.0,
                float(spun[2][0]), float(spun[2][1]), float(spun[2][2]), 0.0,
                0.0, 0.0, 0.0, 1.0)
            drawn = self.drawn_at(world)
            matrix.SetTranslateOnly(Gf.Vec3d(float(drawn[0]), float(drawn[1]),
                                             float(drawn[2])))
            place.Set(matrix)

    def add_up_what_it_carries(self) -> None:
        """Every fitted instrument draws, and the sum is what the battery pays.

        The hotel load used to be one number standing for the electronics, the
        sensors and the lights together — so a dive that unshipped a Doppler
        log or flew with the lamps off lasted exactly as long as one that did
        not. That made `fitted` a label rather than a choice, and made the
        endurance in every cost estimate the endurance of a fully laden
        vehicle whatever anybody chose.

        Each instrument states its own draw now. So does the computer, which
        until today was not modelled at all: a controller needing a hundred
        watts of GPU to think ran here for free and could not run at sea.
        """
        import json

        if self.battery is None:
            return
        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
        except Exception:
            return

        carried, watts = [], 0.0
        for one in described.get("sensors", []):
            kind = str(one.get("kind", ""))
            # A dive may unship what the vehicle has. The same hull without its
            # Doppler log is a different problem and should not need a second
            # vehicle in the catalogue.
            if self.fitted.get(kind) is False or self.fitted.get(one.get("name")) is False:
                continue
            draw = float(one.get("watts", 0.0))
            if draw <= 0.0:
                continue
            carried.append({"what": one.get("name") or kind, "watts": draw})
            watts += draw

        # And the computer it thinks with.
        machine = described.get("computer")
        if isinstance(machine, dict) and self.fitted.get("computer") is not False:
            draw = float(machine.get("watts", 0.0))
            if draw > 0.0:
                carried.append({"what": machine.get("kind", "computer"), "watts": draw})
                watts += draw

        # And whether the thing flying it could actually run on this hull.
        #
        # A stack declares what it needs of a machine, and until now that was
        # checked against the *simulation host* — a datacentre box with an
        # A100 in it. Nothing checked it against the computer the vehicle
        # carries. So a controller that wants a hundred tera-operations to
        # think ran here at full speed and was physically impossible at sea,
        # and the dive that proved it worked proved nothing.
        needs = (self.brief.get("autonomyNeeds") or {})
        if isinstance(machine, dict) and needs:
            wanted = float(needs.get("tops", 0.0) or 0.0)
            has = float(machine.get("tops", 0.0) or 0.0)
            if wanted > has:
                self.say("beyond_the_hull",
                         wanted=wanted, carries=has,
                         computer=machine.get("kind"),
                         why=("this controller needs more of a machine than "
                              "this vehicle carries; it would not run at sea"))
            wantedRam = float(needs.get("ramGb", 0.0) or 0.0)
            if wantedRam > float(machine.get("ramGb", 0.0) or 0.0):
                self.say("beyond_the_hull", wantedRamGb=wantedRam,
                         carriesRamGb=machine.get("ramGb"),
                         computer=machine.get("kind"))

        if not carried:
            return
        self.battery.hotel_w += watts
        self.say("carrying", draws=carried,
                 instrumentsW=round(watts, 2),
                 hotelNowW=round(self.battery.hotel_w, 2))

    def switch_on_the_ctd(self) -> None:
        """Give the vehicle a CTD, if its package says it carries one.

        Conductivity, temperature and depth: the instrument every oceanographic
        vehicle in the world carries, and the reason a glider section is worth
        flying at all. The platform has modelled the water properly since the
        beginning — EOS-80 density from salinity and temperature, a profile
        with depth, compression under pressure — and every bit of it was
        visible only to the physics. A controller could not read the water it
        was flying in, and a mission could not bring a profile home.

        It needs nothing that is not already here, which is why it has been
        waiting so long: the numbers exist, and this hands them to whoever is
        flying and to whoever reads the record afterwards.
        """
        import json

        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
            said = next((one for one in described.get("sensors", [])
                         if one.get("kind") == "ctd"), None)
        except Exception:
            said = None
        if said is None or self.fitted.get("ctd") is False:
            return
        self.ctd = {"everyS": float(said.get("everyS", 1.0)),
                    "name": str(said.get("name", "ctd"))}
        self.profile: list[dict] = []
        self.ctd_last_t = None
        self.say("ctd_on", **self.ctd)


    def switch_on_the_modem(self) -> None:
        """Give the vehicle its acoustic link, as its package describes it.

        A vehicle with no modem declared gets none, and a glider declares a
        link of zero range on purpose: it talks by satellite when it surfaces
        and not at all when it is down, which is the whole reason its decisions
        are made in hours.
        """
        import json

        from modem import Modem

        self.modem = None
        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
            said = described.get("modem")
        except Exception:
            said = None
        if not said or float(said.get("rangeM", 0.0)) <= 0.0:
            return
        if self.fitted.get("modem") is False:
            self.say("modem_off", why="this dive is not carrying one")
            return
        self.modem = Modem(said, seed=int(self.brief.get("seed", 0)))
        self.say("modem_on", **self.modem.said())

    def fits(self, kind: str) -> bool:
        """Whether this dive fits that instrument.

        Everything the package declares, unless the brief names a shorter list.

        The distinction the list is for, because it is easy to get backwards: an
        instrument that **changes what the vehicle does** — the tether, which drags
        — must always be fitted, or the dive is easier than the thing it stands in
        for. An instrument that only **reports** changes nothing at all unless
        something reads it, and a forward-looking sonar costs about four times the
        rest of a step to ray-march: measured, a 30-second tank rollout goes from
        1.16 s to 5.01 s for a fan nobody looks at, and a trainer flies three
        thousand of them.

        So this is opt-in and never inferred: the platform names no list and fits
        everything. The SDK's tank names what the controller declares it needs.
        """
        named = self.brief.get("fitSensors")
        if named is None:
            return True
        return kind in set(named)

    def keep_the_waterfall(self, into: pathlib.Path) -> None:
        """Write the side-scan waterfall beside the recording, amber as survey
        software draws it."""
        image = self.ocean.sidescan.image()
        coloured = np.stack([image, (image * 0.75).astype(np.uint8), (image * 0.25).astype(np.uint8)], axis=2)
        where = pathlib.Path(into) / "sidescan.png"
        try:
            import cv2
            cv2.imwrite(str(where), coloured[:, :, ::-1])
        except Exception:
            try:
                from PIL import Image
                Image.fromarray(coloured).save(where)
            except Exception:
                np.save(pathlib.Path(into) / "sidescan.npy", image)
                where = pathlib.Path(into) / "sidescan.npy"
        self.say("sidescan_kept", file=where.name, pings=len(self.ocean.sidescan.rows))
        if self.ocean.subbottom.traces:
            section = self.ocean.subbottom.image()
            try:
                import cv2
                cv2.imwrite(str(pathlib.Path(into) / "subbottom.png"), 255 - section)
            except Exception:
                try:
                    from PIL import Image
                    Image.fromarray(255 - section).save(pathlib.Path(into) / "subbottom.png")
                except Exception:
                    np.save(pathlib.Path(into) / "subbottom.npy", section)

    def switch_on_the_sonde(self) -> None:
        """Fit the water-quality sonde, if the vehicle carries one."""
        import json

        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
        except Exception:
            return
        said = next((one for one in described.get("sensors") or [] if one.get("kind") == "water_quality"), None)
        if said is not None:
            self.ocean.quality.config = dict(said)
            self.say("sonde_on", measures=said.get("measures"), everyS=said.get("everyS", 1.0))

    def switch_on_the_sidescan(self) -> None:
        """Fit the side-scan, if the vehicle carries one (systems/sidescan.py).
        The dive's tow may say which frequency."""
        import json

        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
        except Exception:
            return
        said = next((one for one in described.get("sensors") or [] if one.get("kind") == "side_scan"), None)
        if said is None:
            return
        tow = (self.objective or {}).get("tow") if isinstance(self.objective, dict) else None
        self.ocean.sidescan.set_for(said, (tow or {}).get("frequencykHz"))
        self.say("sidescan_on", **{k: v for k, v in self.ocean.sidescan.said().items() if k != "pings"})
        # And the sub-bottom profiler beside it, against what the place says
        # lies under it.
        under = next((one for one in described.get("sensors") or [] if one.get("kind") == "sub_bottom"), None)
        if under is not None:
            try:
                site = json.loads((pathlib.Path(self.brief.get("cityPath", "/dive/city")) / "site.json").read_text())
            except Exception:
                site = {}
            self.ocean.subbottom.set_for(under, site.get("subsurface"))
            self.say("subbottom_on", **{k: v for k, v in self.ocean.subbottom.said().items() if k != "traces"})

    def switch_on_the_sonar(self) -> None:
        """Give the vehicle its sonar, if its package says it has one.

        Declared in the BlueROV2's package since the beginning and returning
        nothing this whole time, because there was nothing in the world to
        return off. There is now — and what it is *for* is the one thing a
        controller learns that nobody told it.
        """
        import json

        from sonar import Sonar

        if not self.fits("imaging_sonar"):
            return

        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
            said = next((one for one in described.get("sensors", [])
                         if one.get("kind") == "imaging_sonar"), None)
        except Exception:
            said = None
        if said is None:
            return
        self.sonar = Sonar(said, seed=int(self.brief.get("seed", 0)))
        self.say("sonar_on", **self.sonar.said())

    def switch_on_the_multibeam(self) -> None:
        """And the downward-looking swath, if the package says it has one.

        A separate instrument and a separate question. The forward sonar is
        so a controller can avoid what nobody told it about; this is what a
        survey is actually bought for, and what it leaves behind is a chart.
        """
        import json

        from multibeam import Multibeam

        if not self.fits("multibeam"):
            return

        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
            said = next((one for one in described.get("sensors", [])
                         if one.get("kind") == "multibeam"), None)
        except Exception:
            said = None
        if said is None:
            return
        self.multibeam = Multibeam(said, seed=int(self.brief.get("seed", 0)))
        self.say("multibeam_on", **self.multibeam.said())

    def run_out_the_tether(self) -> None:
        """Put the cable in the water, if this vehicle is on one.

        Three things have to agree for there to be a tether: the vehicle says
        it is tethered, the dive says how much is out, and something is at the
        surface for the dry end to be tied to. The last is the reason this
        waited for a layout — a cable with no surface end is a cable running to
        nowhere, and the force it puts on the vehicle depends entirely on where
        that nowhere is.

        A dive with no ship and no buoy drawn gets one directly overhead, which
        is the best case and is said plainly rather than assumed quietly.
        """
        import json

        from systems.tether import Umbilical

        said = {}
        try:
            described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                    / "dynamics.json").read_text())
            said = dict(described.get("tether") or {})
        except Exception:
            said = {}
        # What the dive asked for, over what the vehicle ships with: how much
        # cable is out is a decision somebody makes on the day.
        asked = (self.brief.get("initialState") or {}).get("tetherOutM")
        if asked is None:
            asked = (self.objective or {}).get("tetherOutM") if isinstance(self.objective, dict) else None
        # A place that is a room says where its cable comes over the rim and
        # how much of it is paid out: a tank does not have a ship.
        rim = None
        try:
            rig = json.loads((pathlib.Path(self.brief.get("cityPath", "/dive/city"))
                              / "site.json").read_text()).get("rig") or {}
            rim = rig.get("tether") if isinstance(rig.get("tether"), dict) else None
        except Exception:
            rim = None
        if asked is None and rim is not None and rim.get("outM") is not None:
            asked = float(rim["outM"])
        if asked is not None:
            said["lengthM"] = float(asked)
        # A tow: the cable is the tow cable, as much as the dive pays out, and
        # its dry end is the ship's stern (systems/tow.py).
        tow = (self.objective or {}).get("tow") if isinstance(self.objective, dict) else None
        if isinstance(tow, dict):
            said = {**said, **(said.get("tow") or {})}
            said["lengthM"] = float(tow.get("cableOutM", 50.0))
        if not said or float(said.get("lengthM", 0.0)) <= 0.0:
            return
        # Where the cable is tied to the vehicle, in its own frame. The middle
        # of the vehicle when the package does not say.
        self.tether_attach = np.array(said.get("attachM", [0.0, 0.0, 0.0]), dtype=float)
        self.tether_lead_out = float(said.get("leadOutM", 0.0))

        floating = self.world.of_kind("ship") + self.world.of_kind("buoy")
        if isinstance(tow, dict):
            # She starts ahead of the fish by most of the cable, steaming
            # away from it, so the dive opens with the tow already streaming.
            a = math.radians(float(tow.get("headingDeg", 0.0)))
            ahead = np.array([math.cos(a), math.sin(a), 0.0]) * 0.8 * said["lengthM"]
            self.ocean.ship.set_for(tow, self.position + ahead)
            rim = None
            floating = []
            surface = self.ocean.ship.at.copy()
            where = f"the ship's stern, towing at {self.ocean.ship.speed_kn:g} kn"
            self.say("towing", **self.ocean.ship.said())
        elif rim is not None and rim.get("at") is not None:
            surface = np.array(rim["at"], dtype=float)
            where = rim.get("what", "where the place says the cable comes over the rim")
        elif floating:
            surface = np.array(floating[0].at, dtype=float)
            where = f"the {floating[0].kind} this dive was laid out with"
        else:
            top = 0.0 if self.water_level is None else float(self.water_level)
            surface = np.array([self.position[0], self.position[1], top])
            where = ("nothing was drawn at the surface, so the cable runs "
                     "straight up — which is the best case and rarely the day")

        cable = Umbilical(said)
        tied = self.position + self.rotation @ self.tether_attach
        cable.start(surface, tied)
        # Let it fall where the still water leaves it before the dive starts:
        # two seconds of the cable's own physics, nothing else moving.
        still = self.ocean.water

        def calm(points):
            return still.flow_at(points, 0.0)

        for _ in range(int(2.0 / self.dt)):
            cable.step(self.dt, tied, calm, self.ocean.place, self.water_level)
        self.tether = cable
        self.say("tether_out", lengthM=round(self.tether.length_m, 1),
                 diameterM=self.tether.diameter_m,
                 from_=[round(float(v), 1) for v in surface], where=where)

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
        """Plan a way of doing what the task asks, and have the helm carry it
        out now. See systems/tasking.py.

        Called from outside the tick — a dive opening, a console carrying the
        vehicle, a task started again — where nothing will step the helm
        before somebody looks at it. Inside the tick the orders wait for the
        helm's own step instead."""
        self.tasking.plan(self.ocean)
        self.helming.carry_out(self.helm, self.ocean.orders)

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

    def envelope(self) -> dict:
        """What this vehicle can be asked to do, as its package states it.

        Read here as well as in the control plane, because a plan handed
        straight to a dive never goes near the control plane, and a limit that
        only one door enforces is a limit with a way round it.
        """
        if not hasattr(self, "_envelope"):
            self._envelope = {}
            try:
                import json
                described = json.loads((pathlib.Path(self.brief.get("vehiclePath", "/dive/vehicle"))
                                        / "dynamics.json").read_text())
                stated = described.get("envelope")
                if isinstance(stated, dict):
                    self._envelope = stated
            except Exception:
                pass
        return self._envelope

    def camera_half_angle(self) -> float | None:
        """Half the camera's horizontal field of view, radians, if it has one.

        A fact about the vehicle, which is why a planner is told it and a task
        is not: how far apart to fly the lanes of a survey depends on what the
        thing can see.
        """
        described = self.camera()
        if described is None:
            return None
        # The task's own function, rather than half of it written again. These
        # were two functions computing one number and only one of them knew
        # that a focal length is a field of view: the BlueROV2 states 21 mm and
        # no angle, so the planner was told the vehicle had no camera and
        # spaced a survey's lanes by the objective's nominal swath — four
        # metres, against the eight and a half the camera actually sees. Every
        # strip was covered twice, the far edge was never reached, and a survey
        # in still water with a perfect fix could not score above 77%.
        from tasks import footprint_half_angle

        return footprint_half_angle(described)

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
        # And what it can say, and how slowly. A controller that phones home
        # has to be judged on the channel it would actually have.
        if self.modem is not None:
            self.helm.carries_a_link(self.modem)

    def where_this_place_is(self) -> dict | None:
        """The place's name and its georeference, off its own record.

        A recording carried the seabed as a grid of heights and nothing that
        said which reef it was or where on the Earth it sat, so everything a
        mission produced — the track, where each coral actually went — was in
        metres from a centre nobody had written down. Deliverables have to be
        in WGS84 or they are not deliverables, and the arithmetic that puts
        them there is the same one `make-site` sampled the bathymetry with,
        run backwards. This is the half of it the runtime knows.
        """
        city = pathlib.Path(self.brief.get("cityPath", "/dive/city"))
        try:
            described = json.loads((city / "site.json").read_text())
        except Exception:
            return None
        came = described.get("from") or {}
        centre = came.get("centre") or {}
        if centre.get("latitude") is None or centre.get("longitude") is None:
            return None
        return {"name": described.get("name") or city.name,
                "centre": {"latitude": float(centre["latitude"]),
                           "longitude": float(centre["longitude"])},
                "acrossMetres": came.get("acrossMetres"),
                "sampleMetres": came.get("sampleMetres"),
                "surveyed": bool(came.get("surveyed")),
                "layoutVersionId": self.world.version or None}

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
            "views": self.views(),
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
        See systems/helm.py."""
        return observe(self.ocean)

    def step(self) -> None:
        """One tick of the dive: every system, in the order their declarations
        give (print `self.engine.order()` to see it). See engine/."""
        self.engine.tick()

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
        """Stop the vehicle where the ground, the glass, the things in the
        water and the cable say it must stop. See systems/contact.py."""
        contact.land(self.ocean.vehicle, self.ocean.place, self.ocean.contacts,
                     self.ocean.cable, self.dt, self.say)

    def film(self) -> dict:
        """What a dive filmed for people rather than for its record asks of
        the picture: {"fps", "width", "height", "spp", "bitrate"}. Empty for an
        ordinary dive. It changes nothing that is computed, only how the
        frames it was going to take anyway are rendered and kept."""
        asked = (self.brief.get("objective") or {}).get("film")
        return dict(asked) if isinstance(asked, dict) else {}







    def what_it_hit(self) -> dict:
        """What this dive struck, for whoever is judging it: things in the
        water, ground it could not ride over, and a tank's glass, each counted
        once per contact. `tools/bench` asks for it, because "things struck"
        is how a controller that arrives short and hits nothing is told apart
        from one that arrives exactly and ploughs through a nursery frame."""
        return self.ocean.contacts.said()

    def strike(self) -> None:
        """Stop the vehicle against ground it cannot ride over. See
        systems/contact.py."""
        contact.strike(self.ocean.vehicle, self.ocean.place, self.ocean.contacts)


    def consider_the_end(self) -> None:
        """Every way a dive can be over other than its clock running out.
        See systems/tasking.py."""
        self.tasking.consider_the_end(self.ocean)

    def submerged(self) -> float:
        """The share of the hull under the surface. See systems/vehicle.py."""
        return self.ocean.vehicle.submerged(self.water_level)

    def across_metres(self) -> float:
        """How wide this place is, in metres."""
        corner, far = self.bounds
        if corner is None:
            return 1000.0
        return max(float(far[0] - corner[0]), float(far[1] - corner[1]))



    def orbital(self):
        """The water's own motion under the waves, where the vehicle is.
        See systems/water.py."""
        return self.ocean.water.orbital(self.position, self.half_height, self.simulated)

    def stock_the_place(self, city: pathlib.Path) -> None:
        """Set the day, and put in the fish the place says live in it.
        See systems/light.py and systems/fish.py."""
        import json

        from systems import fish

        parameters = dict((self.brief.get("conditions") or {}).get("parameters") or {})
        # Or the objective says when the dive is, which is how a dive asked
        # for through the MCP, whose water is a named preset, says it.
        day = (self.brief.get("objective") or {}).get("day") if isinstance(self.brief.get("objective"), dict) else None
        if isinstance(day, dict):
            parameters.update({k: day[k] for k in ("localTimeH", "dayLengthS") if k in day})
        indoors = bool(self.interior is not None or self._site_is_enclosed())
        self.ocean.light.set_for(parameters, indoors)
        self.say("day_is", **self.ocean.light.said())
        self.shoal = None
        try:
            described = json.loads((city / "site.json").read_text())
        except Exception:
            self.say("no_life", why="this place has no record of what lives in it")
            return
        seabed, floor = self.seabed, self.floor

        def bottom_under(x, y):
            return seabed.under(float(x), float(y)) if seabed is not None else floor

        # A tank's water on a grid, so the vehicle's wash lingers after it
        # (systems/flow.py). Open water keeps the analytic jet alone.
        if self.interior is not None and asked_for("CORAL_CITY_FLOW", 1.0) != 0.0:
            low, high = self.interior
            top = 0.0 if self.water_level is None else float(self.water_level)
            self.ocean.flow.set_for([low[0], low[1], low[2]], [high[0], high[1], top], self.ocean.place.bottoms)
            self.say("flow_grid", cells=list(self.ocean.flow.shape), cellM=self.ocean.flow.cell,
                     from_=self.ocean.flow.from_)
        # The coral, solid where it is stony (systems/coral.py).
        from systems.coral import colonies_of
        self.ocean.replace("coral", colonies_of(described, bottom_under))
        if len(self.ocean.coral):
            self.say("coral_is", colonies=len(self.ocean.coral),
                     solid=int(self.ocean.coral.solid().sum()), from_=self.ocean.coral.from_)
        if asked_for("CORAL_CITY_LIFE", 1.0) == 0.0:
            self.say("no_life", why="asked for a reef with nothing living in it")
            return
        self.shoal = fish.stock(described, bottom_under, self.interior, self.position,
                                int(self.brief.get("seed", 0)), self.say,
                                light=(self.ocean.light.hour, self.ocean.light.level))

    # How far the marine snow reaches from the camera, in metres, and how many
    # aggregates will be drawn at most.
    #
    # Three, not four. Backscatter is a near-field thing — it is the lamp
    # lighting the water between itself and the lens — and a particle at four
    # metres is both under a pixel and past most of what the lamp has to
    # give. A four-metre box spent more than half its budget out there and
    # then hit the ceiling, so the density actually drawn came out at 11.7 a
    # cubic metre against the 25.7 the water asked for. Pulling the box in
    # and lifting the ceiling puts the full density where it can be seen.
    SNOW_REACHES_M = 3.0
    SNOW_MOST = 20000

    def stir(self) -> None:
        """Move the water. Still caustics are a painted floor."""
        if self.water is not None:
            self.water.drift(self.stage, self.simulated, follow=self.position)
            self.water.light_for(self.stage, float(-self.position[2]))
        # The snow sinks and goes where the water goes, and the box it lives
        # in keeps up with the camera. The particles themselves do not follow
        # the camera — that is the difference between backscatter and a decal
        # stuck to the lens.
        if getattr(self, "snow", None) is not None:
            import snow as marine_snow

            self.snow.drift(1.0 / 20.0, current=self.current)
            self.snow.follow(self.position)
            marine_snow.move(self.stage, self.snow)
        # What each half of the living reef costs, said once.
        #
        # A reef that hangs the renderer is worse than a reef with nothing in
        # it, and "the frames stopped coming" is not a measurement. These are
        # two numbers and they cost two clock reads a frame.
        import time as _time
        began = _time.perf_counter()
        self.swim(1.0 / 20.0)
        swam = _time.perf_counter()
        self.sway()
        ended = _time.perf_counter()
        self._life_cost[0] += swam - began
        self._life_cost[1] += ended - swam
        self._life_cost[2] += 1
        if self._life_cost[2] == 20:
            self.say("life_costs",
                     swimMs=round(1000 * self._life_cost[0] / 20, 1),
                     swayMs=round(1000 * self._life_cost[1] / 20, 1),
                     fish=0 if self.shoal is None else self.shoal.of_them,
                     rooted=0 if self._rooted is None else int(len(self._rooted[1])))

    def the_snow_is_seen_from(self, eye) -> None:
        """Put the box of aggregates on the camera, when it is not the vehicle.

        `stir` puts it on the vehicle, which is where the camera is on a dive.
        On a tour the camera stands somewhere else, and the box's whole job is
        near-field: it is drawn dense out to three metres and it holds nothing
        closer than `NEAREST_M`, so that no particle ever sits nearer than a
        lens can make sense of.

        Measured from the wrong point, that guard protects nothing. Thuwal
        Deep's lamp view had an eight-millimetre aggregate nineteen centimetres
        off the glass, rendered sixty-one pixels across — a floating boulder in
        the top of the frame — because it was a clear half-metre away from the
        *vehicle*, and the still camera stood a metre and a half below it.

        The water is already moved to the camera this way, in the same place
        in the frame loop. The snow was not.
        """
        if getattr(self, "snow", None) is None or eye is None:
            return
        import snow as marine_snow

        self.snow.follow(eye)
        marine_snow.move(self.stage, self.snow)

    def sway(self) -> None:
        """Bend the rooted things in the water that is actually moving.

        The mean current pushes them over and the surge is what makes them
        move: the orbital motion of the waves overhead reverses every few
        seconds, and it is already computed here because it acts on the hull
        as well. A reef whose gorgonians are still is a reef nobody believes.
        """
        if self._rooted is None or asked_for("CORAL_CITY_LIFE", 1.0) == 0.0:
            return
        import life
        from pxr import Gf, Vt

        under = self.water.orbital_here(
            float(self.position[0]), float(self.position[1]),
            float(-self.position[2]), self.simulated) if self.water else (0.0, 0.0, 0.0)
        flow = (float(self.current[0]) + float(under[0]),
                float(self.current[1]) + float(under[1]))

        instancer, held, turn, phase, stiff = self._rooted
        # The vehicle's wash, where each colony stands (systems/wash.py).
        where = getattr(self, "_rooted_at", None)
        stirred = self.ocean.wash.efflux.any() or self.ocean.flow.on
        if where is not None and stirred:
            flow = np.asarray(flow)[None, :] + self.ocean.wash.at(where)[:, :2]
        lean, towards = life.bending(flow, phase + self.simulated * 1.6, stiff)
        w, x, y, z = life.leaning(lean, towards, turn)
        # The array is kept and written into, not rebuilt. There are 83,000
        # colonies on this reef and 7,300 of them bend; constructing eighty
        # thousand quaternions every frame to change seven thousand of them is
        # most of a frame's budget spent on the ones that did not move.
        was = self._rooted_orientations
        for slot, i in enumerate(held):
            was[i] = Gf.Quath(float(w[slot]), float(x[slot]),
                              float(y[slot]), float(z[slot]))
        instancer.GetOrientationsAttr().Set(Vt.QuathArray(was))

    def _root_the_gorgonians(self, stage, city):
        """Find the rooted colonies once, so the sway is arithmetic after that."""
        import json

        from pxr import UsdGeom

        described = json.loads((city / "site.json").read_text())
        sways = described.get("reef", {}).get("swaysWith") or {}
        if not sways:
            self.say("no_sway", why="this place records nothing that bends")
            return None
        named = described.get("layers", {}).get("coral", "coral.usda")
        instancer = None
        for prim in stage.Traverse():
            if prim.GetTypeName() == "PointInstancer" and "Coral" in str(prim.GetPath()):
                instancer = UsdGeom.PointInstancer(prim)
                break
        if instancer is None:
            self.say("no_sway", why=f"no coral instancer in {named}")
            return None

        which = np.array(instancer.GetProtoIndicesAttr().Get() or [])
        # Copied out of the USD array once, into a plain list.
        #
        # Indexing a Vt array from Python is not the cheap thing it looks like,
        # and the loop below touches seven thousand of eighty-three thousand
        # elements. Left as a Vt array it did not finish: the dive built its
        # reef, drew its fish, and then sat in this one list comprehension
        # until the tour timed out with no frames at all.
        #
        # This is the same line that was a `list(...)` an hour ago, changed to
        # a Vt array to avoid rebuilding eighty thousand quaternions a frame.
        # Both problems are real; the answer is to copy once here and rebuild
        # from the copy, rather than to index the array that USD holds.
        orientations = instancer.GetOrientationsAttr().Get()
        orientations = list(orientations) if orientations is not None else None
        if not len(which) or orientations is None or not len(orientations):
            self.say("no_sway", why="the coral instancer has nothing in it")
            return None

        held, stiff = [], []
        for kind, prototypes in sways.items():
            for i in np.flatnonzero(np.isin(which, list(prototypes))):
                held.append(int(i))
                stiff.append(life_stiffness(kind))
        if not held:
            self.say("no_sway", why="none of the colonies are rooted kinds")
            return None

        held = np.array(held)
        # Their own turn about the vertical, read back off what is there, so a
        # colony that stops bending goes back to where the reef put it.
        # Its own turn about the vertical, read back off what is there, so a
        # colony that stops bending goes back to where the reef put it.
        #
        # No clamp on the real part. Clamping it positive looks like it guards
        # a division and is instead a bug: past half a turn the cosine is
        # negative, atan2 is the function that already knows that, and every
        # gorgonian facing the back half of the compass would have been spun
        # to face the front.
        turn = np.array([2.0 * np.arctan2(float(orientations[i].imaginary[2]),
                                          float(orientations[i].real))
                         for i in held])
        phase = np.linspace(0, 2 * np.pi, len(held), endpoint=False)
        self._rooted_orientations = orientations
        # And where each stands, in metres, so each can be asked about the
        # water where it is rather than where the vehicle is.
        placed = instancer.GetPositionsAttr().Get()
        self._rooted_at = (np.array([[float(placed[i][0]), float(placed[i][1]), float(placed[i][2])]
                                     for i in held]) / self.units_per_metre
                           if placed is not None and len(placed) and self.up_axis == "Z" else None)
        self.say("sway_is", colonies=int(len(held)),
                 kinds=sorted(k for k, v in sways.items() if v))
        return (instancer, held, turn, phase, np.array(stiff))

    def swim(self, dt: float = 0.0) -> None:
        """Draw the fish where they are. They swim in the dive itself, on its
        own clock (systems/fish.py); this only puts the picture where they
        went."""
        if getattr(self, "shoal", None) is None:
            return
        import life

        life.move_them(self.stage, self.shoal)

    def show(self) -> None:
        """Move what is drawn to where the vehicle is.

        Separate from step() because it is not part of the dive: a headless run
        computes the same trajectory without ever doing this, and it must.
        """
        self.placement.Set(self.pose())
        # The lamps are bolted to the vehicle but live at world level, so this
        # is what carries them along.
        self.aim_the_lamps()
        self.draw_the_tether()
        if getattr(self, "_propellers", None):
            from draw import propellers
            propellers.turn(self._propellers, self.ocean.thrust)
        # The place's lamps, by the dive's day (draw/light.py). Only in a
        # room: a reef's light is the water's business (water.py).
        if self.ocean.light.indoors:
            from draw import light as drawn_light
            if getattr(self, "_lamps", None) is None:
                self._lamps = drawn_light.Lights()
            self._lamps.set(self.stage, self.ocean.light, self.say)
        if len(self.ocean.sediment.kg) or getattr(self, "_sediment_drawn", None) is not None:
            from draw import sediment as drawn_sediment
            self._sediment_drawn = drawn_sediment.draw(self.stage, self.ocean.sediment,
                                                       getattr(self, "_sediment_drawn", None),
                                                       self.units_per_metre)
        coral = self.ocean.coral
        if len(coral) and (coral.broken.any() or coral.torn_off.any()):
            from draw import coral as drawn_coral
            if not hasattr(self, "_drawn_broken"):
                self._drawn_broken = set()
            drawn_coral.break_them(self.stage, coral, self._drawn_broken, self.units_per_metre)

    def draw_the_tether(self) -> None:
        """The cable, where its own solve says it is. See draw/tether.py."""
        if self.tether is None or not self.tether.out or self.tether.shape is None:
            return
        if getattr(self, "_tether_drawing", None) is None:
            from draw.tether import TetherDrawing
            self._tether_drawing = TetherDrawing(getattr(self, "tether_attach", np.zeros(3)),
                                                 float(getattr(self, "tether_lead_out", 0.0)),
                                                 self.units_per_metre, self.say)
        self._tether_drawing.draw(self.stage, self.tether, self.ocean.vehicle, self.ocean.place, self.drawn_at)

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
            # And which controller that actually was, when the slot is
            # somebody else's stack.
            "flyingAs": self.helm.flying_as(),
            "onTheBottom": self.on_the_bottom,
            "thrust": [round(float(c), 3) for c in self.commands],
            # How fast each propeller turns, from the command it got: what the
            # drawing spins them at. The full speed's source is in the hello.
            "rpm": [int(round(float(r))) for r in self.ocean.thrust.rpm],
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
        # The plan being flown, so a console can show what the vehicle is
        # trying to do rather than only what it is doing. It is in the slow
        # half of the reading because it changes when a mission changes stage
        # and not otherwise.
        if isinstance(self.document, dict):
            reading["plan"] = {"plan": self.document.get("plan"),
                               "by": self.planned_by or None,
                               "manoeuvres": self.document.get("manoeuvres", [])}
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
                # The side-scan's record goes with the rest of it, as the
                # image a surveyor would look at (systems/sidescan.py).
                if self.ocean.sidescan.fitted and self.ocean.sidescan.rows:
                    self.keep_the_waterfall(self.recorder.into)
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
            # Who actually worked out the route. A controller that plans for
            # itself says so, and is believed over what was recorded when the
            # task was set — otherwise a dive flown on a model's plan is
            # credited to the platform's own planner, which is the record
            # being wrong about the only interesting thing in it.
            planner = getattr(self.helm.flying, "planned_by", None)
            result["plannedBy"] = planner or self.planned_by or None
            # What the slow loops did, when anything used one: how many
            # thoughts, how long they took, and how many failed. A controller
            # that scores well by thinking for four seconds a step is not
            # obviously the better controller, and this is where that shows.
            thought = self.helm.thought()
            if thought:
                result["thought"] = thought
            # What the vehicle was not allowed to do. A score is a judgement on
            # the controller, and it is the wrong judgement when the thrusters
            # were being held down the whole dive by the hull's own limits.
            held = self.helm.held_back()
            if held is not None:
                result["heldBack"] = held
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
                 # And the one number a dive is judged on, said on its own line
                 # rather than left among a dozen others: how far out the
                 # vehicle was when it came up.
                 **({} if self.navigation is None
                    else {"closingFix": self.navigation.closing_fix(
                        self.position, self.submerged() < 1.0)}),
                 **({} if self.battery is None else {"battery": self.battery.said()}),
                 # What the dive was flown through. A run that names a layout
                 # and then says nothing about what was in it leaves whoever
                 # reads it to go and fetch the document — and a run whose
                 # vehicle struck something ought to say so where the result is.
                 **({} if not len(self.world) else {"world": self.world.described()}),
                 # And what it hit, always, including when the answer is
                 # nothing. The benchmark judges a controller on "energy,
                 # time, closing navigation error, things struck", and the
                 # last of those was the one a run never reported: `struck`
                 # events went into the log and nothing gathered them. A
                 # column that is absent when a controller hit nothing and
                 # present when it did cannot be compared down its length.
                 hit=self.what_it_hit(),
                 **({} if self.sonar is None else {"sonar": self.sonar.said()}),
                 # What the vehicle managed to say, and what went missing. A
                 # controller that phones home is judged on a channel that
                 # drops things, or it is not being judged.
                 **({} if self.modem is None else {"modem": self.modem.said()}),
                 # The column, which is what a section is for. Kept whole
                 # rather than summarised: a profile somebody reduced to a mean
                 # is a profile nobody can plot.
                 **({} if not self.profile else {
                     "profile": {"casts": len(self.profile),
                                 "deepestM": round(max(one["depthM"] for one in self.profile), 2),
                                 "readings": self.profile}}),
                 # What the cable did, on a dive that had one. A hundred metres
                 # of it is usually the largest force on the vehicle, and a
                 # record that did not say so would be a record of a different
                 # dive.
                 **({} if self.tether is None or not self.tether.out
                    else {"tether": self.tether.said()}),
                 # What lived in the water and what it did about the vehicle:
                 # how each species spent the dive, how many fish it ran into,
                 # and the day it was flown in.
                 **({} if self.shoal is None else {"life": self.shoal.said()}),
                 # A tow: the ship, and the side-scan's record, whose image
                 # goes with the recording.
                 **({} if not self.ocean.ship.towing else {"tow": self.ocean.ship.said()}),
                 **({} if not self.ocean.sidescan.fitted else {"sidescan": self.ocean.sidescan.said()}),
                 **({} if not self.ocean.subbottom.fitted else {"subbottom": self.ocean.subbottom.said()}),
                 **({} if not self.ocean.quality.readings else {"waterQuality": {
                     "readings": len(self.ocean.quality.readings),
                     "worstTurbidityNtu": max(r["turbidityNtu"] for r in self.ocean.quality.readings),
                     "readingsEvery": self.ocean.quality.config.get("everyS", 1.0)}}),
                 # The coral it touched and what that did, and its hardest
                 # strike of anything: where, how fast, what impulse.
                 **({} if not len(self.ocean.coral) else {"coral": self.ocean.coral.said()}),
                 # The sand it lifted, where it went, and what it cost the
                 # camera and the coral.
                 **({} if not self.ocean.sediment.lifted_kg else {"sediment": self.ocean.sediment.said()}),
                 **({} if self.ocean.contacts.hardest() is None
                    else {"hardestStrike": self.ocean.contacts.hardest()}),
                 day=self.ocean.light.said(),
                 # And what each part of the engine cost a tick, which is how a
                 # coupled ocean is held to running.
                 engine={"msPerTick": self.engine.costs(), "ticks": self.engine.ticks},
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


def life_stiffness(kind: str) -> float:
    """How stiff a rooted colony is. A sea rod is a stick, a sea fan is a net."""
    import life

    return life.STIFFNESS.get(kind, 1.0)
