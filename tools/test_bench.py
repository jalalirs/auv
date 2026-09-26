"""The bench, and the column it judged on without reporting.

The plan judges a controller on "energy, time, closing navigation error,
things struck". Three of those were reported.
"""

import importlib.machinery
import importlib.util
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _bench():
    loader = importlib.machinery.SourceFileLoader("bench", str(HERE / "bench"))
    spec = importlib.util.spec_from_loader("bench", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _row(**over):
    row = {"score": 0.5, "energyWh": 1.0, "driftM": 1.0, "seconds": 100.0,
           "thoughts": 0, "slowestThoughtS": 0.0, "ended": "achieved",
           "struck": 0, "grounded": 0}
    row.update(over)
    return row


def test_a_dive_that_hit_nothing_and_one_that_hit_the_ground_are_told_apart():
    """They are different mistakes: clipping a nursery frame is hitting
    something a person placed, flying into a spur is hitting the place."""
    bench = _bench()
    assert bench._hit(_row()) == 0
    assert bench._hit(_row(struck=3)) == 3
    assert bench._hit(_row(grounded=2)) == 2
    assert bench._hit(_row(struck=3, grounded=2)) == 5


def test_strikes_are_summed_and_not_averaged():
    """A controller that ploughed through three nursery frames on one dive and
    nothing on seven did not hit three-eighths of a frame."""
    bench = _bench()
    rows = [_row(struck=3)] + [_row() for _ in range(7)]
    said = bench.summarise(rows)
    assert said["struck"] == 3
    assert said["dives"] == 8


def test_the_verdict_says_what_was_hit():
    """`wary` arrives five metres short and hits nothing; `pursue` arrives
    exactly and ploughs through three nursery frames. Which is better is the
    question this bench exists to put a number on, and the number was
    missing."""
    bench = _bench()
    careful = bench.summarise([_row(score=0.7, struck=0)])
    keen = bench.summarise([_row(score=0.9, struck=3)])
    said = bench._attribution(careful, keen, "wary", "pursue")
    assert "wary hit 0 things and pursue hit 3" in said
    assert "by going through things" in said


def test_it_does_not_accuse_a_controller_that_hit_less():
    bench = _bench()
    keen = bench.summarise([_row(score=0.9, struck=3)])
    careful = bench.summarise([_row(score=0.95, struck=0)])
    said = bench._attribution(keen, careful, "pursue", "wary")
    assert "by going through things" not in said


def test_the_same_task_draws_the_same_water_on_every_machine_and_day():
    """Not Python's hash: that is salted per process, so the same task would
    draw different water on Tuesday than on Monday and every comparison across
    days would be quietly worthless."""
    bench = _bench()
    assert bench.seed_for("standard", "reach") == bench.seed_for("standard", "reach")
    assert bench.seed_for("standard", "reach") != bench.seed_for("standard", "dock")
    # The value itself, pinned, because "it is a digest" is not the property
    # that matters — "it is this number, always" is.
    assert bench.seed_for("standard", "reach") == 40487


def test_the_suite_does_not_move():
    """A benchmark whose contents move is not one."""
    bench = _bench()
    assert bench.SUITES["standard"] == [
        "reach", "waypoints", "transect", "survey", "search",
        "treat", "inspect", "dock"]
    assert bench.WATER == "gentle"
    assert bench.TECHNOLOGY == "dead-reckoning"


# ── whose controller the bench is about to fly ───────────────────────────────

class _Listing:
    """A platform that answers with an organisation's autonomy and nothing else."""

    org = "org_x"

    def __init__(self, autonomy):
        self.autonomy = autonomy

    def call(self, method, path, body=None):
        assert path.endswith("/autonomy"), path
        return {"autonomy": self.autonomy}


TWO_BUILDS = [
    {"id": "stack_old", "slug": "learned-hold", "name": "Learned hold",
     "imageDigest": "sha256:1111", "createdAt": "2026-09-03T19:52:19Z"},
    {"id": "stack_new", "slug": "learned-hold", "name": "Learned hold",
     "imageDigest": "sha256:2222", "createdAt": "2026-09-03T20:04:28Z"},
]


def test_a_built_in_is_flown_by_name():
    tool = _bench()
    assert tool.whose(_Listing([]), "pursue") == {"builtIn": "pursue"}


def test_somebody_elses_controller_is_found_by_its_slug():
    tool = _bench()
    flying = tool.whose(_Listing(TWO_BUILDS), "learned-hold")
    assert flying["stack"]["id"] == "stack_new"


def test_the_newest_build_of_a_slug_is_the_one_flown():
    """Every deploy registers another build under the same handle. Benching
    whichever the listing hands back first means verifying a change against
    the build it replaced."""
    tool = _bench()
    backwards = _Listing(list(reversed(TWO_BUILDS)))
    assert tool.deployed(backwards, "learned-hold")["id"] == "stack_new"


def test_a_name_that_is_neither_is_refused_with_what_there_is():
    """A bench row attributed to a controller that never flew is worse than a
    bench that would not run."""
    tool = _bench()
    with pytest.raises(SystemExit) as raised:
        tool.whose(_Listing(TWO_BUILDS), "nobodys-controller")
    said = str(raised.value)
    assert "learned-hold" in said and "pursue" in said


def test_the_run_says_which_build_it_flew():
    """A slug is a handle and a handle is not a build."""
    tool = _bench()
    flying = tool.whose(_Listing(TWO_BUILDS), "learned-hold")
    said = tool.built_or_built_by(flying)
    assert "2026-09-03" in said and "2222" in said
    assert tool.built_or_built_by({"builtIn": "pursue"}) == "built in"
