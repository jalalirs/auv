"""The net of light a wavy surface throws on the bottom, from the sea itself.

The caustics on this platform were a painted texture, scrolling. That is the
way every underwater scene has ever done it and it is not wrong — but the
pattern had nothing to do with the sea in the dive. A flat calm threw the same
net as a metre of swell, six hundred metres down looked like six, and turning
the sea state up changed the hull's motion and the surface's shape while the
light on the seabed carried on exactly as before.

The sea is already a sum of wave components with known amplitude, wavenumber,
heading and phase — it is what pushes the hull and shapes the surface mesh. So
the caustics can come from the same place, and then they are a consequence of
the dive rather than a decoration on it.

**How.** Sunlight arriving from overhead meets a surface of height h(x, y) and
refracts. For the small slopes a real sea has, a ray entering at (x, y) lands
on a plane `depth` below displaced by

    delta = depth x (1 - 1/n) x grad h

with n = 1.333 for seawater, so the factor is about a quarter. That is a map
from the surface to the bottom, and light is conserved along it: where the map
squeezes, the bottom is bright. The brightness is the inverse of the map's
Jacobian determinant,

    J = I + depth x (1 - 1/n) x H,   H the Hessian of h

and every second derivative of a sum of sines is another sum of sines, so this
is exact rather than a difference taken across a grid.

Three things come out of it for free, and all three are real:

  - A flat sea throws no net at all, because H is zero and the Jacobian is the
    identity. The light is simply even.
  - The pattern washes out with depth. Further down, the displacement term
    grows until neighbouring rays have crossed over each other many times and
    the focusing averages away — which is why caustics are a shallow-water
    sight and why a reef at forty metres does not have them.
  - A longer swell throws a coarser net than a short chop, because the
    wavenumber enters squared.
"""

from __future__ import annotations

import math

import numpy as np

import sea_state

# Seawater. The refraction factor 1 - 1/n turns a surface slope into a
# displacement on the bottom, and it is about a quarter.
INDEX = 1.333
BENDS = 1.0 - 1.0 / INDEX

# The band of the sea that actually bends light.
#
# `SeaState` samples a third of the peak frequency to three times it, because
# that is where a sea's energy is and energy is what moves a hull. It is the
# wrong band for optics. A swell of eight seconds has a wavelength of a
# hundred and sixty metres and a slope under one per cent: at six metres down
# it displaces a ray by a centimetre and a half, which focuses nothing. The
# net on a reef is thrown by the chop — wavelengths of a metre and less, which
# carry almost none of the sea's energy and almost all of its curvature.
#
# So the same JONSWAP spectrum is sampled again, further up its tail, for this
# one purpose. It is the same sea: same significant height, same heading, same
# f^-5 falloff. Only the question is different.
OPTICAL_FROM = 0.8      # x the peak frequency
OPTICAL_TO = 26.0       # x the peak frequency — about a fifteen-centimetre wave
OPTICAL_COMPONENTS = 40

# The slope of the sea, measured off the sun's glitter.
#
# Cox and Munk photographed the glitter pattern from an aircraft in 1954 and
# got the mean square slope of the surface as a straight line in wind speed.
# It is the number that decides whether anything focuses: a sea of a given
# height can be smooth or steep depending on the wind that made it, and it is
# the steepness that throws the net.
COX_MUNK_STILL = 0.003
COX_MUNK_PER_WIND = 0.00512

# How many rays a texel gets, along each axis.
#
# Sixteen, so two hundred and fifty-six a texel. Three was the first guess and
# it made a texture that was almost entirely its own shot noise: nine rays is
# a Poisson count with a third of its own mean as scatter, and at five metres
# the sun's blur is a twentieth of a texel, so nothing smoothed it out. It
# measured contrast 0.104 between neighbouring texels and 0.090 eight texels
# apart — a net has *more* structure at the larger scale, not less, and that
# ordering is how noise announces itself.
#
# Two hundred and fifty-six rays puts the shot noise at a sixteenth, well
# under the net's own contrast. It costs a few seconds once, as a dive opens.
RAYS_PER_TEXEL = 16

# The sun is not a point, and that is the whole reason caustics are a
# shallow-water sight.
#
# Its disc is about half a degree across, so every ray is really a narrow cone
# and a caustic at depth d is blurred across d x tan(quarter of a degree).
# Fourteen millimetres at three metres, which is nothing beside a chop of
# fifteen centimetres; twenty-eight centimetres at sixty, which is twice the
# chop and rubs the net out entirely.
#
# Without this the model does the opposite of the truth. Rays go on crossing
# and folding the further they travel, so the contrast climbs with depth for
# ever and a reef at sixty metres comes out with a harder net on it than one
# at three. Measured, before this went in: contrast 0.06 at one metre rising
# to 0.59 at a hundred and twenty.
#
# In the water, not in the air: refraction narrows the cone by the index.
SUN_HALF_ANGLE = math.radians(0.265) / INDEX


def bending_waves(sea, seed: int = 11):
    """The same sea, sampled where it bends light instead of where it lifts.

    Returns (amplitude, wavenumber, heading, phase) per component, scaled so
    the whole sea — energy band and optical band together — still has the
    significant height it was asked for.
    """
    if sea is None or getattr(sea, "flat", True):
        return []
    draw = np.random.RandomState(seed % (2 ** 32))
    peak = 1.0 / sea.period
    lows = np.linspace(peak * OPTICAL_FROM, peak * OPTICAL_TO,
                       OPTICAL_COMPONENTS + 1)
    out, variance = [], 0.0
    for low, high in zip(lows, lows[1:]):
        middle = 0.5 * (low + high)
        amplitude = math.sqrt(
            max(0.0, 2.0 * sea_state.jonswap(middle, peak) * (high - low)))
        if amplitude <= 0.0:
            continue
        w = 2.0 * math.pi * middle
        # Round the whole compass, not along the swell.
        #
        # The energy band is long-crested: a swell runs one way and the tour
        # of headings is thirty degrees either side of it. The chop is not.
        # Short waves are stirred by the local wind and by each other and run
        # every way at once, and Cox and Munk measured the difference between
        # along-wind and across-wind slope as about three to two — a bias, not
        # a direction.
        #
        # Taking the swell's spread for the optical band made every component
        # nearly parallel, so every ray was displaced along one axis and what
        # came out was not a net but a curtain of vertical streaks. A net
        # needs rays folding across each other from two directions.
        heading = float(draw.random_sample()) * 2.0 * math.pi
        out.append([amplitude, w * w / sea_state.GRAVITY, heading,
                    float(draw.random_sample()) * 2.0 * math.pi])
        variance += 0.5 * amplitude * amplitude
    if not out:
        return []

    # Scaled to the sea's *slope*, not to its height.
    #
    # This was scaled to a share of the significant height, and that share was
    # a guess. It made a surface far too smooth to focus anything: the waves
    # that throw a net are short, a JONSWAP energy tail gives them almost no
    # amplitude, and at five metres down the displacement came out a
    # centimetre against a wavelength of seventy. Nothing focuses at a
    # fiftieth of a wavelength, so the map that came back was its own shot
    # noise with no net in it.
    #
    # Height is the wrong quantity anyway. What bends a ray is the slope, and
    # the slope of the sea is a thing somebody measured: Cox and Munk read it
    # off the sun's glitter from an aircraft in 1954 and got a mean square
    # slope of 0.003 + 0.00512 U for wind speed U in metres a second, which
    # has stood since. So the band is scaled to carry that slope.
    wind = math.sqrt(max(0.0, sea.height) / 0.0246)
    mss = COX_MUNK_STILL + COX_MUNK_PER_WIND * wind
    have = sum(0.5 * (a * k) ** 2 for a, k, _, _ in out)
    if have <= 0.0:
        return []
    scale = math.sqrt(mss / have)
    for one in out:
        one[0] *= scale
    return [tuple(one) for one in out]


def net(sea, across: float, depth: float, seconds: float = 0.0,
        size: int = 256, middle=(0.0, 0.0), seed: int = 11) -> np.ndarray:
    """Relative brightness on a patch of bottom `depth` below the surface.

    Rays are traced and counted where they land, rather than the map's
    Jacobian being solved. The difference is what happens past the first
    focus: a Jacobian is single-valued, so it can only ever sharpen with
    depth, while real caustics sharpen to a focus and then break up as
    neighbouring rays cross and keep crossing. Counting where light lands gets
    the crossing for nothing, and with it the reason caustics are a
    shallow-water sight.

    One at the mean, so it multiplies a sunlight that is already right rather
    than adding a second sun.
    """
    waves = bending_waves(sea, seed)
    if not waves:
        return np.ones((size, size), dtype="float32")

    # Nothing finer than the texture can hold.
    #
    # A texel here is a third of a metre, and a wave fifteen centimetres long
    # throws a net finer than that. Synthesising it anyway does not put fine
    # detail in the texture — it puts *noise* in it, because structure below
    # the sampling scale folds back as grain. Measured: neighbouring texels
    # differing by more than the whole map's spread, which is how a picture
    # says it is mostly noise.
    #
    # Two texels to a wavelength is the most that can be represented, so the
    # short end of the band is cut there and the net that comes out is the
    # net this patch can actually carry.
    finest = 2.0 * (across / size)
    biggest_k = 2.0 * math.pi / finest
    waves = [one for one in waves if one[1] <= biggest_k]
    if not waves:
        return np.ones((size, size), dtype="float32")

    n = size * RAYS_PER_TEXEL
    half = across / 2.0
    span = np.linspace(-half, half, n, dtype="float64")
    x = span[None, :] + float(middle[0])
    y = span[:, None] + float(middle[1])

    # The slope of the surface where each ray meets it.
    hx = np.zeros((n, n))
    hy = np.zeros((n, n))
    for amplitude, k, heading, phase in waves:
        cos, sin = math.cos(heading), math.sin(heading)
        slope = amplitude * k * np.cos(k * (x * cos + y * sin)
                                       - math.sqrt(k * sea_state.GRAVITY) * seconds
                                       + phase)
        hx += slope * cos
        hy += slope * sin

    bends = max(0.0, float(depth)) * BENDS
    lands_x = np.broadcast_to(x, (n, n)) + bends * hx
    lands_y = np.broadcast_to(y, (n, n)) + bends * hy



    # Where they land, counted. Rays that leave the patch are simply not
    # counted, and as many arrive from outside it as leave, so the mean holds.
    lit, _, _ = np.histogram2d(
        lands_y.ravel(), lands_x.ravel(), bins=size,
        range=[[float(middle[1]) - half, float(middle[1]) + half],
               [float(middle[0]) - half, float(middle[0]) + half]])
    # And the sun's own width, as a blur on the light that landed rather than
    # a wobble on each ray.
    #
    # Jittering the rays was the first attempt and it measured its own shot
    # noise: nine rays a texel is a Poisson count, so randomising where they
    # fall puts a third of a stop of grain into every texel and the "contrast"
    # rises with depth because the grain does. Blurring what landed is the
    # same physics, exactly, with none of the noise and a tenth of the work.
    blur = max(0.0, float(depth)) * math.tan(SUN_HALF_ANGLE)
    lit = _softened(lit, blur / (across / size))

    mean = lit.mean()
    if mean <= 0.0:
        return np.ones((size, size), dtype="float32")
    return (lit / mean).astype("float32")


def _softened(image, sigma: float):
    """A Gaussian blur, separable, in numpy alone.

    The runtime declares numpy and nothing else, and one blur is not worth a
    dependency that has to be present on every machine a dive ever runs on.
    """
    if sigma <= 0.05:
        return image
    reach = max(1, int(round(3.0 * sigma)))
    at = np.arange(-reach, reach + 1, dtype="float64")
    kernel = np.exp(-0.5 * (at / sigma) ** 2)
    kernel /= kernel.sum()
    # Edges repeated rather than wrapped: the patch is a window on a larger
    # sea, so what is past its edge is more sea and not the other side.
    wide = np.pad(image, ((0, 0), (reach, reach)), mode="edge")
    image = np.apply_along_axis(
        lambda row: np.convolve(row, kernel, mode="valid"), 1, wide)
    tall = np.pad(image, ((reach, reach), (0, 0)), mode="edge")
    return np.apply_along_axis(
        lambda col: np.convolve(col, kernel, mode="valid"), 0, tall)


def as_texture(lit: np.ndarray) -> np.ndarray:
    """The net as eight-bit grey, scaled so the mean sits mid-range.

    The light this multiplies is set separately, so what the texture carries
    is the *shape* of the net and not its strength. Normalising on the mean
    keeps a calm sea and a rough one at the same average brightness, with only
    the contrast between them changing — which is the difference a sea state
    actually makes to the bottom.
    """
    mean = float(lit.mean())
    if mean <= 0.0:
        return np.full(lit.shape, 128, dtype="uint8")
    return np.clip(lit / mean * 0.5 * 255.0, 0.0, 255.0).astype("uint8")
