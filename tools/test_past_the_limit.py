"""Ground where the sensor that measured it went blind.

Satellite-derived bathymetry does not return "unknown" past the depth it can
see. It returns *the limit*, for every pixel, so the result is a dead-flat
plateau at exactly one depth. A quarter of Al Fahal was eight hundred metres
of ground at exactly 21.59 m, and every dive flown there flew over a plane
that does not exist.
"""

import importlib.machinery
import importlib.util
import json
import pathlib

import numpy as np
import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _tool():
    loader = importlib.machinery.SourceFileLoader(
        "past_the_limit", str(HERE / "past-the-limit"))
    spec = importlib.util.spec_from_loader("past_the_limit", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _a_reef_the_sensor_loses(n=512, across=2000.0, limit=21.6):
    """A flank falling westward, clamped where it passes the limit."""
    step = across / (n - 1)
    x = (np.arange(n) - (n - 1) / 2) * step
    # Shallow in the east, falling west at about two degrees — steep enough
    # that the western third passes the limit and is clamped.
    depth = np.clip(3.0 - x * 0.035, 0.5, None)
    depth = np.tile(depth, (n, 1))
    return np.minimum(depth, limit), step


GRADIENT = 0.035


def test_a_plateau_at_exactly_one_depth_is_a_clamp():
    tool = _tool()
    depth, _ = _a_reef_the_sensor_loses()
    clamped = tool.where_it_gave_up(depth)
    assert clamped.mean() > 0.2
    # And ground that merely happens to be deep is not.
    rolling = 10.0 + np.random.default_rng(0).normal(0, 2.0, (64, 64))
    assert tool.where_it_gave_up(rolling).mean() < 0.01


def test_the_gradient_is_measured_where_the_sensor_still_worked():
    """Not at the boundary. The last stretch before a satellite depth
    saturates is already compressed, so the apparent slope there is a
    measurement of the sensor: at Al Fahal it reads 0.10 degrees at the
    boundary and 1.68 two metres shallower."""
    tool = _tool()
    assert tool.HONEST_BETWEEN[1] < 1.0
    depth, step = _a_reef_the_sensor_loses()
    clamped = tool.where_it_gave_up(depth)
    said = tool.the_last_honest_gradient(depth, step, clamped)
    assert said["metresPerMetre"] == pytest.approx(GRADIENT, rel=0.15), said
    assert said["rowsMeasured"] > 100


def test_the_flank_leaves_the_boundary_at_the_gradient_it_was_measured_at():
    tool = _tool()
    depth, step = _a_reef_the_sensor_loses()
    clamped = tool.where_it_gave_up(depth)
    said = tool.the_last_honest_gradient(depth, step, clamped)
    out = tool.carry_on(depth, step, clamped, said["metresPerMetre"], 30.0, seed=1)

    row = out[256]
    edge = int(np.flatnonzero(~clamped[256]).min())
    # Just inside the constructed ground, going west, the slope is what was
    # measured on the flank.
    fell = (row[edge - 3] - row[edge - 1]) / (2 * step)
    assert fell == pytest.approx(said["metresPerMetre"], rel=0.5), fell
    # It gets deeper going away from the reef, and never past the shelf.
    assert row[0] > row[edge - 1] >= depth.max()
    assert out.max() <= 31.0


def test_it_arrives_flat_rather_than_meeting_the_shelf_at_a_corner():
    """A kink is as unlike a seabed as a plane is."""
    tool = _tool()
    depth, step = _a_reef_the_sensor_loses()
    clamped = tool.where_it_gave_up(depth)
    said = tool.the_last_honest_gradient(depth, step, clamped)
    out = tool.carry_on(depth, step, clamped, said["metresPerMetre"], 30.0, seed=1)
    row = out[256]
    edge = int(np.flatnonzero(~clamped[256]).min())
    near = abs(row[edge - 2] - row[edge - 6])
    far = abs(row[2] - row[6])
    assert far < near, (near, far)


def test_measured_ground_is_not_touched():
    tool = _tool()
    depth, step = _a_reef_the_sensor_loses()
    clamped = tool.where_it_gave_up(depth)
    said = tool.the_last_honest_gradient(depth, step, clamped)
    out = tool.carry_on(depth, step, clamped, said["metresPerMetre"], 30.0, seed=1)
    assert np.array_equal(out[~clamped], depth[~clamped])


def test_it_will_not_make_up_a_shelf_depth():
    """There is no measurement of that ground in the file — that is the whole
    problem — so it has to come from somewhere and be said."""
    source = (HERE / "past-the-limit").read_text()
    assert "--shelf is required" in source
    assert "--shelf-from must say where that depth came from" in source


def test_a_place_carries_the_fact_that_a_quarter_of_it_is_built():
    """The place is the thing somebody flies, so the place has to say which of
    its seabed is a measurement."""
    source = (HERE / "make-site").read_text()
    assert "constructedPastTheSensor" in source
    # And that ground is sediment, which is known rather than inferred: the
    # flank is continued at 1.77 degrees and `zonation` reads any slope as
    # rock, so Al Fahal's habitat went *up* from 67% to 93% when the geometry
    # was fixed. Fixing the shape made the habitat worse.
    assert "SEDIMENT_APRON" in source
