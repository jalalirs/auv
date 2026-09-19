"""Fish that are there, rather than fish that are drawn.

The point of simulating them is that a monitoring mission can be scored on
counting them, so what these check is mostly that the count means something:
that they are where the record says, that they stay on the reef, and that they
do the one thing an ROV pilot would notice if it were missing.
"""

import numpy as np
import pytest

from coral import life

FLAT = -9.0


def a_seabed(x, y):
    return FLAT


def a_reef(many=400, seed=1, floor=a_seabed):
    counted = [
        {"taxon": "Sparisoma viride", "group": "Actinopterygii", "observations": 160},
        {"taxon": "Ocyurus chrysurus", "group": "Actinopterygii", "observations": 150},
        {"taxon": "Abudefduf saxatilis", "group": "Actinopterygii", "observations": 90},
        {"taxon": "Caranx ruber", "group": "Actinopterygii", "observations": 60},
        {"taxon": "Aluterus scriptus", "group": "Actinopterygii", "observations": 40},
    ]
    return life.Shoal(life.as_observed(counted, many), floor, 600.0, seed=seed)


# ── what is on the reef ──────────────────────────────────────────────────────

def test_a_species_is_sorted_by_its_genus():
    assert life.group_of("Sparisoma viride") == "parrotfish"
    assert life.group_of("Caranx ruber") == "jack"
    # And something nobody has classified is on its own rather than guessed at.
    assert life.group_of("Nothing recorded") == "solitary"


def test_the_shares_are_what_was_observed():
    counted = [
        {"taxon": "Sparisoma viride", "group": "Actinopterygii", "observations": 75},
        {"taxon": "Caranx ruber", "group": "Actinopterygii", "observations": 25},
    ]
    got = life.as_observed(counted, 200)
    assert got == {"parrotfish": 150, "jack": 50}


def test_they_add_up_to_what_was_asked_for():
    """Largest remainder, so a hundred fish is a hundred fish and the rarest
    group is not rounded out of existence."""
    counted = [{"taxon": t, "group": "Actinopterygii", "observations": n}
               for t, n in (("Sparisoma viride", 161), ("Ocyurus chrysurus", 151),
                            ("Abudefduf saxatilis", 93), ("Caranx ruber", 66),
                            ("Aluterus scriptus", 58))]
    for many in (7, 50, 101, 999):
        got = life.as_observed(counted, many)
        assert sum(got.values()) == many, (many, got)


def test_what_is_not_a_fish_is_not_counted():
    """The record holds sea fans, molluscs and a pelican."""
    counted = [
        {"taxon": "Sparisoma viride", "group": "Actinopterygii", "observations": 50},
        {"taxon": "Gorgonia ventalina", "group": "Animalia", "observations": 78},
        {"taxon": "Pelecanus occidentalis", "group": "Aves", "observations": 4},
    ]
    assert life.as_observed(counted, 10) == {"parrotfish": 10}


def test_a_place_with_no_record_gets_no_fish():
    assert life.as_observed([], 500) == {}
    assert life.Shoal({}, a_seabed, 600.0).of_them == 0


# ── where they are ───────────────────────────────────────────────────────────

def test_they_stay_off_the_bottom_and_under_the_surface():
    reef = a_reef()
    for _ in range(60):
        reef.step(0.1)
    assert reef.at[:, 2].min() > FLAT, "a fish inside the seabed"
    assert reef.at[:, 2].max() < 0.0, "a fish in the air"


def test_they_stay_on_the_site():
    """A flock with no home wanders off a reef inside a minute."""
    reef = a_reef()
    for _ in range(200):
        reef.step(0.1)
    assert np.abs(reef.at[:, :2]).max() <= 0.5 * reef.across


def test_a_grazer_is_lower_than_a_jack():
    """Most of what tells one fish from another in a frame is how far off the
    bottom it is."""
    reef = a_reef(many=400)
    for _ in range(40):
        reef.step(0.1)
    above = reef.at[:, 2] - FLAT
    grazing = above[reef.kinds == "parrotfish"].mean()
    passing = above[reef.kinds == "jack"].mean()
    assert passing > grazing + 1.0, (grazing, passing)


def test_a_school_holds_together():
    """One school, not one kind. A kind is spread over the whole reef in a
    dozen separate schools, each over its own patch, so the spread of every
    damselfish on the site is site-wide by construction and says nothing."""
    reef = a_reef()
    biggest = np.bincount(reef.school).argmax()
    theirs = np.flatnonzero(reef.school == biggest)
    assert len(theirs) > 4

    def spread():
        at = reef.at[theirs]
        return float(np.linalg.norm(at - at.mean(axis=0), axis=1).mean())

    for _ in range(120):
        reef.step(0.1)
    assert spread() < 8.0, spread()


def test_a_kind_is_spread_over_the_reef_in_several_schools():
    reef = a_reef()
    assert reef.said()["schools"] > len(reef.said()["byGroup"])


def test_the_same_seed_is_the_same_reef():
    """Two runs of one dive have to be the same dive."""
    one, two = a_reef(seed=4), a_reef(seed=4)
    for _ in range(20):
        one.step(0.1)
        two.step(0.1)
    assert np.allclose(one.at, two.at)


# ── and what they do about a vehicle ─────────────────────────────────────────

def test_a_vehicle_scatters_them():
    """The part an ROV pilot recognises instantly."""
    reef = a_reef()
    for _ in range(30):
        reef.step(0.1)
    # On a fish, not at the middle of the site: the centroid of a reef is
    # open sand and scattering nothing proves nothing.
    middle = reef.at[np.bincount(reef.school).argmax() == reef.school].mean(axis=0)
    close = np.linalg.norm(reef.at - middle, axis=1) < 8.0
    assert close.sum() > 3
    before = np.linalg.norm(reef.at[close] - middle, axis=1).mean()
    for _ in range(12):
        reef.step(0.1, vehicle=middle, thrust=1.0)
    after = np.linalg.norm(reef.at[close] - middle, axis=1).mean()
    assert after > before, (before, after)
    assert reef.said()["scattered"] > 0.0


def test_they_come_back():
    """Scatter without reforming is a reef that empties over a dive."""
    reef = a_reef()
    for _ in range(30):
        reef.step(0.1)
    middle = reef.at[np.bincount(reef.school).argmax() == reef.school].mean(axis=0)
    close = np.flatnonzero(np.linalg.norm(reef.at - middle, axis=1) < 8.0)
    assert len(close) > 3
    for _ in range(15):
        reef.step(0.1, vehicle=middle, thrust=1.0)
    scattered = np.linalg.norm(reef.at[close] - middle, axis=1).mean()
    for _ in range(140):
        reef.step(0.1)
    reformed = np.linalg.norm(reef.at[close] - middle, axis=1).mean()
    assert reformed < scattered, (scattered, reformed)


def test_a_working_vehicle_frightens_more_of_them():
    """A vehicle drifting past on a current is a log; the same vehicle on full
    thrusters clears a hundred square metres."""
    idle, working = a_reef(seed=7), a_reef(seed=7)
    for _ in range(30):
        idle.step(0.1)
        working.step(0.1)
    middle = idle.at[np.bincount(idle.school).argmax() == idle.school].mean(axis=0)
    idle.step(0.1, vehicle=middle, thrust=0.0)
    working.step(0.1, vehicle=middle, thrust=1.0)
    assert working.said()["scattered"] > idle.said()["scattered"]


def test_nothing_is_scattered_by_nothing():
    reef = a_reef()
    reef.step(0.1)
    assert reef.said()["scattered"] == 0.0


# ── and the counting, which is the whole point ───────────────────────────────

def test_a_camera_counts_what_is_in_front_of_it():
    reef = a_reef()
    for _ in range(30):
        reef.step(0.1)
    at = reef.at[0]
    forwards = reef.seen_from(at, (1.0, 0.0, 0.0))
    backwards = reef.seen_from(at, (-1.0, 0.0, 0.0))
    everything = reef.said()["byGroup"]
    for counted in (forwards, backwards):
        for kind, many in counted.items():
            assert many <= everything[kind]
    # And it is a cone, not a sphere: the two views do not hold everything.
    assert sum(forwards.values()) + sum(backwards.values()) < reef.of_them


def test_a_camera_sees_nothing_beyond_its_reach():
    reef = a_reef()
    reef.step(0.1)
    assert reef.seen_from((0.0, 0.0, -5.0), (1.0, 0.0, 0.0), reach=0.01) == {}


def test_an_empty_reef_counts_as_empty():
    empty = life.Shoal({}, a_seabed, 600.0)
    assert empty.seen_from((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)) == {}
    assert empty.said() == {"fish": 0, "byGroup": {}, "schools": 0,
                           "scattered": 0.0}


def test_a_step_of_no_time_changes_nothing():
    reef = a_reef()
    was = reef.at.copy()
    reef.step(0.0)
    assert np.array_equal(reef.at, was)


@pytest.mark.parametrize("kind", sorted(life.GROUPS))
def test_every_group_can_be_put_on_a_reef(kind):
    reef = life.Shoal({kind: 30}, a_seabed, 600.0, seed=2)
    assert reef.of_them == 30
    for _ in range(20):
        reef.step(0.1)
    assert np.isfinite(reef.at).all(), f"{kind} went to infinity"


# ── and the things that are rooted ───────────────────────────────────────────

def test_still_water_does_not_bend_anything():
    phase = np.linspace(0, 6, 40)
    lean, _ = life.bending((0.0, 0.0), phase)
    assert not lean.any()


def test_they_lean_further_in_faster_water():
    phase = np.linspace(0, 6, 40)
    slow, _ = life.bending((0.1, 0.0), phase)
    fast, _ = life.bending((0.4, 0.0), phase)
    assert fast.mean() > slow.mean()


def test_they_lean_the_way_the_water_goes():
    phase = np.zeros(4)
    _, towards = life.bending((0.0, 0.3), phase)
    assert np.allclose(towards, np.pi / 2)


def test_a_field_of_them_does_not_move_as_one_sheet():
    """Real ones are in each other's wake and no two are in step."""
    phase = np.linspace(0, 2 * np.pi, 50)
    lean, _ = life.bending((0.3, 0.0), phase)
    assert lean.std() > 0.0


def test_a_sea_rod_is_stiffer_than_a_sea_fan():
    phase = np.zeros(10)
    fan, _ = life.bending((0.3, 0.0), phase, life.STIFFNESS["fan"])
    plume, _ = life.bending((0.3, 0.0), phase, life.STIFFNESS["plume"])
    assert fan.mean() > plume.mean()


def test_nothing_is_laid_flat_however_hard_the_water_runs():
    phase = np.zeros(10)
    lean, _ = life.bending((9.0, 0.0), phase)
    assert lean.max() <= life.MOST


def test_a_leaning_colony_is_still_a_rotation():
    phase = np.linspace(0, 6, 12)
    lean, towards = life.bending((0.3, 0.2), phase)
    turn = np.linspace(0, 2 * np.pi, 12)
    w, x, y, z = life.leaning(lean, towards, turn)
    assert np.allclose(w * w + x * x + y * y + z * z, 1.0, atol=1e-6)


def test_an_unbent_colony_keeps_its_own_turn():
    turn = np.array([0.0, 1.0, 2.0])
    w, x, y, z = life.leaning(np.zeros(3), np.zeros(3), turn)
    assert np.allclose(x, 0.0, atol=1e-9) and np.allclose(y, 0.0, atol=1e-9)
    assert np.allclose(w, np.cos(turn / 2)) and np.allclose(z, np.sin(turn / 2))


def test_a_shoal_lives_where_the_work_is():
    """A shoal is a patch of reef around the dive, not the whole site. The
    first version built it centred on nothing and slid it across afterwards,
    so every seabed lookup and every edge measured from the wrong place and
    the first step clipped the fish back off the dive."""
    work = np.array([140.0, -60.0])
    across = 200.0
    reef = life.Shoal({"snapper": 400}, a_seabed, across, seed=3, about=work)

    def inside():
        return np.abs(reef.at[:, :2] - work).max()

    # Every one of them is in the water that was stocked, which is around the
    # work and not around the origin.
    assert inside() <= 0.5 * across, inside()
    for _ in range(80):
        reef.step(0.1)
    assert inside() <= 0.5 * across, inside()
    # And with enough schools the middle of them is the middle of the work.
    assert np.allclose(reef.at[:, :2].mean(axis=0), work, atol=0.2 * across)


# ── a record from an ocean this map may not know ─────────────────────────────

def a_record(*pairs):
    return [{"taxon": t, "group": "Actinopterygii", "observations": n}
            for t, n in pairs]


def test_a_caribbean_record_is_almost_all_placed():
    got = life.how_much_was_placed(a_record(
        ("Sparisoma viride", 161), ("Ocyurus chrysurus", 151),
        ("Acanthurus coeruleus", 113), ("Abudefduf saxatilis", 93),
        ("Thalassoma bifasciatum", 90), ("Caranx ruber", 66)))
    assert got["unplacedShare"] == 0.0


def test_a_red_sea_record_is_placed_too():
    """The map was Caribbean only. The moment a Red Sea reef got a record,
    every Pseudanthias, Pomacentrus and Chlorurus on it fell into the
    fallback, and a reef of schooling planktivores was drawn as loners."""
    got = life.how_much_was_placed(a_record(
        ("Pseudanthias squamipinnis", 9), ("Pomacentrus sulfureus", 8),
        ("Halichoeres hortulanus", 7), ("Epibulus insidiator", 6),
        ("Scarus ferrugineus", 6), ("Pygoplites diacanthus", 5),
        ("Chlorurus sordidus", 4), ("Zebrasoma desjardinii", 3)))
    assert got["unplacedShare"] == 0.0, got["commonestUnplaced"]


def test_the_red_sea_genera_land_where_they_belong():
    assert life.group_of("Pseudanthias squamipinnis") == "damselfish"
    assert life.group_of("Chlorurus sordidus") == "parrotfish"
    assert life.group_of("Epibulus insidiator") == "wrasse"
    assert life.group_of("Pygoplites diacanthus") == "butterflyfish"
    assert life.group_of("Zebrasoma desjardinii") == "surgeonfish"


def test_an_ocean_it_does_not_know_says_so():
    """The point of the measurement: a record it cannot place must be loud
    about it rather than quietly filling a reef with loners."""
    got = life.how_much_was_placed(a_record(
        ("Nototheniidae something", 40), ("Notothenia rossii", 30),
        ("Sparisoma viride", 30)))
    assert got["unplacedShare"] == 0.7
    assert "notothenia" in got["commonestUnplaced"]


def test_what_is_not_a_fish_is_not_counted_against_the_map():
    counted = a_record(("Sparisoma viride", 50))
    counted.append({"taxon": "Gorgonia ventalina", "group": "Animalia",
                    "observations": 78})
    assert life.how_much_was_placed(counted)["observations"] == 50


def test_an_empty_record_does_not_divide_by_nothing():
    assert life.how_much_was_placed([])["unplacedShare"] == 0.0


@pytest.mark.parametrize("place,most", [("looe-key", 0.12), ("al-fahal", 0.20)])
def test_a_real_record_is_mostly_placed(place, most):
    """A guard, not a target. The map does not have to know every genus in an
    ocean, and it does have to know most of what a record of one actually
    contains — Al Fahal's came back 45% unplaced on a Caribbean map and a reef
    of schooling planktivores would have been drawn as a reef of loners."""
    import json
    import pathlib as _pathlib

    counted = _pathlib.Path.home() / "coral-city" / "reference" / place / "species_counts.json"
    if not counted.is_file():
        pytest.skip(f"no species record fetched for {place}")
    got = life.how_much_was_placed(json.loads(counted.read_text()))
    assert got["unplacedShare"] <= most, got["commonestUnplaced"]


def test_a_fish_that_sits_on_the_bottom_stays_on_it():
    reef = life.Shoal({"bottom": 40}, a_seabed, 300.0, seed=2)
    for _ in range(60):
        reef.step(0.1)
    above = reef.at[:, 2] - FLAT
    assert above.max() < 0.6, above.max()


def test_a_bottom_sitter_lets_a_vehicle_closer_than_a_jack_does():
    """It is the opposite of everything else here, and it is most of what is
    actually on a reef."""
    assert life.GROUPS["bottom"]["wary"] < life.GROUPS["jack"]["wary"]
    assert life.GROUPS["bottom"]["above"][0] < life.GROUPS["parrotfish"]["above"][0]
