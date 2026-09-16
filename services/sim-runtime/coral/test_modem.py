"""The thin pipe, and what it refuses.

A controller that phoned home got its answer instantly and losslessly, which is
the one arrangement that cannot happen underwater — and a benchmark run that
way rewards exactly the controller that would fail at sea.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from modem import SOUND_MS, Modem  # noqa: E402


def test_sound_takes_time_to_cross_water():
    """A kilometre is two thirds of a second, each way."""
    m = Modem({"bitsPerSecond": 100000.0})
    assert abs(m.carries(10, 1500.0) - 1.0) < 0.01


def test_a_big_message_takes_longer_than_a_small_one():
    """Two kilobits a second is a sentence, not a picture.

    This is the constraint: a controller may ask a question and it may not send
    a camera frame, and the difference is the whole design of the autonomy.
    """
    m = Modem({"bitsPerSecond": 2000.0})
    short = m.carries(64, 100.0)
    frame = m.carries(200_000, 100.0)
    assert short < 1.0
    assert frame > 600.0, f"a frame should be out of the question: {frame:.0f} s"


def test_the_channel_holds_one_thing_at_a_time():
    """Half duplex, and refused rather than queued.

    A modem that accepted everything and delivered it later would let a
    controller talk as much as it liked, which is the assumption this exists
    to break.
    """
    m = Modem({"bitsPerSecond": 2000.0, "lossShare": 0.0})
    assert m.send(0.0, 64, 100.0) is not None
    assert m.send(0.01, 64, 100.0) is None, "the channel was busy"


def test_messages_are_lost_and_more_so_further_away():
    """Sound spreads and absorbs, and past the rated range nothing gets through."""
    m = Modem({"rangeM": 2000.0, "lossShare": 0.08})
    assert m.loss_at(0.0) == 0.0
    assert m.loss_at(1000.0) > m.loss_at(300.0)
    assert m.loss_at(2500.0) == 1.0


def test_over_the_horizon_nothing_arrives():
    m = Modem({"rangeM": 1000.0})
    assert m.send(0.0, 64, 4000.0) is None
    assert m.lost == 1


def test_what_arrives_arrives_when_it_arrives():
    """And not before. A controller reading its answer on the step it asked the
    question is a controller nobody can deploy."""
    m = Modem({"bitsPerSecond": 2000.0, "lossShare": 0.0})
    lands = m.send(0.0, 64, 750.0, payload="turn left")
    assert lands is not None and lands > 0.5
    assert m.arrived(lands - 0.01) == []
    assert m.arrived(lands) == ["turn left"]


def test_the_same_seed_loses_the_same_messages():
    a = Modem({"lossShare": 0.5}, seed=7)
    b = Modem({"lossShare": 0.5}, seed=7)
    for step in range(40):
        one = a.send(step * 10.0, 64, 900.0)
        two = b.send(step * 10.0, 64, 900.0)
        assert (one is None) == (two is None)
    assert a.lost > 0, "half a share of loss should lose something"
