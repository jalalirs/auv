"""A dive nobody is watching.

The renderer was costing the physics a hundred-fold. Measured on the box, the
same dive steps 3,911 times a second with no renderer and 33 with one — 0.256
milliseconds a step against something upwards of half a second a frame — and
nothing a step does asks the stage a question: the fourteen calls a step makes
are numpy, and both the multibeam and the imaging sonar march their rays
against the place's heightfield rather than against its triangles.

So a dive can be opened without being drawn. What the stage was being asked for
was how big the place is, and the place already says, in the same description
its heightfield comes from.
"""

import json
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from hydrodynamics import Allocator, Body, Hydrodynamics
from runner import Dive

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"


def a_place(tmp_path, across=1000.0, deep=-30.0, shallow=-4.0, rows=8, columns=8):
    """A place that describes itself, the way a packaged place does."""
    heights = np.linspace(deep, shallow, rows * columns).astype("<f4")
    (tmp_path / "seabed.f32").write_bytes(heights.tobytes())
    (tmp_path / "site.json").write_text(json.dumps({
        "from": {"acrossMetres": across},
        "mesh": {"heightfield": {"rows": rows, "columns": columns,
                                 "file": "seabed.f32"}},
    }))
    return tmp_path


def a_dive(city, **brief):
    model = Hydrodynamics.from_package(PACKAGE)
    said = {"durationSeconds": 60, "cityPath": str(city)}
    said.update(brief)
    return Dive(said, Body(model), Allocator(model), city / "site.usda",
                lambda kind, **detail: None)


def test_the_place_says_how_far_across_it_is(tmp_path):
    """Not the bounding box of its geometry: the number its author wrote."""
    city = a_place(tmp_path, across=2400.0)
    corner, far, extent = a_dive(city).the_place_describes_itself(city)
    assert extent[0] == extent[1] == 2400.0
    assert corner[0] == -1200.0 and far[0] == 1200.0


def test_the_bottom_comes_from_the_heightfield_and_the_top_from_the_surface(tmp_path):
    """A vehicle at the surface is inside the place. The shallowest rock is
    not the top of the water, and a dive that thought so would report every
    vehicle that came up to breathe as having left the site."""
    city = a_place(tmp_path, deep=-41.0, shallow=-6.0)
    corner, far, extent = a_dive(city).the_place_describes_itself(city)
    assert corner[2] == pytest.approx(-41.0, abs=0.01)
    assert far[2] == 0.0
    assert extent[2] == pytest.approx(41.0, abs=0.01)


def test_a_place_above_the_water_keeps_its_own_top(tmp_path):
    """An island in the site is higher than the surface, and the place is that
    tall. Only the water is a floor under the top, not a ceiling over it."""
    city = a_place(tmp_path, deep=-30.0, shallow=12.0)
    _, far, _ = a_dive(city).the_place_describes_itself(city)
    assert far[2] == pytest.approx(12.0, abs=0.01)


def test_a_place_that_does_not_describe_itself_is_not_flown(tmp_path):
    """Refused rather than guessed. A dive over a place of unknown size would
    spawn the vehicle somewhere arbitrary and score it against nothing."""
    said = []
    model = Hydrodynamics.from_package(PACKAGE)
    dive = Dive({"durationSeconds": 60, "cityPath": str(tmp_path)},
                Body(model), Allocator(model), tmp_path / "site.usda",
                lambda kind, **detail: said.append((kind, detail)))
    assert dive.open_dry() is False
    assert any(kind == "failed" for kind, _ in said)


def test_opening_dry_finds_the_bottom_under_the_vehicle(tmp_path):
    """The whole point of the heightfield: the bottom here, not the deepest
    point in the place. Without it a vehicle holding two metres of altitude
    over a reef with relief flies two metres over the sand between the heads."""
    city = a_place(tmp_path, across=1000.0, deep=-30.0, shallow=-4.0, rows=64, columns=64)
    dive = a_dive(city, initialState={"positionM": [0, 0, -10]})
    assert dive.open_dry() is True
    assert dive.seabed is not None
    here = dive.seabed.under(0.0, 0.0)
    corner = dive.bounds[0]
    assert corner[2] <= here <= 0.0
    # And it is not simply the deepest point.
    assert here > dive.seabed.under(-490.0, -490.0)


def test_a_dry_dive_steps_and_arrives(tmp_path):
    """It is a dive, not a description of one: it flies, and it finishes."""
    city = a_place(tmp_path, across=1000.0, rows=32, columns=32)
    dive = a_dive(city, durationSeconds=20,
                  initialState={"positionM": [0, 0, -12]})
    assert dive.open_dry() is True
    while not dive.done:
        dive.step()
    assert dive.simulated == pytest.approx(20.0, abs=1.0)
    assert dive.steps > 0


def test_nothing_a_step_does_asks_the_stage(tmp_path):
    """The claim the dry path rests on, held against the code: a step that
    reached for the stage would raise here rather than pass silently and cost a
    hundredfold in the app."""
    city = a_place(tmp_path, rows=16, columns=16)
    dive = a_dive(city, durationSeconds=5, initialState={"positionM": [0, 0, -9]})
    assert dive.open_dry() is True
    assert dive.stage is None
    for _ in range(200):
        dive.step()


def test_asking_whether_a_picture_is_owed_does_not_spend_it(tmp_path):
    """`due` answers and marks in one move, which is right for the caller about
    to take the picture and wrong for anybody who only wants to know. The
    headless runner asks in order to decide whether to render, and a render is
    not a capture: if asking spent the frame, a recording would come out one
    frame short at every render for the rest of the dive.
    """
    from recording import Recorder

    keeping = Recorder(tmp_path, frames_hz=4.0)
    assert keeping.owes_a_picture(1.0) is True
    # Asked twice, still owed: nothing has been taken.
    assert keeping.owes_a_picture(1.0) is True
    assert keeping.due(1.0) is True
    # And now it is not owed, because it has been marked taken.
    assert keeping.owes_a_picture(1.0) is False
    assert keeping.due(1.0) is False
    assert keeping.owes_a_picture(1.25) is True


def test_nothing_in_the_runner_paces_a_thinking_controller():
    """Because the runtime already charges thinking, in the dive's own clock.

    `Thinking._deliver` holds a thought until `simulated >= asked_at + took`, so a
    decision that took a second and a half in reality costs a second and a half of
    the dive at any rate — "otherwise the same controller on a quicker computer
    would appear to think for free, and every benchmark would be measuring the
    machine", in its own words.

    A guard was added to these runners on 27 September 2026 believing that charge
    was missing. It was not, and the coarse version of it moved `ponder`'s quick
    suite from 48.8% to **23.3%** — a twenty-five point change to a result that was
    already right. Three runs of one brief agree to every printed digit, so what
    failed the determinism this module promises was the fix and not the promise.
    """
    said = (pathlib.Path(__file__).resolve().parent / "dive.py").read_text()
    for which in ("def fly_dry(", "def fly("):
        inside = said[said.index(which):]
        inside = inside[:inside.index("\ndef ")] if "\ndef " in inside else inside
        assert "deliberating()" not in inside
        assert "thinking_now()" not in inside
    # And the reason is written where somebody would otherwise add it back.
    assert "_deliver" in said


def test_the_runtime_charges_a_thought_in_the_dives_own_clock():
    """The mechanism the runners rely on, held so it cannot quietly go away: the
    comparison is against simulated time, not against the wall clock."""
    where = (pathlib.Path(__file__).resolve().parent
             / "controllers/thinking.py").read_text()
    inside = where[where.index("def _deliver("):]
    inside = inside[:inside.index("\n    def ")]
    assert "now < asked_at + took" in inside, (
        "a thought is no longer held against the dive's clock, so a faster machine "
        "now thinks for free")


def test_the_two_runners_agree_about_what_paces_a_dive():
    """A dive somebody watches and a dive nobody watches must be paced by the same
    two things — a controller in another container, and a controller that thinks —
    or the same brief gives two different answers depending on who is looking."""
    source = (pathlib.Path(__file__).resolve().parent / "dive.py").read_text()
    for which in ("def fly_dry(", "def fly("):
        inside = source[source.index(which):]
        inside = inside[:inside.index("\ndef ")] if "\ndef " in inside else inside
        assert "dive.bridge.commanded" in inside, f"{which} ignores an external controller"


def test_the_slow_loop_can_say_whether_a_thought_is_outstanding():
    """Not used to pace anything — the runtime charges thinking in the dive's own
    clock and needs no help — but it is what `said()` reports as `thinking`, and
    one expression in one place is better than the same one written twice."""
    import threading
    import time as wallclock

    from controllers.thinking import Thinking

    class Instant:
        name = "instant"
        thinks_every = 20.0

        def think(self, seen):
            return None

    slow = Thinking(Instant())
    assert slow.busy() is False, "nothing has been asked yet"
    # A thread that is actually running counts; one that has finished does not.
    held = threading.Event()
    slow._thread = threading.Thread(target=held.wait, daemon=True)
    slow._thread.start()
    assert slow.busy() is True
    held.set()
    slow._thread.join(timeout=2.0)
    assert slow.busy() is False
    # And what it reports is the same answer, not a second implementation of it.
    assert slow.said()["thinking"] is False


def test_a_dive_fits_every_instrument_unless_told_otherwise(tmp_path):
    """The platform names no list, so nothing it flies loses an instrument."""
    city = a_place(tmp_path)
    dive = a_dive(city, initialState={"positionM": [0, 0, -10]})
    assert dive.fits("imaging_sonar") is True
    assert dive.fits("multibeam") is True
    assert dive.fits("anything at all") is True


def test_a_dive_told_a_shorter_list_fits_only_that(tmp_path):
    """What the list is for: a forward-looking sonar costs about four times the rest
    of a step to ray-march, and a trainer flying three thousand rollouts of a
    station hold pays that for a fan nobody looks at.

    The distinction, because it is easy to get backwards: this is for instruments
    that only **report**. Anything that changes what the vehicle *does* — the
    tether, which drags — is never on this list, because a dive missing one of those
    is easier than the thing it stands in for. That mistake is exactly what made the
    SDK's tank flatter every controller tuned in it.
    """
    city = a_place(tmp_path)
    dive = a_dive(city, initialState={"positionM": [0, 0, -10]},
                  fitSensors=["dvl"])
    assert dive.fits("dvl") is True
    assert dive.fits("imaging_sonar") is False
    assert dive.fits("multibeam") is False
    # An empty list is a list, not an absence: it means fit nothing.
    bare = a_dive(city, initialState={"positionM": [0, 0, -10]}, fitSensors=[])
    assert bare.fits("dvl") is False


def test_the_gate_is_asked_before_an_instrument_is_built(tmp_path):
    """Or it costs what it costs and is then thrown away."""
    said = (pathlib.Path(__file__).resolve().parent / "runner.py").read_text()
    for which, kind in (("def switch_on_the_sonar", "imaging_sonar"),
                        ("def switch_on_the_multibeam", "multibeam")):
        inside = said[said.index(which):]
        inside = inside[:inside.index("\n    def ", 10)]
        assert f'self.fits("{kind}")' in inside, f"{which} does not ask"
        # Before the instrument is constructed.
        assert inside.index("self.fits(") < inside.index("(said, seed=")
