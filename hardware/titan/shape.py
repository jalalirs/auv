"""The mini Titan's outside, as one moulded form.

    hardware/.venv/bin/python hardware/titan/shape.py

The first drawing was boxes and cylinders placed side by side, and it looked
it. The Titan is moulded: its arms grow out of the hull and into the pods
with no seam. This draws the outside the same way, as a signed distance
field in which every join is a blend, and turns it into a mesh. MJF prints a
mesh as readily as a solid, so nothing is lost by it.

Writes to hardware/out/titan/: cover.stl (red, the lid), chassis.stl (black,
everything else that is printed), the bought parts' stand-ins for the
pictures, and shape.json for the viewer.

Frame: x forward, y port, z up, millimetres, origin at the centre of the box.
"""

from __future__ import annotations

import base64
import json
import pathlib
import sys
import time

import numpy as np
import trimesh
from skimage.measure import marching_cubes

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "titan"
STEP_MM = 0.5
LO = np.array([-175.0, -120.0, -52.0])
HI = np.array([82.0, 120.0, 58.0])


# ── distance primitives, all vectorised over (x, y, z) arrays ───────────────

def smin(a, b, k):
    """The blend that makes it moulded: a fillet of size about k where a meets b."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def union(*ds):
    out = ds[0]
    for d in ds[1:]:
        out = np.minimum(out, d)
    return out


def cut(a, b):
    return np.maximum(a, -b)


def smooth_cut(a, b, k):
    """A cut whose edge is rounded by about k."""
    return -smin(-a, b, k)


def rrect(u, v, cu, cv, hu, hv, r):
    qu = np.abs(u - cu) - hu + r
    qv = np.abs(v - cv) - hv + r
    return np.minimum(np.maximum(qu, qv), 0) + np.hypot(np.maximum(qu, 0), np.maximum(qv, 0)) - r


def lift(d2, w, lo, hi, r_hi, r_lo):
    """A 2-D section extruded over w in [lo, hi], its two edges rounded."""
    c, h = (lo + hi) / 2, (hi - lo) / 2
    r = np.where(w > c, r_hi, r_lo)
    a = d2 + r
    b = np.abs(w - c) - h + r
    return np.minimum(np.maximum(a, b), 0) + np.hypot(np.maximum(a, 0), np.maximum(b, 0)) - r


def polygon(u, v, pts):
    """Signed distance to a closed polygon in the (u, v) plane."""
    pts = np.asarray(pts, float)
    d = (u - pts[0, 0]) ** 2 + (v - pts[0, 1]) ** 2
    s = np.ones_like(u)
    n = len(pts)
    for i in range(n):
        (ax, ay), (bx, by) = pts[i - 1], pts[i]
        ex, ey = ax - bx, ay - by
        wx, wy = u - bx, v - by
        t = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0, 1)
        d = np.minimum(d, (wx - ex * t) ** 2 + (wy - ey * t) ** 2)
        c1 = v >= by
        c2 = v < ay
        c3 = ex * wy > ey * wx
        flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
        s = np.where(flip, -s, s)
    return s * np.sqrt(d)


def round_cone(x, y, z, a, b, r1, r2):
    """A tapered rod from a (radius r1) to b (radius r2), ends rounded."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ba = b - a
    l2 = ba @ ba
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pax, pay, paz = x - a[0], y - a[1], z - a[2]
    yy = pax * ba[0] + pay * ba[1] + paz * ba[2]
    zz = yy - l2
    qx, qy, qz = pax * l2 - ba[0] * yy, pay * l2 - ba[1] * yy, paz * l2 - ba[2] * yy
    x2 = qx * qx + qy * qy + qz * qz
    y2 = yy * yy * l2
    z2 = zz * zz * l2
    k = np.sign(rr) * rr * rr * x2
    d_end = np.sqrt(x2 + z2) * il2 - r2
    d_start = np.sqrt(x2 + y2) * il2 - r1
    d_mid = (np.sqrt(x2 * a2 * il2) + yy * rr) * il2 - r1
    return np.where(np.sign(zz) * a2 * z2 > k, d_end, np.where(np.sign(yy) * a2 * y2 < k, d_start, d_mid))


def cyl_z(x, y, z, cx, cy, radius, lo, hi, r=0.0):
    return lift(np.hypot(x - cx, y - cy) - radius, z, lo, hi, r, r)


def cyl_x(x, y, z, cy, cz, radius, lo, hi, r=0.0):
    return lift(np.hypot(y - cy, z - cz) - radius, x, lo, hi, r, r)


# ── the vehicle ─────────────────────────────────────────────────────────────

S = P  # shorthand in the long expressions below


def body(x, y, z):
    """The capsule: a long rounded pill in plan, flat-topped with rounded
    edges, narrowing towards the tail the way the Titan's does."""
    half = np.where(x > S.TAPER_FROM, S.HULL_W / 2,
                    S.HULL_W / 2 + (S.TAIL_W / 2 - S.HULL_W / 2) * (S.TAPER_FROM - x) / (S.TAPER_FROM - S.HULL_TAIL))
    yy = y * (S.HULL_W / 2) / half
    cx = (S.HULL_NOSE + S.HULL_TAIL) / 2
    corner = np.where(x > cx, S.NOSE_CORNER_R, S.TAIL_CORNER_R)
    plan = rrect(x, yy, cx, 0.0, (S.HULL_NOSE - S.HULL_TAIL) / 2, S.HULL_W / 2, corner)
    return lift(plan, z, -S.HULL_H / 2, S.HULL_H / 2, S.TOP_EDGE_R, S.BELLY_EDGE_R)


def cavity(x, y, z):
    return body(x, y, z) + S.SKIN


def pod_shell(x, y, z, at):
    px, py, pz = at
    top = pz + S.POD_H / 2
    shell = cyl_z(x, y, z, px, py, S.POD_OD / 2, pz - S.POD_H / 2, top, S.POD_EDGE_R)
    lip = cyl_z(x, y, z, px, py, S.POD_OD / 2 + S.POD_LIP, top - 7.0, top, 1.5)
    return smin(shell, lip, 1.5)


def pod_bore(x, y, z, at):
    px, py, pz = at
    return cyl_z(x, y, z, px, py, S.BORE_D / 2, pz - S.POD_H, pz + S.POD_H)


def stern_shell(x, y, z, at):
    px, py, pz = at
    return cyl_x(x, y, z, py, pz, S.POD_OD / 2, px - S.POD_H / 2, px + S.POD_H / 2, S.POD_EDGE_R)


def stern_bore(x, y, z, at):
    px, py, pz = at
    return cyl_x(x, y, z, py, pz, S.BORE_D / 2, px - S.POD_H, px + S.POD_H)


def guard(x, y, z, at):
    """Three spokes and a domed hub across the top of a vertical pod, as on
    the Titan: it keeps fingers out of the propeller and reads as the pod's face."""
    px, py, pz = at
    top = pz + S.POD_H / 2
    u, v = x - px, y - py
    out = None
    for i in range(3):
        a = np.radians(90 + 120 * i)
        along = u * np.cos(a) + v * np.sin(a)
        across = -u * np.sin(a) + v * np.cos(a)
        spoke = lift(rrect(along, across, S.BORE_D / 4, 0, S.BORE_D / 4 + 1.0, S.SPOKE_W / 2, 1.0), z, top - 4.0, top - 0.5, 1.0, 1.0)
        out = spoke if out is None else smin(out, spoke, 1.5)
    hub = np.sqrt(u * u + v * v + (z - (top - 3.0)) ** 2 * 1.6) - S.HUB_D / 2
    hub = np.maximum(hub, (top - 6.0) - z)
    return smin(out, hub, 2.0)


def stern_guard(x, y, z, at):
    px, py, pz = at
    rear = px - S.POD_H / 2
    u, v = y - py, z - pz
    out = None
    for i in range(3):
        a = np.radians(90 + 120 * i)
        along = u * np.cos(a) + v * np.sin(a)
        across = -u * np.sin(a) + v * np.cos(a)
        spoke = lift(rrect(along, across, S.BORE_D / 4, 0, S.BORE_D / 4 + 1.0, S.SPOKE_W / 2, 1.0), x, rear + 0.5, rear + 4.0, 1.0, 1.0)
        out = spoke if out is None else smin(out, spoke, 1.5)
    hub = np.sqrt(u * u + v * v + (x - (rear + 3.0)) ** 2 * 1.6) - S.HUB_D / 2
    hub = np.maximum(hub, x - (rear + 6.0))
    return smin(out, hub, 2.0)


def arm(x, y, z, at, root):
    """A swept arm from the hull's side to a pod, thick at the root and
    flattened, blended at both ends."""
    return round_cone(x, y, z * S.ARM_FLATTEN, (root[0], root[1], root[2] * S.ARM_FLATTEN),
                      (at[0], at[1], at[2] * S.ARM_FLATTEN), S.ARM_ROOT_R, S.ARM_TIP_R) / S.ARM_FLATTEN


def light(x, y, z, at):
    px, py, pz = at
    return cyl_x(x, y, z, py, pz + S.LIGHT_DZ, S.LIGHT_D / 2, px, px + S.LIGHT_REACH, 3.0)


def wing(x, y, z):
    """The black tail plate the lid sits on, swept back to two points."""
    pts = list(S.WING_PLAN) + [(px, -py) for px, py in reversed(S.WING_PLAN[:-1])]
    plan = polygon(x, y, pts) - 3.0
    return lift(plan, z, S.WING_Z - S.WING_T, S.WING_Z, 2.0, 2.0)


def fin(x, y, z):
    """The raised red scoop at the stern of the lid, which is the handle."""
    side = polygon(x, z, S.FIN_PROFILE) - 4.0
    return lift(side, y, -S.FIN_W / 2, S.FIN_W / 2, 4.0, 4.0)


def knob(x, y, z):
    """The round boss on the crown. On the Titan it is the plug; here it is
    the vent cap the capsule breathes through when it floods."""
    top = S.HULL_H / 2
    d = cyl_z(x, y, z, S.KNOB_X, 0, S.KNOB_D / 2, top - 6.0, top + S.KNOB_H, 3.0)
    d = cut(d, np.abs(np.hypot(x - S.KNOB_X, y) - S.KNOB_D * 0.3) - 0.8 + np.maximum(0, (top + S.KNOB_H - 1.2) - z) * 10)
    return cut(d, cyl_z(x, y, z, S.KNOB_X, 0, S.VENT_D / 2, top - 20, top + 20))


def bezel_ring(x, y, z):
    """The camera's ring in the black nose: proud of the skin, knurled."""
    th = np.arctan2(z - S.CAM_Z, y)
    rad = S.RING_OD / 2 - 0.5 + 0.5 * np.cos(S.RING_KNURLS * th)
    ring = lift(np.hypot(y, z - S.CAM_Z) - rad, x, S.HULL_NOSE - 8.0, S.HULL_NOSE + S.RING_PROUD, 2.0, 2.0)
    return ring


def outside(x, y, z):
    """Everything printed, before it is split into lid and chassis."""
    d = body(x, y, z)
    for name, at, axis in S.THRUSTERS:
        if axis[2] == 1.0:
            side = np.sign(at[1])
            root = S.ARM_ROOTS[name]
            a = arm(x, y, z, at, (root[0], side * root[1], root[2]))
            d = smin(d, a, S.BLEND_HULL)
            d = smin(d, pod_shell(x, y, z, at), S.BLEND_POD)
            if at[0] > 0:
                d = smin(d, light(x, y, z, at), 4.0)
        else:
            d = smin(d, stern_shell(x, y, z, at), S.BLEND_STERN)
    d = smin(d, wing(x, y, z), S.BLEND_WING)
    d = smin(d, fin(x, y, z), 5.0)
    d = smin(d, knob(x, y, z), 3.0)
    d = smin(d, bezel_ring(x, y, z), 2.0)
    # Hollow the hull; the arms and pods stay solid nylon.
    d = cut(d, cavity(x, y, z))
    for name, at, axis in S.THRUSTERS:
        if axis[2] == 1.0:
            d = smooth_cut(d, pod_bore(x, y, z, at), 1.2)
            d = union(d, guard(x, y, z, at))
        else:
            d = smooth_cut(d, stern_bore(x, y, z, at), 1.2)
            d = union(d, stern_guard(x, y, z, at))
    # The camera looks out through the ring; the lights' faces are lenses.
    d = cut(d, cyl_x(x, y, z, 0, S.CAM_Z, S.NOSE_OPENING_D / 2, S.BOX_X + S.BOX_L / 2 - 1, S.HULL_NOSE + 20))
    for name, at, axis in S.THRUSTERS:
        if axis[2] == 1.0 and at[0] > 0:
            d = cut(d, cyl_x(x, y, z, at[1], at[2] + S.LIGHT_DZ, S.LIGHT_D / 2 - 2.0, at[0] + S.LIGHT_REACH - 2.0, at[0] + S.LIGHT_REACH + 5))
    # The tether leaves through the stern, under the wing; a drain slot under the tail.
    d = cut(d, cyl_x(x, y, z, 0, S.TETHER_Z, S.TETHER_HOLE_D / 2, S.HULL_TAIL - 10, S.HULL_TAIL + 10))
    d = cut(d, lift(rrect(x, y, S.HULL_TAIL + 30, 0, 12, 4, 3.9), z, -S.HULL_H / 2 - 5, -S.HULL_H / 2 + 5, 0, 0))
    # Inside: two ribs cradle the box, four bosses take the lid's screws.
    ribs = None
    for rx in (S.BOX_X - 36.0, S.BOX_X + 36.0):
        r = lift(np.abs(y) - S.HULL_W, x, rx - 2.5, rx + 2.5, 0, 0)
        r = np.maximum(r, np.maximum(cavity(x, y, z) - 0.1, z - 0.0))
        ribs = r if ribs is None else union(ribs, r)
    box = lift(rrect(x, y, S.BOX_X, 0, S.BOX_L / 2 + 0.5, S.BOX_W / 2 + 0.5, 3), z, -S.BOX_H / 2 - 0.5, S.BOX_H / 2 + 0.5, 0, 0)
    d = union(d, cut(ribs, box))
    for bx, by in S.LID_BOSSES:
        b = cyl_z(x, y, z, bx, by, S.BOSS_OD / 2, S.PARTING_Z - 10, S.PARTING_Z + 10, 0)
        b = np.maximum(b, cavity(x, y, z) - S.SKIN)  # stays inside the skin
        b = cut(b, cyl_z(x, y, z, bx, by, S.SCREW_D / 2, -100, 100))
        d = union(d, b)
    return d


def lid_zone(x, y, z):
    """Where the red lid is: the hull above the parting line, short of the
    black nose, plus the scoop and the knob."""
    hull = np.maximum(np.abs(y) - (S.HULL_W / 2 + 6), z - 100)
    zone = np.maximum(hull, np.maximum(S.PARTING_Z - z, x - S.LID_NOSE_X))
    return zone


def thrusters_ref(x, y, z):
    """The bought thrusters as seen in the bores: a motor and three blades."""
    d = None
    for name, at, axis in S.THRUSTERS:
        px, py, pz = at
        if axis[2] == 1.0:
            m = cyl_z(x, y, z, px, py, 8.0, pz - 18, pz + 14, 3.0)
            blades = None
            for i in range(3):
                a = np.radians(30 + 120 * i)
                u, v = x - px, y - py
                along = u * np.cos(a) + v * np.sin(a)
                across = -u * np.sin(a) + v * np.cos(a)
                bl = lift(rrect(along, across, 11, 0, 9.5, 4.5, 4), z - (along * 0.0), pz - 2, pz + 1.5, 1, 1)
                blades = bl if blades is None else union(blades, bl)
            t = union(m, blades)
        else:
            m = cyl_x(x, y, z, py, pz, 8.0, px - 14, px + 18, 3.0)
            blades = None
            for i in range(3):
                a = np.radians(30 + 120 * i)
                u, v = y - py, z - pz
                along = u * np.cos(a) + v * np.sin(a)
                across = -u * np.sin(a) + v * np.cos(a)
                bl = lift(rrect(along, across, 11, 0, 9.5, 4.5, 4), x, px - 1.5, px + 2, 1, 1)
                blades = bl if blades is None else union(blades, bl)
            t = union(m, blades)
        d = t if d is None else union(d, t)
    return d


def glass(x, y, z):
    """The camera window and lens, and the two lights' lenses."""
    w = cyl_x(x, y, z, 0, S.CAM_Z, S.NOSE_OPENING_D / 2 + 0.5, S.BOX_X + S.BOX_L / 2, S.BOX_X + S.BOX_L / 2 + 3, 1.0)
    lens = np.sqrt((x - (S.BOX_X + S.BOX_L / 2 + 3)) ** 2 * 2.5 + y ** 2 + (z - S.CAM_Z) ** 2) - 9.0
    d = union(w, lens)
    for name, at, axis in S.THRUSTERS:
        if axis[2] == 1.0 and at[0] > 0:
            d = union(d, cyl_x(x, y, z, at[1], at[2] + S.LIGHT_DZ, S.LIGHT_D / 2 - 2.0, at[0] + S.LIGHT_REACH - 3, at[0] + S.LIGHT_REACH - 0.5, 1.0))
    return d


# ── sampling and meshing ────────────────────────────────────────────────────

def sample(fn, lo=LO, hi=HI, step=STEP_MM):
    xs = np.arange(lo[0], hi[0] + step, step, dtype=np.float32)
    ys = np.arange(lo[1], hi[1] + step, step, dtype=np.float32)
    zs = np.arange(lo[2], hi[2] + step, step, dtype=np.float32)
    vol = np.empty((len(xs), len(ys), len(zs)), np.float32)
    Y, Z = np.meshgrid(ys, zs, indexing="ij")
    chunk = 24
    for i in range(0, len(xs), chunk):
        X = xs[i:i + chunk, None, None]
        n = X.shape[0]
        vol[i:i + n] = fn(np.broadcast_to(X, (n,) + Y.shape),
                          np.broadcast_to(Y, (n,) + Y.shape), np.broadcast_to(Z, (n,) + Y.shape))
    return vol, xs[0], ys[0], zs[0]


def mesh(vol, origin, step=STEP_MM):
    # No smoothing pass: on a field this fine it only folds thin walls, and
    # degenerate triangles are what made the decimated mesh crumple.
    v, f, _, _ = marching_cubes(vol, level=0.0, spacing=(step, step, step), allow_degenerate=False)
    m = trimesh.Trimesh(v + np.asarray(origin), f, process=True)
    if m.volume < 0:
        m.invert()
    return m


def to_viewer(name, m, colour, finish, faces=150000):
    if len(m.faces) > faces:
        m = m.simplify_quadric_decimation(face_count=faces, aggression=2)
    # Split the shading at real edges (the parting line, the bores) so a
    # crease is drawn as a crease and not smeared across.
    m = trimesh.graph.smooth_shade(m, angle=np.radians(35))
    v = m.vertices.astype(np.float32)
    n = m.vertex_normals.astype(np.float32)
    i = m.faces.astype(np.uint32)
    enc = lambda a: base64.b64encode(a.tobytes()).decode("ascii")  # noqa: E731
    return {"name": name, "colour": colour, "finish": finish,
            "positions": enc(v), "normals": enc(n), "indices": enc(i)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    vol, *origin = sample(outside)
    print(f"sampled outside {vol.shape} in {time.time() - t0:.0f} s")
    zone, *_ = sample(lid_zone)
    lid = np.maximum(vol, zone)
    rest = np.maximum(vol, -zone)
    parts = {}
    for name, v, colour, finish in (("cover", lid, S.COVER_COLOUR, "gloss"), ("chassis", rest, S.CHASSIS_COLOUR, "satin")):
        m = mesh(v, origin)
        m.export(OUT / f"{name}.stl")
        parts[name] = (m, colour, finish)
        print(f"{name:8s} {m.volume / 1000:6.1f} cm³ ≈ {m.volume / 1000 * 1.01:4.0f} g PA12  bbox {np.round(m.extents, 1)}  watertight {m.is_watertight}")
    for name, fn, colour, finish in (("ref-thrusters", thrusters_ref, "#26292c", "satin"), ("ref-glass", glass, "#0b1a24", "glass")):
        v, *o = sample(fn, step=0.6)
        m = mesh(v, o, step=0.6)
        m.export(OUT / f"{name}.stl")
        parts[name] = (m, colour, finish)
    viewer = [to_viewer(n, m, c, f) for n, (m, c, f) in parts.items()]
    (OUT / "shape.json").write_text(json.dumps(viewer))
    allm = trimesh.util.concatenate([m for m, _, _ in parts.values()])
    print(f"overall {np.round(allm.extents, 0)} mm, {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
