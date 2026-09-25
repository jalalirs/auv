"""What a dive hit, which is the column the benchmark was missing.

The plan judges a controller on "energy, time, closing navigation error,
things struck". The first three were reported and the fourth was not: `struck`
events went into the log and nothing gathered them. That is the whole
difference between `wary`, which arrives five metres short and hits nothing,
and `pursue`, which arrives exactly and ploughs through three nursery frames —
and it was the one number nobody could see.
"""

import numpy as np
import pytest


class _Thing:
    def __init__(self, name, kind="frame"):
        self.id = name
        self.kind = kind
        self.spec = type("Spec", (), {"what": kind})()


def _a_dive():
    """A Dive with only the bookkeeping this touches, built by hand.

    Constructing a real one wants a vehicle package, a stage and a seabed;
    what is under test is counting, and counting does not need any of them.
    """
    import runner

    dive = object.__new__(runner.Dive)
    dive._struck = set()
    dive._grounded = 0
    dive.against_the_ground = False
    return dive


def test_a_dive_that_hit_nothing_says_so_rather_than_saying_nothing():
    """A column that is absent when a controller hit nothing and present when
    it did cannot be compared down its length."""
    said = _a_dive().what_it_hit()
    assert said == {"things": 0, "which": [], "ground": 0}


def test_each_thing_is_counted_once_however_long_it_was_held_against():
    """A vehicle held against a frame for four seconds struck it once. Four
    hundred events saying so is a record nobody can read."""
    dive = _a_dive()
    for _ in range(400):
        struck = _Thing("nursery-frame-854--1099")
        if struck.id not in dive._struck:
            dive._struck.add(struck.id)
    assert dive.what_it_hit()["things"] == 1

    dive._struck.add("mooring-block-909--1107")
    said = dive.what_it_hit()
    assert said["things"] == 2
    assert said["which"] == ["mooring-block-909--1107", "nursery-frame-854--1099"]


def test_the_seabed_is_counted_apart_from_what_somebody_put_there():
    """They are different mistakes. A vehicle that clips a nursery frame has
    hit something somebody put there; one that flies into a spur has hit the
    place."""
    dive = _a_dive()
    dive._struck.add("nursery-frame-1")
    dive._grounded = 3
    said = dive.what_it_hit()
    assert said["things"] == 1
    assert said["ground"] == 3
    assert "ground" in said and "things" in said


def test_a_run_reports_it_whether_or_not_there_was_a_layout():
    """`world` is only in the outcome when the dive had one. `hit` is always,
    because "nothing was struck" is an answer and a missing key is not."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent / "runner.py").read_text()
    settled = source[source.index('self.say("settled",'):]
    settled = settled[:settled.index("if self.bridge is not None:")]
    assert "hit=self.what_it_hit()," in settled
    # And it is not behind a conditional, the way `world` is.
    for line in settled.splitlines():
        if "what_it_hit" in line:
            assert "if " not in line, line
