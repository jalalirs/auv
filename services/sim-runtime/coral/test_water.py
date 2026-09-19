"""Water that has a density, and a depth gauge that was set for a different sea.

Density was a constant in the runtime and an argument to the vehicle's
constructor, which put the water's own property inside the vehicle. A dive
could not ask for different water, so Florida and the Red Sea were the same
sea and the difference between them — four kilos a cubic metre, a fifth of
what our BlueROV2 is out of trim by — did not exist.
"""

import pathlib
import sys


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import water
from hydrodynamics import DENSITY_SEAWATER, Allocator, Body, Hydrodynamics, density_of
from runner import Dive

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"

LOOE_KEY = {"salinityPsu": 36.0, "temperatureC": 29.0}
RED_SEA = {"salinityPsu": 40.6, "temperatureC": 26.0}


def a_dive(water):
    model = Hydrodynamics.from_package(PACKAGE)
    brief = {"durationSeconds": 120, "initialState": {"positionM": [0, 0, -7]},
             "conditions": {"kind": "constructed", "parameters": water}}
    return Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"), lambda k, **d: None)


def test_the_equation_of_state_is_the_published_one():
    """EOS-80 verbatim, against the check values in the tables.

    Worth testing rather than trusting, because the whole point of carrying the
    real equation is a difference of four kilos a cubic metre, and an equation
    that is wrong by four is indistinguishable from the constant it replaced.
    """
    for salinity, temperature, published in ((0.0, 5.0, 999.96675),
                                             (35.0, 0.0, 1028.10623),
                                             (35.0, 20.0, 1024.76346),
                                             (35.0, 25.0, 1023.34306)):
        got = density_of(salinity, temperature)
        assert abs(got - published) < 1e-3, f"S={salinity} T={temperature}: {got} not {published}"


def test_water_that_says_nothing_floats_a_vehicle_the_way_it_always_did():
    """No silent re-pricing of every dive already in the record."""
    dive = a_dive({})
    assert dive.density == DENSITY_SEAWATER
    assert dive.body.model.density == DENSITY_SEAWATER


def test_the_same_hull_floats_differently_in_two_real_seas():
    florida, red_sea = a_dive(LOOE_KEY), a_dive(RED_SEA)
    assert red_sea.density > florida.density
    assert abs((red_sea.density - florida.density) - 4.45) < 0.1, "the gap between the two sites"

    # What that is worth to the vehicle: buoyancy is density times displaced
    # volume times g, and the vehicle's whole trim is under two newtons.
    heavier = florida.body.model.net_buoyancy_n
    lighter = red_sea.body.model.net_buoyancy_n
    assert lighter > heavier, "saltier water holds it up better"
    assert abs(lighter - heavier) > 0.4, "and by enough to matter against a 1.9 N trim"


def test_a_measured_density_is_not_second_guessed():
    dive = a_dive({"salinityPsu": 40.6, "temperatureC": 26.0, "densityKgM3": 1031.0})
    assert dive.density == 1031.0


def test_a_depth_gauge_set_for_the_wrong_sea_is_wrong_in_proportion():
    """Biased, not noisy: the same fraction wrong at every depth.

    A gauge calibrated on shore for ordinary seawater and flown in the Red Sea
    divides the pressure it feels by too small a number, so it reads deep —
    and it reads further deep the deeper the vehicle goes, which is the
    opposite of how every other error in this platform behaves.
    """
    dive = a_dive({**RED_SEA, "depthGaugeDensityKgM3": DENSITY_SEAWATER})
    scale = dive.density / dive.depth_gauge_density
    assert scale > 1.0, "the Red Sea is denser than the gauge was told"
    for depth in (10.0, 50.0, 100.0):
        assert 0.0 < depth * (scale - 1.0) < 0.5
    assert abs(100.0 * (scale - 1.0) - 0.22) < 0.05, "about a fifth of a metre at a hundred"

    # And a gauge that suits its water is not wrong at all.
    honest = a_dive(RED_SEA)
    assert honest.depth_gauge_density == honest.density


def test_the_dive_says_what_water_it_was_in():
    said = a_dive({**RED_SEA, "depthGaugeDensityKgM3": DENSITY_SEAWATER}).conditions_said()
    assert said["salinityPsu"] == 40.6
    assert said["temperatureC"] == 26.0
    assert abs(said["densityKgM3"] - 1027.27) < 0.01
    assert said["depthGaugeDensityKgM3"] == DENSITY_SEAWATER
    # A gauge that matches its water is not worth a line.
    assert "depthGaugeDensityKgM3" not in a_dive(RED_SEA).conditions_said()


# ── a hull that is squeezed and chilled ──────────────────────────────────────

def a_hull(compressibility=0.0, expansion=0.0, reference=20.0, volume=0.0507, mass=52.0):
    """A bare model with the coefficients set directly.

    No vehicle in the catalogue states these yet, deliberately: the BlueROV2
    works in a hundred metres where the effect is small, and inventing a
    compressibility for it would be putting a number in the record that nobody
    measured. The Seaglider will be the first package to state them, because
    for a vehicle that works to a thousand metres they are not a correction.
    """
    model = Hydrodynamics.from_package(PACKAGE)
    model.displaced_volume_m3 = volume
    model.mass_kg = mass
    model.compressibility_per_dbar = compressibility
    model.thermal_expansion_per_c = expansion
    model.reference_temperature_c = reference
    return model


def test_the_pressure_half_of_the_equation_of_state_is_published_too():
    for salinity, temperature, dbar, published in ((35.0, 25.0, 0.0, 1023.34306),
                                                   (35.0, 5.0, 0.0, 1027.67547),
                                                   (35.0, 25.0, 10000.0, 1062.53817),
                                                   (35.0, 5.0, 10000.0, 1069.48914)):
        got = density_of(salinity, temperature, dbar)
        assert abs(got - published) < 1e-3, f"S={salinity} T={temperature} p={dbar}: {got}"


def test_water_is_denser_underneath_more_water():
    surface = density_of(40.6, 22.0, 0.0)
    deep = density_of(40.6, 22.0, 1000.0)
    assert deep > surface
    # Four kilos a cubic metre — as much as the whole gap between the two sites.
    assert 4.0 < deep - surface < 4.6


def test_a_rigid_hull_is_the_same_size_everywhere():
    """What every vehicle in the catalogue is, and must go on being."""
    model = a_hull()
    assert model.volume_at(0.0, 26.0) == model.displaced_volume_m3
    assert model.volume_at(1000.0, 2.0) == model.displaced_volume_m3


def test_a_hull_squeezed_at_depth_displaces_less():
    model = a_hull(compressibility=4.0e-6)
    lost = model.displaced_volume_m3 - model.volume_at(1000.0)
    assert lost > 0.0
    # About 200 cc on a glider-sized hull, which is most of the working range
    # of the buoyancy engine that is its only means of propulsion.
    assert 0.00018 < lost < 0.00022, f"{lost * 1e6:.0f} cc"


def test_a_hull_shrinks_when_the_water_is_cold():
    model = a_hull(expansion=69e-6, reference=26.0)
    assert model.volume_at(0.0, 4.0) < model.volume_at(0.0, 26.0)
    assert model.volume_at(0.0, 26.0) == model.displaced_volume_m3


def test_whether_it_sinks_faster_as_it_goes_down_is_which_effect_wins():
    """The design problem of a glider, and not something to assume.

    Water gets denser with depth and the hull gets smaller; they push the same
    sum in opposite directions. A hull squeezed harder than the water loses the
    race and grows heavier the deeper it goes, which runs away. One squeezed
    less than the water grows lighter and stops descending. Gliders are built
    to sit near the middle on purpose.
    """
    shallow_water = density_of(40.6, 22.0, 0.0)
    deep_water = density_of(40.6, 22.0, 1000.0)
    water_compressibility = (deep_water / shallow_water - 1.0) / 1000.0

    soft = a_hull(compressibility=water_compressibility * 2.0)
    stiff = a_hull(compressibility=water_compressibility * 0.5)
    for model in (soft, stiff):
        model.density = shallow_water
    up_top = soft.buoyancy_n_at(0.0, density=shallow_water)
    assert soft.buoyancy_n_at(1000.0, density=deep_water) < up_top, "too soft: it sinks away"
    assert stiff.buoyancy_n_at(1000.0, density=deep_water) > up_top, "too stiff: it stops going down"


def test_a_temperature_profile_is_read_down_the_column():
    """The Red Sea stays warm at depth, which is why it is worth stating."""
    dive = a_dive({"salinityPsu": 40.6,
                   "temperatureProfile": [[0, 26.0], [200, 21.5], [1000, 21.5]]})
    assert dive.temperature_at(0.0) == 26.0
    assert dive.temperature_at(100.0) == 23.75            # straight line between the two
    assert dive.temperature_at(200.0) == 21.5
    assert dive.temperature_at(5000.0) == 21.5            # flat below the last point
    # And the water is denser down there for both reasons at once.
    assert dive.density_at(1000.0) > dive.density_at(0.0)


def test_water_somebody_measured_is_not_extrapolated():
    dive = a_dive({"salinityPsu": 40.6, "temperatureC": 26.0, "densityKgM3": 1031.0})
    assert dive.density_at(0.0) == 1031.0
    assert dive.density_at(1000.0) == 1031.0


# ── the horizon has to enclose the site it stands round ──────────────────────

def test_the_wall_clears_the_corners_of_its_site():
    """A site is a square and the wall is a circle, so it has to clear half
    the diagonal, not half the edge."""
    import math

    for across in (600.0, 1000.0, 3000.0, 6000.0):
        half_diagonal = across / 2 * math.sqrt(2)
        assert water.horizon_for(across) > half_diagonal, across


def test_the_wall_clears_where_a_dive_actually_begins():
    """Al Fahal is three kilometres across and its dive begins 1,398 m from
    the origin. At a fixed nine hundred metres the camera was outside its own
    horizon: the band came back, and the downward view was onto nothing."""
    assert water.horizon_for(3000.0) > 1398.0


def test_the_sea_reaches_past_the_wall():
    """If the sea stops short of the horizon, the gap between them is the band
    again, in the one place nothing else can cover it."""
    for across in (600.0, 1000.0, 3000.0, 6000.0):
        assert water.sea_reaches(across) > water.horizon_for(across), across


def test_a_small_site_still_gets_a_wall_worth_having():
    assert water.horizon_for(200.0) >= water.HORIZON_AT_LEAST_M


def test_the_sea_is_sampled_finely_near_the_middle_whatever_the_site():
    """Fine cells where the waves can be seen, growing cells after that. A
    three kilometre site must not buy its reach by coarsening the near field."""
    for across in (1000.0, 3000.0):
        steps = water._across(across)
        middle = len(steps) // 2
        assert abs((steps[middle + 1] - steps[middle]) - water.SURFACE_CELL) < 1e-6
        assert steps[-1] >= water.sea_reaches(across)


def test_the_far_sea_is_flat_because_it_cannot_carry_a_wave():
    """The mesh grows outwards, so the far cells are hundreds of metres across.
    A two metre wave sampled once per two hundred metres is not a coarse wave,
    it is noise, and since the surface is glass at a grazing angle that noise
    filled the top third of every frame."""
    steps = water._across(1000.0)
    fine = water.SURFACE_ACROSS / 2.0
    far = [s for s in steps if abs(s) > 2 * fine]
    assert far, "the sea should reach well past its fine region"
    # Two cells out from the fine region, nothing is left of the amplitude.
    for out in (2 * fine, 3 * fine):
        carries = max(0.0, 1.0 - (out - fine) / fine)
        assert carries == 0.0, out
    # And inside it, the full wave.
    assert max(0.0, 1.0 - (0.5 * fine - fine) / fine) == 1.0
