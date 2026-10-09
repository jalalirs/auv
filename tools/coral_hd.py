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
    "pocillopora": [((0.70, 0.56, 0.38), (0.36, 0.27, 0.16)),  # brown, the commonest
                    ((0.62, 0.62, 0.40), (0.30, 0.32, 0.18)),  # olive-green
                    ((0.80, 0.68, 0.42), (0.45, 0.36, 0.20)),  # yellow-tan
                    ((0.78, 0.58, 0.50), (0.40, 0.28, 0.24))], # the pinkish ones
    "galaxea": [((0.62, 0.66, 0.50), (0.24, 0.28, 0.20)),   # grey-green, the commonest
                ((0.70, 0.62, 0.44), (0.30, 0.26, 0.17)),   # brown
                ((0.74, 0.76, 0.66), (0.32, 0.34, 0.28))],  # pale
    "acropora": [((0.72, 0.62, 0.50), (0.38, 0.32, 0.24)),   # tan with pale tips
                 ((0.62, 0.66, 0.70), (0.30, 0.34, 0.38)),   # the blue-grey ones
                 ((0.66, 0.58, 0.40), (0.34, 0.30, 0.18))],  # olive-brown
    "plate": [((0.66, 0.56, 0.40), (0.36, 0.28, 0.18)),      # brown
              ((0.62, 0.64, 0.46), (0.30, 0.32, 0.20)),      # green-brown
              ((0.72, 0.62, 0.30), (0.42, 0.34, 0.14))],     # yellow, Turbinaria
    "millepora": [((0.86, 0.80, 0.58), (0.62, 0.52, 0.22)),  # mustard with pale edges
                  ((0.80, 0.74, 0.50), (0.55, 0.46, 0.20))],
    "leather": [((0.74, 0.70, 0.56), (0.52, 0.48, 0.34)),    # pale tan
                ((0.62, 0.62, 0.44), (0.40, 0.42, 0.28))],   # olive
    "porites": [((0.70, 0.60, 0.40), (0.48, 0.40, 0.25)),   # tan
                ((0.52, 0.56, 0.40), (0.33, 0.37, 0.24)),   # olive
                ((0.78, 0.72, 0.58), (0.56, 0.50, 0.38)),   # cream
                ((0.68, 0.46, 0.30), (0.45, 0.28, 0.17))],  # the orange-brown ones
    "sponge": [((0.62, 0.30, 0.20), (0.30, 0.12, 0.08)),    # rust-red barrels
               ((0.48, 0.34, 0.46), (0.20, 0.13, 0.20)),    # purple tubes
               ((0.66, 0.56, 0.40), (0.30, 0.24, 0.16)),    # tan
               ((0.50, 0.50, 0.48), (0.22, 0.22, 0.21))],   # grey
    "fan": [((0.72, 0.30, 0.20), (0.48, 0.18, 0.12)),       # red-orange Annella
            ((0.80, 0.56, 0.24), (0.55, 0.36, 0.14)),       # orange-yellow
            ((0.56, 0.32, 0.26), (0.36, 0.18, 0.15))],      # brown-red Subergorgia
    "rubble": [((0.56, 0.52, 0.44), (0.30, 0.28, 0.22)),    # bare grey-tan
               ((0.46, 0.44, 0.32), (0.24, 0.24, 0.16))],   # turf-covered
    "finger": [((0.74, 0.64, 0.42), (0.40, 0.32, 0.18)),    # tan-yellow, the commonest
               ((0.62, 0.60, 0.46), (0.32, 0.30, 0.20)),    # grey-tan
               ((0.60, 0.62, 0.72), (0.30, 0.30, 0.36))],   # the blue-tipped ones
    "staghorn": [((0.82, 0.70, 0.50), (0.46, 0.36, 0.20)),  # golden-brown, pale tips
                 ((0.72, 0.60, 0.44), (0.40, 0.30, 0.18))],
    "elkhorn": [((0.80, 0.64, 0.34), (0.48, 0.34, 0.14)),   # mustard-brown
                ((0.72, 0.58, 0.36), (0.42, 0.30, 0.16))],
    "sea_rod": [((0.50, 0.36, 0.40), (0.30, 0.20, 0.24)),   # purple-brown
                ((0.74, 0.64, 0.46), (0.48, 0.40, 0.26)),   # tan
                ((0.80, 0.70, 0.36), (0.52, 0.42, 0.18))],  # yellow
    # Other reefs' colours for the same shapes, named by species.
    "lobata": [((0.72, 0.66, 0.42), (0.44, 0.38, 0.20)),    # Porites lobata: yellow-tan
               ((0.56, 0.62, 0.48), (0.30, 0.36, 0.24))],   # green-grey
    "capitata": [((0.62, 0.42, 0.30), (0.34, 0.20, 0.13)),  # Montipora capitata: red-brown
                 ((0.74, 0.56, 0.36), (0.40, 0.28, 0.16))],  # orange-tan
    "meandrina": [((0.72, 0.60, 0.48), (0.40, 0.30, 0.22)),  # Pocillopora meandrina: cream-tan
                  ((0.70, 0.56, 0.54), (0.38, 0.28, 0.28))],  # pinkish
    "orbicella": [((0.66, 0.58, 0.38), (0.34, 0.28, 0.16)),  # Orbicella: tan-brown
                  ((0.56, 0.58, 0.40), (0.28, 0.30, 0.18))],  # green-brown
    "diploria": [((0.70, 0.62, 0.42), (0.34, 0.30, 0.18)),  # grooved brain: tan
                 ((0.58, 0.60, 0.44), (0.28, 0.30, 0.20))],
    "agaricia": [((0.66, 0.54, 0.36), (0.34, 0.26, 0.16)),  # lettuce coral: brown
                 ((0.64, 0.60, 0.40), (0.32, 0.30, 0.18))],
    "ventalina": [((0.56, 0.34, 0.56), (0.34, 0.18, 0.34)),  # Gorgonia ventalina: purple
                  ((0.78, 0.70, 0.40), (0.50, 0.42, 0.20))],  # yellow
    "caribbean-sponge": [((0.48, 0.30, 0.22), (0.24, 0.12, 0.08)),  # barrel: brown-red
                         ((0.80, 0.66, 0.24), (0.48, 0.36, 0.10)),  # yellow tube
                         ((0.50, 0.32, 0.52), (0.24, 0.14, 0.26))],  # purple vase
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


# Which way a colony's patches drift in hue: greener where the algae in the
# tissue are thicker, browner, or paler where they are thinner. Chosen.
DRIFTS = np.array([(-0.6, 0.6, -0.2), (0.6, 0.0, -0.6), (0.5, 0.5, 0.5)])


def _patches(directions: np.ndarray, rng, count: int, width: tuple) -> np.ndarray:
    """Smooth patches over the colony, -1 to 1, about half of it beyond a
    half either way. Scaled by their spread, not their peak: by the peak, one
    tall bump left the rest of the colony near nought."""
    p = _bumps(directions, rng, count, width, (-1, 1))
    return np.clip((p - p.mean()) / (1.5 * p.std() + 1e-9), -1, 1)


def _shade(ridge: np.ndarray, palette, rng, directions, z: np.ndarray) -> np.ndarray:
    """Colour per vertex: the palette's light on the ridges and dark in the
    valleys, patches over the colony, and the bottom edge darker where turf
    and sediment take the tissue back.

    A living colony is not one colour. Over tens of centimetres its tissue
    shifts in shade and hue, and from a few metres that is most of what
    tells a colony from a painted stone. The first mottle here was a tenth
    either way and read in the dives as no change at all (on most of a
    colony the colour spanned 0.02); the patches are now broad (a third of
    the colony) and blotches (a few centimetres), both visible at a metre."""
    top, low = (np.asarray(c) for c in palette)
    colour = low[None] + (top - low)[None] * ridge[:, None]
    broad = _patches(directions, rng, 10, (0.35, 0.8))
    blotch = _patches(directions, rng, 60, (0.06, 0.15))
    hue = _patches(directions, rng, 8, (0.3, 0.7))
    colour = colour * (1.0 + 0.22 * broad + 0.10 * blotch)[:, None]
    colour = colour + 0.07 * hue[:, None] * DRIFTS[rng.integers(len(DRIFTS))][None]
    base = np.clip(z / max(z.max(), 1e-6) / 0.15, 0, 1)[:, None]           # the bottom 15% of its height
    colour = colour * (0.55 + 0.45 * base)
    return np.clip(colour, 0, 1)


class Field:
    """A smooth union of simple shapes, as a signed distance field on a grid.

    Shapes are spheres and capsules (a segment with a radius), each written as
    its distance function; their smooth minimum (log-sum-exp, sharpness `k`
    metres) merges neighbours with a rounded crease rather than a seam. Each
    shape is added only inside its own box, beyond which its term is nothing,
    so tens of thousands of them are cheap. `mesh` pulls the surface out by
    marching cubes."""

    def __init__(self, lo, hi, voxel: float, k: float):
        self.lo, self.voxel, self.k = np.asarray(lo, float), voxel, k
        self.axes = [np.arange(a, b, voxel, dtype=np.float32) for a, b in zip(lo, hi)]
        self.shape = tuple(len(a) for a in self.axes)
        self.total = np.zeros(self.shape, np.float32)

    def _box(self, lo, hi):
        reach = 8 * self.k
        a = np.maximum(((np.asarray(lo) - reach - self.lo) / self.voxel).astype(int), 0)
        b = np.minimum(((np.asarray(hi) + reach - self.lo) / self.voxel).astype(int) + 1, self.shape)
        if (b <= a).any():
            return None
        sl = tuple(slice(i, j) for i, j in zip(a, b))
        x, y, z = np.meshgrid(self.axes[0][sl[0]], self.axes[1][sl[1]], self.axes[2][sl[2]], indexing="ij")
        return sl, x, y, z

    def _add(self, sl, dist):
        self.total[sl] += np.exp(-np.clip(dist, -0.1, 0.1) / self.k)

    def sphere(self, c, r):
        box = self._box(np.asarray(c) - r, np.asarray(c) + r)
        if box:
            sl, x, y, z = box
            self._add(sl, np.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2) - r)

    def capsule(self, a, b, r):
        a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
        box = self._box(np.minimum(a, b) - r, np.maximum(a, b) + r)
        if box:
            sl, x, y, z = box
            ab = b - a
            t = np.clip(((x - a[0]) * ab[0] + (y - a[1]) * ab[1] + (z - a[2]) * ab[2]) / max(float(ab @ ab), 1e-12), 0, 1)
            self._add(sl, np.sqrt((x - a[0] - t * ab[0]) ** 2 + (y - a[1] - t * ab[1]) ** 2
                                  + (z - a[2] - t * ab[2]) ** 2) - r)

    def within(self, lo, hi, dist_of):
        """A shape given by its own distance function `dist_of(x, y, z)`,
        evaluated only inside the box `lo`..`hi`."""
        box = self._box(lo, hi)
        if box:
            sl, x, y, z = box
            self._add(sl, dist_of(x, y, z))

    def ellipsoid(self, c, radii, up=(0, 0, 1), along=None):
        """An ellipsoid, approximately: radii along (u, w, up), turned so its
        third axis is `up` and, when given, its first lies in the direction
        of `along`. A plate is one with a small third radius."""
        c, radii = np.asarray(c, float), np.asarray(radii, float)
        n = np.asarray(up, float) / np.linalg.norm(up)
        hint = np.asarray(along, float) if along is not None else np.array([0.31, 0.47, 0.83])
        u = hint - n * (hint @ n)
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(n, [0.31, 0.47, 0.83])
        u /= np.linalg.norm(u)
        w = np.cross(n, u)
        reach = radii.max()

        def dist(x, y, z):
            # Inigo Quilez's bound for an ellipsoid: k0 (k0 - 1) / k1, with k0
            # the point's length in units of the radii and k1 in units of their
            # squares. The plain (k0 - 1) * smallest radius underestimates the
            # distance beyond a long axis twenty times over, and in a smooth
            # union that swelled every blade into a loaf.
            dx, dy, dz = x - c[0], y - c[1], z - c[2]
            pa = dx * u[0] + dy * u[1] + dz * u[2]
            pb = dx * w[0] + dy * w[1] + dz * w[2]
            pc = dx * n[0] + dy * n[1] + dz * n[2]
            k0 = np.sqrt((pa / radii[0]) ** 2 + (pb / radii[1]) ** 2 + (pc / radii[2]) ** 2)
            k1 = np.sqrt((pa / radii[0] ** 2) ** 2 + (pb / radii[1] ** 2) ** 2 + (pc / radii[2] ** 2) ** 2)
            return k0 * (k0 - 1) / np.maximum(k1, 1e-9)

        self.within(c - reach, c + reach, dist)

    def everywhere(self, dist_of):
        """A shape too big for a box (a core mound): its distance at every cell."""
        x, y, z = np.meshgrid(*self.axes, indexing="ij")
        self._add(tuple(slice(None) for _ in range(3)), dist_of(x, y, z))

    def mesh(self, ground: float = 0.0, settle: bool = True):
        """Vertices, triangles and normals of the surface, cut flat at
        `ground`; `settle` sets its lowest point at z = 0."""
        from skimage.measure import marching_cubes

        field = -self.k * np.log(self.total + 1e-30)
        z = self.axes[2][None, None, :]
        field = np.maximum(field, ground - z)
        v, f, normals, _ = marching_cubes(field, level=0.0, spacing=(self.voxel,) * 3)
        v = v + self.lo
        if settle:
            v[:, 2] -= v[:, 2].min()
        return v, f[:, ::-1], normals


def colonise(rng, attractors: np.ndarray, roots: np.ndarray, step: float, influence: float, kill: float,
             up: float = 0.25, rounds: int = 400):
    """Space colonisation: branches grow from `roots` towards the free space
    `attractors` mark out, a step at a time, each node towards the mean of
    the attractors nearest it, and an attractor a branch has reached is used
    up. The branches fill the shape the attractors fill, never cross, and
    fork where two groups of attractors pull a node two ways. Returns node
    positions and each node's parent (-1 for a root)."""
    from scipy.spatial import cKDTree

    nodes = [np.asarray(r, float) for r in roots]
    parent = [-1] * len(nodes)
    free = np.asarray(attractors, float)
    for _ in range(rounds):
        if not len(free):
            break
        where = np.array(nodes)
        dist, near = cKDTree(where).query(free, distance_upper_bound=influence)
        pulled = np.isfinite(dist)
        if not pulled.any():
            break
        pull = np.zeros_like(where)
        towards = free[pulled] - where[near[pulled]]
        towards /= np.linalg.norm(towards, axis=1, keepdims=True) + 1e-12
        np.add.at(pull, near[pulled], towards)
        growing = np.where(np.linalg.norm(pull, axis=1) > 0)[0]
        # A step onto a node already there is the method's known stall: a
        # node pulled evenly two ways steps back and forth on the spot and
        # piles up a lump. Such a step is not taken.
        occupied = cKDTree(where)
        grew = 0
        for n in growing:
            d = pull[n] / np.linalg.norm(pull[n]) + np.array([0, 0, up])
            d /= np.linalg.norm(d)
            new = where[n] + d * step
            if occupied.query(new)[0] < 0.5 * step:
                continue
            nodes.append(new)
            parent.append(int(n))
            grew += 1
        if not grew:
            break
        dist, _ = cKDTree(np.array(nodes)).query(free)
        free = free[dist > kill]
    return np.array(nodes), np.array(parent)



def brain(rng, diameter: float = 0.55, level: int = 8, ridge_m: float = 0.005, palette=None, grooves: bool = True):
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
    if not grooves:
        # A colony for a reef, where the maze is the material's
        # (corallite.py "brain") rather than the mesh's.
        palette = palette or PALETTES["brain"][rng.integers(len(PALETTES["brain"]))]
        # Paler on top, where it faces the light, than down the sides.
        return v, f, _shade(0.55 + 0.45 * np.clip(d[:, 2], 0, 1), palette, rng, d, v[:, 2])
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


def pocillopora(rng, diameter: float = 0.60, voxel: float = 0.0015, palette=None):
    """A Pocillopora: a cushion of short branches about a centimetre thick,
    forking, each studded with verrucae (the warts a few millimetres across
    that give the colony its knobbly look) and ending in a blunt tip.

    The branches are grown by space colonisation into a cushion-shaped space
    from a handful of roots at the base; each branch is a run of capsules
    whose radius follows the pipe model (a branch is as thick as the tips it
    carries need), and the verrucae are small spheres on the upper branches,
    all merged into one surface."""
    radius = diameter / 2
    height = radius * rng.uniform(0.6, 0.85)
    # Free space to grow into: a cushion with a lobed outline (a colony grows
    # unevenly, faster where it has room), mostly its outer shell.
    pts = rng.uniform(-1, 1, size=(30000, 3))
    pts[:, 2] = np.abs(pts[:, 2])
    angle = np.arctan2(pts[:, 1], pts[:, 0])
    lobed = 1 + sum(rng.uniform(0.05, 0.15) * np.cos(m * angle + rng.uniform(0, 2 * np.pi)) for m in (2, 3, 5))
    rho = np.linalg.norm(pts, axis=1) / lobed
    # Mostly the outer shell, where the branch ends are, but a thinned trail
    # inside too: branches start at the base and need something to reach for
    # all the way out.
    keep = (rho <= 1) & ((rho > 0.6) | (rng.random(len(rho)) < 0.2))
    pts = pts[keep][:10000]
    attractors = pts * np.array([radius, radius, height])
    roots = np.column_stack([rng.normal(0, radius * 0.25, (12, 2)), np.zeros(12)])
    # Upward and outward: a Pocillopora's branches radiate from the base of the
    # colony, so each step leans away from the colony's axis as well as up.
    # A branch's neighbours stand about two of its widths away: the kill
    # distance sets that spacing, and closer than this the tips merge into a
    # carpet instead of reading as branches.
    nodes, parent = colonise(rng, attractors, roots, step=0.009, influence=0.06, kill=0.024, up=0.6)
    # Pipe model: a node's radius from how many tips it carries.
    children = np.bincount(parent[parent >= 0], minlength=len(nodes))
    tips = np.where(children == 0)[0]
    carried = np.zeros(len(nodes))
    carried[tips] = 1
    for n in range(len(nodes) - 1, -1, -1):
        if parent[n] >= 0:
            carried[parent[n]] += carried[n]
    tip_r = rng.uniform(0.0055, 0.0068)
    r = np.clip(tip_r * carried ** 0.45, tip_r, 0.016)
    # Smoothed along each branch, so its thickness changes gradually and not
    # in steps a segment long, which drew rings like a stack of coins.
    for _ in range(3):
        smooth = r.copy()
        has = parent >= 0
        smooth[has] = 0.5 * r[has] + 0.5 * r[parent[has]]
        r = np.maximum(smooth, tip_r)
    top = nodes[:, 2].max()
    field = Field(nodes.min(0) - 0.03, nodes.max(0) + 0.03, voxel, k=0.003)
    field.lo[2] = -0.01
    for n in range(len(nodes)):
        if parent[n] >= 0:
            field.capsule(nodes[parent[n]], nodes[n], r[n])
    for n in tips:
        field.sphere(nodes[n], r[n] * 1.25)                                  # the blunt, slightly swollen tip
    # Verrucae: on the upper two thirds of the branches.
    for n in np.where((parent >= 0) & (nodes[:, 2] > top * 0.33))[0]:
        a, b = nodes[parent[n]], nodes[n]
        axis = (b - a) / (np.linalg.norm(b - a) + 1e-12)
        for _ in range(int(rng.integers(2, 6))):
            side = rng.normal(size=3)
            side -= axis * (side @ axis)
            side /= np.linalg.norm(side) + 1e-12
            at = a + (b - a) * rng.uniform() + side * r[n] * 0.9
            field.sphere(at, rng.uniform(0.002, 0.003))
    v, f, normals = field.mesh()
    # Tips lighter and pinker, the bases darker: light and new growth at the
    # top, shade and older tissue below.
    from scipy.spatial import cKDTree
    to_tip = cKDTree(nodes[tips]).query(v)[0]
    tipness = np.clip(1 - to_tip / 0.015, 0, 1)
    # How far out in the cushion a point is: the inside is in the branches'
    # own shade and darker.
    outward = np.clip(np.sqrt((v[:, 0] / radius) ** 2 + (v[:, 1] / radius) ** 2 + (v[:, 2] / height) ** 2), 0, 1)
    light = np.clip(0.05 + 0.45 * outward ** 2 + 0.55 * tipness, 0, 1)
    directions = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    palette = palette or PALETTES["pocillopora"][rng.integers(len(PALETTES["pocillopora"]))]
    return v, f, _shade(light, palette, rng, directions, v[:, 2])


def galaxea(rng, diameter: float = 0.45, voxel: float = 0.003, palette=None):
    """A Galaxea: a low lumpy mound, a smooth union of a few broad lobes.

    Its corallites, cups six or seven millimetres across ringed by a dozen
    septa that make each a star, are finer than a mesh a colony can afford:
    they are the material's (corallite.py "galaxea"). Built as geometry they
    came out below the grid's resolution and left pits."""
    radius = diameter / 2
    squash = rng.uniform(0.35, 0.55)
    lobes = []
    for _ in range(int(rng.integers(5, 12))):
        d = rng.normal(size=3)
        d[2] = abs(d[2]) + 0.4
        d /= np.linalg.norm(d)
        lobes.append((d * np.array([radius, radius, radius * squash]) * rng.uniform(0.6, 0.85),
                      radius * rng.uniform(0.3, 0.5)))

    def mound(field):
        field.everywhere(lambda x, y, z: np.sqrt(x ** 2 + y ** 2 + (z / squash) ** 2) - radius * 0.75)
        for c, r in lobes:
            field.sphere(c, r)

    lo = np.array([-radius * 1.3, -radius * 1.3, -0.01])
    hi = np.array([radius * 1.3, radius * 1.3, radius * squash * 1.6 + 0.05])
    fine = Field(lo, hi, voxel, k=0.02)
    mound(fine)
    v, f, normals = fine.mesh()
    height_off = np.clip(v[:, 2] / max(v[:, 2].max(), 1e-6), 0, 1)
    light = np.clip(0.35 + 0.5 * height_off, 0, 1)
    directions = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    palette = palette or PALETTES["galaxea"][rng.integers(len(PALETTES["galaxea"]))]
    return v, f, _shade(light, palette, rng, directions, v[:, 2])


def _branching_colony(rng, nodes, parent, tip_r, max_r, voxel, k=0.003, tip_scale=1.1, lo=None, hi=None):
    """A field of capsules along a colonised skeleton, thickness by the pipe
    model and smoothed along each branch; the tips' nodes back. `lo` and `hi`
    widen the field's box for anything else that will be added to it."""
    children = np.bincount(parent[parent >= 0], minlength=len(nodes))
    tips = np.where(children == 0)[0]
    carried = np.zeros(len(nodes))
    carried[tips] = 1
    for n in range(len(nodes) - 1, -1, -1):
        if parent[n] >= 0:
            carried[parent[n]] += carried[n]
    r = np.clip(tip_r * carried ** 0.45, tip_r, max_r)
    for _ in range(3):
        smooth = r.copy()
        has = parent >= 0
        smooth[has] = 0.5 * r[has] + 0.5 * r[parent[has]]
        r = np.maximum(smooth, tip_r)
    low, high = nodes.min(0) - 0.04, nodes.max(0) + 0.04
    if lo is not None:
        low = np.minimum(low, lo)
    if hi is not None:
        high = np.maximum(high, hi)
    low[2] = -0.01
    field = Field(low, high, voxel, k=k)
    for n in range(len(nodes)):
        if parent[n] >= 0:
            field.capsule(nodes[parent[n]], nodes[n], r[n])
    for n in tips:
        field.sphere(nodes[n], r[n] * tip_scale)
    return field, tips, r


def _tips_light(v, nodes, tips, reach):
    from scipy.spatial import cKDTree

    to_tip = cKDTree(nodes[tips]).query(v)[0]
    return np.clip(1 - to_tip / reach, 0, 1)


def acropora(rng, diameter: float = 0.55, voxel: float = 0.002, palette=None):
    """A branching Acropora: a bushy thicket of slender branches that taper
    to pale tips, each branch studded with tubular corallites (the
    material's, corallite.py "acropora")."""
    radius = diameter / 2
    height = radius * rng.uniform(0.7, 1.0)
    pts = rng.uniform(-1, 1, size=(30000, 3))
    pts[:, 2] = np.abs(pts[:, 2])
    rho = np.linalg.norm(pts, axis=1)
    keep = (rho <= 1) & ((rho > 0.55) | (rng.random(len(rho)) < 0.25))
    attractors = pts[keep][:8000] * np.array([radius, radius, height])
    roots = np.column_stack([rng.normal(0, radius * 0.15, (5, 2)), np.zeros(5)])
    nodes, parent = colonise(rng, attractors, roots, step=0.012, influence=0.08, kill=0.032, up=0.9)
    field, tips, _ = _branching_colony(rng, nodes, parent, rng.uniform(0.004, 0.0055), 0.018, voxel, tip_scale=0.9)
    v, f, _ = field.mesh()
    light = np.clip(0.15 + 0.35 * v[:, 2] / max(v[:, 2].max(), 1e-6) + 0.6 * _tips_light(v, nodes, tips, 0.03), 0, 1)
    palette = palette or PALETTES["acropora"][rng.integers(len(PALETTES["acropora"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def table(rng, diameter: float = 0.8, voxel: float = 0.003, palette=None):
    """A table Acropora: a stout stalk, and on it a flat plate of fused
    branches growing out horizontally, its top bristling with short upright
    branchlets. The shape the Red Sea's fore-reef slopes are known for."""
    radius = diameter / 2
    stalk_h = rng.uniform(0.12, 0.25)
    stalk_r = rng.uniform(0.025, 0.04)
    tilt = rng.normal(0, 0.08, 2)
    top = np.array([tilt[0], tilt[1], stalk_h])
    # The plate: branches grown outwards in a thin disc at the stalk's top.
    a = rng.uniform(0, 2 * np.pi, 9000)
    rr = radius * np.sqrt(rng.uniform(0.02, 1, 9000)) * (1 + 0.12 * np.cos(3 * a + rng.uniform(0, 6)))
    attractors = np.column_stack([top[0] + rr * np.cos(a), top[1] + rr * np.sin(a),
                                  top[2] + rng.uniform(-0.01, 0.015, 9000) + 0.03 * (rr / radius)])
    roots = top[None] + np.column_stack([rng.normal(0, 0.01, (4, 2)), np.zeros(4)])
    nodes, parent = colonise(rng, attractors, roots, step=0.012, influence=0.07, kill=0.02, up=0.0)
    field, tips, r = _branching_colony(rng, nodes, parent, 0.005, 0.02, voxel, k=0.006,
                                       lo=np.array([-0.1, -0.1, -0.01]), hi=nodes.max(0) + np.array([0, 0, 0.05]))
    field.capsule(np.array([0, 0, -0.01]), top, stalk_r)
    field.sphere(np.array([0, 0, 0.0]), stalk_r * 1.6)                       # the foot
    # Branchlets: short and upright, all over the top of the plate.
    for n in np.where(parent >= 0)[0][::2]:
        base = nodes[n]
        tip = base + np.array([rng.normal(0, 0.004), rng.normal(0, 0.004), rng.uniform(0.012, 0.028)])
        field.capsule(base, tip, rng.uniform(0.0035, 0.005))
    v, f, _ = field.mesh()
    light = np.clip(0.2 + 0.6 * np.clip((v[:, 2] - stalk_h + 0.02) / 0.06, 0, 1), 0, 1)
    palette = palette or PALETTES["acropora"][rng.integers(len(PALETTES["acropora"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def plate(rng, diameter: float = 0.5, voxel: float = 0.002, palette=None):
    """Encrusting and plating coral (Montipora, Turbinaria, Echinopora): thin
    plates in overlapping tiers, each tilted up a little towards the light,
    like shelves of a fungus."""
    radius = diameter / 2
    field = Field([-radius * 1.3, -radius * 1.3, -0.01], [radius * 1.3, radius * 1.3, radius * 0.9], voxel, k=0.004)
    tiers = int(rng.integers(5, 11))
    for i in range(tiers):
        h = 0.02 + (i / tiers) * radius * rng.uniform(0.4, 0.7)
        a = rng.uniform(0, 2 * np.pi)
        out = radius * rng.uniform(0.0, 0.45) * (1 - i / tiers)
        c = np.array([out * np.cos(a), out * np.sin(a), h])
        size = radius * rng.uniform(0.45, 0.8) * (1 - 0.5 * i / tiers)
        up = np.array([np.cos(a) * 0.35, np.sin(a) * 0.35, 1.0]) + rng.normal(0, 0.15, 3)
        field.ellipsoid(c, (size, size * rng.uniform(0.7, 1.0), rng.uniform(0.009, 0.013)), up)
        field.capsule(np.array([c[0] * 0.3, c[1] * 0.3, 0]), c, 0.02)       # what holds the tier up
    v, f, normals = field.mesh()
    up_facing = np.clip(np.abs(normals[:, 2]), 0, 1)
    light = np.clip(0.3 + 0.6 * up_facing, 0, 1)
    palette = palette or PALETTES["plate"][rng.integers(len(PALETTES["plate"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def millepora(rng, diameter: float = 0.45, voxel: float = 0.0018, palette=None):
    """Fire coral (Millepora dichotoma, platyphylla): upright blades and
    crests that branch and fuse, mustard yellow with pale edges."""
    radius = diameter / 2
    field = Field([-radius * 1.2, -radius * 1.2, -0.01], [radius * 1.2, radius * 1.2, radius * 1.3], voxel, k=0.003)
    edges = []
    for _ in range(int(rng.integers(3, 7))):
        a = rng.uniform(0, np.pi)
        along = np.array([np.cos(a), np.sin(a), 0.0])
        off = rng.normal(0, radius * 0.35, 2)
        h = radius * rng.uniform(0.6, 1.1)
        # A blade is a row of overlapping upright ellipsoids, its crest wavy.
        for t in np.linspace(-1, 1, 12):
            base = np.array([off[0], off[1], 0]) + along * t * radius * 0.8
            top = h * (1 - 0.35 * t * t) * (1 + 0.1 * np.sin(5 * t + a))
            across = np.array([-along[1], along[0], 0.0])
            field.ellipsoid(base + np.array([0, 0, top / 2]), (radius * 0.12, top / 2, 0.005),
                            up=across, along=along)
            edges.append(base + np.array([0, 0, top]))
    v, f, _ = field.mesh()
    from scipy.spatial import cKDTree
    to_edge = cKDTree(np.array(edges)).query(v)[0]
    light = np.clip(0.3 + 0.7 * np.clip(1 - to_edge / 0.04, 0, 1), 0, 1)
    palette = palette or PALETTES["millepora"][rng.integers(len(PALETTES["millepora"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def leather(rng, diameter: float = 0.45, voxel: float = 0.0025, palette=None):
    """A leather coral (Sarcophyton): a thick stalk and a broad cap whose
    margin folds in waves, smooth, pale tan or olive."""
    radius = diameter / 2
    stalk_h = rng.uniform(0.06, 0.14)
    folds = int(rng.integers(5, 10))
    amp = rng.uniform(0.02, 0.045)
    phase = rng.uniform(0, 2 * np.pi)
    field = Field([-radius * 1.3, -radius * 1.3, -0.01], [radius * 1.3, radius * 1.3, stalk_h + 0.12], voxel, k=0.01)
    field.capsule(np.array([0, 0, 0.0]), np.array([0, 0, stalk_h]), radius * rng.uniform(0.25, 0.35))

    def cap(x, y, z):
        rr = np.sqrt(x * x + y * y)
        th = np.arctan2(y, x)
        edge = radius * (1 + 0.08 * np.sin(3 * th + phase))
        sag = amp * np.sin(folds * th + phase) * (rr / radius) ** 2 + 0.03 * (rr / radius) ** 2
        mid = stalk_h + 0.02 + sag
        thick = 0.012 * (1 - 0.5 * np.clip(rr / edge, 0, 1)) + 0.004
        return np.maximum(np.abs(z - mid) - thick, rr - edge)

    field.within(np.array([-radius * 1.2, -radius * 1.2, stalk_h - 0.07]),
                 np.array([radius * 1.2, radius * 1.2, stalk_h + 0.1]), cap)
    v, f, _ = field.mesh()
    light = np.clip(0.4 + 0.5 * np.clip((v[:, 2] - stalk_h * 0.5) / 0.06, 0, 1), 0, 1)
    palette = palette or PALETTES["leather"][rng.integers(len(PALETTES["leather"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def sponge(rng, diameter: float = 0.35, voxel: float = 0.004, palette=None):
    """A barrel or tube sponge: one to four thick-walled tubes, waisted at
    the holdfast, widest two thirds up, open at the top, the outside ribbed
    lengthwise as a barrel sponge's is. Darker inside the opening."""
    tubes = int(rng.choice([1, 1, 2, 3, 4]))
    reach = diameter / 2
    tall = diameter * rng.uniform(0.9, 1.6) if tubes > 1 else diameter * rng.uniform(0.7, 1.1)
    field = Field([-reach * 1.6, -reach * 1.6, -0.01], [reach * 1.6, reach * 1.6, tall * 1.25], voxel, k=0.006)
    axes = []
    for _ in range(tubes):
        away = rng.uniform(0, 2 * np.pi)
        at = np.array([np.cos(away), np.sin(away), 0.0]) * (reach * 0.45 if tubes > 1 else 0.0)
        h = tall * rng.uniform(0.7, 1.15)
        r0 = (reach if tubes == 1 else reach * rng.uniform(0.35, 0.55))
        lean = np.array([at[0] * 0.6, at[1] * 0.6, h]) / max(h, 1e-6)
        wall = r0 * rng.uniform(0.22, 0.32)
        ribs, rib_h, phase = int(rng.integers(8, 16)), r0 * rng.uniform(0.04, 0.08), rng.uniform(0, 2 * np.pi)

        def tube(x, y, z, at=at, h=h, r0=r0, lean=lean, wall=wall, ribs=ribs, rib_h=rib_h, phase=phase):
            s = np.clip(z / h, 0, 1)
            cx, cy = at[0] + lean[0] * z, at[1] + lean[1] * z
            dx, dy = x - cx, y - cy
            rr = np.sqrt(dx * dx + dy * dy)
            th = np.arctan2(dy, dx)
            outer = r0 * (0.55 + 0.5 * np.sin(np.pi * np.clip(s, 0, 1) ** 0.8)) + rib_h * np.sin(ribs * th + phase)
            inner = outer - wall
            shell = np.maximum(rr - outer, inner - rr)
            return np.maximum(np.maximum(shell, z - h), -z)

        field.within(np.array([-reach * 1.6, -reach * 1.6, -0.01]), np.array([reach * 1.6, reach * 1.6, h + 0.02]), tube)
        axes.append((at, lean, h, r0, wall))
    v, f, _ = field.mesh()
    # Darker in the opening and down its throat: the light does not get in.
    inside = np.zeros(len(v), bool)
    for at, lean, h, r0, wall in axes:
        cx, cy = at[0] + lean[0] * v[:, 2], at[1] + lean[1] * v[:, 2]
        rr = np.hypot(v[:, 0] - cx, v[:, 1] - cy)
        s = np.clip(v[:, 2] / h, 0, 1)
        outer = r0 * (0.55 + 0.5 * np.sin(np.pi * s ** 0.8))
        inside |= (rr < outer - wall * 0.5) & (v[:, 2] > h * 0.15)
    light = np.where(inside, 0.15, 0.6 + 0.4 * np.clip(v[:, 2] / max(v[:, 2].max(), 1e-6), 0, 1))
    palette = palette or PALETTES["sponge"][rng.integers(len(PALETTES["sponge"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def fan(rng, diameter: float = 0.8, voxel: float = 0.0025, palette=None):
    """A sea fan (Annella, Subergorgia): a flat net of thin branches in one
    upright plane, grown by space colonisation from a short trunk, and the
    branches that grow close fused across into a mesh, as Annella's do."""
    from scipy.spatial import cKDTree

    radius = diameter / 2
    height = diameter * rng.uniform(0.8, 1.1)
    pts = rng.uniform(-1, 1, size=(20000, 2))
    # A fan: a half disc, wider than tall, raised on its trunk.
    keep = (pts[:, 0] ** 2 + pts[:, 1] ** 2 <= 1) & (pts[:, 1] > -0.15)
    pts = pts[keep][:7000]
    attractors = np.column_stack([pts[:, 0] * radius, rng.normal(0, 0.004, len(pts)),
                                  0.04 * height + (pts[:, 1] + 0.15) / 1.15 * 0.96 * height])
    trunk = int(rng.integers(3, 6))
    roots = [np.array([0, 0, 0.0])]
    nodes, parent = colonise(rng, attractors, np.array(roots), step=0.01, influence=0.07, kill=0.02, up=0.15)
    nodes[:, 1] = np.clip(nodes[:, 1], -0.01, 0.01)
    tip_r, max_r = rng.uniform(0.0022, 0.003), rng.uniform(0.008, 0.012)
    field, _, _ = _branching_colony(rng, nodes, parent, tip_r, max_r, voxel, k=0.0015, tip_scale=1.0,
                                       lo=np.array([-radius - 0.05, -0.05, 0]), hi=np.array([radius + 0.05, 0.05, height + 0.05]))
    # The net: a node near another branch's node, not its own parent or
    # child, is joined to it.
    tree = cKDTree(nodes)
    along = nodes - nodes[np.maximum(parent, 0)]
    along /= np.linalg.norm(along, axis=1, keepdims=True) + 1e-9
    for a, b in tree.query_pairs(0.032):
        if parent[a] == b or parent[b] == a or nodes[a, 2] < trunk * 0.015:
            continue
        # Across, not along: a join along a branch is the branch again.
        ab = (nodes[b] - nodes[a]) / (np.linalg.norm(nodes[b] - nodes[a]) + 1e-9)
        if abs(ab @ along[a]) > 0.5 or abs(ab @ along[b]) > 0.5:
            continue
        if rng.random() < 0.5:
            field.capsule(nodes[a], nodes[b], tip_r)
    v, f, _ = field.mesh()
    light = np.clip(0.45 + 0.55 * v[:, 2] / max(v[:, 2].max(), 1e-6), 0, 1)
    palette = palette or PALETTES["fan"][rng.integers(len(PALETTES["fan"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def rubble(rng, diameter: float = 0.4, voxel: float = 0.003, palette=None):
    """Coral rubble: broken branch ends and a few rolled blocks, lying in a
    heap, grey-brown with turf and pink patches of coralline algae."""
    radius = diameter / 2
    field = Field([-radius * 1.2, -radius * 1.2, -0.01], [radius * 1.2, radius * 1.2, radius * 0.6], voxel, k=0.004)
    for _ in range(int(rng.integers(45, 90))):
        at = np.array([*rng.normal(0, radius * 0.35, 2), 0.0])
        if np.linalg.norm(at[:2]) > radius:
            continue
        length = rng.uniform(0.03, 0.10)
        turn = rng.uniform(0, 2 * np.pi)
        tilt = rng.uniform(-0.3, 0.3)
        d = np.array([np.cos(turn), np.sin(turn), tilt])
        d /= np.linalg.norm(d)
        thick = rng.uniform(0.006, 0.014)
        at[2] = thick + rng.exponential(0.008)                     # most on the sand, some on others
        field.capsule(at - d * length / 2, at + d * length / 2, thick)
        if rng.random() < 0.4:                                      # a stub of a side branch
            side = d + rng.normal(0, 0.8, 3)
            side /= np.linalg.norm(side)
            field.capsule(at, at + side * length * 0.35, thick * 0.7)
    for _ in range(int(rng.integers(1, 4))):
        at = np.array([*rng.normal(0, radius * 0.3, 2), 0.0])
        size = rng.uniform(0.03, 0.07)
        field.ellipsoid(at, (size * rng.uniform(1, 1.6), size, size * 0.6), up=rng.normal(0, 0.2, 3) + [0, 0, 1])
    v, f, _ = field.mesh()
    light = np.clip(0.5 + 0.5 * v[:, 2] / max(v[:, 2].max(), 1e-6), 0, 1)
    palette = palette or PALETTES["rubble"][rng.integers(len(PALETTES["rubble"]))]
    colour = _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])
    # Crustose coralline algae: pink patches on the tops.
    pink = np.clip(_patches(v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), rng, 12, (0.2, 0.5)), 0, 1)
    pink = pink * np.clip(v[:, 2] / max(v[:, 2].max(), 1e-6) * 2, 0, 1)
    return v, f, np.clip(colour * (1 - 0.6 * pink[:, None]) + np.array([0.62, 0.42, 0.46]) * 0.6 * pink[:, None], 0, 1)


def finger(rng, diameter: float = 0.5, voxel: float = 0.003, palette=None):
    """Finger coral (Porites compressa in Hawaii, Porites porites in the
    Caribbean): a clump of stubby upright fingers two to three centimetres
    thick, club-ended, forking once or twice, packed close on a low base."""
    radius = diameter / 2
    height = radius * rng.uniform(0.6, 0.9)
    pts = rng.uniform(-1, 1, size=(20000, 3))
    pts[:, 2] = np.abs(pts[:, 2])
    # Fingers stand: the space they grow into is the colony's upper part, and
    # they start all over a broad base rather than from a few roots.
    rho = np.linalg.norm(pts, axis=1)
    keep = (rho <= 1) & (pts[:, 2] > 0.25)
    attractors = pts[keep][:5000] * np.array([radius, radius, height])
    spread = np.sqrt(rng.uniform(0, 1, 60)) * radius * 0.8
    turn = rng.uniform(0, 2 * np.pi, 60)
    roots = np.column_stack([spread * np.cos(turn), spread * np.sin(turn), np.full(60, height * 0.15)])
    nodes, parent = colonise(rng, attractors, roots, step=0.012, influence=0.12, kill=0.034, up=3.0)
    tip_r = rng.uniform(0.010, 0.013)
    field, tips, _ = _branching_colony(rng, nodes, parent, tip_r, 0.022, voxel, k=0.005, tip_scale=1.25,
                                       lo=np.array([-radius, -radius, 0]), hi=np.array([radius, radius, height]))
    # The fingers stand on a low mound of their own dead bases.
    field.ellipsoid(np.array([0, 0, 0.0]), (radius * 0.85, radius * 0.85, height * 0.3))
    v, f, _ = field.mesh()
    light = np.clip(0.25 + 0.35 * v[:, 2] / max(v[:, 2].max(), 1e-6) + 0.45 * _tips_light(v, nodes, tips, 0.025), 0, 1)
    palette = palette or PALETTES["finger"][rng.integers(len(PALETTES["finger"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def staghorn(rng, diameter: float = 0.8, voxel: float = 0.003, palette=None):
    """Staghorn coral (Acropora cervicornis): long cylindrical branches a
    couple of centimetres thick, few and far apart, reaching out and up at a
    slant and forking at wide angles, with pale growing tips."""
    radius = diameter / 2
    height = radius * rng.uniform(0.6, 0.9)
    pts = rng.uniform(-1, 1, size=(20000, 3))
    pts[:, 2] = np.abs(pts[:, 2])
    keep = np.linalg.norm(pts, axis=1) <= 1
    attractors = pts[keep][:2500] * np.array([radius, radius, height])
    roots = np.column_stack([rng.normal(0, radius * 0.1, (3, 2)), np.zeros(3)])
    nodes, parent = colonise(rng, attractors, roots, step=0.02, influence=0.16, kill=0.07, up=0.35)
    tip_r = rng.uniform(0.007, 0.009)
    field, tips, _ = _branching_colony(rng, nodes, parent, tip_r, 0.016, voxel, k=0.003, tip_scale=0.9)
    v, f, _ = field.mesh()
    light = np.clip(0.3 + 0.25 * v[:, 2] / max(v[:, 2].max(), 1e-6) + 0.6 * _tips_light(v, nodes, tips, 0.04), 0, 1)
    palette = palette or PALETTES["staghorn"][rng.integers(len(PALETTES["staghorn"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def elkhorn(rng, diameter: float = 1.0, voxel: float = 0.005, palette=None):
    """Elkhorn coral (Acropora palmata): a thick trunk and broad flattened
    branches like a moose's antlers, spreading out and up, forking into
    blunt flat lobes; mustard-brown with pale margins."""
    radius = diameter / 2
    trunk_h = rng.uniform(0.08, 0.18)
    field = Field([-radius * 1.3, -radius * 1.3, -0.01], [radius * 1.3, radius * 1.3, trunk_h + radius * 0.9], voxel, k=0.005)
    field.capsule([0, 0, 0], [0, 0, trunk_h], rng.uniform(0.05, 0.08))
    margins = []

    def blade(start, heading, rise, length, width, depth):
        if depth > 2 or length < 0.06:
            return
        d = np.array([np.cos(heading), np.sin(heading), rise])
        d /= np.linalg.norm(d)
        end = start + d * length
        mid = (start + end) / 2
        flat_up = np.cross(d, np.cross([0, 0, 1], d))
        flat_up = flat_up / (np.linalg.norm(flat_up) + 1e-9) if np.linalg.norm(flat_up) > 1e-6 else np.array([0, 0, 1.0])
        field.ellipsoid(mid, (length * 0.55, width, 0.014), up=flat_up, along=d)
        if depth == 3 or rng.random() < 0.15:
            margins.append(end)
            return
        for turn in (-1, 1):
            blade(end - d * length * 0.1, heading + turn * rng.uniform(0.35, 0.6), rise * 0.8,
                  length * rng.uniform(0.6, 0.75), width * 0.85, depth + 1)

    # A few main antlers, spread evenly round the trunk so they do not merge.
    main = int(rng.integers(2, 5))
    first = rng.uniform(0, 2 * np.pi)
    for m in range(main):
        blade(np.array([0, 0, trunk_h]), first + 2 * np.pi * m / main + rng.normal(0, 0.2), rng.uniform(0.25, 0.6),
              radius * rng.uniform(0.3, 0.42), rng.uniform(0.045, 0.06), 0)
    v, f, _ = field.mesh()
    from scipy.spatial import cKDTree
    edge = np.clip(1 - cKDTree(np.array(margins)).query(v)[0] / 0.08, 0, 1) if margins else np.zeros(len(v))
    light = np.clip(0.35 + 0.3 * v[:, 2] / max(v[:, 2].max(), 1e-6) + 0.4 * edge, 0, 1)
    palette = palette or PALETTES["elkhorn"][rng.integers(len(PALETTES["elkhorn"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


def sea_rod(rng, diameter: float = 0.6, voxel: float = 0.0025, palette=None):
    """A sea rod or sea plume (Eunicea, Plexaura, Antillogorgia): a bush of
    thin flexible upright branches from one holdfast, candelabra-like,
    taller than wide, swaying; purple-brown, tan or yellow."""
    radius = diameter / 2
    height = diameter * rng.uniform(0.9, 1.4)
    pts = rng.uniform(-1, 1, size=(20000, 3))
    pts[:, 2] = np.abs(pts[:, 2])
    keep = (np.linalg.norm(pts[:, :2], axis=1) <= 0.3 + 0.7 * pts[:, 2]) & (pts[:, 2] > 0.1)
    attractors = pts[keep][:3000] * np.array([radius, radius, height])
    nodes, parent = colonise(rng, attractors, np.array([[0, 0, 0.0]]), step=0.015, influence=0.15, kill=0.05, up=1.0)
    # Sway: each node pushed sideways by a gentle curve that grows with height.
    lean = rng.normal(0, 0.12, 2)
    nodes[:, :2] += lean[None] * (nodes[:, 2:3] / max(height, 1e-6)) ** 2 * height
    tip_r = rng.uniform(0.0035, 0.005)
    field, tips, _ = _branching_colony(rng, nodes, parent, tip_r, 0.012, voxel, k=0.002, tip_scale=1.0,
                                       lo=np.array([-radius * 1.5, -radius * 1.5, 0]), hi=np.array([radius * 1.5, radius * 1.5, height * 1.1]))
    v, f, _ = field.mesh()
    light = np.clip(0.5 + 0.3 * v[:, 2] / max(v[:, 2].max(), 1e-6) + 0.2 * _tips_light(v, nodes, tips, 0.03), 0, 1)
    palette = palette or PALETTES["sea_rod"][rng.integers(len(PALETTES["sea_rod"]))]
    return v, f, _shade(light, palette, rng, v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9), v[:, 2])


FORMS = {"brain": brain, "porites": porites, "pocillopora": pocillopora, "galaxea": galaxea,
         "finger": finger, "staghorn": staghorn, "elkhorn": elkhorn, "sea_rod": sea_rod,
         "acropora": acropora, "table": table, "plate": plate, "millepora": millepora, "leather": leather,
         "sponge": sponge, "fan": fan, "rubble": rubble}


def read_ply(path: pathlib.Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """What write_ply wrote: vertices, triangles, colours (0 to 1)."""
    data = pathlib.Path(path).read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    head = data[:end].decode().split("\n")
    nv = int(next(h for h in head if h.startswith("element vertex")).split()[-1])
    nf = int(next(h for h in head if h.startswith("element face")).split()[-1])
    vert = np.frombuffer(data, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"),
                                      ("b", "u1")], count=nv, offset=end)
    face = np.frombuffer(data, dtype=[("n", "u1"), ("i", "<i4", 3)], count=nf, offset=end + vert.nbytes)
    v = np.stack([vert["x"], vert["y"], vert["z"]], 1).astype(float)
    c = np.stack([vert["r"], vert["g"], vert["b"]], 1) / 255.0
    return v, face["i"].astype(int), c


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
    ap.add_argument("form", choices=sorted(FORMS))
    ap.add_argument("--into", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--diameter", type=float)
    ap.add_argument("--level", type=int, help="brain: icosphere subdivisions")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    kw = {k: getattr(a, k) for k in ("diameter",) if getattr(a, k) is not None}
    if a.level is not None and a.form == "brain":
        kw["level"] = a.level
    v, f, c = FORMS[a.form](rng, **kw)
    write_ply(pathlib.Path(a.into), v, f, c)
    print(f"{a.form}: {len(v):,} vertices, {len(f):,} triangles, {np.ptp(v[:, 0]):.2f} m across, "
          f"{v[:, 2].max():.2f} m tall -> {a.into}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
