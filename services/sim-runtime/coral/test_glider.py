"""The Seaglider: a vehicle with no propeller anywhere on it.

It moves by displacing a few hundred cubic centimetres more or less than its
own mass of seawater and letting a pair of wings turn falling into going
somewhere, and it steers by rolling a battery. A quarter of a metre a second,
a thousand metres, ten months.

What it cannot do is as much of the point as what it can: it cannot hover, it
cannot hold a station, and it cannot make headway against much more than
0.4 m/s. Three of the five waters in the matrix simply carry it away, and that
is the envelope rather than a defect to tune out.
"""

import math
import pathlib
import sys
import warnings

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
warnings.filterwarnings("ignore", category=RuntimeWarning)

from hydrodynamics import Allocator, Body, Hydrodynamics, density_of  # noqa: E402

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/seaglider/dynamics.json"


def a_glider(temperature=12.0, salinity=35.0):
    model = Hydrodynamics.from_package(PACKAGE)
    model.density = density_of(salinity, temperature)
    return model


def free_flight(model, vbd_cc, nose_down_deg, seconds=900.0, dt=0.005):
    """Let it settle into a glide at a held attitude, and say how fast it goes."""
    body = Body(model)
    model.vbd_m3 = vbd_cc * 1e-6
    angle = math.radians(nose_down_deg)
    rotation = np.array([[math.cos(angle), 0, math.sin(angle)],
                         [0, 1, 0],
                         [-math.sin(angle), 0, math.cos(angle)]])
    velocity = np.zeros(6)
    mass = body.effective_mass()
    for _ in range(int(seconds / dt)):
        wrench = body.step(rotation, velocity, np.zeros(0), dt, 1.0,
                           depth_m=200.0, temperature_c=12.0, density=model.density)
        acceleration = wrench / mass
        acceleration[3:] = 0.0                 # attitude held: the question is speed
        velocity += acceleration * dt
        velocity[1] = velocity[4] = velocity[5] = 0.0
    world = rotation @ velocity[:3]
    return float(world[0]), float(world[2])


def test_the_package_says_it_has_no_thrusters():
    model = a_glider()
    assert model.thrusters == []
    assert model.commanded_in == "buoyancy"
    assert model.wings, "and that it has wings instead"
    assert model.attitude_guard == 0.0, "a guard that holds lean down would stop it flying"


def test_heavy_and_nose_down_is_forward_and_down():
    """The whole mechanism. A vehicle that is merely heavy sinks; one that is
    heavy and pointing slightly down turns the sinking into going somewhere."""
    forward, vertical = free_flight(a_glider(), vbd_cc=-250.0, nose_down_deg=25.0)
    assert forward > 0.0, "it goes forward"
    assert vertical < 0.0, "and down"
    assert 0.15 < math.hypot(forward, vertical) < 0.45, "at a glider's quarter of a metre a second"


def test_light_and_nose_up_climbs_and_still_goes_forward():
    forward, vertical = free_flight(a_glider(), vbd_cc=250.0, nose_down_deg=-25.0)
    assert forward > 0.0, "a glider makes ground on the way up too"
    assert vertical > 0.0


def test_it_glides_rather_than_sinking():
    """Glide slope: how far forward for each metre down. A Seaglider's pitch
    range gives slopes from a fifth to three; a vehicle with no wings would
    give nothing."""
    for vbd, nose in ((-150.0, 20.0), (-250.0, 25.0), (-350.0, 30.0)):
        forward, vertical = free_flight(a_glider(), vbd, nose)
        slope = abs(forward / vertical)
        assert 0.2 <= slope <= 3.0, f"{vbd} cc at {nose}° gave a slope of {slope:.2f}"


def test_the_wings_buy_the_glide_rather_than_the_motion():
    """What a wing is actually for, which is not what I first assumed.

    Take the wings off and the hull still goes forward, because a slender body
    has fifteen times less drag along its axis than across it and a pitched one
    slides like a sled on a slope. What the wings change is the exchange rate:
    the same buoyancy at the same attitude buys more distance for each metre of
    depth, and buys it at a lower speed. That is lift over drag, and it is the
    whole of why a glider crosses an ocean on a battery.
    """
    winged = a_glider()
    bare = a_glider()
    bare.wings = {}
    with_wings = free_flight(winged, vbd_cc=-250.0, nose_down_deg=25.0)
    without = free_flight(bare, vbd_cc=-250.0, nose_down_deg=25.0)

    slope_with = abs(with_wings[0] / with_wings[1])
    slope_without = abs(without[0] / without[1])
    assert slope_with > slope_without, (
        f"wings should flatten the glide: {slope_with:.2f} against {slope_without:.2f}")
    assert math.hypot(*with_wings) < math.hypot(*without), "and slow it down doing it"


def test_a_hull_going_backwards_is_not_flying():
    """A wing only works from in front. Computing an angle of attack anyway
    gives a number that grows without limit and takes the integrator with it —
    which is exactly what it did."""
    model = a_glider()
    body = Body(model)
    backwards = np.array([-0.3, 0.0, -0.1, 0.0, 0.0, 0.0])
    wrench = body.lift_and_drag(backwards, model.density)
    assert np.isfinite(wrench).all()
    # Drag only, opposing the motion, and no lift holding it up.
    assert wrench[0] > 0.0, "drag pushes back against going backwards"


def test_the_red_sea_costs_it_a_third_of_its_engine():
    """A hull ballasted for ordinary seawater is buoyant in the Red Sea, and
    cancelling that comes out of the only propulsion it has."""
    model = a_glider()
    ballasted_for = density_of(35.0, 20.0)
    model.displaced_volume_m3 = model.mass_kg / ballasted_for
    red_sea = density_of(40.6, 26.0)
    surplus_kg = model.displaced_volume_m3 * red_sea - model.mass_kg
    cc = surplus_kg / red_sea * 1e6
    assert surplus_kg > 0.0, "it floats where it was meant to be neutral"
    assert 100.0 < cc < 160.0, f"{cc:.0f} cc of an engine whose working range is 350"


# ── missions a glider can be given, and the ones it cannot ───────────────────

def a_dive_of(objective, package=PACKAGE, seconds=4000.0):
    from runner import Dive
    said = []
    model = Hydrodynamics.from_package(package)
    model.density = density_of(35.0, 15.0)
    brief = {"durationSeconds": seconds,
             "initialState": {"positionM": [0, 0, -10]},
             "conditions": {"kind": "constructed", "parameters": {"salinityPsu": 35.0,
                                                                  "temperatureC": 15.0}},
             "objective": objective}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **detail: said.append((kind, detail)))
    return dive, said


def test_a_glider_asked_to_hold_station_says_it_cannot():
    """Not badly. At all. It has no way to hold a position or a depth, and a
    dive that lets it try wastes a day proving something arithmetic."""
    dive, said = a_dive_of({"kind": "hold-station", "seconds": 300})
    dive.begin_task(dive.brief["objective"])
    refusals = [d for k, d in said if k == "task_refused"]
    assert refusals, "it should have refused"
    assert refusals[0]["task"] == "hold-station"
    assert "profile" in refusals[0]["instead"]
    assert dive.task is None


def test_the_same_task_is_fine_on_a_vehicle_with_thrusters():
    rov = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"
    dive, said = a_dive_of({"kind": "hold-station", "seconds": 300}, package=rov)
    dive.begin_task(dive.brief["objective"])
    assert not [d for k, d in said if k == "task_refused"]
    assert dive.task is not None


def test_a_glider_is_given_the_controller_that_can_fly_it():
    dive, _ = a_dive_of({"kind": "profile", "toM": 100.0, "fromM": 10.0})
    assert "glide" in dive.helm.controllers
    assert "hold" not in dive.helm.controllers, "a hold on a hull with no thrusters does nothing"
    assert dive.helm.flying.name == "glide"


def test_a_glider_flies_a_profile_down_and_back():
    """The unit a glider mission is built from, flown for real: buoyancy,
    wings, a sliding battery, and no thrust anywhere."""
    dive, _ = a_dive_of({"kind": "profile", "toM": 60.0, "fromM": 12.0, "cycles": 1,
                         "timeLimitS": 4000.0}, seconds=4000.0)
    dive.begin_task(dive.brief["objective"])
    assert dive.task is not None
    for _ in range(int(3000.0 / dive.dt)):
        dive.step()
        if dive.done:
            break
    detail = dive.task.detail()
    assert detail["deepestM"] > 55.0, f"it should have got down: {detail}"
    assert dive.task.legs >= 1, "and turned round"
    assert float(np.linalg.norm(dive.position[:2])) > 50.0, "making ground while it did it"


def test_a_hull_that_cannot_hover_is_the_one_launched_from_the_surface():
    """The rule behind where a glider starts.

    The default start is the middle of the water, which is right for something
    that can stop there. It put a Seaglider on the seabed of a six-hundred-metre
    site and then asked it to profile the top three hundred, so the dive was
    spent climbing and the task was never flown. A vehicle that cannot hold a
    depth is launched from the surface instead, the way one goes over the side
    of a ship.

    Only the decision is checked here. The placement itself happens while a
    scene is being opened and wants a scene to test against; what it turns on
    is this.
    """
    glider = Hydrodynamics.from_package(PACKAGE)
    rov = Hydrodynamics.from_package(
        pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json")
    assert not glider.can_hover, "no thrusters, so no holding anything"
    assert rov.can_hover


def test_a_hull_ballasted_for_the_wrong_sea_is_caught_on_shore():
    """Arithmetic somebody should do before the ship sails.

    A glider's propulsion *is* its buoyancy, so a hull that is out of trim has
    spent its engine before it starts. Ballast it in ordinary seawater, put it
    in the Red Sea at 40.6 PSU, and cancelling the difference costs a third of
    the working range — a known way to lose a deployment, and pure arithmetic.
    """
    dive, said = a_dive_of({"kind": "profile", "toM": 100.0, "fromM": 10.0})
    # Ballasted for ordinary seawater rather than for here.
    dive.body.model.displaced_volume_m3 = dive.body.model.mass_kg / density_of(35.0, 20.0)
    dive.salinity_psu, dive.temperature_c = 40.6, 26.0
    dive.stated_density = None
    dive.density = density_of(40.6, 26.0)

    trim = dive.ballasted_for_this_water()
    assert trim is not None, "a glider is exactly the vehicle this matters for"
    assert trim["outOfTrimKg"] > 0.0, "it floats where it was meant to hang still"
    assert 100.0 < abs(trim["toCancelCc"]) < 160.0, trim
    assert 0.25 < trim["shareOfEngine"] < 0.5, "about a third of the engine, spent on salt"
    assert trim["enough"], "costly, but it can still be trimmed"


def test_an_ROV_is_not_asked_the_question():
    """A vehicle that flies on thrusters is a newton out and never notices."""
    rov = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"
    dive, _ = a_dive_of({"kind": "hold-station", "seconds": 60}, package=rov)
    assert dive.ballasted_for_this_water() is None


def test_water_too_far_out_of_trim_is_refused_before_the_dive():
    dive, said = a_dive_of({"kind": "profile", "toM": 100.0, "fromM": 10.0})
    dive.body.model.displaced_volume_m3 *= 1.03      # grossly mis-ballasted
    dive.begin_task(dive.brief["objective"])
    refusals = [d for k, d in said if k == "task_refused"]
    assert refusals, "it cannot be made neutral and should say so"
    assert "cc" in refusals[0]["why"]
    assert dive.task is None


def test_a_section_that_arrives_with_nothing_in_it_is_not_a_section():
    """Covering the ground is half of it.

    A section is a picture of the water column against distance. A glider that
    makes the far end but profiles every two kilometres has brought back a
    picture with nothing in it: the eddy it was sent to find is smaller than
    the gap between its teeth. That is a failed section that looks exactly like
    a successful transit, and scoring it on distance alone says so.
    """
    from tasks import task_for

    def fly(every_m):
        task = task_for({"kind": "section", "toward": {"dx": 4000, "dy": 0},
                         "bandM": [10, 200], "profileEveryM": 500.0,
                         "timeLimitS": 40000}, np.array([0.0, 0.0, -10.0]), 0.0)
        for metre in range(0, 4001, 25):
            deep = 200.0 if (metre // every_m) % 2 else 10.0
            task.step(float(metre), np.array([float(metre), 0.0, -deep]),
                      0.0, -400.0, [0.0])
        return task

    sparse = fly(1000)
    assert sparse.detail()["alongFraction"] == 1.0, "it got there"
    assert sparse.detail()["profiles"] < 4
    assert sparse.score() < 0.5, "and brought back almost nothing"

    proper = fly(250)
    assert proper.detail()["profiles"] >= 7
    assert proper.score() > 0.85
    assert proper.score() > sparse.score()
