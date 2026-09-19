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
# How bright the water's own light is, as a multiple of the veiling colour.
#
# One, meaning: a surface far enough away that none of its own light survives
# looks exactly like the colour of this water, which is what looking into deep
# water is. `veiling_colour()` already carries the brightness; this is here so
# a place can be made lighter or darker than its water type without moving the
# colour, and so that taking the water away is veil = 0.
#
# It was 0.12 for a fortnight, tuned against a fog whose distance ramp was
# silently running at the renderer's default five kilometres, where near and
# far got the same wash and the only way to keep a close colony its own colour
# was to turn the whole thing off.
VEIL_STRENGTH = 1.6

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
         wave_heading_deg: float | None = None, seed: int = 0,
         begins_at=None) -> None:
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
    # The renderer's global fog, which is a general atmospheric effect that was
    # being used for the thing it is *not* a good model of: a participating medium
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
        say("water_cleared", why="showing the reef rather than the water over it")
        _clear = True
    else:
        _clear = False

    # Volumetric fog, not the post-process kind.
    #
    # `/rtx/fog` *adds* veiling light and never takes any away: a reef at three
    # hundred metres gets a wash of green laid over it and stays perfectly
    # sharp. That is airlight without absorption, which is half of what water
    # does, and it is why every frame this platform has made has had a seabed
    # legible to the horizon through water that absorbs green in seventeen
    # metres. The comment in this file has said "the fog is added to everything
    # the camera sees" since it was written, which turns out to have been the
    # literal truth.
    #
    # The ray-traced volumetric effects absorb as well as scatter, which is a
    # medium rather than a filter over the picture.
    # `/rtx/fog` back on, and the absorbing half done by not drawing what the
    # water would have swallowed.
    #
    # The medium wants two things: light added by the column in front of a
    # surface, and light taken from the surface itself. This fog does the
    # first and cannot do the second, so a reef stays sharp to the horizon
    # however it is set. The ray-traced volumetric effects want a volume prim
    # this scene has no way to author.
    #
    # Doing it in the materials instead needs each surface's distance from the
    # camera, and three renders went into finding out what Kit's MDL will
    # actually hand a shader for that: `state::position()` through
    # `coordinate_internal -> coordinate_world` came back as nothing useful,
    # and bisecting a shading language eight minutes at a time is not a way to
    # spend an afternoon. That code is still here behind `veil = 0` and the
    # question is written down rather than guessed at.
    #
    # What is left is honest and simple: **beyond about three attenuation
    # lengths there is nothing to see**, so stop drawing there. The far clip
    # goes to the same distance the fog reaches full strength at, and the
    # background is the water's own colour, so a surface arrives at the clip
    # plane already the colour of what is behind it.
    # On, and they do more than nothing.
    #
    # They were switched off here for an afternoon on the grounds that they
    # expose no settings of their own without a volume prim, and the frame got
    # visibly worse: the gap between the far edge of the sea and the far edge
    # of the seabed went from a thin dark strip to a third of the picture.
    # Whatever they are doing with the lights in the column, they are doing it,
    # and a diff against the commit that made the better frame is what found
    # that — not the settings tree, which says nothing about them at all.
    settings.set("/rtx/raytracing/globalVolumetricEffects/enabled", not _clear)
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
    #
    # CORAL_CITY_VEIL pins it, the same way CORAL_CITY_ISO pins the exposure:
    # a question about one number gets answered in one run rather than in an
    # afternoon of "that change did nothing".
    from coral.runner import asked_for
    veil = asked_for("CORAL_CITY_VEIL", VEIL_STRENGTH * (0.4 + 0.6 * left))
    # Not clamped at one. This fog adds veiling light rather than blending
    # towards it, so "how much" is a brightness and not a fraction, and the
    # distance at which a thing is lost is the distance at which the light in
    # front of it out-shines it.
    settings.set("/rtx/fog/fogColorIntensity", float(max(0.0, veil)))

    # And the colour of nothing at all.
    #
    # The fog is applied per pixel from that pixel's depth, so a pixel with no
    # geometry behind it gets no fog and comes back the background colour,
    # which is black. That is the band across the top of every frame this
    # platform has ever made: not the water surface, not the fog giving out,
    # but the gap between the far edge of the sea and the far edge of the
    # seabed, painted in the colour of nothing. Two rounds of work went into
    # moving the fog's height plane to chase it.
    #
    # A pixel with nothing behind it is a pixel looking at infinitely deep
    # water, and infinitely deep water is the veiling colour at full strength.
    # So that is what it is painted.
    nothing = [float(min(1.0, one * max(0.0, veil))) for one in veiling]
    settings.set("/rtx/post/backgroundZeroAlpha/backgroundDefaultColor", nothing)
    settings.set("/rtx/post/backgroundZeroAlpha/enabled", True)

    # And the medium in the materials, which is the half /rtx/fog cannot do:
    # what the water takes out rather than what it adds, per channel. Nought
    # when the water is asked to be taken away, which is what that view is.
    # Nought: the materials carry the medium and cannot yet measure the
    # distance it depends on. See the note above the fog settings.
    # On, at last.
    #
    # It was pinned at nought while the materials had no way to tell how far a
    # pixel was from the camera — six attempts to read a position out of the
    # renderer came back either as the ordinary seabed or as a constant. The
    # seabed's own texture coordinates turned out to be the answer: they run
    # nought to one over the site and have been laying the colour map on since
    # September, so the world position is that times the site width.
    #
    # What this buys that `/rtx/fog` never could is the per-channel part. Red
    # is gone in four metres of this water and green takes seventeen, and a fog
    # with one distance cannot say that. It is why everything below ten metres
    # is blue.
    put_the_water_in_the_materials(stage, veiling, lengths,
                                   0.0 if _clear else float(veil),
                                   eye=begins_at)

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
    # How far a camera in this water can see anything at all, for whoever is
    # placing one: the distance the fog reaches full strength at, which is also
    # where the far clip goes, so the two are one number and not two.
    #
    # Set here and not earlier, because `green` is worked out here. It was set
    # forty lines above this, where the name does not exist yet, and `make`
    # raised a NameError halfway through building the water: no sun, no
    # surface, no caustics, and a tour that sat at nought frames for a quarter
    # of an hour with nothing in the log after the line before it.
    global SEEN_TO_M
    SEEN_TO_M = float(green * 3.0)
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
    # The wall of water that stands where the seabed runs out, so that no
    # pixel in the frame is looking at nothing.
    _horizon(stage, water_level, floor, veiling, veil, across)

    surface = UsdGeom.Mesh.Define(stage, "/World/Surface")
    _wave_mesh(surface, water_level, across=across)
    drift._across = across
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
        veil=round(float(veil), 3),
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
# How far anything can be seen in the water a dive is in. Set as the water is
# made; read by whoever places a camera, so that the far clip and the distance
# the fog reaches full strength are one number and not two.
SEEN_TO_M = 60.0

SURFACE_ACROSS = 200.0
SURFACE_CELL = 0.7
# And how far the sea goes after that.
#
# The wave mesh was 200 m across over a site 1000 m across, so from the middle
# the sea ran out at 100 m and the seabed ran on to 500. Between the far edge
# of one and the far edge of the other there was a gap with nothing in it, and
# that gap is the hard band across the top of every frame this platform has
# made. It was read as the fog giving out and chased through two rounds of
# height settings; it was the sea ending.
#
# Fine cells where the waves can be seen, then cells that grow until the sea
# reaches past anything a dive can look at. A wave four hundred metres away is
# four hundred metres away.
SURFACE_REACH = 2500.0
SURFACE_GROWTH = 1.35

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



# How far out the water goes before it is just water.
#
# Beyond the seabed there is no geometry, and the renderer's fog is applied per
# pixel from that pixel's depth — so a pixel with nothing behind it gets no fog
# and comes back the background colour. That is the dark band across the
# horizon of every frame this platform has made.
#
# It cannot be fixed by choosing a better background colour, and an afternoon
# went into trying. This fog *adds* veiling light without absorbing any, so
# fully-fogged geometry is always brighter than empty space by exactly the
# light that geometry reflects. One colour cannot match both.
#
# So: give those pixels something to be. A wall of water standing round the
# site, from the deepest point up to the surface, far enough out to be behind
# the seabed and well inside the sea above it. Every ray then lands on
# something, everything gets fogged the same way, and the horizon is continuous
# because it is made of the same stuff as everything in front of it.
HORIZON_AT_LEAST_M = 900.0
HORIZON_SIDES = 96


def horizon_for(across: float) -> float:
    """How far out the wall has to stand for a site this size.

    Past the corners, not past the edges. A site is a square and the wall is a
    circle, so it has to clear half the *diagonal* — and then some, because a
    dive does not begin in the middle. Al Fahal is three kilometres across and
    its dive begins 1,398 m from the origin; at a fixed nine hundred metres
    the camera was outside its own horizon, which does not look like a wall in
    the wrong place. It looks like the band coming back, and like a downward
    view onto nothing.
    """
    return max(HORIZON_AT_LEAST_M, 0.85 * float(across))


def sea_reaches(across: float) -> float:
    """And how far the sea goes, which must be past the wall.

    If the sea stops short of the horizon, the gap between them is the band
    again, in the one place nothing else can cover it.
    """
    return max(SURFACE_REACH, 1.25 * horizon_for(across))


def _horizon(stage, water_level: float, lowest: float, veiling, veil: float,
             across: float = 1000.0):
    """The wall of water that stands where the seabed runs out."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    import math as _math

    top = float(water_level)
    # Down past the deepest thing here, so no view under the seabed's edge
    # finds the gap under the wall.
    bottom = float(lowest) - 50.0
    radius = horizon_for(across)

    points, counts, indices = [], [], []
    for i in range(HORIZON_SIDES):
        angle = 2 * _math.pi * i / HORIZON_SIDES
        x, y = radius * _math.cos(angle), radius * _math.sin(angle)
        points.append(Gf.Vec3f(float(x), float(y), bottom))
        points.append(Gf.Vec3f(float(x), float(y), top))
    for i in range(HORIZON_SIDES):
        a = 2 * i
        b = 2 * ((i + 1) % HORIZON_SIDES)
        counts.append(4)
        # Wound so the inside is the side that faces the camera.
        indices.extend([a, b, b + 1, a + 1])

    wall = UsdGeom.Mesh.Define(stage, "/World/Horizon")
    wall.CreatePointsAttr(Vt.Vec3fArray(points))
    wall.CreateFaceVertexCountsAttr(Vt.IntArray(counts))
    wall.CreateFaceVertexIndicesAttr(Vt.IntArray(indices))
    wall.CreateDoubleSidedAttr(True)
    wall.CreateExtentAttr([Gf.Vec3f(-radius, -radius, bottom),
                           Gf.Vec3f(radius, radius, top)])

    # Emissive, and dark otherwise. It is not a surface being lit at nine
    # hundred metres — there is no light down there to light it. It is the
    # colour looking into water that far goes, which is the veiling colour, and
    # the fog then adds its own on top exactly as it does to everything else.
    colour = Gf.Vec3f(*[float(min(1.0, one * max(0.0, veil))) for one in veiling])
    material = UsdShade.Material.Define(stage, "/World/Looks/Horizon")
    shader = UsdShade.Shader.Define(stage, "/World/Looks/Horizon/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.0, 0.0, 0.0))
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(colour)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    material.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(wall.GetPrim()).Bind(material)
    return radius


def _across(across: float = 1000.0):
    """Where the sea is sampled along one axis, from the middle outwards.

    Even at the size of a wave out to `SURFACE_ACROSS`, then growing by a third
    each step until it reaches `SURFACE_REACH`. Uniform cells all the way out
    would be eight million quads for one flat sheet, and stopping at two
    hundred metres is what put the band in the picture.
    """
    half = SURFACE_ACROSS / 2.0
    n = int(round(SURFACE_ACROSS / SURFACE_CELL))
    steps = [-half + i * SURFACE_CELL for i in range(n + 1)]

    at, wide = half, SURFACE_CELL
    reach = sea_reaches(across)
    while at < reach:
        wide *= SURFACE_GROWTH
        at += wide
        steps.append(at)
        steps.insert(0, -at)
    return steps


def carries_a_wave(out: float) -> float:
    """How much of the wave a cell this far from the middle can hold.

    One inside the fine region, falling to nothing over the same distance
    again. Named rather than written inline because a test that repeats the
    expression is a test of the expression it repeated: the first one asserted
    1.5 == 1.0 because it applied the taper where the code does not.
    """
    fine = SURFACE_ACROSS / 2.0
    if out <= fine:
        return 1.0
    return max(0.0, 1.0 - (out - fine) / fine)


def _wave_mesh(surface, water_level: float, seconds: float = 0.0,
               centre=(0.0, 0.0), across: float = 1000.0) -> None:
    """Build the patch of sea, displaced by the waves on it."""
    from pxr import Gf, Vt

    cx, cy = float(centre[0]), float(centre[1])
    steps = _across(across)
    n = len(steps) - 1

    # Waves only where the cells are fine enough to carry them.
    #
    # The mesh grows geometrically outwards, so the far cells are hundreds of
    # metres across. Sampling a two-metre wave at one point per two hundred
    # metres does not make a coarse wave, it makes noise: the normals of those
    # cells point wherever the sampling happened to land, and since the surface
    # is glass seen at a grazing angle, that noise is what fills the top third
    # of every frame. It read as a smeared repeating reflection and it was the
    # ugliest thing left in the picture.
    #
    # So the amplitude falls to nothing over the last of the fine region, and
    # beyond that the sea is flat — which is also what a sea a kilometre away
    # looks like from half a metre under it.
    points, counts, indices = [], [], []
    for j in range(n + 1):
        for i in range(n + 1):
            x, y = cx + steps[i], cy + steps[j]
            carries = carries_a_wave(max(abs(steps[i]), abs(steps[j])))
            lift = (water_level + carries * surface_height(x, y, seconds)
                    if carries > 0.0 else water_level)
            points.append(Gf.Vec3f(x, y, lift))
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
    reach = steps[-1]
    surface.CreateExtentAttr([
        Gf.Vec3f(cx - reach, cy - reach, water_level - 1.0),
        Gf.Vec3f(cx + reach, cy + reach, water_level + 1.0)])
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

    from pxr import Gf, UsdGeom

    x, y = (follow[0], follow[1]) if follow is not None else (0.0, 0.0)
    if follow is not None:
        tell_the_water_where_the_camera_is(stage, follow)

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
            # The size the sea was first built at. Rebuilt smaller, it would
            # shrink inside the horizon the moment the vehicle moved, and the
            # band would come back a few seconds into every dive.
            _wave_mesh(mesh, level, seconds, centre=(x, y),
                       across=getattr(drift, "_across", 1000.0))
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


# Which materials hold a column of water between themselves and the camera.
# Every material that draws something at a distance has to, because the water
# is a property of the trip and not of the thing.
LOOKS_WITH_WATER = ("/World/Looks/Seabed/Surface", "/Coral/Skins")


def tell_the_water_where_the_camera_is(stage, at) -> None:
    """Move the medium with the camera.

    The materials do the water themselves: `/rtx/fog` adds veiling light and
    never absorbs, so a reef stays sharp to the horizon however the fog is set,
    and the ray-traced volumetric effects want a volume prim this scene has no
    way to author. What is left is each surface's own distance from the camera,
    which the surface knows and which lets the attenuation be per channel. Red
    dies in four metres of this water and green takes seventeen; a fog with one
    distance cannot say that, and it is why everything below ten metres is
    blue.

    The cost is this: something has to tell them where the camera is, every
    frame. A stale value does not break the picture, it puts the water in the
    wrong place, which is harder to notice.
    """
    from pxr import Gf

    where = Gf.Vec3f(float(at[0]), float(at[1]), float(at[2]))
    if getattr(tell_the_water_where_the_camera_is, "_last", None) == tuple(where):
        return
    tell_the_water_where_the_camera_is._last = tuple(where)

    told = 0
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Shader":
            continue
        eye = prim.GetAttribute("inputs:eye")
        if not eye:
            continue
        eye.Set(where)
        told += 1
    # Said once, because a medium that is silently attached to nothing looks
    # exactly like a medium that is working badly: with the camera left at the
    # origin the water measures from the middle of the site, so the ground
    # under the vehicle is the most veiled thing in the frame and the horizon
    # is the clearest. Which is what the first attempt rendered.
    if not getattr(tell_the_water_where_the_camera_is, "_said", False):
        tell_the_water_where_the_camera_is._said = True
        # Read back, not just written. Setting an attribute that nothing reads
        # looks exactly like setting one that works, and the medium spent a
        # day measuring distance from the middle of the site because of it.
        back = None
        for prim in stage.Traverse():
            got = prim.GetAttribute("inputs:eye")
            if got and got.Get() is not None:
                back = tuple(round(float(v), 1) for v in got.Get())
                break
        print('{"event": "water_follows", "materials": %d, "asked": %s, '
              '"readBack": %s}' % (told, list(where), list(back) if back else None),
              flush=True)


def put_the_water_in_the_materials(stage, veiling, lengths, veil: float,
                                   eye=None) -> None:
    """Tell every surface what the water between it and the camera is.

    Once, when the dive opens: the type of water does not change under a
    vehicle. Where the camera is does, and that is the other function.
    """
    from pxr import Gf

    colour = Gf.Vec3f(*[float(one) for one in veiling])
    lengths = Gf.Vec3f(*[max(0.01, float(one)) for one in lengths])
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Shader":
            continue
        if not prim.GetAttribute("inputs:eye"):
            continue
        # A shader cannot print. CORAL_CITY_SHOW_DISTANCE paints what it
        # thinks the distance to the camera is instead of the ground, in
        # metres, white at the number given. It is the only way to find out.
        import os as _os
        shown = _os.environ.get("CORAL_CITY_SHOW_DISTANCE", "")
        # The camera, set here and not only per frame.
        #
        # An MDL parameter is baked when the material compiles, and the
        # material compiles once, before the first frame. So the value that
        # matters is the one sitting in the attribute at that moment — which is
        # this one. Every per-frame update after it went into an attribute the
        # compiled shader had already stopped reading, which is why the
        # distance was measured from the middle of the site: the attribute
        # still held the nought it was written with.
        #
        # A dive moves and this does not follow it. Over a sheet of stills, all
        # four cameras sit within a few metres of where the dive begins, so the
        # near field is right to within a few metres of water. That is worth
        # having and it is not the whole answer.
        settings = [("inputs:veiling", colour),
                    ("inputs:attenuation", lengths),
                    ("inputs:veil", float(veil)),
                    ("inputs:show_distance", float(shown) if shown else 0.0)]
        if eye is not None:
            settings.append(("inputs:eye", Gf.Vec3f(*[float(v) for v in eye])))
        for name, value in settings:
            got = prim.GetAttribute(name)
            if got:
                got.Set(value)
