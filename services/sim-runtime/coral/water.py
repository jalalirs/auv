"""What makes a place look like it is underwater.

Isaac Sim has nothing for this. NVIDIA say so themselves — no underwater
environment feature, no water material, no hydrodynamics — so what follows is
built from the general-purpose parts the renderer does have: volumetric fog, a
light that can carry a texture, and a surface with an index of refraction.

The physics of it is worth stating, because the numbers below are not taste.
Water absorbs light exponentially with distance, and it does so far faster at
the red end than the blue: red is gone within a few metres, green survives
perhaps twenty, blue further still. That is why the sea is blue, why a red
vehicle at fifteen metres photographs grey, and why an autonomy stack trained on
uncorrected images off a reef learns colours that do not exist. A simulator that
gets this wrong teaches the same wrong thing, so it is worth getting right.

Jerlov's water types are the standard shorthand — I is the clearest open ocean,
III is coastal, 1C through 9C are increasingly turbid coastal water. The
coefficients here are for clear coastal water, which is what a reef in a bay is.
"""

from __future__ import annotations

import math
import os

# Jerlov's types, as attenuation lengths in metres: how far light of each
# colour travels before it is dimmed to 1/e.
#
# The shorthand the whole field uses. I is the clearest open ocean, III the
# murkiest oceanic; 1C through 9C are increasingly turbid coastal water. A reef
# in a bay is coastal; the Red Sea off a fringing reef is close to oceanic.
#
# These are the water, and until now only one third of them reached the
# picture: the renderer's fog takes a single distance, so the green length was
# used for how dark it gets with depth and red and blue were computed and
# thrown away. Which is the whole reason a red vehicle at fifteen metres came
# out the same colour as a blue one.
JERLOV = {
    "I":   (8.0, 40.0, 50.0),    # clearest open ocean
    "IA":  (7.0, 32.0, 40.0),
    "IB":  (6.5, 27.0, 33.0),
    "II":  (5.5, 23.0, 24.0),
    "III": (5.0, 19.0, 16.0),    # murkiest oceanic: blue dies before green
    "1C":  (4.0, 17.0, 13.0),    # clear coastal
    "3C":  (3.5, 12.0, 8.0),
    "5C":  (3.0, 8.5, 5.0),
    "7C":  (2.5, 6.0, 3.2),
    "9C":  (2.0, 4.0, 2.0),      # turbid harbour: everything dies together
}
# What a place is flown in unless its conditions say otherwise.
DEFAULT_TYPE = "1C"

# Stamped so a frame can be traced to the code that made it. Bumped by hand
# whenever this file changes in a way a picture should show.
BUILD = "water-15"

# The two facts that make the far half of a frame the colour it is.
#
# Light that never reaches the camera directly is what the medium scattered
# into the line of sight, and at any distance past a few attenuation lengths
# that veiling light *is* the picture. Its colour is not what the water
# absorbs — it is what survives, which is the reciprocal of the attenuation,
# normalised. So it is derived here rather than picked: a number picked by eye
# is a number that has to be re-picked for every water type, and there are ten.
#
# How much of the light that goes into the medium comes back rather than being
# absorbed. Seawater's single-scattering albedo is low — most of what is lost
# is lost, not redirected — and this is what stops the distance being a bright
# white wall. The first attempt at this filled forty metres with white haze.
SCATTERING_ALBEDO = 0.28

# How much veiling light there is at all, before depth dims it. Read off the
# same ladder: at 0.28 the whole frame went the colour of the water, at 0.05
# there was no water in the picture.
VEIL_STRENGTH = 0.12

# How bright the water's own glow is as a fill light. Read off a ladder.
DOME_SHARE = 55.0


def water_of(kind: str | None = None):
    """The attenuation lengths of a named water type."""
    return JERLOV.get(str(kind or DEFAULT_TYPE).upper().replace(" ", ""),
                      JERLOV[DEFAULT_TYPE])


# How far the veil is pulled back towards grey, and how bright it is allowed
# to get. Light that reaches the camera from the side has been scattered many
# times over, and every bounce mixes the channels: a veil left at the raw ratio
# is fully saturated in whichever channel survives best, and a reef behind it
# looks like a reef behind coloured glass rather than a reef in water.
#
# Both read off a ladder: eleven frames of one view, stepping the veil. At full
# saturation the corals lost their own colour entirely; at these the reds and
# oranges come through and the distance still goes the colour of the sea.
VEIL_TOWARDS_GREY = 0.35
VEIL_BRIGHTNESS = 0.62


def veiling_colour(lengths) -> tuple:
    """The colour the distance goes, for a water of these lengths.

    What survives, then mixed back towards grey and dimmed. Clear ocean comes
    out blue because blue survives; turbid harbour comes out green-brown
    because by then blue does not.
    """
    most = max(lengths)
    ratio = [float(one) / most for one in lengths]
    grey = sum(ratio) / 3.0
    mixed = [one + (grey - one) * VEIL_TOWARDS_GREY for one in ratio]
    return tuple(round(one * VEIL_BRIGHTNESS, 4) for one in mixed)


# Kept as the name the rest of this file used before water types existed.
ATTENUATION_METRES = water_of(DEFAULT_TYPE)
SCATTER = veiling_colour(ATTENUATION_METRES)


def is_it_deep(depth: float, lengths=None) -> float:
    """How much daylight is left at a depth, as a fraction of the surface."""
    lengths = lengths or ATTENUATION_METRES
    return max(0.02, 2.718 ** (-depth / lengths[1]))


def make(stage, say, floor: float, water_level: float = 0.0,
         across: float = 1000.0, working_depth: float = 10.0,
         visibility_m: float | None = None, water_type: str | None = None,
         significant_height_m: float | None = None,
         wave_period_s: float | None = None,
         wave_heading_deg: float | None = None, seed: int = 0) -> None:
    """Put water over a place, and light it from above.

    Four things, in the order they matter: the fog that is the water itself, the
    sun coming through the surface, the surface seen from below, and the caustic
    light the surface throws on the bottom.
    """
    import carb
    from pxr import Gf, Sdf, UsdGeom, UsdLux

    settings = carb.settings.get_settings()

    # Said first, and said loudly, because this file has been edited and
    # rebuilt a dozen times against a picture that never changed, and twice the
    # reason turned out to be that the code under test was not the code that
    # ran. Nothing below is worth reading if this line is not in the log.
    say("water_begins", build=BUILD, twin=os.environ.get("CORAL_CITY_TWIN") or None,
        lampSize=os.environ.get("CORAL_CITY_LAMP_SIZE") or None)

    # How much daylight is left where this dive is happening. Wanted by both the
    # lights and the camera, so it is worked out once.
    # Which water this is. Named by the conditions, or clear coastal, and every
    # number below comes off it rather than out of this file.
    # The sea, from what was measured or from a quiet day.
    global _SEA
    from sea_state import SeaState

    _SEA = SeaState(
        CALM_HEIGHT_M if significant_height_m is None else float(significant_height_m),
        CALM_PERIOD_S if wave_period_s is None else float(wave_period_s),
        0.0 if wave_heading_deg is None else float(wave_heading_deg),
        seed=int(seed))
    say("sea_is", **_SEA.said(),
        measured=significant_height_m is not None)

    lengths = water_of(water_type)
    veiling = veiling_colour(lengths)
    left = is_it_deep(max(0.0, working_depth), lengths)
    say("water_is", type=str(water_type or DEFAULT_TYPE),
        attenuationM=list(lengths), veiling=list(veiling),
        daylightLeft=round(left, 3))

    # ── the camera ───────────────────────────────────────────────────────────
    #
    # A fixed exposure, because automatic exposure makes a simulator lie. It
    # brightens a dark scene until it looks normal, which is exactly the
    # information a dive is meant to carry — how much light there is at fifteen
    # metres — and it means the same reef photographs differently depending on
    # where the camera happens to be pointing. Two runs of one dive would not
    # match, and an autonomy stack would learn from images no real camera takes.
    #
    # It is also why tuning the lights was a fight: every change was being
    # partly undone by the renderer trying to be helpful.
    #
    # The names here are the renderer's own, and three of them were not.
    # `/rtx/post/tonemap/iso` and `/rtx/post/tonemap/cameraShutter` do not
    # exist: carb takes any key you give it, so writing to them created two
    # settings nothing reads. A thirty-two fold change in "iso" moved the
    # picture by a thousandth of a stop, which is how this was finally caught,
    # and it means every argument about the lamps for the last fortnight was an
    # argument against a control that was not connected.
    #
    # The real ones are `filmIso` and `exposureTime`, and
    # CORAL_CITY_SETTINGS=1 prints the whole tree from inside the frame loop,
    # which is where it has to be asked: before the renderer starts, every key
    # under /rtx is one this code invented.
    settings.set("/rtx/post/histogram/enabled", False)
    settings.set("/rtx/post/tonemap/op", 1)
    settings.set("/rtx/post/tonemap/exposureTime", 1.0 / 60.0)
    # Measured off an exposure ladder — the same reef at four apertures in one
    # run — and then reopened by a third of a stop once the fill light came
    # down, because the two are the same knob seen from different ends and
    # changing one without re-reading the other is how a scene ends up dark and
    # correct at the same time.
    settings.set("/rtx/post/tonemap/fNumber", 4.5)
    # Exposed for the depth this dive works at, which is what anybody pointing
    # a camera underwater does before they get in.
    #
    # The lights carry the real dimming — half the daylight is gone by twelve
    # metres — and a fixed exposure on top of that makes the deep reef simply
    # dark, which is true and is not a photograph. Compensating in the camera
    # keeps both: the reef is exposed where the vehicle is working, and moving
    # deeper than that still gets visibly darker, because the lights keep
    # tracking depth while the exposure stays where it was set.
    # Metered off the depth, which is a formula and not a light meter.
    #
    # A tenth of the shallow reef was blowing to white while the deep site was
    # a stop under. Both move the same way: a little less sensitivity at the
    # top of the column, a lot more allowed at the bottom of it.
    #
    # This is now a *starting point* and not the answer. coral/metering.py
    # reads the first few frames of a run and sets the exposure from what is
    # actually in the picture, then stops; this is where it starts from, which
    # is worth having good because a meter that starts close converges in one
    # round instead of three. The reason it could not stay the answer is that
    # a formula over depth knows nothing about the lamps, which is why a lamp
    # correct at six hundred metres blew the frame out at six.
    #
    # CORAL_CITY_ISO pins it, which is how a question about the exposure gets
    # answered in one run instead of an afternoon of "that change did nothing".
    from coral.runner import asked_for
    iso = asked_for("CORAL_CITY_ISO", min(9000.0, 140.0 / max(left, 0.05)))
    settings.set("/rtx/post/tonemap/filmIso", float(iso))
    say("camera_is", filmIso=round(float(iso), 1), fNumber=4.5,
        exposureTime=1 / 60.0, pinned=asked_for("CORAL_CITY_ISO") is not None)
    if os.environ.get("CORAL_CITY_SETTINGS") == "1":
        _say_what_the_renderer_has(settings, say)

    # ── the water ────────────────────────────────────────────────────────────
    #
    # The renderer's global fog, which is a general atmospheric effect being
    # used for the thing it is actually a good model of: a participating medium
    # that absorbs and scatters over distance.
    # Local lights, which this renderer does not draw until it is told to.
    #
    # The sun and the dome have always worked, because they are infinite
    # lights and the direct-lighting pass handles those. A lamp on a vehicle is
    # neither: it is an analytic light with a position, and RTX leaves those to
    # the sampled-lighting pass, which is off by default. The way that presents
    # is a light that is created, placed correctly and switched on, and changes
    # nothing at any brightness — which is how a whole afternoon goes.
    # Sharpen the ground when it is looked along.
    #
    # A seabed viewed at a grazing angle has an enormous screen-space
    # derivative, so the renderer picks a mip level that has averaged the
    # texture away and the bottom of every frame is a smooth slab. It is not
    # the texture: the map was replaced with pure red and the whole floor went
    # red, and replaced with strong metre-scale grain and the floor stayed
    # smooth. Anisotropic filtering is what a grazing view needs.
    settings.set("/rtx/hydra/TBNFrameMode", 1)
    settings.set("/rtx/materialDb/anisotropyLevel", 16)
    settings.set("/rtx/texturestreaming/maxAnisotropy", 16)

    settings.set("/rtx/directLighting/sampledLighting/enabled", True)
    settings.set("/rtx/directLighting/sampledLighting/autoEnable", False)
    settings.set("/rtx/directLighting/sampledLighting/samplesPerSurface", 4)
    settings.set("/rtx/directLighting/sampledLighting/maxLightCount", 32)

    # Clear water, for looking at what is actually on the bottom.
    #
    # Not a dive: fifteen metres of visibility is the truth about this water
    # and it is also a blue wall at any height worth surveying from, so a
    # picture of the reef itself needs the scattering out of the way. The
    # seabed, the coral and the light are exactly what a dive gets; what goes
    # is the medium between them and the camera.
    if os.environ.get("CORAL_CITY_CLEAR") == "1":
        settings.set("/rtx/fog/enabled", False)
        say("water_cleared", why="showing the reef rather than the water over it")
        _clear = True
    else:
        _clear = False

    settings.set("/rtx/fog/enabled", not _clear)
    settings.set("/rtx/fog/fogColor", list(veiling))
    # The fog is added to everything the camera sees, so its strength is how
    # much of the picture is water rather than reef, and where it starts is how
    # close a thing has to be to keep its own colour.
    #
    # How bright the veiling light gets. Not picked: it is how much of what
    # the medium takes is scattered back rather than absorbed, times how much
    # daylight is down here at all. A reef at thirty metres has a dimmer
    # distance than the same reef at five, and it should.
    #
    # It was 0.55, measured off an exposure ladder — which was honest, and was
    # one number standing in for two facts that move independently.
    settings.set("/rtx/fog/fogColorIntensity",
                 float(min(1.0, VEIL_STRENGTH * (0.4 + 0.6 * left))))
    # The distance is the water's own attenuation length, for green.
    #
    # Green because it is most of what the eye reads as brightness, and green
    # because it is the middle of three lengths the fog can only take one of.
    # That is the approximation in this file and it is worth naming: red really
    # does die four times faster than green and the fog cannot say so, so a red
    # thing at ten metres is still too red. Putting that right needs a medium
    # the renderer does not have, or the frame's own depth, which the capture
    # does not hand back.
    #
    # It was thirty metres, which is not this water: looking straight down at a
    # reef from twelve metres — an ordinary survey altitude — came back as an
    # empty blue rectangle. A fog tuned by eye on one horizontal view is tuned
    # for that view.
    # One attenuation length, which is the water's own.
    #
    # It was tried at three, on a guess that the renderer runs to full strength
    # linearly rather than e-folding. The ladder says otherwise: at three the
    # far field is still only three quarters veiled, so the underside of the
    # surface stays visible forty metres away and fills the top of every frame
    # with a bright ceiling. Real water at forty metres in this type is gone.
    scale = 1.0 if not visibility_m else max(0.15, float(visibility_m) / lengths[1])
    green = float(lengths[1] * scale)
    # The renderer's own names are `fogStartDist` and `fogEndDist`, and they
    # were never set. `fogDistance` and `fogStartDistance`, which this file has
    # been writing for a fortnight, are not settings this renderer has: carb
    # takes any key you hand it and creates one nothing reads, which is the
    # same way the exposure was written to `/rtx/post/tonemap/iso` and quietly
    # did nothing.
    #
    # So the fog has been running at its default five kilometres. At five
    # kilometres a reef a hundred metres away is two per cent veiled, and every
    # frame this platform has produced has had a seabed sharp to the horizon
    # through water that absorbs green in seventeen metres.
    #
    # Three lengths, not one: the control is a linear ramp from start to end,
    # not an e-folding, so the distance where it reaches full strength is the
    # distance where real water has already gone, and that is about three
    # attenuation lengths.
    settings.set("/rtx/fog/fogStartDist", 0.0)
    settings.set("/rtx/fog/fogEndDist", float(green * 3.0))
    settings.set("/rtx/fog/fogDensity", 1.0)
    settings.set("/rtx/fog/fogDistanceDensity", 1.0)
    # Fog everywhere in the water, not only near the bottom.
    #
    # The renderer's fog thins with height above a plane, which is right for
    # ground mist and wrong for the sea: it left a hard line across every frame
    # where the fog stopped and the underside of the surface came through
    # unveiled. The plane goes above the water and the falloff goes off, so the
    # whole column is the same medium, which is what water is.
    # Up is z.
    #
    # The renderer's fog measures height along **y** unless told otherwise, and
    # this platform is z-up. So every height setting in this block was being
    # applied sideways: the fog thinned across the scene horizontally instead
    # of upward, which is why a hard band kept appearing across the frame and
    # why moving the height plane never quite killed it. Two rounds of work
    # went into that band against a control pointing the wrong way.
    settings.set("/rtx/fog/fogZup/enabled", True)
    settings.set("/rtx/fog/fogHeightDensity", 1.0)
    # And no falloff at all, because the sea is not ground mist. Water is the
    # same medium from the seabed to the surface; a column that thins with
    # height leaves the underside of the surface unveiled, which is the bright
    # ceiling this is trying to be rid of.
    settings.set("/rtx/fog/fogHeightFalloff", 0.0)
    # The plane the height is measured from, put well above the water so that
    # everything a dive can see is on the dense side of it.
    settings.set("/rtx/fog/fogHeight", float(water_level + 200.0))
    settings.set("/rtx/fog/fogStartHeight", float(water_level + 200.0))
    # Water starts at the lens, because it does. It was eleven metres, to keep
    # close things their own colour — which is a real problem solved in the
    # wrong place: what greyed out a close colony was a veiling intensity above
    # one, not haze at half a metre. At this water's length a thing a metre
    # away is six per cent hazed, which is what a photograph shows.
    # `fogStartDist` above is the one the renderer reads; this is kept only
    # because a place opened in some other Kit application may read it.
    settings.set("/rtx/fog/fogStartDistance", 0.0)

    # ── the sun ──────────────────────────────────────────────────────────────
    #
    # Angled rather than overhead, so the seabed has relief in it. A light
    # straight down flattens everything it touches.
    sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
    # Bright, because the fog is between the sun and everything it lights and
    # takes most of it. The first attempt used a daylight intensity and produced
    # a seabed that was a black silhouette in green water: correct absorption,
    # nothing left to absorb.
    # Full daylight lights the seabed like a beach, because it is the light
    # above the surface and not the light that got down here. The fog gives the
    # colour of depth and this gives its dimness.
    sun.CreateIntensityAttr(1500.0 * left)
    sun.CreateAngleAttr(2.0)
    # White balanced, the way every camera that has ever been pointed at a reef
    # is white balanced.
    #
    # The light that reaches ten metres really is blue-green, and lighting the
    # reef with it really does render a mustard coral blue-green: the first
    # version did exactly that, correctly, and the reef came out the colour of
    # nothing on earth. Every photograph of a reef in existence — including the
    # ones this is being built from — was either strobed or white balanced,
    # because otherwise there is no picture. So the key light carries the water's
    # dimness but not its cast, the distance stays blue because the fog is still
    # blue, and a yellow coral in front of the camera comes out yellow.
    sun.CreateColorAttr(Gf.Vec3f(1.0, 0.98, 0.94))
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-52.0, 0.0, 18.0))

    # Everything the water scatters back, which is what stops the shadows being
    # black. Underwater there is no such thing as an unlit surface: the medium
    # itself glows in every direction.
    sky = UsdLux.DomeLight.Define(stage, "/World/Water")
    # A quarter of every frame was this light.
    #
    # Measured: turning it off took the picture from 99 to 74. A dome light
    # arrives from every direction at once, so whatever share of the light it
    # carries is a share with no shape in it — and worse, it was blue-grey
    # against a reef that is mustard and ochre, so it lifted the blue channel
    # of every colony and every one of them came out pale. The palette was
    # never wrong; it was being washed.
    #
    # Water really does glow in every direction and this is not zero. But it is
    # a fill, and a fill is not a quarter of the light.
    sky.CreateIntensityAttr(DOME_SHARE * left)
    # Coloured, but not so coloured that it becomes the illuminant. This was
    # (0.05, 0.38, 0.72) — almost pure blue — and at that saturation it was not
    # a fill light, it was the light: everything not in direct sun was rendered
    # in blue, and since most of a reef is not in direct sun, the reef was blue.
    # Measured, the brightest coral in the frame came out (0.14, 0.17, 0.18)
    # against a mustard albedo of (0.72, 0.58, 0.22).
    # And the colour of the water it is in, rather than a blue-grey chosen
    # separately. The medium and its glow are the same thing, so they take the
    # same number: a turbid green bay now fills green and a clear ocean fills
    # blue, without anybody picking either.
    sky.CreateColorAttr(Gf.Vec3f(*[min(1.0, one * 1.35) for one in veiling]))

    # ── the surface, from below ──────────────────────────────────────────────
    #
    # Seen from underneath, water is a mirror everywhere except a cone straight
    # up — total internal reflection, the "Snell's window" every diver knows.
    # A transmissive surface with water's index of refraction produces that for
    # free, which is worth far more than painting it on.
    surface = UsdGeom.Mesh.Define(stage, "/World/Surface")
    _wave_mesh(surface, water_level)
    # Where the mean level is, for the rebuilds that follow the vehicle.
    drift._level = float(water_level)
    surface.CreateDoubleSidedAttr(True)

    # And it casts no shadow. It is a sheet of glass the size of the site
    # directly between the sun and everything below, and a renderer that treats
    # it as an occluder puts the entire seabed in shade — which is most of why
    # the first water was a silhouette. Light through the surface is what the
    # fog and the caustics are already modelling.
    surface.GetPrim().CreateAttribute(
        "primvars:doNotCastShadows", Sdf.ValueTypeNames.Bool).Set(True)
    _water_material(stage, surface)

    # ── caustics ─────────────────────────────────────────────────────────────
    #
    # The net of light the surface focuses onto the bottom. Ray-traced caustics
    # are the honest way and they are far too slow to fly against, so this is
    # the way every underwater scene has ever done it: a light with a caustic
    # texture projected downward, scrolling.
    #
    # It is a cheat and it is the correct cheat — the pattern is real, its
    # motion is real, and what is being simulated here is a vehicle rather than
    # photon transport.
    # Sized to the water it lights, not to the site. A rectangle a kilometre
    # across, normalised, spreads its intensity over a square kilometre and
    # arrives as nothing — which is what the first attempt did. This one is a
    # patch that travels with the vehicle, which is the only part anybody can
    # see anyway.
    caustics = UsdLux.RectLight.Define(stage, "/World/Caustics")
    caustics.CreateWidthAttr(90.0)
    caustics.CreateHeightAttr(90.0)
    # A modulation of sunlight, not a second sun.
    #
    # At 5200 this was adding twenty-five points of brightness to the whole
    # frame and burning a white pool into the near ground of every shallow
    # site — a tenth to a fifth of those frames were clipped, and it read as
    # the lamps being too strong when the lamps had nothing to do with it.
    # Caustics are the sun's own light concentrated and thinned by the surface;
    # they can be brighter than the sun in the bright parts and they cannot be
    # five times it everywhere.
    caustics.CreateIntensityAttr(1400.0 * left)
    caustics.CreateColorAttr(Gf.Vec3f(1.0, 0.97, 0.90))
    caustics.CreateNormalizeAttr(False)
    caustics.GetPrim().CreateAttribute(
        "inputs:texture:file", Sdf.ValueTypeNames.Asset).Set("/isaac-sim/coral/caustics.png")
    # No rotation. A rect light already faces its own -Z, which is downward
    # here; turning it a half turn about X — which looked like the obvious way
    # to point it at the seabed — pointed it at the sky, and the caustics lit
    # the underside of the surface from above where nobody could see them.
    moving = UsdGeom.Xformable(caustics.GetPrim())
    moving.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, water_level - 0.5))

    # A second light, built here beside the caustics that work, because every
    # difference between them has now been ruled out one at a time: type, size,
    # brightness, cone, parenting, the scope above it. What is left is *where
    # in the code it is made*, which should not matter and is the only thing
    # not yet tested. CORAL_CITY_TWIN steps it from an exact copy of the
    # caustics towards a lamp, one attribute at a time.
    twin = os.environ.get("CORAL_CITY_TWIN")
    if twin:
        step = int(twin)
        second = UsdLux.RectLight.Define(stage, "/World/CausticsTwin")
        # 1: an exact copy, twenty metres along.
        wide = 90.0 if step < 2 else 0.08
        second.CreateWidthAttr(wide)
        second.CreateHeightAttr(wide)
        second.CreateIntensityAttr(5200.0 * left if step < 3 else 200000.0)
        second.CreateColorAttr(Gf.Vec3f(1.0, 0.97, 0.90))
        second.CreateNormalizeAttr(False)
        if step < 4:
            second.GetPrim().CreateAttribute(
                "inputs:texture:file", Sdf.ValueTypeNames.Asset).Set(
                    "/isaac-sim/coral/caustics.png")
        # Follows the vehicle, like the caustics. The first version of this
        # test put it at twenty metres from the world origin, which at this
        # site is fourteen hundred metres from the reef — so four steps of the
        # bisect came back identical because none of them was in the picture.
        UsdGeom.Xformable(second.GetPrim()).AddTranslateOp().Set(
            Gf.Vec3d(0.0, 0.0, water_level - 0.5))
        say("twin", step=step, acrossM=wide,
            textured=step < 4)

    # Read back, not assumed. A carb setting that does not exist accepts a
    # value silently and changes nothing, so every number below could have been
    # doing exactly nothing for as long as it has been here — and the way that
    # presents is a scene that looks vaguely underwater because of the light
    # while every adjustment to the fog does not move the picture at all.
    lit = {name: settings.get("/rtx/directLighting/sampledLighting/" + name)
           for name in ("enabled", "autoEnable", "samplesPerSurface", "maxLightCount")}
    say("sampled_lighting", **{k: v for k, v in lit.items()})

    applied = {name: settings.get("/rtx/fog/" + name)
               for name in ("enabled", "fogDistance", "fogStartDistance",
                            "fogColorIntensity", "fogHeight", "fogHeightDensity")}

    say("water_made",
        fogApplied=applied,
        visibilityM=round(17.0 * scale, 1), fogEndsAtM=round(green * 3.0, 1),
        surfaceAtM=water_level,
        daylightLeft=round(left, 3), atDepthM=round(working_depth, 1),
        absorbsInM=list(ATTENUATION_METRES))


# How big a patch of surface to draw, and how fine.
#
# It was one flat quad four and a half kilometres across, which is a sheet of
# glass: every part of it reflects the same way, so looking up gave a bright
# ceiling with hard edges rather than water. Water looks like water because it
# is not flat.
#
# A patch rather than the whole site, because the fog takes everything past a
# couple of attenuation lengths and there is no point shading what nobody can
# see. Two hundred metres is far beyond visibility in any of Jerlov's waters.
SURFACE_ACROSS = 200.0
SURFACE_CELL = 0.7

# The sea this place is having, set when the water is made and used by every
# vertex of the surface after that.
#
# It was four wave trains somebody chose: fixed lengths, fixed heights, the
# same sea every day, and no way to tell it that today is half a metre and
# Thursday is two. It is a JONSWAP spectrum now, driven by the significant
# height and period a wave buoy reports — which is what `asMeasured` takes off
# a Sofar Spotter and records as observed conditions.
_SEA = None
# A quiet day on a reef, for a dive that says nothing about the weather.
CALM_HEIGHT_M = 0.4
CALM_PERIOD_S = 6.0


def surface_height(x: float, y: float, seconds: float = 0.0) -> float:
    """How high the water stands above its mean level at a point."""
    return 0.0 if _SEA is None else _SEA.height_at(x, y, seconds)


def orbital_here(x: float, y: float, depth: float, seconds: float = 0.0):
    """What the water itself is doing at a depth, under this sea.

    The half of a sea state that acts on a vehicle. Zero when the surface is
    only being drawn and nothing has set a sea, so a dive that says nothing
    about the weather is the dive it always was.
    """
    import numpy as _np

    if _SEA is None or _SEA.flat:
        return _np.zeros(3)
    return _SEA.orbital_at(x, y, depth, seconds)


def _wave_mesh(surface, water_level: float, seconds: float = 0.0,
               centre=(0.0, 0.0)) -> None:
    """Build the patch of sea, displaced by the waves on it."""
    from pxr import Gf, Vt

    n = int(SURFACE_ACROSS / SURFACE_CELL)
    half = SURFACE_ACROSS / 2.0
    cx, cy = float(centre[0]), float(centre[1])

    points, counts, indices = [], [], []
    for j in range(n + 1):
        for i in range(n + 1):
            x = cx - half + i * SURFACE_CELL
            y = cy - half + j * SURFACE_CELL
            points.append(Gf.Vec3f(x, y, water_level + surface_height(x, y, seconds)))
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            counts.append(4)
            indices.extend([a, a + 1, a + n + 2, a + n + 1])

    surface.CreatePointsAttr(Vt.Vec3fArray(points))
    surface.CreateFaceVertexCountsAttr(Vt.IntArray(counts))
    surface.CreateFaceVertexIndicesAttr(Vt.IntArray(indices))
    # No authored normals. The renderer works them out from the displaced
    # geometry, which is the whole point: a normal per square metre is what
    # makes the underside of a sea look like a sea.
    surface.CreateExtentAttr([
        Gf.Vec3f(cx - half, cy - half, water_level - 1.0),
        Gf.Vec3f(cx + half, cy + half, water_level + 1.0)])
    surface.SetNormalsInterpolation("faceVarying")


def _water_material(stage, surface) -> None:
    """Glass with water's index of refraction, because that is what water is.

    1.333 is not a number to tune. It is why the surface is a mirror at a
    glancing angle and a window overhead, and getting it right gives Snell's
    window for nothing — the bright circle straight up that every diver knows,
    which no amount of painting produces convincingly.
    """
    from pxr import Gf, Sdf, UsdShade

    material = UsdShade.Material.Define(stage, "/World/Looks/Water")
    shader = UsdShade.Shader.Define(stage, "/World/Looks/Water/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.05, 0.22, 0.30))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.06)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.22)
    shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.333)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(surface.GetPrim()).Bind(material)


def light_for(stage, depth: float) -> None:
    """Set the light to what is left at this depth.

    Called as the vehicle moves, because the light at two metres and the light
    at fifteen are not the same light — and a scene lit once at the surface
    stays lit that way all the way to the bottom, which is the single most
    obviously wrong thing an underwater renderer can do.
    """
    from pxr import UsdLux

    left = is_it_deep(max(0.0, depth))
    # The sun is the key light and everything else is fill. The first balance
    # had the caustics three and a half times the sun and a dome bright enough
    # to fill every shadow, which is a scene with no direction in it — and a
    # reef with no shadows on it has no shape.
    for path, base in (("/World/Sun", 1500.0), ("/World/Water", DOME_SHARE),
                       ("/World/Caustics", 1400.0)):
        prim = stage.GetPrimAtPath(path)
        if prim:
            attribute = prim.GetAttribute("inputs:intensity")
            if attribute:
                attribute.Set(base * left)


def drift(stage, seconds: float, follow=None) -> None:
    """Move the caustics with the water, and keep them over the vehicle.

    Still caustics are a painted floor, and caustics fixed to the world are a
    patch of light the vehicle flies out of.
    """
    import math

    from pxr import Gf, UsdGeom

    x, y = (follow[0], follow[1]) if follow is not None else (0.0, 0.0)

    # The sea moves, and the patch of it that is drawn stays over the vehicle.
    # Rebuilt rather than translated, because the waves have to travel through
    # the patch and not with it — a sea that slides along under a vehicle is a
    # painted ceiling that happens to be moving.
    #
    # Only when the vehicle has gone far enough to matter, because eighty
    # thousand points is not free and a tenth of a metre of drift is not worth
    # them.
    sea = stage.GetPrimAtPath("/World/Surface")
    if sea:
        from pxr import UsdGeom as _UsdGeom

        mesh = _UsdGeom.Mesh(sea)
        was = getattr(drift, "_rebuilt_at", None)
        moved = was is None or math.hypot(x - was[0], y - was[1]) > SURFACE_CELL * 4
        if moved or seconds - (getattr(drift, "_rebuilt_t", -99.0)) > 0.25:
            level = getattr(drift, "_level", 0.0)
            _wave_mesh(mesh, level, seconds, centre=(x, y))
            drift._rebuilt_at = (x, y)
            drift._rebuilt_t = seconds

    twin = stage.GetPrimAtPath("/World/CausticsTwin")
    if twin:
        for op in UsdGeom.Xformable(twin).GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                op.Set(Gf.Vec3d(x + 3.0, y, op.Get()[2]))
                break

    light = stage.GetPrimAtPath("/World/Caustics")
    if not light:
        return
    # A slow wander, the way a swell moves a caustic net across a bottom.
    x += 5.0 * math.sin(seconds * 0.06)
    y += 4.0 * math.cos(seconds * 0.043)
    for op in UsdGeom.Xformable(light).GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            op.Set(Gf.Vec3d(x, y, op.Get()[2]))
            return


def _say_what_the_renderer_has(settings, say, under: str = "/rtx/post") -> None:
    """Every setting the renderer actually has under a branch, and its value.

    Because a knob that does not exist takes a setting silently. The exposure
    was written to `/rtx/post/tonemap/iso` for weeks; a thirty-two fold change
    in it moved the picture by a thousandth of a stop, which is to say it was
    never connected to anything, and every argument about the lamps was an
    argument against a control that did nothing.

    CORAL_CITY_SETTINGS=1 and read the log. It is cheap and it is the only way
    to tell a setting that is ignored from a setting that is wrong.
    """
    def walk(branch: str, depth: int = 0):
        if depth > 4:
            return
        try:
            here = settings.get(branch)
        except Exception:
            return
        if isinstance(here, dict):
            for key in sorted(here):
                walk(f"{branch}/{key}", depth + 1)
        else:
            say("renderer_setting", at=branch, value=here)

    walk(under)
