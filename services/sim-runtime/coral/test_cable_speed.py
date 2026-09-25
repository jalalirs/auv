"""The cable relaxation, which was most of the dry benchmark.

`tools/bench dry` calls itself "the difference between benchmarking as a
ritual and as a habit". Seventy-eight per cent of it was `cable.relax`, in
964,002 calls to `np.linalg.norm` on three-element vectors — where numpy costs
more to dispatch than the arithmetic costs to do.
"""

import time

import numpy as np
import pytest

import cable


def _the_old_way(shape, segment, ends=(True, True), sweeps=None):
    """The implementation this replaced, kept to compare against.

    Not a reimplementation from the description: this is the code that was
    there, so "the same arithmetic" is a claim the test can actually check.
    """
    last = len(shape) - 1
    if sweeps is None:
        sweeps = max(2, last // 4)
    for _ in range(sweeps):
        for i in range(last):
            first = 0.0 if (i == 0 and ends[0]) else 0.5
            second = 0.0 if (i + 1 == last and ends[1]) else 0.5
            share = first + second
            if share <= 0.0:
                continue
            a, b = shape[i], shape[i + 1]
            apart = b - a
            length = float(np.linalg.norm(apart))
            if length < 1e-9:
                continue
            correct = (length - segment) / length * apart
            shape[i] = a + correct * (first / share)
            shape[i + 1] = b - correct * (second / share)


@pytest.mark.parametrize("ends", [(True, True), (True, False), (False, False)])
@pytest.mark.parametrize("nodes", [2, 5, 40, 101])
def test_it_is_the_same_arithmetic(nodes, ends):
    rng = np.random.default_rng(nodes * 7 + len(ends))
    start = rng.normal(0, 4.0, (nodes, 3))
    mine, theirs = start.copy(), start.copy()
    cable.relax(mine, 1.0, ends=ends)
    _the_old_way(theirs, 1.0, ends=ends)
    assert np.allclose(mine, theirs, rtol=0, atol=1e-12), np.abs(mine - theirs).max()


def test_a_chain_of_one_node_does_not_raise():
    """`last` is zero there and the loop must simply not run."""
    one = np.zeros((1, 3))
    cable.relax(one, 1.0)
    assert one.shape == (1, 3)


def test_it_still_pulls_the_nodes_together():
    """The arithmetic being identical is not the same as it being right."""
    nodes = np.zeros((21, 3))
    nodes[:, 0] = np.linspace(0.0, 40.0, 21)      # twice as long as it should be
    cable.relax(nodes, 1.0, ends=(True, False), sweeps=200)
    apart = np.linalg.norm(np.diff(nodes, axis=0), axis=1)
    # Every span has come in towards the segment length from two metres.
    assert apart.max() < 1.5, apart.max()
    assert apart.min() == pytest.approx(1.0, abs=1e-6)
    # The pinned end stayed pinned and the free end came in.
    assert nodes[0] == pytest.approx(np.zeros(3))
    assert nodes[-1, 0] < 30.0


def test_the_sweep_is_still_sequential():
    """The loop runs from node 0 upwards and a correction at constraint i
    moves node i+1 before constraint i+1 is applied, so a disturbance at the
    *near* end travels the whole chain in one sweep — while one at the far end
    travels exactly one node, which is the case the hundred-node mooring line
    was hitting.

    Red-black ordering would vectorise this and propagate two nodes a sweep in
    either direction, which is neither behaviour.
    """
    near = np.zeros((9, 3))
    near[:, 0] = np.arange(9) * 1.0
    near[0, 0] = -30.0
    cable.relax(near, 1.0, ends=(False, True), sweeps=1)
    moved = np.abs(near[:, 0] - np.arange(9) * 1.0)
    # Every node felt it in one sweep except the pinned far end and the one
    # constrained against it: the last constraint pins its own node back to a
    # segment from a node that cannot move, which puts it where it started.
    assert (moved[:-2] > 1e-9).all(), moved
    assert moved[-1] == pytest.approx(0.0)

    far = np.zeros((9, 3))
    far[:, 0] = np.arange(9) * 1.0
    far[-1, 0] = 40.0
    cable.relax(far, 1.0, ends=(True, False), sweeps=1)
    moved = np.abs(far[:, 0] - np.arange(9) * 1.0)
    assert (moved[1:-2] < 1e-9).all(), moved


def test_it_is_fast_enough_to_be_a_habit():
    """A hundred-node tether, swept as a dive sweeps it, at the rate a dive
    calls it. The old way managed about 1,200 relaxations a second."""
    shape = np.zeros((101, 3))
    shape[:, 0] = np.linspace(0.0, 100.0, 101)
    began = time.perf_counter()
    for _ in range(200):
        cable.relax(shape.copy(), 1.0)
    each = (time.perf_counter() - began) / 200
    assert each < 2.5e-3, f"{each * 1e3:.2f} ms a relaxation"
