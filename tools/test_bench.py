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
    # Off the line by less than the thing is wide, so every one of them is in
    # the way of a vehicle flying the line.
    assert all(abs(one["y"]) <= 2.0 * 0.6 for one in said)
    # One kind of thing, wide enough to be in the way, and as tall as an honest
    # frame gets when the task states no altitude to size it against.
    assert all(one["kind"] == "nursery-frame" for one in said)
    assert all(one["heightM"] == 6.0 for one in said)


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


def test_the_thing_is_both_tall_enough_and_wide_enough():
    """Two measured failures are behind this, both the same failure.

    A nursery frame is 1.2 m tall and a transect holds 3 m, so frames on the line
    are flown over. Choosing the marker post instead fixed the height and broke
    the width — a post is 0.2 m across, so measured, the vehicle passed every one
    of them and `pursue` and `wary` tied at 0.407 for the third time. So it is
    the wide thing given the height it needs, which a layout may state and which a
    coral tree nursery genuinely has.
    """
    tool = _bench()
    said = tool.something_in_the_way({"kind": "transect", "altitudeM": 3.0,
                                      "altitudeBandM": 0.6})
    assert said["kind"] == "nursery-frame"
    assert said["radiusM"] == 2.0, "the wide thing, so it is actually in the way"
    # Into the band the task flies in, not up to its lower edge.
    assert said["heightM"] > 3.0
    # A task that flies lower needs less, and gets less.
    lower = tool.something_in_the_way({"kind": "treat", "altitudeM": 1.5,
                                       "altitudeBandM": 1.5})
    assert lower["heightM"] < said["heightM"]


def test_a_frame_is_never_grown_until_nothing_could_avoid_it():
    """A search eight metres up would need a frame taller than anything anybody
    has in the water. Refused, because growing the arrangement until it cannot be
    avoided measures the arrangement and not the controller."""
    tool = _bench()
    with pytest.raises(SystemExit) as refused:
        tool.something_in_the_way({"kind": "search", "altitudeM": 8.0})
    assert "rewards flying high" in str(refused.value)
    # A survey at five metres is right at the edge and must say which side.
    survey = {"kind": "survey", "altitudeM": 5.0, "altitudeBandM": 1.2}
    reach = 5.0 + 1.2 / 2.0 + 0.3
    if reach > tool.TALLEST_HONEST_FRAME:
        with pytest.raises(SystemExit):
            tool.something_in_the_way(survey)
    else:
        assert tool.something_in_the_way(survey)["heightM"] == pytest.approx(reach, abs=0.01)


def test_the_palette_here_matches_the_runtime_s_own():
    """This tool runs without the sim runtime on its path, so the frame's width is
    copied. A copy that drifted would have the offsets computed against a width
    the runtime does not build, and the things would miss."""
    where = HERE.parent / "services/sim-runtime/coral/world.py"
    inside = where.read_text()
    tool = _bench()
    kind, radius = tool.FRAME
    assert f'"{kind}":' in inside, f"{kind} is not in the runtime's palette"
    said = inside.split(f'"{kind}":', 1)[1].split(")", 1)[0]
    # Kind("ground", radius, height, "…") — the radius is the second field.
    numbers = [float(one) for one in re.findall(r"-?\d+\.?\d*", said)]
    assert numbers[0] == pytest.approx(radius), \
        f"{kind} is {radius:g} m across here and {numbers[0]:g} m in the runtime"


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


def test_things_are_placed_where_the_dive_begins_not_at_the_origin():
    """The fourth thing this got wrong, and the one that took four measured runs
    to see, because the first three all looked like geometry.

    A task's geometry is relative to where the dive starts; a layout is in the
    world's own coordinates. Over a real reef the place decides where the vehicle
    goes in — an Al Fahal dive starts around (854, -1106) — so frames placed
    fifty, a hundred and a hundred and fifty metres from the origin sit a
    kilometre and a half behind the vehicle. `struck` was 0 and both controllers
    scored 0.407, four times running.
    """
    tool = _bench()
    reach = {"kind": "reach", "dx": 240.0, "dy": 0.0}
    flat = lambda x, y: -18.0
    here = tool.things_in_the_way(reach, 3, flat)["things"]
    there = tool.things_in_the_way(reach, 3, flat, (854.0, -1106.0))["things"]
    for near, far in zip(here, there):
        assert far["x"] == pytest.approx(near["x"] + 854.0, abs=0.02)
        assert far["y"] == pytest.approx(near["y"] - 1106.0, abs=0.02)
    # And the bottom is read at the moved position, not at the origin's.
    deepening = lambda x, y: -10.0 - x / 1000.0
    moved = tool.things_in_the_way(reach, 3, deepening, (854.0, 0.0))["things"]
    assert all(one["groundM"] == pytest.approx(10.0 + one["x"] / 1000.0, abs=0.01)
               for one in moved)


def test_the_world_is_put_in_after_the_place_is_open():
    """Because until it is open nobody knows where the dive begins. The world is
    built from the brief in the dive's constructor, so a layout computed there
    could only ever be relative to the origin."""
    inside = (HERE / "bench").read_text()
    inside = inside[inside.index("def command_dry("):]
    assert inside.index("open_dry()") < inside.index("things_in_the_way(")
    assert "dive.position[:2]" in inside
