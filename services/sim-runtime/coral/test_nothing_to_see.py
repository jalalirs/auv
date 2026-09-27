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


def test_a_thought_is_charged_what_it_costs_and_nothing_else_is():
    """Two ways to get this wrong, and the second is the one I shipped first.

    Too little: a dive running six times faster than the clock hands a thought a
    sixth of the real seconds it takes, which makes the **machine** look fast
    rather than the controller, and a bench that rewarded whoever ran on the
    slower box would be measuring the box.

    Too much: pacing the whole dive whenever a controller *can* think slowly.
    `ponder`'s `thinkS` — how long a decision takes, standing in for a model call
    — **defaults to zero**, so most deliberating dives were charged a second per
    second for thinking that cost nothing, and a bench row went from three minutes
    to twenty for no reason.

    The rule is the outstanding thought and only that.
    """
    from controllers.helm import Helm  # noqa: F401  (imported for the surface)
    from controllers.thinking import Thinking  # noqa: F401

    said = (pathlib.Path(__file__).resolve().parent / "dive.py").read_text()
    for which in ("def fly_dry(", "def fly("):
        inside = said[said.index(which):]
        inside = inside[:inside.index("\ndef ")] if "\ndef " in inside else inside
        assert "thinking(dive)" in inside, f"{which} does not ask whether a thought is out"
        assert "deliberating()" not in inside, (
            f"{which} still paces on whether a controller *can* think, which "
            "over-charges every instant decision")


def test_the_two_runners_agree_about_what_paces_a_dive():
    """A dive somebody watches and a dive nobody watches must be paced by the same
    two things — a controller in another container, and a controller that thinks —
    or the same brief gives two different answers depending on who is looking."""
    source = (pathlib.Path(__file__).resolve().parent / "dive.py").read_text()
    for which in ("def fly_dry(", "def fly("):
        inside = source[source.index(which):]
        inside = inside[:inside.index("\ndef ")] if "\ndef " in inside else inside
        assert "dive.bridge.commanded" in inside, f"{which} ignores an external controller"
        assert "thinking(dive)" in inside, f"{which} would charge thinking at the wrong rate"


def test_an_outstanding_thought_is_what_is_asked_about_not_a_capability():
    """`deliberating` answers whether a controller *can* think slowly;
    `thinking_now` answers whether one is thinking at this instant. The dive needs
    the second, and asking the first is how a controller with instant decisions
    came to be charged a second per second."""
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
