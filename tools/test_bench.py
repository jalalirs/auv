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


# ── failures are rows, and whose they are matters ────────────────────────────

def test_a_bench_that_hides_failures_flatters():
    """A controller whose every dive fell over had no rows at all, and the
    bench said "nothing on the bench yet"."""
    tool = _bench()
    row = tool.failed_row({"id": "d1", "name": "bench · quick · pursue · reach"},
                          ["bench", "quick", "pursue", "reach"],
                          {"id": "r1", "failureReason":
                           "the controller started and then stopped, so nothing flew this dive: boom"})
    assert row["ended"] == "failed" and row["score"] == 0.0
    assert row["fault"] == "theirs"
    assert "boom" in row["why"]


def test_a_dive_the_platform_could_not_start_is_not_the_controllers_fault():
    tool = _bench()
    assert tool.whose_fault("the simulator could not be started: no such image") \
        == "the platform's"
    assert tool.whose_fault("this dive was defined with a controller and it would not "
                            "start, so nothing could fly it: no such image") == "theirs"


def test_an_unknown_reason_is_not_pinned_on_somebody_s_controller():
    """Attributing a failure to a controller on a guess is the one direction
    that must not be guessed."""
    tool = _bench()
    assert tool.whose_fault("") == "the platform's"
    assert tool.whose_fault("something nobody has seen before") == "the platform's"


def test_a_dive_that_never_flew_is_not_averaged_as_a_zero():
    tool = _bench()
    rows = [{"score": 0.8, "energyWh": 4.0, "driftM": 1.0, "seconds": 100.0,
             "thoughts": 0, "slowestThoughtS": 0.0, "ended": "achieved"},
            {"score": 0.0, "energyWh": 0.0, "driftM": 0.0, "seconds": 0.0,
             "thoughts": 0, "slowestThoughtS": 0.0, "ended": "failed",
             "fault": "the platform's"}]
    said = tool.summarise(rows)
    assert said["dives"] == 1
    assert said["score"] == pytest.approx(0.8)


def test_a_controllers_own_failure_is_averaged_as_the_zero_it_is():
    tool = _bench()
    rows = [{"score": 0.8, "energyWh": 4.0, "driftM": 1.0, "seconds": 100.0,
             "thoughts": 0, "slowestThoughtS": 0.0, "ended": "achieved"},
            {"score": 0.0, "energyWh": 0.0, "driftM": 0.0, "seconds": 0.0,
             "thoughts": 0, "slowestThoughtS": 0.0, "ended": "failed",
             "fault": "theirs"}]
    assert tool.summarise(rows)["score"] == pytest.approx(0.4)


def test_a_comparison_leaves_out_dives_that_never_happened(capsys):
    """A comparison against a dive the platform could not start is not a
    comparison."""
    tool = _bench()

    class _Args:
        suite = "quick"
        left = "pursue"
        right = "ponder"
        here = True

    rows = [
        {"task": "reach", "controller": "pursue", "score": 0.8, "energyWh": 3.0,
         "driftM": 1.0, "seconds": 90.0, "thoughts": 0, "slowestThoughtS": 0.0,
         "struck": 0, "grounded": 0, "ended": "achieved"},
        {"task": "reach", "controller": "ponder", "score": 0.6, "energyWh": 4.0,
         "driftM": 1.0, "seconds": 95.0, "thoughts": 2, "slowestThoughtS": 0.4,
         "struck": 0, "grounded": 0, "ended": "achieved"},
        {"task": "dock", "controller": "pursue", "score": 0.0, "energyWh": 0.0,
         "driftM": 0.0, "seconds": 0.0, "thoughts": 0, "slowestThoughtS": 0.0,
         "struck": 0, "grounded": 0, "ended": "failed", "fault": "the platform's"},
    ]
    tool.rows_for = lambda args: rows
    assert tool.command_compare(_Args()) == 0
    said = capsys.readouterr().out
    assert "1 tasks" in said, said
    assert "never flew" in said and "dock" in said


def test_a_row_names_the_hull_when_it_is_not_the_usual_one():
    """Fly pursue on a BlueROV2 and then on a Heavy and both rows were
    called the same thing. A Heavy has eight thrusters and half again the
    surge; that is not the same controller doing better."""
    tool = _bench()
    assert tool.named("quick", "pursue", "reach") == "bench · quick · pursue · reach"
    assert tool.named("quick", "pursue", "reach", "bluerov2") \
        == "bench · quick · pursue · reach"
    assert tool.named("quick", "pursue", "reach", "bluerov2-heavy") \
        == "bench · quick · pursue on bluerov2-heavy · reach"


def test_a_named_hull_still_parses_as_four_parts():
    """Every row already in the record has to keep reading as it did."""
    tool = _bench()
    name = tool.named("quick", "pursue", "reach", "remus-100")
    parts = [p.strip() for p in name.split("·")]
    assert len(parts) == 4
    assert parts[2] == "pursue on remus-100"


def test_a_dry_row_names_its_hull_too():
    """A dry row that did not name the hull would collide with a flown one
    exactly as the flown ones collided with each other."""
    tool = _bench()
    source = (HERE / "bench").read_text()
    inside = source[source.index("def command_dry("):]
    assert 'named(args.suite, called, task, args.vehicle)' in inside


def test_the_overall_row_lines_up_with_the_columns_above_it(capsys):
    """It read "-5.36 Wh0/0": the hit column was left-aligned after the
    energy and the two ran together."""
    tool = _bench()

    class _Args:
        suite = "quick"
        left = "a"
        right = "b"
        here = True

    rows = [{"task": t, "controller": c, "score": s, "energyWh": e, "driftM": 1.0,
             "seconds": 90.0, "thoughts": 0, "slowestThoughtS": 0.0,
             "struck": 0, "grounded": 0, "ended": "achieved"}
            for t, c, s, e in (("reach", "a", 0.2, 14.0), ("reach", "b", 0.5, 8.0))]
    tool.rows_for = lambda args: rows
    tool.command_compare(_Args())
    overall = [line for line in capsys.readouterr().out.splitlines()
               if "overall" in line][0]
    assert "Wh0/0" not in overall
    assert " Wh" in overall and "0/0" in overall


def test_two_long_names_do_not_run_together_in_the_header(capsys):
    """Two controllers with twelve-character names read as one word:
    "station-holdlearned-hold"."""
    tool = _bench()

    class _Args:
        suite = "quick"
        left = "station-hold"
        right = "learned-hold"
        here = True

    rows = [{"task": "reach", "controller": c, "score": 0.0, "energyWh": e,
             "driftM": 1.0, "seconds": 90.0, "thoughts": 0, "slowestThoughtS": 0.0,
             "struck": 0, "grounded": 0, "ended": "time"}
            for c, e in (("station-hold", 9.5), ("learned-hold", 36.25))]
    tool.rows_for = lambda args: rows
    tool.command_compare(_Args())
    header = [line for line in capsys.readouterr().out.splitlines()
              if "energy" in line][0]
    assert "station-holdlearned" not in header
    assert "…" in header
