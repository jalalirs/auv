"""Coral colonies at the detail of a photograph of one.

`coral.py` grows a reef's worth of colonies cheaply: a brain coral there is a
dome of three hundred points with a ripple on it, which reads as a coral from
ten metres and as a ball of clay from one. These are the close-up versions,
made the way the real ones are made rather than painted on afterwards:

  brain    a dome, lumped, whose grooves are grown *on its own surface* by a
           Gray-Scott reaction-diffusion: two substances spreading and
           reacting across the mesh settle into the meandering ridges and
           valleys a Platygyra or Diploria has. Grown on the surface, so they
           wrap the dome with no seam and no stretching, at the valley width
           the genus has (a ridge-to-ridge period of about a centimetre).
  porites  a boulder made of lobes, the shape Porites lutea and lobata take in
           the Red Sea: hillocks of four to twelve centimetres on a dome,
           pitted finely all over (the pits are in the material, not here).

Each comes back as vertices (metres, z up, base at z = 0), triangles and a
colour per vertex, from a palette read off colonies cut out of Red Sea dive
video (ml/cover catalogs). Writes PLY so anything can open it.

    tools/coral_hd brain --into /tmp/brain.ply --seed 3
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np

# Colours of the living surface, as (ridge or lobe top, valley or lobe side).
# Read off cut-outs of the Red Sea videos' brain corals and Porites, with the
# water's blue-green cast taken back out by eye. Chosen, not measured.
PALETTES = {
    "brain": [((0.62, 0.60, 0.42), (0.26, 0.27, 0.16)),     # green-tan, the commonest
              ((0.66, 0.54, 0.36), (0.30, 0.22, 0.13)),     # brown
              ((0.78, 0.60, 0.48), (0.42, 0.28, 0.22)),     # the pink-orange ones
              ((0.70, 0.70, 0.58), (0.34, 0.36, 0.28))],    # pale
    "porites": [((0.70, 0.60, 0.40), (0.48, 0.40, 0.25)),   # tan
                ((0.52, 0.56, 0.40), (0.33, 0.37, 0.24)),   # olive
                ((0.78, 0.72, 0.58), (0.56, 0.50, 0.38)),   # cream
                ((0.68, 0.46, 0.30), (0.45, 0.28, 0.17))],  # the orange-brown ones
}


def icosphere(level: int) -> tuple[np.ndarray, np.ndarray]:
    """A unit sphere of triangles, each edge split `level` times."""
    t = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                  [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    f = np.array([[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2],
                  [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5],
                  [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]])
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    for _ in range(level):
        edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
        unique, inverse = np.unique(edges, axis=0, return_inverse=True)
        mid = v[unique[:, 0]] + v[unique[:, 1]]
        mid /= np.linalg.norm(mid, axis=1, keepdims=True)
        m = len(v) + inverse.reshape(3, -1).T                       # midpoints of (01, 12, 20) per face
        v = np.concatenate([v, mid])
        a, b, c = f[:, 0], f[:, 1], f[:, 2]
        ab, bc, ca = m[:, 0], m[:, 1], m[:, 2]
        f = np.concatenate([np.stack([a, ab, ca], 1), np.stack([b, bc, ab], 1),
                            np.stack([c, ca, bc], 1), np.stack([ab, bc, ca], 1)])
    return v, f


def upper(v: np.ndarray, f: np.ndarray, below: float = -0.05) -> tuple[np.ndarray, np.ndarray]:
    """The part of a sphere above `below` (a dome bedded slightly into the seabed)."""
    keep = v[:, 2] >= below
    whole = keep[f].all(1)
    used = np.unique(f[whole])
    index = -np.ones(len(v), int)
    index[used] = np.arange(len(used))
    return v[used], index[f[whole]]


def laplacian(v: np.ndarray, f: np.ndarray):
    """Uniform graph Laplacian, scaled so it matches a grid's four-neighbour
    stencil at the mesh's own spacing: L u = (mean of neighbours - u) * 4."""
    from scipy import sparse

    n = len(v)
    i = np.concatenate([f[:, 0], f[:, 1], f[:, 2], f[:, 1], f[:, 2], f[:, 0]])
    j = np.concatenate([f[:, 1], f[:, 2], f[:, 0], f[:, 0], f[:, 1], f[:, 2]])
    a = sparse.coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr()
    a.data[:] = 1.0
    degree = np.asarray(a.sum(1)).ravel()
    return (sparse.diags(4.0 / degree) @ a - sparse.diags(np.full(n, 4.0))).tocsr()


def gray_scott(lap, rng, steps: int = 24000, feed: float = 0.037, kill: float = 0.06,
               du: float = 0.05, dv: float = 0.025) -> np.ndarray:
    """The Gray-Scott pattern on a mesh: v per vertex, 0 to 1. With this feed
    and kill it settles into long meanders, the labyrinth a brain coral is.
    Grown on the undeformed dome, where the mesh's spacing is even, so the
    valleys come out one width everywhere; the humps then carry them."""
    n = lap.shape[0]
    u, v = np.ones(n), np.zeros(n)
    seed = rng.random(n) < 0.12
    v[seed], u[seed] = 0.5, 0.5
    for _ in range(steps):
        uvv = u * v * v
        u += du * (lap @ u) - uvv + feed * (1 - u)
        v += dv * (lap @ v) + uvv - (feed + kill) * v
    return (v - v.min()) / (np.ptp(v) + 1e-9)


def _bumps(directions: np.ndarray, rng, count: int, width: tuple, height: tuple) -> np.ndarray:
    """A sum of smooth bumps over the unit sphere: `count` of them, each a
    Gaussian in angle `width` (radians) wide and `height` (a fraction of the
    radius) high, centred on random directions in the upper half."""
    centres = rng.normal(size=(count, 3))
    centres[:, 2] = np.abs(centres[:, 2]) + 0.2
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    w = rng.uniform(*width, count)
    h = rng.uniform(*height, count)
    out = np.zeros(len(directions))
    for c, wi, hi in zip(centres, w, h):
        angle = np.arccos(np.clip(directions @ c, -1, 1))
        out += hi * np.exp(-0.5 * (angle / wi) ** 2)
    return out


def _normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    out = np.zeros_like(v)
    for k in range(3):
        np.add.at(out, f[:, k], n)
    return out / (np.linalg.norm(out, axis=1, keepdims=True) + 1e-12)


def _shade(ridge: np.ndarray, palette, rng, directions, z: np.ndarray) -> np.ndarray:
    """Colour per vertex: the palette's light on the ridges and dark in the
    valleys, a slow mottle over the colony, and the bottom edge darker where
    turf and sediment take the tissue back."""
    top, low = (np.asarray(c) for c in palette)
    mottle = 1.0 + 0.10 * (_bumps(directions, rng, 25, (0.15, 0.5), (-1, 1)) / 2.0)
    colour = low[None] + (top - low)[None] * ridge[:, None]
    base = np.clip(z / max(z.max(), 1e-6) / 0.15, 0, 1)[:, None]           # the bottom 15% of its height
    colour = colour * mottle[:, None] * (0.55 + 0.45 * base)
    return np.clip(colour, 0, 1)


def brain(rng, diameter: float = 0.55, level: int = 8, ridge_m: float = 0.005, palette=None):
    """A brain coral colony: vertices (m), triangles, colours."""
    d, f = upper(*icosphere(level))
    squash = rng.uniform(0.4, 0.6)                                        # domes are lower than spheres
    # Two to four humps, as a smooth union of broad caps: a brain coral grows
    # as lobes that meet in folds, not as an egg.
    count = int(rng.integers(2, 5))
    centres = rng.normal(size=(count, 3))
    centres[:, 2] = np.abs(centres[:, 2]) * 0.6 + 0.3
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    width = rng.uniform(0.55, 0.95, count)
    height = rng.uniform(0.12, 0.32, count)
    angle = np.arccos(np.clip(d @ centres.T, -1, 1))
    caps = height[None] * np.clip(1 - (angle / width[None]) ** 2, 0, None) ** 0.5
    sharp = 30.0
    humps = np.log(np.exp(sharp * caps).sum(1) + np.exp(0.0)) / sharp
    lumps = humps + _bumps(d, rng, 6, (0.3, 0.6), (0.01, 0.04))
    r = diameter / 2 * (1 + lumps)
    v = d * r[:, None] * np.array([1, 1, squash])
    v[:, 2] -= v[:, 2].min()
    pattern = gray_scott(laplacian(d, f), rng)
    ridge = np.clip((pattern - 0.25) / 0.5, 0, 1)                          # 1 on the ridge, 0 in the valley
    ridge = ridge * ridge * (3 - 2 * ridge)
    v = v + _normals(v, f) * (ridge[:, None] - 0.5) * ridge_m
    palette = palette or PALETTES["brain"][rng.integers(len(PALETTES["brain"]))]
    # Ridge and valley are the same tissue; the valley is darker by its own
    # shadow, which the renderer draws, and a little by its colour.
    return v, f, _shade(0.65 + 0.35 * ridge, palette, rng, d, v[:, 2])


def porites(rng, diameter: float = 0.60, voxel: float = 0.003, palette=None):
    """A Porites boulder, as a smooth union of lobes.

    Each lobe is a sphere, written as its distance function |p - c| - r; the
    colony is their smooth minimum, so neighbouring lobes merge into one
    surface with a rounded crease between them, the way a Porites boulder's
    lobes do, and the mesh is pulled out of that field by marching cubes
    (`voxel` metres a cell). Lobes four to eleven centimetres across sit on a
    mound, packed so no smooth dome shows between them, over a core that
    fills the inside. The fine pitting is the material's."""
    from skimage.measure import marching_cubes

    radius = diameter / 2
    squash = rng.uniform(0.55, 0.8)
    lobes = []
    # Darts on the mound's surface, each a lobe; a dart too close to one
    # already thrown is thrown again, so they pack without stacking.
    tries = 0
    while tries < 6000:
        tries += 1
        d = rng.normal(size=3)
        d[2] = abs(d[2]) * 1.2 + 0.05
        d /= np.linalg.norm(d)
        r = rng.uniform(0.04, 0.08) * (0.6 + 0.4 * d[2])                  # smaller towards the rim
        c = d * np.array([radius, radius, radius * squash]) * rng.uniform(0.88, 1.0)
        if any(np.linalg.norm(c - c2) < 0.62 * (r + r2) for c2, r2 in lobes):
            continue
        lobes.append((c, r))
    # And on every lobe, knobs: the second scale, a centimetre and a half to
    # three and a half across, which is what makes the surface a cauliflower.
    knobs = []
    for c, r in lobes:
        for _ in range(int(rng.integers(20, 36))):
            u = rng.normal(size=3)
            u[2] = abs(u[2]) + 0.3
            u /= np.linalg.norm(u)
            r2 = rng.uniform(0.015, 0.035)
            knobs.append((c + u * (r - 0.35 * r2), r2))
    spheres = lobes + knobs
    centres = np.array([c for c, _ in spheres])
    radii = np.array([r for _, r in spheres])
    k = 0.005                                                              # how round the creases are, m
    lo = np.array([-radius * 1.4, -radius * 1.4, -0.02])
    hi = np.array([radius * 1.4, radius * 1.4, radius * squash + 0.3])
    axes = [np.arange(a, b, voxel) for a, b in zip(lo, hi)]
    shape = tuple(len(a) for a in axes)
    # Smooth minimum by log-sum-exp, each sphere added only inside its own
    # box (beyond a few k its term is nothing), so thousands of knobs are cheap.
    total = np.zeros(shape, np.float64)
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")
    core = np.sqrt(gx ** 2 + gy ** 2 + (gz / squash) ** 2) - radius * 0.8
    total += np.exp(-np.clip(core, -0.1, 0.1) / k)
    reach = 8 * k
    for c, r in zip(centres, radii):
        a = np.maximum(((c - r - reach - lo) / voxel).astype(int), 0)
        b = np.minimum(((c + r + reach - lo) / voxel).astype(int) + 1, shape)
        sl = tuple(slice(i, j) for i, j in zip(a, b))
        dist = np.sqrt((gx[sl] - c[0]) ** 2 + (gy[sl] - c[1]) ** 2 + (gz[sl] - c[2]) ** 2) - r
        total[sl] += np.exp(-np.clip(dist, -0.1, 0.1) / k)
    field = -k * np.log(total + 1e-300)
    for _ in range(4):
        w = rng.normal(size=3)
        w *= 2 * np.pi / rng.uniform(0.05, 0.12) / np.linalg.norm(w)
        field += rng.uniform(0.001, 0.002) * np.sin(gx * w[0] + gy * w[1] + gz * w[2] + rng.uniform(0, 2 * np.pi))
    field = np.maximum(field, -gz)                                         # cut flat at the seabed
    v, f, normals, _ = marching_cubes(field, level=0.0, spacing=(voxel, voxel, voxel))
    v = v + lo
    f = f[:, ::-1]                                                         # outward winding
    v[:, 2] -= v[:, 2].min()
    # How deep in a crease each point is: the plain nearest lobe is further
    # than the smooth surface there. Creases are shaded and darker.
    from scipy.spatial import cKDTree
    near = cKDTree(centres).query(v, k=8)[1]
    nearest = np.min(np.linalg.norm(v[:, None, :] - centres[near], axis=-1) - radii[near], axis=1)
    crease = np.clip(nearest / 0.01, 0, 1)
    up = np.clip(-normals[:, 2] if np.mean(normals[:, 2]) < 0 else normals[:, 2], 0, 1)
    light = np.clip(0.55 * (1 - crease) + 0.45 * up, 0, 1)
    directions = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    palette = palette or PALETTES["porites"][rng.integers(len(PALETTES["porites"]))]
    return v, f, _shade(light, palette, rng, directions, v[:, 2])


def write_ply(path: pathlib.Path, v: np.ndarray, f: np.ndarray, c: np.ndarray) -> None:
    """Binary PLY with a colour per vertex."""
    path.parent.mkdir(parents=True, exist_ok=True)
    head = ("ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n")
    vert = np.zeros(len(v), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    vert["x"], vert["y"], vert["z"] = v[:, 0], v[:, 1], v[:, 2]
    rgb = (np.clip(c, 0, 1) * 255).astype(np.uint8)
    vert["r"], vert["g"], vert["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    face = np.zeros(len(f), dtype=[("n", "u1"), ("i", "<i4", 3)])
    face["n"], face["i"] = 3, f
    with open(path, "wb") as out:
        out.write(head.encode())
        out.write(vert.tobytes())
        out.write(face.tobytes())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("form", choices=("brain", "porites"))
    ap.add_argument("--into", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--diameter", type=float)
    ap.add_argument("--level", type=int, help="brain: icosphere subdivisions")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    kw = {k: getattr(a, k) for k in ("diameter",) if getattr(a, k) is not None}
    if a.level is not None and a.form == "brain":
        kw["level"] = a.level
    v, f, c = (brain if a.form == "brain" else porites)(rng, **kw)
    write_ply(pathlib.Path(a.into), v, f, c)
    print(f"{a.form}: {len(v):,} vertices, {len(f):,} triangles, {np.ptp(v[:, 0]):.2f} m across, "
          f"{v[:, 2].max():.2f} m tall -> {a.into}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
