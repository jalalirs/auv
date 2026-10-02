"""The engine on its own: order from declarations, ownership, rates, the clock.

No vehicle and no water. What is under test is that the tick does what the
declarations say, because every coupled system after this trusts it to.
"""

import pytest

from engine import Clock, Engine, System, World, order
from engine.engine import Tick


class Log(System):
    """A system that writes down that it ran, and what it saw."""

    def __init__(self, name, reads=(), before=(), writes=(), every=None, seen=None):
        self.name, self.reads, self.before, self.writes, self.every = name, tuple(reads), tuple(before), tuple(writes), every
        self.seen = [] if seen is None else seen

    def step(self, world):
        self.seen.append((self.name, world.clock.simulated))
        for part in self.writes:
            world[part].append(self.name)


def a_world(*parts, owners=None):
    world = World()
    world.put("clock", Clock(0.1), owner="clock")
    for part in parts:
        world.put(part, [], owner=(owners or {}).get(part))
    return world


def test_a_reader_runs_after_what_it_reads():
    a, b = Log("a", writes=["x"]), Log("b", reads=["x"])
    assert [s.name for s in order([b, a])] == ["a", "b"]


def test_reading_the_start_of_the_tick_runs_before_the_writer():
    """The controller commands on where the vehicle was; so it goes first."""
    vehicle = Log("vehicle", reads=["commands"], writes=["pose"])
    helm = Log("helm", before=["pose"], writes=["commands"])
    assert [s.name for s in order([vehicle, helm])] == ["helm", "vehicle"]


def test_a_loop_nobody_breaks_is_an_error_that_names_it():
    a, b = Log("a", reads=["y"], writes=["x"]), Log("b", reads=["x"], writes=["y"])
    with pytest.raises(ValueError, match="each wait on another"):
        order([a, b])


def test_where_the_declarations_leave_it_open_the_listing_decides():
    a, b, c = Log("a"), Log("b"), Log("c")
    assert [s.name for s in order([c, a, b])] == ["c", "a", "b"]


def test_nobody_writes_what_is_not_theirs():
    world = a_world("x", owners={"x": "a"})
    with pytest.raises(ValueError, match="belongs to"):
        Engine(world, [Log("b", writes=["x"]), Tick()])


def test_nobody_reads_what_is_not_there():
    world = a_world()
    with pytest.raises(ValueError, match="does not have"):
        Engine(world, [Log("a", reads=["ghost"]), Tick()])


def test_the_clock_moves_between_what_acts_and_what_judges():
    """Sensing at the start of the tick, judging at the end of it."""
    world = a_world("pose", owners={"pose": "vehicle"})
    seen = []
    sense = Log("sense", before=["pose", "clock"], seen=seen)
    vehicle = Log("vehicle", before=["clock"], writes=["pose"], seen=seen)
    judge = Log("judge", reads=["pose", "clock"], seen=seen)
    engine = Engine(world, [judge, vehicle, sense, Tick(after=("pose",))])
    engine.tick()
    assert [n for n, _ in seen] == ["sense", "vehicle", "judge"]
    assert [round(t, 9) for _, t in seen] == [0.0, 0.0, 0.1]


def test_a_rate_is_kept_without_drift():
    world = a_world()
    seen = []
    slow = Log("slow", every=0.5, seen=seen)
    engine = Engine(world, [slow, Tick()])
    for _ in range(100):                       # ten seconds at 0.1 s
        engine.tick()
    assert len(seen) == 20
    assert [round(t, 6) for _, t in seen[:3]] == [0.0, 0.5, 1.0]


def test_the_order_can_be_read():
    world = a_world("x", owners={"x": "a"})
    engine = Engine(world, [Log("b", reads=["x"]), Log("a", writes=["x"]), Tick()])
    said = engine.order()
    assert said.index(" a ") < said.index(" b ")
    assert "writes x" in said


def test_what_each_system_cost_is_kept():
    world = a_world()
    engine = Engine(world, [Log("a"), Tick()])
    engine.tick()
    assert set(engine.costs()) == {"a", "clock"}
