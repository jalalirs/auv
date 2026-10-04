"""A hull's panels, for the runtime to push the water against.

    hardware/.venv/bin/python hardware/hull_panels.py <hull.usd> [--into <package dir>] [--wake 0.5]
    hardware/.venv/bin/python hardware/hull_panels.py --check     # the BlueROV2 against Li et al.

The runtime's panel model (services/sim-runtime/coral/panels.py) needs, for
each panel of the hull: where it is, which way it faces, how big it is, and
from which directions the oncoming water reaches it straight rather than
through the wake of another part. This works those out from the mesh:

  **Panels.** The mesh's triangles, each part's normals turned outward, gathered
  into cells a thirtieth of the hull long and, within a cell, by which way they
  face — the vector sum of their areas is the panel. A million-triangle moulded
  hull and an eight-thousand-triangle frame come out as a thousand or two panels
  either way, which is what a step can afford.

  **Who meets the water.** From each of 26 directions (the faces, edges and
  corners of a cube), a ray from each panel that faces that way, out towards
  where the water comes from: if it hits the hull, the panel is in a wake.

  **The coefficients.** A face meeting the water feels 0.8 of the stagnation
  pressure and a face leaving it 0.37 of it as suction, which together are a
  flat plate's 1.17 (Hoerner, Fluid-Dynamic Drag, ch. 3). The share of the
  free stream left in a wake is fitted: to the BlueROV2's surge drag measured
  by Li et al. (2020) — about 45 N at 1 m/s, read off their figure — with the
  Heavy's mesh, the only BlueROV2 mesh there is. Their measured sway is then a
  check, not a fit.
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys

import numpy as np
import trimesh

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "services/sim-runtime/coral"))

import hull_coefficients  # noqa: E402
from panels import Panels  # noqa: E402

RHO = 1025.0
FRONT, BACK = 0.8, 0.37

# Li, Cao, Li, Ingram & Kiprakis (2020), J. Mar. Sci. Eng. 8, 688, Table 2: the
# second-order fits to their drag on the standard BlueROV2, N against m/s. The
# surge points under it were measured in a current on load cells; sway and
# heave lean on their CFD.
LI = {"surge": (1.3125, 38.169), "sway": (9.1435, 129.6607), "heave": (2.015, 243.25)}
LI_YAW_QUADRATIC = 4.86          # CFD, units not stated (taken as N·m/(rad/s)²)
# What they measured, read off their figures 13 and 14 (no table is given):
# about 45 N of surge drag at 1.0 m/s and about 30 N of sway at 0.6 m/s.
LI_MEASURED = {"surge": (1.0, 45.0), "sway": (0.6, 30.0)}
WU_YAW_QUADRATIC = (1.5, 1.55)   # Wu 2018, Heavy and standard, system identification


def directions() -> np.ndarray:
    out = [d for d in itertools.product((-1, 0, 1), repeat=3) if any(d)]
    out = np.array(out, dtype=float)
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def coarse(vertices: np.ndarray, faces: np.ndarray, most: int = 60_000) -> tuple[np.ndarray, np.ndarray]:
    """A mesh too fine to cast rays against, its vertices snapped to a grid and
    merged: mini-hoot's moulded hull is a million triangles, and drag does not
    need the texture of its print lines."""
    if len(faces) <= most:
        return vertices, faces
    length = float(np.max(vertices.max(axis=0) - vertices.min(axis=0)))
    cell = length / 120.0
    while True:
        snapped, inverse = np.unique(np.round(vertices / cell).astype(np.int64), axis=0, return_inverse=True)
        f = inverse.ravel()[faces]
        f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
        f = np.unique(np.sort(f, axis=1), axis=0, return_index=True)[1]
        kept = inverse.ravel()[faces][np.sort(f)]
        if len(kept) <= most or cell > length / 20.0:
            return snapped * cell, kept
        cell *= 1.4


def outward(vertices: np.ndarray, faces: np.ndarray) -> trimesh.Trimesh:
    """The hull, each closed part's normals turned out of it."""
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    parts = mesh.split(only_watertight=False)
    for part in parts:
        trimesh.repair.fix_normals(part)
        # Wound consistently, but not necessarily outward: a part that is not
        # quite closed (a coarsened mesh seldom is) can come out inside out,
        # and its faces then meet the water from behind. Its signed volume
        # says which way round it is.
        if part.volume < 0.0:
            part.invert()
    return trimesh.util.concatenate(parts) if len(parts) > 1 else mesh


def gather(mesh: trimesh.Trimesh, cell: float) -> dict:
    """Triangles into panels: by cell, then by which way they face."""
    centres = mesh.triangles_center
    vector_area = mesh.face_normals * mesh.area_faces[:, None]
    ways = directions()
    facing = np.argmax(mesh.face_normals @ ways.T, axis=1)
    key = np.concatenate([np.floor(centres / cell).astype(np.int64), facing[:, None]], axis=1)
    _, group = np.unique(key, axis=0, return_inverse=True)
    group = group.ravel()
    n = int(group.max()) + 1
    summed = np.zeros((n, 3))
    np.add.at(summed, group, vector_area)
    weight = np.zeros(n)
    np.add.at(weight, group, mesh.area_faces)
    where = np.zeros((n, 3))
    np.add.at(where, group, centres * mesh.area_faces[:, None])
    where /= np.maximum(weight, 1e-12)[:, None]
    area = np.linalg.norm(summed, axis=1)
    keep = area > 1e-8
    return {"at": where[keep], "normal": summed[keep] / area[keep, None], "area": area[keep]}


def exposure(mesh: trimesh.Trimesh, at: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """(26, n): whether each panel meets the water coming at it from each way.

    Against a coarsened copy of the hull when it is a fine one: which way its
    faces point no longer matters here, only what is in the way."""
    ways = directions()
    v, f = coarse(np.asarray(mesh.vertices), np.asarray(mesh.faces))
    shoot = trimesh.ray.ray_triangle.RayMeshIntersector(trimesh.Trimesh(vertices=v, faces=f, process=False))
    out = np.ones((len(ways), len(at)))
    for k, way in enumerate(ways):
        facing = normal @ way > 1e-3
        if not facing.any():
            continue
        start = at[facing] + 1e-4 * normal[facing] + 1e-4 * way
        hit = shoot.intersects_any(start, np.repeat(way[None, :], int(facing.sum()), axis=0))
        out[k, np.flatnonzero(facing)] = np.where(hit, 0.0, 1.0)
    return out


def panels_of(hull: pathlib.Path, centre=None) -> tuple[dict, trimesh.Trimesh]:
    vertices, faces = hull_coefficients.load(hull)
    if centre is not None:
        vertices = vertices - np.asarray(centre, dtype=float)
    mesh = outward(vertices, faces)
    length = float(np.max(mesh.bounds[1] - mesh.bounds[0]))
    got = gather(mesh, length / 30.0)
    got["exposed"] = exposure(mesh, got["at"], got["normal"])
    # A panel that meets the water from none of the ways it faces is inside
    # the hull — the electronics in a sealed tube, the battery behind a moulded
    # shell — and no water reaches it at all, slowed or otherwise.
    facing = (got["normal"] @ directions().T) > 1e-3
    inside = ~np.any(facing.T & (got["exposed"] > 0.5), axis=0)
    for key in ("at", "normal", "area"):
        got[key] = got[key][~inside]
    got["exposed"] = got["exposed"][:, ~inside]
    return got, mesh


def rotation_quadratic(got: dict, wake: float) -> list[float]:
    """What the panels alone damp a turn by, roll, pitch and yaw, N·m/(rad/s)²."""
    panels = Panels(document(got, wake, "", rotation=[0.0, 0.0, 0.0]))
    return [round(push(panels, axis, 1.0), 4) for axis in (3, 4, 5)]


def document(got: dict, wake: float, said: str, rotation=None) -> dict:
    r = lambda a, k=5: np.round(a, k).tolist()  # noqa: E731
    if rotation is None:
        rotation = rotation_quadratic(got, wake)
    return {"note": ("The hull as panels, for the runtime's panel drag (services/sim-runtime/coral/panels.py): "
                     "where each is, which way it faces, its area, and from which of 26 directions the oncoming "
                     "water reaches it straight. Body frame, metres, origin at the centre of gravity."),
            "from": said,
            "frontCoefficient": FRONT, "backCoefficient": BACK, "wakeShare": wake,
            # What the panels give a pure turn: where a package's own rotational
            # damping is more (a measured one usually is: ducts and interference
            # no panel sees), the runtime adds only the difference.
            "rotationQuadratic": rotation,
            "centresM": r(got["at"]), "normals": r(got["normal"], 4), "areasM2": r(got["area"], 7),
            "directions": r(directions(), 4), "exposed": got["exposed"].astype(int).tolist()}


def push(panels: Panels, axis: int, speed: float) -> float:
    v = np.zeros(6)
    v[axis] = speed
    return -float(panels.wrench(v, RHO)[axis])


def check(hull: pathlib.Path) -> dict:
    """Fit the wake to Li's surge and say what that makes sway, heave and yaw."""
    got, _ = panels_of(hull)
    def with_wake(wake):
        return Panels(document(got, wake, "", rotation=[0.0, 0.0, 0.0]))
    at, target = LI_MEASURED["surge"]
    low, high = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (low + high)
        (low, high) = (mid, high) if push(with_wake(mid), 0, at) < target else (low, mid)
    wake = round(0.5 * (low + high), 3)
    p = with_wake(wake)
    table = {}
    for name, axis, speeds in (("surge", 0, (0.2, 0.6, 1.0)), ("sway", 1, (0.2, 0.6, 1.0)),
                               ("heave", 2, (0.2, 0.6, 1.0))):
        lin, quad = LI[name]
        table[name] = [{"speedMs": s, "panelsN": round(push(p, axis, s), 1),
                        "liN": round(lin * s + quad * s * s, 1)} for s in speeds]
    yaw = push(p, 5, 1.0)
    sway_at, sway_measured = LI_MEASURED["sway"]
    return {"wakeShare": wake, "panels": len(got["area"]), "table": table,
            "swayMeasured": {"speedMs": sway_at, "panelsN": round(push(p, 1, sway_at), 1), "liMeasuredN": sway_measured},
            "yawQuadratic": round(yaw, 2), "yawLi": LI_YAW_QUADRATIC, "yawWu": WU_YAW_QUADRATIC}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("hull", nargs="?")
    ap.add_argument("--into", help="a package directory to write panels.json into")
    ap.add_argument("--wake", type=float, help="the wake share; fitted on the BlueROV2 when not given")
    ap.add_argument("--check", action="store_true", help="the BlueROV2 Heavy's mesh against Li et al.")
    args = ap.parse_args(argv)
    heavy = ROOT / "catalog/vehicles/bluerov2-heavy/bluerov2-heavy.usd"
    if args.check or args.hull is None:
        print(json.dumps(check(heavy), indent=1))
        return 0
    wake = args.wake if args.wake is not None else check(heavy)["wakeShare"]
    got, _ = panels_of(pathlib.Path(args.hull))
    said = (f"derived: {len(got['area'])} panels of {pathlib.Path(args.hull).name} (hardware/hull_panels.py); "
            f"front 0.8 and back 0.37 of the dynamic pressure, a flat plate's 1.17 (Hoerner 1965); the wake share "
            f"{wake} fitted to the BlueROV2's surge drag measured by Li et al. (2020), about 45 N at 1 m/s, with the Heavy's mesh")
    if args.into:
        out = pathlib.Path(args.into) / "panels.json"
        out.write_text(json.dumps(document(got, wake, said)) + "\n")
        print(f"{len(got['area'])} panels -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
