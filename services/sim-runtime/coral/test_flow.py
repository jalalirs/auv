"""The stirred water on a grid: driven by the jets, incompressible, walled, and
lingering after the thrusters stop."""

import time

import numpy as np

from engine import Clock
from systems.flow import Flow, FlowSystem, project
from systems.wash import Wash

BED = -0.95


def a_tank():
    class World:
        pass

    w = World()
    w.clock = Clock(0.05)
    w.flow = Flow()
    w.flow.set_for([-1.0, -0.5, BED], [1.0, 0.5, 0.0],
                   lambda p: np.where((np.abs(p[:, 0] - 0.5) < 0.1) & (np.abs(p[:, 1]) < 0.1), -0.3, BED))
    w.wash = Wash()
    w.wash.diameter = 0.038
    w.wash.origin = np.array([[-0.6, 0.0, -0.4]])
    w.wash.axis = np.array([[1.0, 0.0, 0.0]])
    w.wash.efflux = np.array([2.6])
    w.wash.grid = w.flow
    return w


def run(w, seconds):
    s = FlowSystem()
    for _ in range(int(seconds / 0.05)):
        s.step(w)


def test_projection_takes_the_divergence_out():
    rng = np.random.default_rng(0)
    u = rng.normal(0, 0.1, (16, 12, 10, 3))
    solid = np.zeros((16, 12, 10), dtype=bool)
    v, _ = project(u, solid, 0.05, iterations=200)
    div = ((v[2:, 1:-1, 1:-1, 0] - v[:-2, 1:-1, 1:-1, 0]) + (v[1:-1, 2:, 1:-1, 1] - v[1:-1, :-2, 1:-1, 1])
           + (v[1:-1, 1:-1, 2:, 2] - v[1:-1, 1:-1, :-2, 2])) / 0.1
    before = ((u[2:, 1:-1, 1:-1, 0] - u[:-2, 1:-1, 1:-1, 0]) + (u[1:-1, 2:, 1:-1, 1] - u[1:-1, :-2, 1:-1, 1])
              + (u[1:-1, 1:-1, 2:, 2] - u[1:-1, 1:-1, :-2, 2])) / 0.1
    assert np.abs(div).mean() < 0.3 * np.abs(before).mean()


def test_a_jet_sets_the_tanks_water_moving_its_way():
    w = a_tank()
    run(w, 2.0)
    ahead = w.flow.at([[-0.3, 0.0, -0.4]])[0]
    assert ahead[0] > 0.1


def test_the_wash_lingers_after_the_thrusters_stop_and_then_dies_away():
    w = a_tank()
    run(w, 2.0)
    w.wash.efflux = np.zeros(1)
    run(w, 1.0)
    soon = np.abs(w.flow.u).max()
    assert soon > 0.02, "the water goes on moving"
    assert np.abs(w.wash.at([[-0.3, 0.0, -0.4]])).max() > 0.0, "and the wash still says so"
    run(w, 40.0)
    assert np.abs(w.flow.u).max() < 0.5 * soon, "until it comes to rest"


def test_nothing_moves_inside_the_rock():
    w = a_tank()
    run(w, 2.0)
    assert not np.abs(w.flow.u[w.flow.solid]).any()


def test_a_tank_steps_in_milliseconds():
    w = a_tank()
    s = FlowSystem()
    began = time.perf_counter()
    for _ in range(20):
        s.step(w)
    assert (time.perf_counter() - began) / 20 < 0.03


def test_in_open_water_the_box_follows_the_vehicle_and_keeps_what_it_stirred():
    flow = Flow()
    flow.set_for([-1.5, -1.5, -6.0], [1.5, 1.5, -4.0], lambda p: np.full(len(p), -9.0), cell=0.1, follows=True)
    flow.u[15, 15, 10] = (0.3, 0.0, 0.0)            # stirred water at about the origin
    flow.follow([0.8, 0.0, -5.0])                   # the vehicle has moved on 0.8 m
    assert np.isclose(flow.low[0], -1.5 + 0.8)
    assert np.isclose(flow.at([[0.05, 0.05, -4.95]])[0][0], 0.3, atol=0.05), "what it stirred is still there"
