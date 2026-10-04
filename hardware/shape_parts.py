"""The parts a hull is drawn from: rods, rings, lathed bodies, fins, boxes.

Each returns a trimesh in metres, x forward, z up, so a vehicle's shape.py reads
as an assembly of named parts at published sizes. Boxfish Luna's shape.py has
its own copies of the first three, from before this file; new vehicles use these.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh


def along(mesh, start, end):
    """A mesh made along +z from 0 to its length, laid from `start` to `end`."""
    start, end = np.asarray(start, float), np.asarray(end, float)
    axis = end - start
    mesh.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], axis / np.linalg.norm(axis)))
    mesh.apply_translation(start)
    return mesh


def rod(r, start, end, sections=32):
    long = float(np.linalg.norm(np.subtract(end, start)))
    m = trimesh.creation.cylinder(radius=r, height=long, sections=sections)
    m.apply_translation([0, 0, long / 2])
    return along(m, start, end)


def ring(r_in, r_out, start, end, sections=40):
    long = float(np.linalg.norm(np.subtract(end, start)))
    m = trimesh.creation.annulus(r_min=r_in, r_max=r_out, height=long, sections=sections)
    m.apply_translation([0, 0, long / 2])
    return along(m, start, end)


def box(extents, centre):
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(centre)
    return m


def lathe(profile, sections=64, centre=(0.0, 0.0, 0.0)):
    """A closed body of revolution about the x axis from (x, r) pairs, nose
    first. A radius of zero is a pole — one vertex — and an end with a radius
    is capped flat."""
    rings = []          # per profile point: list of vertex indices
    verts = []
    theta = np.linspace(0, 2 * math.pi, sections, endpoint=False)
    for x, r in profile:
        if r <= 1e-9:
            rings.append([len(verts)] * sections)
            verts.append([x, 0.0, 0.0])
        else:
            rings.append(list(range(len(verts), len(verts) + sections)))
            verts += [[x, r * math.cos(t), r * math.sin(t)] for t in theta]
    faces = []
    for i in range(len(rings) - 1):
        a_ring, b_ring = rings[i], rings[i + 1]
        for j in range(sections):
            a, b = a_ring[j], a_ring[(j + 1) % sections]
            c, d = b_ring[j], b_ring[(j + 1) % sections]
            if a != b:
                faces.append([a, b, d])
            if c != d:
                faces.append([a, d, c])
    for end, flip in ((0, True), (len(rings) - 1, False)):
        if profile[end][1] > 1e-9:
            hub = len(verts)
            verts.append([profile[end][0], 0.0, 0.0])
            ring_ = rings[end]
            for j in range(sections):
                a, b = ring_[j], ring_[(j + 1) % sections]
                faces.append([hub, b, a] if flip else [hub, a, b])
    m = trimesh.Trimesh(np.array(verts) + np.asarray(centre), np.array(faces), process=True)
    trimesh.repair.fix_normals(m)
    return m


def stretched(mesh, y=1.0, z=1.0):
    """A body of revolution squashed or widened across, for a hull that is not round."""
    mesh.apply_transform(np.diag([1.0, y, z, 1.0]))
    return mesh


def fin(root_chord, tip_chord, span, thickness, sweep=0.0):
    """A flat fin with a rounded leading edge and a sharp trailing edge. Its
    root chord runs aft along -x from the origin, its span along +z, the tip
    set back by `sweep` metres. Lay it with `placed`."""
    t = thickness / 2

    def section(chord, x0, z):
        nose = [[x0 - t + t * math.cos(a), t * math.sin(a), z] for a in np.linspace(-math.pi / 2, math.pi / 2, 9)]
        return nose + [[x0 - chord, 0.0, z]]

    root = section(root_chord, 0.0, 0.0)
    tip = section(tip_chord, -sweep, span)
    verts = np.array(root + tip, float)
    n = len(root)
    faces = []
    for j in range(n):
        a, b = j, (j + 1) % n
        faces += [[a, b, n + b], [a, n + b, n + a]]
    faces += [[0, j + 1, j] for j in range(1, n - 1)]
    faces += [[n, n + j, n + j + 1] for j in range(1, n - 1)]
    m = trimesh.Trimesh(verts, np.array(faces), process=True)
    m.fix_normals()
    return m


def placed(mesh, roll_deg=0.0, at=(0.0, 0.0, 0.0), yaw_deg=0.0):
    """Turn a part about x (roll), then z (yaw), then move it."""
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(roll_deg), [1, 0, 0]))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(yaw_deg), [0, 0, 1]))
    mesh.apply_translation(at)
    return mesh


def prism_x(outline, x0, x1):
    """A solid along x from x0 to x1 whose cross-section is `outline`, a convex
    polygon of (y, z) points in order."""
    n = len(outline)
    verts = [[x0, y, z] for y, z in outline] + [[x1, y, z] for y, z in outline]
    faces = []
    for j in range(n):
        a, b = j, (j + 1) % n
        faces += [[a, b, n + b], [a, n + b, n + a]]
    faces += [[0, j + 1, j] for j in range(1, n - 1)]
    faces += [[n, n + j, n + j + 1] for j in range(1, n - 1)]
    m = trimesh.Trimesh(np.array(verts, float), np.array(faces), process=True)
    trimesh.repair.fix_normals(m)
    return m


def rounded_outline(width, height, radius, sections=8, centre=(0.0, 0.0)):
    """A rectangle's outline in (y, z) with rounded corners, in order."""
    r = min(radius, width / 2, height / 2)
    out = []
    for cy, cz, a0 in ((width / 2 - r, height / 2 - r, 0.0), (-(width / 2 - r), height / 2 - r, math.pi / 2),
                       (-(width / 2 - r), -(height / 2 - r), math.pi), (width / 2 - r, -(height / 2 - r), 1.5 * math.pi)):
        out += [(centre[0] + cy + r * math.cos(a), centre[1] + cz + r * math.sin(a))
                for a in np.linspace(a0, a0 + math.pi / 2, sections)]
    return out


def rounded_box(extents, centre, radius, sections=8):
    """A box with its long edges (along x) rounded: a towbody's shell."""
    lx, ly, lz = extents
    cx, cy, cz = centre
    return prism_x(rounded_outline(ly, lz, radius, sections, (cy, cz)), cx - lx / 2, cx + lx / 2)


def loft(sections):
    """A closed solid through cross-sections along x: [(x, outline), ...],
    each outline the same number of (y, z) points in the same order. Capped
    flat at both ends — a pole is an outline shrunk to a point's size."""
    n = len(sections[0][1])
    verts, faces = [], []
    for x, outline in sections:
        verts += [[x, y, z] for y, z in outline]
    for i in range(len(sections) - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c, d = (i + 1) * n + j, (i + 1) * n + (j + 1) % n
            faces += [[a, b, d], [a, d, c]]
    last = (len(sections) - 1) * n
    faces += [[0, j + 1, j] for j in range(1, n - 1)]
    faces += [[last, last + j, last + j + 1] for j in range(1, n - 1)]
    m = trimesh.Trimesh(np.array(verts, float), np.array(faces), process=True)
    trimesh.repair.fix_normals(m)
    return m
