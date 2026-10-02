"""Fish with minds, held to what real fish are measured doing.

Each test names the number it is checked against and where it comes from. The
ranges are wide on purpose: the swimming data are lab tetras and wild reef
fish, and these are sheets for tank and reef species, so what is checked is
that a fish here is in the right world — a kick every half second, not every
two; a body length or two a second, not ten.
"""

import time

import numpy as np
import pytest

import fishmind as fm

FLOOR = -0.93


def a_tank(floor=None, seed=0):
    rng = np.random.default_rng(seed)
    refuges = {
        "branch": np.array([[x, y, -0.8] for x, y in rng.uniform([-0.8, -0.35], [0.8, 0.35], (8, 2))]),
        "crevice": np.array([[x, y, -0.88] for x, y in rng.uniform([-0.8, -0.35], [0.8, 0.35], (8, 2))]),
        "burrow": np.array([[x, y, FLOOR] for x, y in rng.uniform([-0.8, -0.35], [0.8, 0.35], (6, 2))]),
    }
    return fm.Habitat(floor or (lambda x, y: FLOOR), (0.0, 0.0), 2.0, 0.0,
                      box=(0.92, 0.46), refuges=refuges, scale=0.14)


def settled(stock, seconds=20.0, hour=11.0, seed=1, habitat=None, tank=True):
    school = fm.School(stock, habitat or a_tank(), seed=seed, tank=tank)
    light = fm.daylight(hour)
    for _ in range(int(seconds / 0.05)):
        school.step(0.05, light=(hour, light))
    return school


def test_they_swim_in_kicks_about_half_a_second_apart():
    """Calovi et al. 2018: a kick about every 0.5 s while active."""
    school = settled({"chromis_viridis": 16})
    kicks, before = 0, school.kick_in.copy()
    for _ in range(int(60 / 0.05)):
        school.step(0.05, light=(11.0, 1.0))
        kicks += int(((school.kick_in - before) > 0).sum())
        before = school.kick_in.copy()
    every = 16 * 60 / kicks
    assert 0.3 < every < 0.9, f"a kick every {every:.2f} s"


def test_a_chromis_cruises_at_a_body_length_or_two_a_second():
    """Reef damselfish cruise at about 1–2 body lengths a second; a lab tetra
    bursting is 4.5 (Calovi). Faster than 3 is a fish that never stops."""
    school = settled({"chromis_viridis": 16})
    seen = []
    for _ in range(int(60 / 0.05)):
        school.step(0.05, light=(11.0, 1.0))
        seen.append(school.speed / school.length)
    assert 0.6 < float(np.mean(seen)) < 3.0


def test_a_school_keeps_a_body_length_or_two_apart():
    """Nearest neighbours a couple of body lengths apart (Calovi: a pair holds
    about 2.4 BL); not piled on each other, not scattered across the tank."""
    school = settled({"chromis_viridis": 16}, seconds=40)
    d = np.linalg.norm(school.at[:, None] - school.at[None], axis=2)
    np.fill_diagonal(d, np.inf)
    nearest = np.median(d.min(axis=1) / school.length)
    assert 0.7 < nearest < 6.0, f"{nearest:.1f} body lengths"


def test_by_night_the_day_fish_are_in_their_refuges():
    """Damselfish shelter in branching coral all night (Goldshmid 2004);
    wrasse in crevices and sand; a goby in its burrow."""
    stock = {"chromis_viridis": 10, "pseudocheilinus_hexataenia": 4, "amblyeleotris_wheeleri": 4}
    school = settled(stock, seconds=90, hour=23.0)
    home = np.linalg.norm(school.at - school.home, axis=1)
    assert np.median(home) < 0.06, f"median {np.median(home):.3f} m from home"
    assert (school.mode == fm.REST).mean() > 0.8


def test_a_night_fish_is_out_when_the_day_fish_are_in():
    """The Banggai cardinalfish hovers by day and feeds at night."""
    day = settled({"pterapogon_kauderni": 6}, seconds=60, hour=12.0)
    night = settled({"pterapogon_kauderni": 6}, seconds=60, hour=23.0)
    assert (day.mode == fm.REST).mean() > 0.6
    assert (night.mode == fm.REST).mean() < 0.4


def a_crossing(speed, school, size=0.15, start=0.8, seconds=None):
    """A vehicle driven through the middle of a school along x."""
    centre = school.at.mean(axis=0)
    vehicle = centre + np.array([start, 0.0, 0.0])
    fled = np.zeros(school.of_them, dtype=bool)
    steps = int((seconds or (2 * start / max(speed, 1e-6))) / 0.05)
    for _ in range(steps):
        vehicle = vehicle - np.array([speed * 0.05, 0.0, 0.0])
        school.step(0.05, vehicle=vehicle, light=(11.0, 1.0), vehicle_size=size)
        fled |= school.mode == fm.FLEE
    return fled


def test_a_vehicle_coming_at_them_scatters_them():
    """Fish flee a looming threat (Hein et al. 2018); 57% of fish reacted to
    an ROV in Laidig 2013's surveys."""
    school = settled({"chromis_viridis": 16}, seed=2)
    assert a_crossing(0.3, school).mean() > 0.6


def test_a_vehicle_sitting_still_is_mostly_ignored():
    """Looming is the vehicle growing in the fish's eye because *it* is coming;
    a fish swimming up to a still one is not frightened by its own approach."""
    school = settled({"chromis_viridis": 16}, seed=2)
    still = school.at.mean(axis=0) + np.array([0.7, 0.0, 0.0])
    fled = np.zeros(16, dtype=bool)
    for _ in range(200):
        school.step(0.05, vehicle=still, light=(11.0, 1.0), vehicle_size=0.15)
        fled |= school.mode == fm.FLEE
    assert fled.mean() < 0.35


def test_they_come_back_when_it_has_gone():
    school = settled({"chromis_viridis": 16}, seed=2)
    a_crossing(0.3, school)
    for _ in range(int(40 / 0.05)):
        school.step(0.05, light=(11.0, 1.0))
    assert (school.mode == fm.FLEE).mean() < 0.15


def test_a_crossing_through_open_water_hardly_touches_one():
    """On a reef, with room to go: a fish that sees a vehicle coming at a
    third of a metre a second gets out of the way."""
    habitat = fm.Habitat(lambda x, y: -9.0, (0.0, 0.0), 60.0, 0.0)
    school = fm.School({"chromis_cyanea": 30}, habitat, seed=4)
    for _ in range(400):
        school.step(0.05, light=(11.0, 1.0))
    a_crossing(0.3, school, size=0.25, start=3.0)
    assert school.bumped <= 3, f"{school.bumped} fish struck"


def test_they_never_leave_the_water_or_go_through_the_glass_or_the_floor():
    school = settled({"chromis_viridis": 12, "amblyeleotris_wheeleri": 4}, seconds=60)
    assert (np.abs(school.at[:, 0]) <= 0.92 + 1e-9).all()
    assert (np.abs(school.at[:, 1]) <= 0.46 + 1e-9).all()
    assert (school.at[:, 2] >= FLOOR).all() and (school.at[:, 2] < 0.0).all()


def test_they_go_round_a_rock_and_not_over_it():
    """A pillar from the sand to near the surface, as in iocean-tank-1: the
    fish should rarely be found above its footprint."""
    def pillar(x, y):
        return -0.25 if (x - 0.0) ** 2 + (y - 0.0) ** 2 < 0.08 ** 2 else FLOOR
    school = fm.School({"chromis_viridis": 16}, a_tank(floor=pillar), seed=5, tank=True)
    over = 0
    for _ in range(int(60 / 0.05)):
        school.step(0.05, light=(11.0, 1.0))
        over += int((np.hypot(school.at[:, 0], school.at[:, 1]) < 0.08).sum())
    # The pillar is 1% of the tank's floor; fish piling over it would be more.
    assert over / (16 * 1200) < 0.01


def test_a_current_carries_them_and_they_face_into_it():
    """Fish hold station facing into the flow (rheotaxis); in a current too
    strong for them they are carried."""
    school = settled({"chromis_viridis": 16}, seconds=10)
    flow = np.tile([0.05, 0.0, 0.0], (16, 1))
    headings = []
    for _ in range(int(30 / 0.05)):
        school.step(0.05, light=(11.0, 1.0), flow=flow)
        headings.append(np.cos(school.heading))
    # Facing upstream: heading towards -x more often than not.
    assert np.mean(headings) < -0.1


def test_the_wash_pushes_a_fish_behind_the_vehicle():
    """A fish in a thruster's jet is carried downstream of it."""
    habitat = fm.Habitat(lambda x, y: -9.0, (0.0, 0.0), 20.0, 0.0)
    calm = fm.School({"chromis_cyanea": 1}, habitat, seed=6)
    blown = fm.School({"chromis_cyanea": 1}, habitat, seed=6)
    jet = np.array([[-0.5, 0.0, 0.0]])
    for _ in range(40):
        calm.step(0.05, light=(11.0, 1.0))
        blown.step(0.05, light=(11.0, 1.0), flow=jet)
    assert blown.at[0, 0] < calm.at[0, 0] - 0.5


def test_a_reef_of_fourteen_hundred_steps_in_a_few_milliseconds():
    """A reef's fish step twenty times a simulated second; at 1,400 of them a
    step must stay well under the 50 ms it has."""
    habitat = fm.Habitat(lambda x, y: -9.0, (0.0, 0.0), 198.0, 0.0)
    school = fm.School({"damselfish": 400, "parrotfish": 300, "surgeonfish": 250, "wrasse": 200,
                        "snapper": 150, "butterflyfish": 60, "bottom": 40}, habitat, seed=3)
    began = time.perf_counter()
    for _ in range(40):
        school.step(0.05, vehicle=np.array([0.0, 0.0, -7.0]), light=(11.0, 1.0))
    each = (time.perf_counter() - began) / 40
    assert each < 0.03, f"{each * 1000:.1f} ms a step"


def test_the_same_seed_is_the_same_fish():
    a = settled({"chromis_viridis": 8}, seconds=10, seed=9)
    b = settled({"chromis_viridis": 8}, seconds=10, seed=9)
    assert np.array_equal(a.at, b.at)


def test_what_they_did_is_said():
    school = settled({"chromis_viridis": 8, "pseudocheilinus_hexataenia": 3}, seconds=30)
    said = school.said()
    assert said["fish"] == 11 and set(said["spent"]) == {"chromis_viridis", "pseudocheilinus_hexataenia"}
    for budget in said["spent"].values():
        assert abs(sum(budget.values()) - 1.0) < 0.01
