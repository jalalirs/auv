"""Bioturbated mud: the ground of a seabed below the reach of the waves.

Every place on this platform lays two photographed surfaces over its seabed —
`coral_ground_02` where the ground is hard and `damp_beach_sand_02` where it is
soft. The second one is wet rippled sand, and the ripples in it were made by
surface waves. There are no surface waves at five hundred and fifty metres.

Thuwal Deep was therefore being floored with a beach. Under a lamp at two
metres that is not a subtle error: the ripples are regular, they run in one
direction, and a regular directional corrugation is exactly what a diver reads
as "shallow, and the swell comes from over there".

What is actually down there is mud that nothing has stirred but animals. The
whole surface is worked over — trails ploughed by holothurians and irregular
urchins, the open mouths of burrows with the spoil heaped round them, low
mounds pushed up from below, and the coiled casts of what lives in the mud and
eats it. Collectively *lebensspuren*, and on bathyal sediment they are not a
decoration on the ground: below the light they are the only texture there is.

**Provenance.** The trace *kinds* are what the Red Sea Decade Expedition's ROV
transects show on the Saudi slope, and they are what any bathyal seabed
photograph shows. The *numbers* here — how many trails cross a square metre,
how wide, how deep — are chosen, not counted. They are stated in metres so that
somebody with a photograph and a scale bar can say they are wrong.

Tileable, because the ground repeats it every ten metres. Every stamp wraps.
"""

from __future__ import annotations

import numpy as np

# Below this, the waves do not reach the bottom and the ripples in a sand
# texture are a lie about where the place is.
#
# Storm wave base in the open ocean: waves stir the bottom to about half their
# wavelength, and the long swell of a storm runs a few hundred metres from
# crest to crest. Two hundred metres is the round number that oceanography and
# sedimentology both use for it, and it is deliberately deeper than the
# fifty-odd metres of ordinary swell: a place between the two is one where
# ripples are made sometimes, which is a thing a photograph would have to
# settle rather than this file.
BELOW_THE_WAVES_M = 200.0

# How much ground a trail covers. Chosen: on bathyal mud the traces overlap
# each other and the undisturbed patches are the exception, so this is set to
# leave a surface that is mostly worked rather than mostly smooth.
TRAILS_PER_SQUARE_M = 1.1
TRAIL_WIDE_M = (0.03, 0.09)
TRAIL_DEEP_M = (0.004, 0.015)
# How far one animal goes before this stops following it. Trails on the real
# thing run further than a photograph's frame; this is a tile.
TRAIL_RUNS_M = (0.8, 6.0)
# How sharply it turns, in radians per metre travelled. A holothurian grazes,
# so it wanders; it does not corner.
#
# This was 1.1 and the trails came out as straight scratches — a random walk
# in heading accumulates as the square root of the number of steps, so over
# three metres 1.1 a metre is about twenty degrees of total wander, which is a
# ruled line. Six is an animal following food across the mud.
TRAIL_TURNS = 6.0

# Burrow openings: a hole with the spoil heaped round it.
BURROWS_PER_SQUARE_M = 4.5
BURROW_WIDE_M = (0.008, 0.035)
BURROW_DEEP_M = (0.01, 0.04)

# Low mounds pushed up from underneath, with no opening.
MOUNDS_PER_SQUARE_M = 0.6
MOUND_WIDE_M = (0.10, 0.35)
MOUND_HIGH_M = (0.008, 0.03)

# And the coiled casts of a deposit feeder, which are raised and sinuous.
CASTS_PER_SQUARE_M = 1.2
CAST_WIDE_M = (0.010, 0.025)
CAST_HIGH_M = (0.006, 0.018)
CAST_RUNS_M = (0.05, 0.25)

# What the mud is, before anything walked on it: oxidised surface sediment,
# a pale olive-grey. Linear reflectance, because that is the space the
# renderer multiplies in, and the encoder puts it back into sRGB on the way
# out.
SURFACE_MUD = (0.164, 0.160, 0.139)
# And what is a centimetre under it, which is reduced and darker and greyer.
# Turned up by a trail or thrown out of a burrow, this is what shows.
TURNED_MUD = (0.074, 0.076, 0.073)

# The mud's own unevenness, before any animal: a gentle swell with no
# direction in it, at the scale of tens of centimetres.
MUD_ROLLS_M = 0.45
MUD_ROLLS_HIGH_M = 0.006


def _wrapped(size: int, centre: float, reach: float):
    """Indices and offsets for a stamp that runs off the edge and back on."""
    half = int(np.ceil(reach))
    step = np.arange(-half, half + 1)
    middle = int(round(centre))
    return (middle + step) % size, (middle + step) - centre


def _stamp(field, cx: float, cy: float, reach: float, profile) -> None:
    """Add `profile(distance)` round a point, wrapped into the tile."""
    if reach < 0.5:
        return
    xs, dx = _wrapped(field.shape[1], cx, reach)
    ys, dy = _wrapped(field.shape[0], cy, reach)
    far = np.hypot(dy[:, None], dx[None, :])
    field[np.ix_(ys, xs)] += profile(far)


def _rolling(size: int, rng, texels_per_m: float) -> np.ndarray:
    """The mud's own gentle unevenness, tileable and without direction.

    Band-limited noise, filtered in the Fourier domain and brought back. A
    discrete Fourier transform is periodic by construction, so this wraps
    exactly, and filtering on |k| alone means it has no direction in it.

    The first version summed nine sine pairs at whole numbers of cycles across
    the tile, which also wraps exactly — and nine components interfere, so the
    ground came out with a regular diagonal corrugation running across it. That
    is the *precise* thing this file exists to remove: a regular directional
    corrugation is what a diver reads as "shallow, and the swell comes from
    over there", and it is why a beach texture cannot be used down here. Having
    taken the ripples out it would have been quite something to put a moiré in.
    """
    white = rng.normal(0.0, 1.0, (size, size))
    ky = np.fft.fftfreq(size)[:, None]
    kx = np.fft.fftfreq(size)[None, :]
    k = np.hypot(ky, kx)
    # Cycles per texel at the scale the mud rolls over.
    peak = 1.0 / max(1.0, MUD_ROLLS_M * texels_per_m)
    # Everything longer than that, rolled off above it. Not a hard cut: a
    # brick wall in the spectrum is rings in the picture.
    keep = np.exp(-(k / max(peak, 1e-9)) ** 2)
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * keep))
    spread = out.std()
    return out / spread if spread > 1e-9 else out


def worked_over(tile_metres: float = 10.0, texels: int = 2048,
                seed: int = 0) -> dict:
    """One tile of bioturbated mud: its height, and how much is freshly turned.

    Returns metres of relief in `height` and a nought-to-one `turned` saying
    where the surface has been broken open, which is what carries the colour.
    """
    rng = np.random.default_rng(int(seed))
    size = int(texels)
    per_m = size / float(tile_metres)
    area = float(tile_metres) ** 2

    height = _rolling(size, rng, per_m) * MUD_ROLLS_HIGH_M
    turned = np.zeros((size, size), dtype="float64")

    def how_many(per_square_m: float) -> int:
        return max(1, int(round(per_square_m * area)))

    # ── trails ───────────────────────────────────────────────────────────────
    #
    # A groove with a levee either side: the animal ploughs the sediment aside
    # rather than compressing it, so the spoil stands up at the edges. That
    # pair — down in the middle, up at the shoulders — is what makes a trail
    # read as a trail under a raking lamp rather than as a scratch.
    for _ in range(how_many(TRAILS_PER_SQUARE_M)):
        wide = rng.uniform(*TRAIL_WIDE_M) * per_m
        deep = rng.uniform(*TRAIL_DEEP_M)
        runs = rng.uniform(*TRAIL_RUNS_M) * per_m
        heading = rng.uniform(0, 2 * np.pi)
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        step = max(1.0, wide / 3.0)
        turn = TRAIL_TURNS / per_m * step
        for _ in range(int(runs / step)):
            heading += rng.normal(0.0, turn)
            x = (x + np.cos(heading) * step) % size
            y = (y + np.sin(heading) * step) % size
            reach = wide * 1.5

            def groove(far, wide=wide, deep=deep):
                inside = np.clip(far / (wide * 0.5), 0.0, 2.0)
                cut = -deep * np.cos(np.clip(inside, 0, 1) * np.pi / 2) ** 2
                levee = deep * 0.35 * np.exp(-((inside - 1.15) / 0.35) ** 2)
                return (cut + levee) * (step / max(wide, 1e-9))

            _stamp(height, x, y, reach, groove)
            _stamp(turned, x, y, wide * 0.5,
                   lambda far, wide=wide: (far < wide * 0.5) * 0.35)

    # ── burrow openings ──────────────────────────────────────────────────────
    for _ in range(how_many(BURROWS_PER_SQUARE_M)):
        wide = rng.uniform(*BURROW_WIDE_M) * per_m
        deep = rng.uniform(*BURROW_DEEP_M)
        x, y = rng.uniform(0, size), rng.uniform(0, size)

        def mouth(far, wide=wide, deep=deep):
            inside = far / max(wide * 0.5, 1e-9)
            hole = -deep * np.exp(-(inside ** 2) * 2.2)
            rim = deep * 0.5 * np.exp(-((inside - 1.4) / 0.55) ** 2)
            return hole + rim

        _stamp(height, x, y, wide * 1.8, mouth)
        _stamp(turned, x, y, wide * 1.8,
               lambda far, wide=wide: 0.8 * np.exp(-(far / max(wide, 1e-9)) ** 2))

    # ── mounds ───────────────────────────────────────────────────────────────
    #
    # Pushed up from underneath with nothing broken open at the top, so they
    # lift the ground and do not turn it: no `turned` written.
    for _ in range(how_many(MOUNDS_PER_SQUARE_M)):
        wide = rng.uniform(*MOUND_WIDE_M) * per_m
        high = rng.uniform(*MOUND_HIGH_M)
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        _stamp(height, x, y, wide,
               lambda far, wide=wide, high=high:
               high * np.exp(-((far / max(wide * 0.45, 1e-9)) ** 2)))

    # ── casts ────────────────────────────────────────────────────────────────
    #
    # What a deposit feeder leaves behind it: a raised sinuous string, tighter
    # than a trail and much shorter. These are freshly turned by definition —
    # the mud in them has been through an animal.
    for _ in range(how_many(CASTS_PER_SQUARE_M)):
        wide = rng.uniform(*CAST_WIDE_M) * per_m
        high = rng.uniform(*CAST_HIGH_M)
        runs = rng.uniform(*CAST_RUNS_M) * per_m
        heading = rng.uniform(0, 2 * np.pi)
        curl = rng.choice((-1.0, 1.0)) * rng.uniform(4.0, 12.0) / per_m
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        step = max(1.0, wide / 3.0)
        for _ in range(int(runs / step)):
            heading += curl * step
            x = (x + np.cos(heading) * step) % size
            y = (y + np.sin(heading) * step) % size
            _stamp(height, x, y, wide,
                   lambda far, wide=wide, high=high, step=step:
                   high * np.exp(-((far / max(wide * 0.5, 1e-9)) ** 2))
                   * (step / max(wide, 1e-9)))
            _stamp(turned, x, y, wide * 0.6,
                   lambda far, wide=wide: (far < wide * 0.5) * 0.5)

    return {"height": height, "turned": np.clip(turned, 0.0, 1.0)}


def _srgb(linear):
    """Linear reflectance into the sRGB a colour texture is decoded from.

    Written down because getting it backwards has already cost this platform
    one seabed: `derived_colour` put linear numbers straight into an sRGB PNG,
    the renderer decoded them, and a reflectance of 0.20 arrived as 0.033 —
    six times too dark, and dark in a way that reads as "the water is doing
    it".
    """
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(linear <= 0.0031308,
                    linear * 12.92,
                    1.055 * linear ** (1 / 2.4) - 0.055)


def _normal_from(height, tile_metres: float, size: int):
    """A tangent-space normal map from relief in metres.

    Central differences, wrapped, because the tile wraps. A one-sided
    difference at the edge is a seam, and a seam every ten metres over eight
    kilometres is eight hundred of them.
    """
    per_texel = float(tile_metres) / size
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) / (2 * per_texel)
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) / (2 * per_texel)
    normal = np.stack([-dx, -dy, np.ones_like(height)], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return normal * 0.5 + 0.5


def maps_for(tile_metres: float = 10.0, texels: int = 2048,
             seed: int = 0) -> dict:
    """The four maps the ground material reads, as arrays ready to be written.

    `colour` and `rough` are sRGB-encoded because that is how a PNG of them is
    decoded; `height` and `normal` are not, because they are geometry and the
    material reads them raw.
    """
    worked = worked_over(tile_metres=tile_metres, texels=texels, seed=seed)
    height, turned = worked["height"], worked["turned"]
    size = int(texels)

    surface = np.array(SURFACE_MUD, dtype="float64")
    turned_colour = np.array(TURNED_MUD, dtype="float64")
    colour = (surface[None, None, :] * (1.0 - turned[..., None])
              + turned_colour[None, None, :] * turned[..., None])
    # And a little unevenness in the mud's own tone, so that undisturbed
    # ground is not a flat field of one number.
    grain = np.random.default_rng(int(seed) + 977).normal(0, 0.012, (size, size))
    colour = np.clip(colour * (1.0 + grain[..., None]), 0.0, 1.0)

    # Mud is rough everywhere. Freshly turned mud is rougher still: it is
    # broken open rather than settled and smoothed by what falls on it.
    rough = 0.90 + 0.06 * turned

    lift = height - height.min()
    span = max(float(lift.max()), 1e-9)
    return {
        "colour": (_srgb(colour) * 255).astype("uint8"),
        "normal": (_normal_from(height, tile_metres, size) * 255).astype("uint8"),
        # Roughness is read as a scalar out of a colour channel, so it is
        # encoded the same way the colour is.
        "rough": (_srgb(rough) * 255).astype("uint8"),
        "height": (lift / span * 255).astype("uint8"),
        "average": tuple(float(c) for c in colour.reshape(-1, 3).mean(axis=0)),
        "reliefM": float(span),
        "workedFraction": float((turned > 0.05).mean()),
    }


def write_into(where, tile_metres: float = 10.0, texels: int = 2048,
               seed: int = 0, prefix: str = "soft") -> dict:
    """Write the four maps beside a place, under the names the material reads."""
    import pathlib

    from PIL import Image

    into = pathlib.Path(where)
    into.mkdir(parents=True, exist_ok=True)
    made = maps_for(tile_metres=tile_metres, texels=texels, seed=seed)
    # PNG, not JPEG. The same reason the survival map is a PNG: a normal map
    # is three channels of geometry and a DCT is entitled to smooth any of
    # them, and a burrow mouth eight texels across is precisely what it will
    # smooth away.
    for role in ("colour", "normal", "rough", "height"):
        array = made[role]
        image = Image.fromarray(
            array if array.ndim == 3 else array, mode="RGB" if array.ndim == 3 else "L")
        image.save(into / f"{prefix}_{role}.png")
    return {"average": made["average"], "reliefM": made["reliefM"],
            "workedFraction": made["workedFraction"],
            "tileMetres": float(tile_metres), "texels": int(texels)}
