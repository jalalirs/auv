"""The surface of a coral, at the scale of its polyps.

A coral skeleton is not a smooth dome. It is a few hundred thousand corallites:
cups two or three millimetres across, each one a polyp's socket, packed with
raised rims between them. On a brain coral they are not cups at all but
meandering valleys four to eight millimetres wide. That texture is most of why
a coral head reads as living stone and a sphere with a colour on it reads as a
blob of clay, and no amount of noise on a low-polygon dome produces it.

There is no CC0 photograph of a corallite surface to tile, so this makes one:
a height field and the normal map that falls out of it, per growth form, with
the corallite sizes taken from the genera that build these reefs.

    tools/corallite massive --into ~/iocean/places/looe-key/textures

Tileable. Seeds are replicated across the eight neighbouring copies of the tile
before the distance field is taken, so the pattern wraps without a seam, which
matters because a colony is covered in perhaps forty repeats of it.
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np

# How big a polyp's cup is, in millimetres, and how the surface is organised.
#
# From the genera that build the reefs this platform has places for. These are
# the middle of a published range, not a measurement of one specimen, and the
# range is wide: Orbicella corallites run 2 to 3 mm, Porites under 1.5, the
# brain corals' valleys 4 to 8 across with ridges between.
FORMS = {
    "massive":    {"kind": "cups", "across": 2.6, "deep": 0.45, "rim": 0.30,
                   "says": "Orbicella, Montastraea: separate cups with raised rims"},
    "brain":      {"kind": "maze", "across": 8.0, "deep": 1.2, "rim": 1.0,
                   "says": "Platygyra, Diploria: meandering valleys and ridges, about 8 mm ridge to ridge"},
    "branching":  {"kind": "cups", "across": 1.2, "deep": 0.25, "rim": 0.35,
                   "says": "Acropora: small crowded corallites on a branch"},
    "table":      {"kind": "cups", "across": 1.6, "deep": 0.30, "rim": 0.22,
                   "says": "Agaricia: fine corallites in rows"},
    "encrusting": {"kind": "cups", "across": 1.0, "deep": 0.20, "rim": 0.18,
                   "says": "Millepora: pores, finer than a corallite"},
    "finger":     {"kind": "cups", "across": 1.4, "deep": 0.30, "rim": 0.28,
                   "says": "Porites: very fine, shallow cups"},
    # The Red Sea forms the close-up colonies (tools/coral_hd) wear.
    "porites":    {"kind": "cups", "across": 1.3, "deep": 0.22, "rim": 0.16,
                   "says": "Porites lutea, lobata: cups barely a millimetre across, shallow, walls sharp"},
    "pocillopora": {"kind": "cups", "across": 0.9, "deep": 0.25, "rim": 0.20,
                    "says": "Pocillopora: small immersed corallites between the verrucae"},
    "galaxea":    {"kind": "stars", "across": 6.5, "deep": 0.9, "rim": 1.6,
                   "says": "Galaxea fascicularis: tall cups with a dozen exsert septa, a star each"},
    "acropora":   {"kind": "tubes", "across": 1.8, "deep": 0.5, "rim": 0.9,
                   "says": "Acropora: radial corallites standing off the branch as little tubes"},
    "millepora":  {"kind": "cups", "across": 0.45, "deep": 0.08, "rim": 0.03,
                   "says": "Millepora: smooth, with pores, not corallites"},
    # The octocorals have no skeleton like this at all. A sea fan's surface is
    # a mesh of spicules and polyps standing off it, which is a different thing
    # and is not this.
}

# How much of a colony one tile covers. Forty millimetres at 1024 pixels is
# 39 microns a pixel, which is finer than a corallite needs and coarse enough
# that a tile is a megabyte rather than sixteen.
TILE_MM = 40.0
PIXELS = 1024


def _seeds(across_mm: float, tile_mm: float, rng) -> np.ndarray:
    """Corallite centres on a jittered hexagonal lattice.

    Hexagonal because that is how cups that are all trying to be round pack
    into a plane, and jittered because a coral is not a crystal. The lattice is
    sized to the tile so that whole rows fit and the pattern wraps.
    """
    rows = max(2, int(round(tile_mm / (across_mm * np.sqrt(3) / 2))))
    columns = max(2, int(round(tile_mm / across_mm)))
    step_x, step_y = tile_mm / columns, tile_mm / rows
    i, j = np.meshgrid(np.arange(columns), np.arange(rows))
    x = (i + 0.5 * (j % 2)) * step_x
    y = j * step_y
    at = np.stack([x.ravel(), y.ravel()], axis=-1)
    at += rng.normal(0.0, 0.14 * across_mm, at.shape)
    return np.mod(at, tile_mm)


def _wrapped(at: np.ndarray, tile_mm: float) -> np.ndarray:
    """The same seeds, and eight copies of them, one per neighbouring tile.

    This is what makes the tile seamless. Take the distance field of the seeds
    alone and every edge is a row of half corallites against a flat strip.
    """
    shifts = [(dx * tile_mm, dy * tile_mm)
              for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    return np.concatenate([at + np.array(s) for s in shifts])


def _cups(shape: dict, tile_mm: float, pixels: int, rng) -> np.ndarray:
    """A field of corallites: a cup, a raised rim, and the wall between them."""
    from scipy import spatial

    at = _wrapped(_seeds(shape["across"], tile_mm, rng), tile_mm)
    grid = (np.arange(pixels) + 0.5) * (tile_mm / pixels)
    gx, gy = np.meshgrid(grid, grid)
    away, _ = spatial.cKDTree(at).query(
        np.stack([gx.ravel(), gy.ravel()], axis=-1), k=1)
    away = away.reshape(pixels, pixels)

    radius = shape["across"] / 2.0
    # Inside six tenths of the radius is the cup; between there and the edge is
    # the rim standing over it.
    inside = np.clip(away / (0.6 * radius), 0.0, 1.0)
    cup = -shape["deep"] * (1.0 - inside ** 2)
    out = np.clip((away - 0.6 * radius) / (0.4 * radius), 0.0, 1.0)
    rim = shape["rim"] * np.sin(np.pi * out)
    return np.where(away < 0.6 * radius, cup, rim)


def _nearest(shape: dict, tile_mm: float, pixels: int, rng):
    """Distance and direction from every pixel to its nearest corallite centre."""
    from scipy import spatial

    at = _wrapped(_seeds(shape["across"], tile_mm, rng), tile_mm)
    grid = (np.arange(pixels) + 0.5) * (tile_mm / pixels)
    gx, gy = np.meshgrid(grid, grid)
    points = np.stack([gx.ravel(), gy.ravel()], axis=-1)
    away, which = spatial.cKDTree(at).query(points, k=1)
    offset = points - at[which]
    angle = np.arctan2(offset[:, 1], offset[:, 0])
    # Each corallite turned its own way, so the stars do not all line up.
    turn = rng.uniform(0, 2 * np.pi, len(at))[which]
    return away.reshape(pixels, pixels), (angle + turn).reshape(pixels, pixels)


def _stars(shape: dict, tile_mm: float, pixels: int, rng) -> np.ndarray:
    """Tall cups whose septa stand out past the wall: a star each.

    A cup sunk in the middle, a wall around it, and twelve plates radiating
    from the centre out past the wall, highest at the wall and falling away."""
    away, angle = _nearest(shape, tile_mm, pixels, rng)
    radius = shape["across"] / 2.0
    r = away / radius
    cup = -shape["deep"] * np.clip(1 - (r / 0.45) ** 2, 0, None)
    wall = shape["rim"] * 0.55 * np.exp(-((r - 0.55) / 0.12) ** 2)
    septa = np.clip(np.cos(12 * angle), 0, None) ** 6
    plates = shape["rim"] * septa * np.clip(1 - np.abs(r - 0.6) / 0.55, 0, None)
    between = -0.25 * shape["rim"] * np.clip((r - 1.0) / 0.3, 0, 1)
    return cup + np.maximum(wall, plates) + between


def _tubes(shape: dict, tile_mm: float, pixels: int, rng) -> np.ndarray:
    """Small tubes standing off the surface, each with a hole in its end."""
    away, _ = _nearest(shape, tile_mm, pixels, rng)
    r = away / (shape["across"] / 2.0)
    tube = shape["rim"] * np.clip(1 - (r / 0.8) ** 4, 0, None)
    hole = -shape["deep"] * np.clip(1 - (r / 0.3) ** 2, 0, None)
    return tube + hole


def _maze(shape: dict, tile_mm: float, pixels: int, rng) -> np.ndarray:
    """A brain coral's maze, grown by Gray-Scott reaction-diffusion on a small
    torus (so it tiles without a seam) and enlarged smoothly: the same process
    the close-up colonies' grooves are grown by (tools/coral_hd), here flat."""
    from scipy import ndimage

    # The pattern settles at about eleven cells ridge to ridge.
    n = max(16, int(round(tile_mm / shape["across"] * 11)))
    u, v = np.ones((n, n)), np.zeros((n, n))
    seed = rng.random((n, n)) < 0.12
    v[seed], u[seed] = 0.5, 0.5

    def lap(a):
        return np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1) - 4 * a

    for _ in range(12000):
        uvv = u * v * v
        u += 0.16 * lap(u) - uvv + 0.037 * (1 - u)
        v += 0.08 * lap(v) + uvv - (0.037 + 0.06) * v
    big = ndimage.zoom(np.tile(v, (3, 3)), pixels / n, order=3)[pixels:2 * pixels, pixels:2 * pixels]
    ridge = np.clip((big - big.min()) / (np.ptp(big) + 1e-9) * 2 - 0.5, 0, 1)
    ridge = ridge * ridge * (3 - 2 * ridge)
    return shape["rim"] * ridge - shape["deep"] * (1 - ridge)


def _valleys(shape: dict, tile_mm: float, pixels: int, rng) -> np.ndarray:
    """Meandering valleys, which is what a brain coral has instead of cups.

    From a band-limited noise field built out of whole-numbered frequencies, so
    it is tileable by construction, folded into ridges. A brain coral's surface
    is one continuous groove that never quite closes, and a ridged sine of
    smooth noise is the cheapest thing that does not close either.
    """
    grid = (np.arange(pixels) + 0.5) / pixels
    gx, gy = np.meshgrid(grid, grid)
    field = np.zeros((pixels, pixels))
    for harmonic, weight in ((1, 1.0), (2, 0.5), (3, 0.25)):
        for _ in range(3):
            angle = rng.uniform(0, 2 * np.pi)
            phase = rng.uniform(0, 2 * np.pi)
            # Whole-numbered frequencies in both directions: anything else
            # does not come back to itself at the edge of the tile.
            kx = int(round(harmonic * np.cos(angle) * 3)) or 1
            ky = int(round(harmonic * np.sin(angle) * 3)) or 1
            field += weight * np.sin(2 * np.pi * (kx * gx + ky * gy) + phase)

    # Folded into ridges at an even spacing.
    #
    # Dividing by the field's own slope first is what makes the spacing even.
    # Folding the field directly packs the ridges tight where it happens to be
    # steep and leaves them wide where it is flat, which comes out as nested
    # contour rings — a topographic map, not a coral. A brain coral's valleys
    # are the same width all over the head.
    slope = np.hypot(*np.gradient(field))
    spacing = max(1.0, tile_mm / shape["across"])
    phase = field / (float(slope.mean()) * pixels + 1e-9) * spacing
    folded = np.abs(np.sin(np.pi * phase))
    # Flattened towards a valley floor and a ridge top, rather than a sine's
    # smooth swing: a brain coral has a floor and a crest, not a ripple.
    folded = np.clip((folded - 0.15) / 0.7, 0.0, 1.0)
    return shape["rim"] * folded - shape["deep"] * (1.0 - folded)


def height_for(form: str, tile_mm: float = TILE_MM, pixels: int = PIXELS,
               seed: int = 1) -> np.ndarray:
    """The surface of this growth form, in millimetres about zero."""
    if form not in FORMS:
        raise KeyError(f"nobody has said what {form} corallites look like")
    shape = FORMS[form]
    rng = np.random.default_rng(seed)
    made = {"cups": _cups, "valleys": _valleys, "stars": _stars, "tubes": _tubes, "maze": _maze}[shape["kind"]](
        shape, tile_mm, pixels, rng)
    return made - float(made.mean())


def normal_from(height: np.ndarray, tile_mm: float = TILE_MM) -> np.ndarray:
    """A tangent-space normal map, as the renderer wants it.

    Wrapped gradients, because a tileable height field whose normals are not
    tileable has a seam in the lighting and nowhere else, which is a thing that
    takes a while to find.
    """
    step = tile_mm / height.shape[0]
    dy, dx = np.gradient(height, step, step)
    # A tileable difference at the edges: np.gradient uses a one-sided
    # difference at the border and that is exactly where the seam would be.
    dx[:, 0] = (height[:, 1] - height[:, -1]) / (2 * step)
    dx[:, -1] = (height[:, 0] - height[:, -2]) / (2 * step)
    dy[0, :] = (height[1, :] - height[-1, :]) / (2 * step)
    dy[-1, :] = (height[0, :] - height[-2, :]) / (2 * step)

    normal = np.stack([-dx, -dy, np.ones_like(dx)], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return ((normal * 0.5 + 0.5) * 255).astype("uint8")


def grey_from(height: np.ndarray) -> np.ndarray:
    """The height itself, for a material that blends by it."""
    low, high = float(height.min()), float(height.max())
    if high - low < 1e-9:
        return np.full(height.shape, 128, dtype="uint8")
    return (255 * (height - low) / (high - low)).astype("uint8")


def write(form: str, into: pathlib.Path, tile_mm: float = TILE_MM,
          pixels: int = PIXELS, seed: int = 1) -> dict:
    """Both maps for one growth form, beside a place."""
    from PIL import Image

    into.mkdir(parents=True, exist_ok=True)
    height = height_for(form, tile_mm, pixels, seed)
    Image.fromarray(normal_from(height, tile_mm)).save(
        into / f"corallite_{form}_normal.png")
    Image.fromarray(grey_from(height)).save(
        into / f"corallite_{form}_height.png")
    return {"form": form, "tileMm": tile_mm, "pixels": pixels,
            "corallliteMm": FORMS[form]["across"],
            "reliefMm": round(float(np.ptp(height)), 3),
            "says": FORMS[form]["says"]}


def main() -> int:
    parse = argparse.ArgumentParser(description="the surface of a coral at polyp scale")
    parse.add_argument("form", nargs="*", default=sorted(FORMS),
                       help="growth forms; all of them by default")
    parse.add_argument("--into", required=True)
    parse.add_argument("--tile-mm", type=float, default=TILE_MM)
    parse.add_argument("--pixels", type=int, default=PIXELS)
    parse.add_argument("--seed", type=int, default=1)
    asked = parse.parse_args()
    for form in asked.form:
        made = write(form, pathlib.Path(asked.into).expanduser(),
                     asked.tile_mm, asked.pixels, asked.seed)
        print(f"  {form:11s} {made['corallliteMm']:.1f} mm corallites, "
              f"{made['reliefMm']:.2f} mm of relief  ({made['says']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
