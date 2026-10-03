"""A tank's glass: the box it sits in, and whether it is round.

A place's `interior` is the inside of its glass. It was always a box — two
corners, low and high — and everything that keeps something in the tank (the
vehicle, its cable, the fish, the sand in the water, the sonar's echo off the
wall, the camera) reads it as `low, high = place.interior`. A tank can be a
cylinder instead: the Jeddah airport tank is ten metres across and round.

So the interior is a `Glass`: still the box, unpacked as before, and with
`round` — (centre x, centre y, radius) — when the glass is a cylinder. What
keeps things in asks `held_in` and `out_through`, which answer for either.
"""

from __future__ import annotations

import numpy as np


class Glass(tuple):
    """(low, high), and `round` when the glass is a cylinder about z."""

    def __new__(cls, low, high, round=None):
        glass = super().__new__(cls, (np.asarray(low, dtype=float), np.asarray(high, dtype=float)))
        glass.round = None if round is None else tuple(float(v) for v in round)
        return glass


def round_of(interior):
    return getattr(interior, "round", None)


def held_in(xy, interior, margin=0.0):
    """Points pulled back inside the glass, `margin` clear of it: (where they
    are now, which were outside, the inward normal at each — zero for those
    that were inside). The box's sides, and the cylinder's when it is round."""
    xy = np.array(np.atleast_2d(xy)[:, :2], dtype=float)
    margin = np.broadcast_to(np.asarray(margin, dtype=float), (len(xy),))
    normal = np.zeros_like(xy)
    out = np.zeros(len(xy), dtype=bool)
    if interior is None:
        return xy, out, normal
    low, high = interior
    for axis in (0, 1):
        lo, hi = low[axis] + margin, high[axis] - margin
        under, over = xy[:, axis] < lo, xy[:, axis] > hi
        normal[under, axis] = 1.0
        normal[over, axis] = -1.0
        xy[:, axis] = np.clip(xy[:, axis], lo, hi)
        out |= under | over
    circle = round_of(interior)
    if circle is not None:
        cx, cy, r = circle
        off = xy - np.array([cx, cy])
        far = np.linalg.norm(off, axis=1)
        limit = r - margin
        beyond = far > limit
        if beyond.any():
            unit = off[beyond] / np.maximum(far[beyond], 1e-12)[:, None]
            xy[beyond] = np.array([cx, cy]) + unit * limit[beyond][:, None]
            normal[beyond] = -unit
            out |= beyond
    return xy, out, normal


def out_through(origin, way, interior):
    """How far a ray from inside goes before it meets the glass's side, or
    None: the box's sides, or the cylinder when it is round."""
    if interior is None:
        return None
    circle = round_of(interior)
    if circle is not None:
        cx, cy, r = circle
        o = np.asarray(origin, dtype=float)[:2] - np.array([cx, cy])
        w = np.asarray(way, dtype=float)[:2]
        a = float(w @ w)
        if a < 1e-12:
            return None
        b = 2.0 * float(o @ w)
        c = float(o @ o) - r * r
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return None
        t = (-b + np.sqrt(disc)) / (2.0 * a)
        return float(t) if t >= 0.0 else None
    low, high = interior
    best = None
    for axis in (0, 1):
        if way[axis] > 1e-9:
            t = (float(high[axis]) - float(origin[axis])) / float(way[axis])
        elif way[axis] < -1e-9:
            t = (float(low[axis]) - float(origin[axis])) / float(way[axis])
        else:
            continue
        if t >= 0.0 and (best is None or t < best):
            best = t
    return best
