"""A Red Sea fringing reef, constructed.

There is no free high-resolution bathymetry for the Red Sea. NOAA's metre-scale
topobathy is United States coast only, EMODnet is European, and the Allen Coral
Atlas — which is CC BY and does cover it — is ten metres and behind an account.
GEBCO covers the whole world and is four hundred and fifty metres a sample,
which over a one kilometre site is four numbers.

So this terrain is built rather than surveyed, and the site says so. That
distinction already exists in this platform for the water a dive happens in —
observed conditions name the instant they were measured, constructed ones may
not, because saying when would claim a provenance they lack — and it applies
exactly as much to the ground.

What is built is the morphology, which is not invented. A fringing reef has the
same parts everywhere it occurs, for reasons that are mechanical: a shallow reef
flat scoured by waves; a crest at the lowest tide where growth stops; a fore-reef
slope where the coral does most of its building; spur-and-groove down that slope,
which is the reef's own drainage, cut by the water that breaks over the crest and
has to get back out; a sand terrace where the slope eases and the debris settles;
and the deeper slope beyond. An AUV site with those parts in the right order is
a useful site whether or not any particular metre of it was measured.
"""

from __future__ import annotations

import numpy as np


def build(across: float, samples: int, seed: int = 1,
          shallowest: float = 0.6, deepest: float = 38.0) -> tuple:
    """A reef running from shore at −x to open water at +x.

    Returns heights in metres above the water — negative everywhere below it —
    on a square grid, plus a description of what was made.
    """
    rng = np.random.default_rng(seed)

    y, x = np.mgrid[0:samples, 0:samples] / (samples - 1)
    # Metres from the middle. Shore lies at the −x edge.
    ex = (x - 0.5) * across
    ey = (y - 0.5) * across

    # ── the parts, as fractions across the site ──────────────────────────────
    flat_to = -0.22 * across      # reef flat runs from the shore to here
    crest_at = -0.20 * across     # the crest: shallowest, and narrow
    slope_to = 0.18 * across      # fore-reef slope ends at the terrace
    terrace_to = 0.34 * across    # sand terrace, then the deeper slope

    depth = np.zeros_like(ex)

    # Reef flat: shallow, nearly level, slightly deeper towards the shore where
    # a lagoon forms behind the crest.
    flat = ex <= crest_at
    towards_shore = np.clip((crest_at - ex) / (crest_at - (-across / 2)), 0, 1)
    depth[flat] = (shallowest + 2.2 * towards_shore[flat] ** 0.7)

    # Fore-reef slope: from the crest down to the terrace. Steep near the top,
    # easing as it goes, which is what a slope built by growth looks like —
    # coral builds fastest where the light is.
    slope = (ex > crest_at) & (ex <= slope_to)
    along = np.clip((ex[slope] - crest_at) / (slope_to - crest_at), 0, 1)
    depth[slope] = shallowest + (24.0 - shallowest) * along ** 1.55

    # Sand terrace: where the slope eases and everything the reef sheds settles.
    terrace = (ex > slope_to) & (ex <= terrace_to)
    along = np.clip((ex[terrace] - slope_to) / (terrace_to - slope_to), 0, 1)
    depth[terrace] = 24.0 + 3.0 * along

    # And the deeper slope beyond it.
    deep = ex > terrace_to
    along = np.clip((ex[deep] - terrace_to) / (across / 2 - terrace_to), 0, 1)
    depth[deep] = 27.0 + (deepest - 27.0) * along ** 1.2

    # ── spur and groove ──────────────────────────────────────────────────────
    #
    # The reef's drainage. Water breaking over the crest has to get back out,
    # and it does so along channels it keeps clear of coral; the coral builds
    # the ridges between. They run down the slope, are a few metres apart, and
    # fade out as the slope eases and the wave energy goes.
    wavelength = 22.0
    ridges = np.sin(2 * np.pi * ey / wavelength
                    + 1.1 * np.sin(2 * np.pi * ey / (wavelength * 3.7)))
    # Grooves are flat-bottomed and spurs are rounded, which is what the sign
    # asymmetry below is for — a plain sine gives corrugated iron.
    ridges = np.sign(ridges) * np.abs(ridges) ** 0.65

    on_the_slope = np.clip((ex - crest_at) / (slope_to - crest_at), 0, 1)
    strength = np.clip(np.sin(np.pi * on_the_slope) ** 0.8, 0, 1)
    strength[ex <= crest_at] = 0.0
    strength[ex > slope_to] *= 0.25
    depth -= ridges * strength * 1.9

    # ── rugosity ─────────────────────────────────────────────────────────────
    #
    # Reef is rough at every scale, and a smooth slope is the one thing no reef
    # is. Octaves of noise, strongest where the coral is and least on the sand.
    rough = np.zeros_like(depth)
    amplitude, size = 0.55, 6
    for _ in range(5):
        coarse = rng.normal(0, 1, (size, size))
        up_r = (np.arange(samples) * size // samples).clip(0, size - 1)
        layer = coarse[np.ix_(up_r, up_r)]
        # Smoothed, so each octave is a hill and not a grid of spikes.
        for _ in range(2):
            layer = 0.25 * (np.roll(layer, 1, 0) + np.roll(layer, -1, 0)
                            + np.roll(layer, 1, 1) + np.roll(layer, -1, 1))
        rough += layer * amplitude
        amplitude *= 0.52
        size *= 2

    # Roughest on the fore-reef slope, where the coral builds; nearly smooth on
    # the flat, which the waves scour level, and on the sand terrace, which is
    # sand. A reef flat with three metres of relief on it is not a reef flat.
    building = np.clip(np.sin(np.pi * np.clip(on_the_slope, 0, 1)) ** 0.6, 0, 1)
    building[ex <= crest_at] = 0.18
    building[ex > slope_to] = 0.22
    depth -= rough * building

    depth = np.clip(depth, 0.35, deepest + 6.0)

    # Where a dive should begin: over the fore-reef slope, in the middle of the
    # coral, at a depth an ROV actually works at. The middle of a site is only
    # the right answer when the site is uniform, and a reef is the opposite of
    # uniform — its whole point is that the parts are different.
    # Two thirds of the way down the slope, where a reef is at its best and an
    # ROV has room under it. Near the crest the bottom is a metre or two down,
    # the light is almost surface light, and there is nowhere to fly.
    begin_x = float(crest_at + (slope_to - crest_at) * 0.62)
    begin_column = int((begin_x / across + 0.5) * (samples - 1))
    begin_column = max(0, min(samples - 1, begin_column))

    # Over a spur, not in a groove. The grooves are the reef's drainage: bare
    # sand channels, deliberately clear of coral, and the middle of the site
    # lands in one about as often as not — which puts the vehicle in the only
    # empty strip on the whole slope, looking along it.
    begin_y = wavelength * 0.25
    begin_row = int((begin_y / across + 0.5) * (samples - 1))
    begin_row = max(0, min(samples - 1, begin_row))
    bottom = float(depth[begin_row, begin_column])

    return -depth.astype("float32"), {
        "morphology": "fringing reef: flat, crest, fore-reef slope with "
                      "spur-and-groove, sand terrace, deeper slope",
        "shoreAt": "the -x edge",
        # Four metres off the bottom, and never shallower than six down. The
        # first version subtracted a fixed six metres from the bottom depth and
        # clamped, which on a shallow spur put the vehicle two metres under the
        # surface — in the brightest water on the reef, with nothing beneath it.
        "beginAt": [round(begin_x, 1), round(begin_y, 1),
                    -round(max(6.0, bottom - 4.0), 1)],
        "beginBecause": "over a spur, two thirds down the fore-reef slope",
        "spurSpacingM": wavelength,
        "crestDepthM": round(float(shallowest), 2),
        "terraceDepthM": 24.0,
    }
