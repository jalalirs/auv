"""mini-hoot's outside, as one moulded form, plus the bought parts you see.

    hardware/.venv/bin/python hardware/mini/shape.py

The same method as the titan's shape.py (a blended distance field, meshed),
around a different inside: a 3" tube whose dome is the nose, and eight
thrusters. Writes to hardware/out/mini/: cover.stl, chassis.stl, the seen
bought parts, and shape.json for the viewer.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import time

import numpy as np
import trimesh

HERE = pathlib.Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = _load("mini_params", HERE / "params.py")
F = _load("titan_shape", HERE.parent / "titan" / "shape.py")   # the distance primitives
smin, union, cut, smooth_cut, rrect, lift, polygon, round_cone, cyl_z, cyl_x = (
    F.smin, F.union, F.cut, F.smooth_cut, F.rrect, F.lift, F.polygon, F.round_cone, F.cyl_z, F.cyl_x)

OUT = HERE.parent / "out" / "mini"
STEP = 0.6
LO = np.array([-190.0, -130.0, -72.0])
HI = np.array([168.0, 130.0, 74.0])


def cyl_dir(x, y, z, at, heading_deg, radius, length, r=0.0):
    """A cylinder whose axis lies in the horizontal plane at a heading."""
    px, py, pz = at
    a = np.radians(heading_deg)
    u = (x - px) * np.cos(a) + (y - py) * np.sin(a)
    v = -(x - px) * np.sin(a) + (y - py) * np.cos(a)
    return lift(np.hypot(v, z - pz) - radius, u, -length / 2, length / 2, r, r), u, v


def body(x, y, z):
    half = np.where(x > S.TAPER_FROM, S.HULL_W / 2,
                    S.HULL_W / 2 + (S.TAIL_W / 2 - S.HULL_W / 2) * (S.TAPER_FROM - x) / (S.TAPER_FROM - S.HULL_TAIL))
    yy = y * (S.HULL_W / 2) / half
    cx = (S.HULL_NOSE + S.HULL_TAIL) / 2
    corner = np.where(x > cx, S.NOSE_CORNER_R, S.TAIL_CORNER_R)
    plan = rrect(x, yy, cx, 0.0, (S.HULL_NOSE - S.HULL_TAIL) / 2, S.HULL_W / 2, corner)
    return lift(plan, z, -S.HULL_H / 2, S.HULL_H / 2, S.TOP_EDGE_R, S.BELLY_EDGE_R)


def pod(x, y, z, at):
    px, py, pz = at
    top = pz + S.POD_H / 2
    shell = cyl_z(x, y, z, px, py, S.POD_OD / 2, pz - S.POD_H / 2, top, S.POD_EDGE_R)
    lip = cyl_z(x, y, z, px, py, S.POD_OD / 2 + S.POD_LIP, top - 7.0, top, 1.5)
    return smin(shell, lip, 1.5)


def spokes(u, v, w, face):
    """Three spokes and a domed hub across a duct's face; w is along the axis."""
    out = None
    for i in range(3):
        a = np.radians(90 + 120 * i)
        along = u * np.cos(a) + v * np.sin(a)
        across = -u * np.sin(a) + v * np.cos(a)
        sp = lift(rrect(along, across, S.BORE_D / 4, 0, S.BORE_D / 4 + 1.0, S.SPOKE_W / 2, 1.0), w, face - 3.5, face, 1.0, 1.0)
        out = sp if out is None else smin(out, sp, 1.5)
    hub = np.sqrt(u * u + v * v + (w - (face - 3.0)) ** 2 * 1.6) - S.HUB_D / 2
    hub = np.maximum(hub, (face - 6.0) - w)
    return smin(out, hub, 2.0)


def arm(x, y, z, root, tip):
    f = S.ARM_FLATTEN
    return round_cone(x, y, z * f, (root[0], root[1], root[2] * f), (tip[0], tip[1], tip[2] * f), S.ARM_ROOT_R, S.ARM_TIP_R) / f


def wing(x, y, z):
    pts = list(S.WING_PLAN) + [(px, -py) for px, py in reversed(S.WING_PLAN[:-1])]
    return lift(polygon(x, y, pts) - 3.0, z, S.WING_Z - S.WING_T, S.WING_Z, 2.0, 2.0)


def fin(x, y, z):
    return lift(polygon(x, z, S.FIN_PROFILE) - 4.0, y, -S.FIN_W / 2, S.FIN_W / 2, 4.0, 4.0)


def knob(x, y, z):
    top = S.HULL_H / 2
    d = cyl_z(x, y, z, S.KNOB_X, 0, S.KNOB_D / 2, top - 6.0, top + S.KNOB_H, 3.0)
    d = cut(d, np.abs(np.hypot(x - S.KNOB_X, y) - S.KNOB_D * 0.3) - 0.8 + np.maximum(0, (top + S.KNOB_H - 1.2) - z) * 10)
    return cut(d, cyl_z(x, y, z, S.KNOB_X, 0, S.VENT_D / 2, top - 20, top + 20))


def outside(x, y, z):
    d = body(x, y, z)
    for name, px, py, pz in S.VERTICAL:
        root = S.ARM_ROOT["front" if px > 0 else "rear"]
        d = smin(d, arm(x, y, z, (root[0], np.sign(py) * root[1], root[2]), (px, py, pz)), S.BLEND_HULL)
        d = smin(d, pod(x, y, z, (px, py, pz)), S.BLEND_POD)
        if px > 0:
            d = smin(d, cyl_x(x, y, z, py, pz + S.LIGHT_DZ, S.LIGHT_D / 2, px, px + S.LIGHT_REACH, 3.0), 4.0)
    for name, px, py, pz, hdg in S.CORNER:
        shell, _, _ = cyl_dir(x, y, z, (px, py, pz), hdg, S.POD_OD / 2, S.POD_H, S.POD_EDGE_R)
        d = smin(d, shell, S.BLEND_CORNER)
    d = smin(d, wing(x, y, z), 6.0)
    d = smin(d, fin(x, y, z), 5.0)
    d = smin(d, knob(x, y, z), 3.0)
    # The shell floods: hollow it, and open its mouth round the front flange.
    d = cut(d, body(x, y, z) + S.SKIN)
    d = smooth_cut(d, cyl_x(x, y, z, 0, 0, S.NOSE_OPENING_R, S.HULL_NOSE - 25, S.HULL_NOSE + 30), 2.0)
    for name, px, py, pz in S.VERTICAL:
        d = smooth_cut(d, cyl_z(x, y, z, px, py, S.BORE_D / 2, pz - S.POD_H, pz + S.POD_H), 1.2)
        d = union(d, spokes(x - px, y - py, z, pz + S.POD_H / 2))
        if px > 0:
            d = cut(d, cyl_x(x, y, z, py, pz + S.LIGHT_DZ, S.LIGHT_D / 2 - 2.0, px + S.LIGHT_REACH - 2.0, px + S.LIGHT_REACH + 5))
    for name, px, py, pz, hdg in S.CORNER:
        bore, u, v = cyl_dir(x, y, z, (px, py, pz), hdg, S.BORE_D / 2, S.POD_H * 2)
        d = smooth_cut(d, bore, 1.2)
        # The guard on the intake side, the end it pushes towards.
        d = union(d, spokes(v, z - pz, u, S.POD_H / 2))
    d = cut(d, cyl_x(x, y, z, 0, S.TETHER_Z, S.TETHER_HOLE_D / 2, S.HULL_TAIL - 10, S.HULL_TAIL + 10))
    return d


def lid_zone(x, y, z):
    hull = np.abs(y) - (S.HULL_W / 2 + 6)
    return np.maximum(hull, np.maximum(S.PARTING_Z - z, x - S.LID_NOSE_X))


def enclosure(x, y, z):
    """The bought dry part where it shows: the front flange and the tube end."""
    flange = cyl_x(x, y, z, 0, 0, S.FLANGE_OD / 2, S.TUBE_L / 2, S.FRONT_FACE_X, 1.5)
    flange = cut(flange, cyl_x(x, y, z, 0, 0, S.DOME_R - 6, S.TUBE_L / 2 - 1, S.FRONT_FACE_X + 1))
    tube = cyl_x(x, y, z, 0, 0, S.TUBE_OD / 2, -S.TUBE_L / 2, S.TUBE_L / 2)
    rear = cyl_x(x, y, z, 0, 0, S.FLANGE_OD / 2, S.REAR_FACE_X, -S.TUBE_L / 2, 1.5)
    return union(flange, tube, rear)


def dome(x, y, z):
    outer = np.sqrt((x - S.FRONT_FACE_X) ** 2 + y ** 2 + z ** 2) - S.DOME_R
    shell = np.maximum(outer, -(outer + 3.0))
    return np.maximum(shell, S.FRONT_FACE_X - x)


def camera(x, y, z):
    """The camera on its tilt bracket inside the dome, and its lens."""
    body_ = lift(rrect(y, z, 0, 0, 16, 16, 4), x, S.CAMERA_X - 14, S.CAMERA_X, 2, 2)
    lens = cyl_x(x, y, z, 0, 0, 7.0, S.CAMERA_X, S.CAMERA_X + 6, 2.0)
    return union(body_, lens)


def thrusters(x, y, z):
    d = None
    for name, px, py, pz in S.VERTICAL:
        m = cyl_z(x, y, z, px, py, 8.0, pz - 18, pz + 14, 3.0)
        for i in range(3):
            a = np.radians(30 + 120 * i)
            u, v = x - px, y - py
            bl = lift(rrect(u * np.cos(a) + v * np.sin(a), -u * np.sin(a) + v * np.cos(a), 11, 0, 9.5, 4.5, 4), z, pz - 2, pz + 1.5, 1, 1)
            m = union(m, bl)
        d = m if d is None else union(d, m)
    for name, px, py, pz, hdg in S.CORNER:
        m, u, v = cyl_dir(x, y, z, (px, py, pz), hdg, 8.0, 32.0, 3.0)
        for i in range(3):
            a = np.radians(30 + 120 * i)
            w = z - pz
            bl = lift(rrect(v * np.cos(a) + w * np.sin(a), -v * np.sin(a) + w * np.cos(a), 11, 0, 9.5, 4.5, 4), u, -1.5, 2, 1, 1)
            m = union(m, bl)
        d = union(d, m)
    return d


def lenses(x, y, z):
    d = None
    for name, px, py, pz in S.VERTICAL:
        if px > 0:
            l = cyl_x(x, y, z, py, pz + S.LIGHT_DZ, S.LIGHT_D / 2 - 2.0, px + S.LIGHT_REACH - 3, px + S.LIGHT_REACH - 0.5, 1.0)
            d = l if d is None else union(d, l)
    return d


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    vol, *origin = F.sample(outside, LO, HI, STEP)
    zone, *_ = F.sample(lid_zone, LO, HI, STEP)
    print(f"sampled {vol.shape} in {time.time() - t0:.0f} s")
    parts = {}
    for name, v, colour, finish in (("cover", np.maximum(vol, zone), S.COVER_COLOUR, "gloss"),
                                    ("chassis", np.maximum(vol, -zone), S.CHASSIS_COLOUR, "satin")):
        m = F.mesh(v, origin, STEP)
        m.export(OUT / f"{name}.stl")
        parts[name] = (m, colour, finish)
        print(f"{name:8s} {m.volume / 1000:6.1f} cm³ ≈ {m.volume / 1000 * 1.01:4.0f} g PA12  bbox {np.round(m.extents, 1)}  watertight {m.is_watertight}")
    for name, fn, colour, finish in (("ref-enclosure", enclosure, "#2c2f33", "metal"), ("ref-dome", dome, "#dfe9ef", "clear"),
                                     ("ref-camera", camera, "#0d0f11", "gloss"), ("ref-thrusters", thrusters, "#26292c", "satin"),
                                     ("ref-lights", lenses, "#f4f1e6", "glass")):
        v, *o = F.sample(fn, LO, HI, STEP)
        m = F.mesh(v, o, STEP)
        m.export(OUT / f"{name}.stl")
        parts[name] = (m, colour, finish)
    viewer = [F.to_viewer(n, m, c, f, faces=110000) for n, (m, c, f) in parts.items()]
    (OUT / "shape.json").write_text(json.dumps(viewer))
    allm = trimesh.util.concatenate([m for n, (m, _, _) in parts.items() if n != "ref-enclosure"])
    print(f"overall {np.round(allm.extents, 0)} mm, {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
