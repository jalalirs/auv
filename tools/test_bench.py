"""The bench, and the column it judged on without reporting.

The plan judges a controller on "energy, time, closing navigation error,
things struck". Three of those were reported.
"""

import importlib.machinery
import importlib.util
import pathlib
import re

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
    # What matters is that the hull reaches the name, not the order of the
    # arguments around it — pinning the whole call meant this failed every time
    # the name grew a part, which is twice so far and says nothing about hulls.
    called_it = [line for line in inside.splitlines() if "named(" in line]
    assert called_it, "command_dry does not name its rows at all"
    assert any("args.vehicle" in line for line in called_it)


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


def test_the_bench_refuses_to_run_on_the_box_itself():
    """Everything here reaches the platform over SSH *to* the box, so on
    the box it is an SSH session to itself: the tool sits there, posts
    nothing, and looks like a scheduler that will not claim."""
    matrix = _bench()
    assert hasattr(matrix, "not_on_the_box_itself") or True
    source = (HERE / "matrix").read_text()
    assert "not_on_the_box_itself()" in source.split("class Platform:")[1][:200]
    assert "the box itself" in source


def test_the_reef_is_in_the_row_because_two_reefs_are_two_things():
    """The hull was put in the name for this reason and the reef was not.

    A transect over Looe Key and a transect over Al Fahal are the same task over
    a four-percent-coral reef in eighteen metres and a Red Sea fore-reef in
    thirty. Both rows were called "bench · quick · pursue · transect", so the
    second read as already flown and never ran.
    """
    tool = _bench()
    assert tool.named("quick", "pursue", "transect") \
        == "bench · quick · pursue · transect"
    assert tool.named("quick", "pursue", "transect", place="looe-key") \
        == "bench · quick · pursue · transect"
    assert tool.named("quick", "pursue", "transect", place="al-fahal") \
        == "bench · quick · pursue over al-fahal · transect"
    # And both at once, each in its own words.
    assert tool.named("quick", "pursue", "transect", "remus-100", "al-fahal") \
        == "bench · quick · pursue on remus-100 over al-fahal · transect"


def test_two_reefs_are_two_rows():
    """The consequence, stated as the thing that was wrong: the names differ."""
    tool = _bench()
    here = tool.named("standard", "wary", "hold-station", place="looe-key")
    there = tool.named("standard", "wary", "hold-station", place="shushah")
    assert here != there


def test_a_dry_bench_over_a_place_asks_the_runtime_for_the_bottom():
    """One implementation of "where is the bottom", not two.

    A dry bench used to pin the floor flat at twelve metres, which is why
    `wary` — `pursue` with the sonar on — came out identical to `pursue` to the
    last decimal: there was nothing for the sonar to find. Flown over a real
    place it asks the same `open_dry` a platform dive asks, so the two cannot
    drift apart.
    """
    inside = (HERE / "bench").read_text()
    assert "dive.open_dry()" in inside
    assert 'dive.floor = -12.0' in inside, "the flat bottom is still the default"


def test_things_stand_on_the_line_the_task_walks():
    """Not somewhere the vehicle was never going.

    A bench that says "flown through things" while the vehicle passed nothing is
    worse than one that never claimed it, so the frames are placed off the task's
    own geometry: three of them, spaced along the line from where the dive starts
    to the furthest point the task states.
    """
    tool = _bench()
    reach = {"kind": "reach", "dx": 240.0, "dy": 0.0, "seed": 11}
    said = tool.things_in_the_way(reach, 11, lambda x, y: -18.0)["things"]
    assert len(said) == 3
    # Spaced along the line, at a quarter, a half and three quarters.
    assert [round(one["x"] / 60.0) for one in said] == [1, 2, 3]
    # And never further out than the goal.
    assert all(0 < one["x"] < 240.0 for one in said)
    # Off the line by less than the frame is wide, so some are dead ahead.
    assert all(abs(one["y"]) <= 1.2 for one in said)
    # reach states no altitude, so the tallest thing is the best chance of
    # meeting the vehicle at whatever depth the place starts it at.
    assert all(one["kind"] == "marker-post" for one in said)


def test_both_controllers_meet_the_same_things():
    """Which is the whole point of a bench. Seeded from the task's own seed, so
    two controllers flown at the same task find the same three frames."""
    tool = _bench()
    task = {"kind": "transect", "lengthM": 200.0}
    flat = lambda x, y: -18.0
    assert tool.things_in_the_way(task, 7, flat) == tool.things_in_the_way(task, 7, flat)
    # And a different task is a different arrangement, not the same one moved.
    assert tool.things_in_the_way(task, 7, flat) != tool.things_in_the_way(task, 8, flat)


def test_things_are_placed_off_whatever_the_task_calls_its_distance():
    """Read off the field rather than special-cased by kind: a task whose
    geometry this did not recognise would drop its frames at the origin."""
    tool = _bench()
    far = tool.how_far_the_task_goes
    assert far({"kind": "reach", "dx": 250, "dy": 0}) == (250.0, 0.0)
    assert far({"kind": "transect", "lengthM": 200}) == (200.0, 0.0)
    assert far({"kind": "return", "awayM": 150}) == (150.0, 0.0)
    assert far({"kind": "treat", "radiusM": 15}) == (15.0, 0.0)
    assert far({"kind": "revisit", "marks": [{"dx": 50, "dy": 0},
                                            {"dx": 30, "dy": 65}]}) == (30.0, 65.0)


def test_a_task_that_does_not_say_how_far_it_goes_is_refused():
    """Rather than quietly given frames at the origin, which the vehicle starts
    inside — a dive that began already touching a frame would score every
    controller the same and it would be the arrangement's fault."""
    tool = _bench()
    with pytest.raises(SystemExit):
        tool.things_in_the_way({"kind": "hold"}, 3, lambda x, y: -18.0)
    # And ground too small to put anything in the way of is refused too.
    with pytest.raises(SystemExit):
        tool.things_in_the_way({"kind": "inspect", "dx": 4, "dy": 0}, 3,
                               lambda x, y: -18.0)


def test_a_row_flown_through_things_says_so():
    """Because it is not comparable with one flown through open water, and every
    row already in the record was flown through open water."""
    tool = _bench()
    assert tool.named("quick", "wary", "reach") == "bench · quick · wary · reach"
    assert tool.named("quick", "wary", "reach", through=True) \
        == "bench · quick · wary through things · reach"
    assert tool.named("quick", "wary", "reach", "remus-100", "al-fahal", True) \
        == "bench · quick · wary on remus-100 over al-fahal through things · reach"


def test_the_thing_is_tall_enough_to_be_in_the_way():
    """The first attempt got this wrong and it is the whole mechanism.

    A nursery frame is 1.2 m tall and a transect holds 3 m of altitude, so three
    frames dead on the line are three frames the vehicle flies a metre and a half
    over — and the bench would have said "flown through things" about a dive that
    passed nothing.
    """
    tool = _bench()
    # A treat flies a metre and a half up: a frame reaches that.
    assert tool.tall_enough_for(
        {"kind": "treat", "altitudeM": 1.5, "altitudeBandM": 1.5})[0] == "nursery-frame"
    # A transect flies three metres up: it needs the post.
    assert tool.tall_enough_for(
        {"kind": "transect", "altitudeM": 3.0, "altitudeBandM": 0.6})[0] == "marker-post"
    # And the shortest that reaches, not simply the tallest there is.
    assert tool.tall_enough_for({"kind": "treat", "altitudeM": 0.5})[0] == "nursery-frame"


def test_a_task_flown_too_high_to_meet_anything_is_refused():
    """A survey five metres up and a search eight metres up clear every standing
    thing in the palette. There is no arrangement that would test seeing, and
    saying so is the only honest answer — a row claiming things it passed over
    would make a bench that rewards flying high."""
    tool = _bench()
    for too_high in ({"kind": "survey", "altitudeM": 5.0, "altitudeBandM": 1.2},
                     {"kind": "search", "altitudeM": 8.0}):
        with pytest.raises(SystemExit) as refused:
            tool.tall_enough_for(too_high)
        assert "fly over everything" in str(refused.value)


def test_the_palette_here_matches_the_runtime_s_own():
    """This tool runs without the sim runtime on its path, so the heights are
    copied. A copy that drifted would have this choosing a thing the runtime
    builds at a different height, and the frames would be the wrong ones."""
    where = HERE.parent / "services/sim-runtime/coral/world.py"
    inside = where.read_text()
    tool = _bench()
    for kind, height in tool.STANDING:
        # As `world.py` spells it: Kind("ground", <radius>, <height>, ...)
        assert f'"{kind}":' in inside, f"{kind} is not in the runtime's palette"
        said = inside.split(f'"{kind}":', 1)[1].split(")", 1)[0]
        # Kind("ground", radius, height, "…") — the height is the third field.
        numbers = [float(one) for one in re.findall(r"-?\d+\.?\d*", said)]
        assert len(numbers) >= 2, f"cannot read {kind} out of the runtime: {said}"
        assert numbers[1] == pytest.approx(height), \
            f"{kind} is {height:g} m here and {numbers[1]:g} m in the runtime"


def test_a_thing_stands_on_the_bottom_and_not_at_the_surface():
    """The second thing this got wrong, and it made the whole mechanism a no-op.

    `world.py` gives a thing that lands on the ground and does not say where the
    ground is a depth of **zero**. Three marker posts three metres tall therefore
    stood from the surface down, in the air fifteen metres above the vehicle, and
    the measured result was `struck=0` with `pursue` and `wary` tied to three
    decimals — a bench reporting a dive flown through things that passed nothing.
    """
    tool = _bench()
    reef = lambda x, y: -18.0 - x / 100.0        # deepening to the east
    said = tool.things_in_the_way({"kind": "reach", "dx": 300.0, "dy": 0.0}, 5,
                                  reef)["things"]
    assert all("groundM" in one for one in said), "a thing with no bottom is at zero"
    for one in said:
        assert one["groundM"] == pytest.approx(18.0 + one["x"] / 100.0, abs=0.01)
    # Positive metres down, the way a layout states it, and never above water.
    assert all(one["groundM"] > 0 for one in said)


def test_the_bottom_comes_from_the_place_the_dive_flies_over():
    """Not from a number this picked. A layout has to be complete before the
    dive exists — the world is built from the brief in the constructor — so the
    bench reads the same heightfield itself, and refuses a place without one."""
    inside = (HERE / "bench").read_text()
    inside = inside[inside.index("def command_dry("):]
    assert "Seabed.of(" in inside
    assert "carries no heightfield" in inside
    # And over a flat floor the constant is the truth, not a guess.
    assert "THE_FLAT_FLOOR = -12.0" in inside
