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

# How far light of each colour travels before it is dimmed to 1/e, in metres.
#
# Clear coastal water, roughly Jerlov type 1C. Red is gone in four metres, which
# is the single most visible fact about being underwater and the one a grey fog
# gets wrong.
ATTENUATION_METRES = (4.0, 17.0, 26.0)

# What colour the water itself glows, from everything scattering light back.
# Not the same as what it absorbs: the sea is blue-green because that is what is
# left, and it is bright because the whole volume is scattering.
#
# Deeper and more saturated than the first version. A photograph of this reef
# has warm coral against a strong blue; a paler scatter colour gives the same
# geometry against a grey-cyan wash, and the coral picks the wash up too.
SCATTER = (0.012, 0.10, 0.31)


def is_it_deep(depth: float) -> float:
    """How much daylight is left at a depth, as a fraction of the surface."""
    return max(0.02, 2.718 ** (-depth / ATTENUATION_METRES[1]))


def make(stage, say, floor: float, water_level: float = 0.0,
         across: float = 1000.0, working_depth: float = 10.0) -> None:
    """Put water over a place, and light it from above.

    Four things, in the order they matter: the fog that is the water itself, the
    sun coming through the surface, the surface seen from below, and the caustic
    light the surface throws on the bottom.
    """
    import carb
    from pxr import Gf, Sdf, UsdGeom, UsdLux

    settings = carb.settings.get_settings()

    # How much daylight is left where this dive is happening. Wanted by both the
    # lights and the camera, so it is worked out once.
    left = is_it_deep(max(0.0, working_depth))

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
    settings.set("/rtx/post/histogram/enabled", False)
    settings.set("/rtx/post/tonemap/op", 1)
    settings.set("/rtx/post/tonemap/cameraShutter", 1.0 / 60.0)
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
    settings.set("/rtx/post/tonemap/iso",
                 float(min(2000.0, 200.0 / max(left, 0.05))))

    # ── the water ────────────────────────────────────────────────────────────
    #
    # The renderer's global fog, which is a general atmospheric effect being
    # used for the thing it is actually a good model of: a participating medium
    # that absorbs and scatters over distance.
    settings.set("/rtx/fog/enabled", True)
    settings.set("/rtx/fog/fogColor", list(SCATTER))
    # The fog is added to everything the camera sees, so its strength is how
    # much of the picture is water rather than reef, and where it starts is how
    # close a thing has to be to keep its own colour.
    #
    # This began at 1.35 starting three metres from the lens, which put four
    # fifths of a close-up colony under water: the reef came out the colour of
    # marzipan and no exposure fixed it, because darkening the picture darkens
    # the wash by exactly as much. Measured at twelve metres on the fore reef,
    # the near reef was still rendering (0.10, 0.17, 0.28) — blue over red — at
    # 0.95 starting at eight metres. A photograph of this reef holds its colour
    # out to about ten metres and goes blue behind that, so that is where the
    # haze starts.
    settings.set("/rtx/fog/fogColorIntensity", 0.55)
    # Visibility, near enough. Twenty metres is a good day on a reef; a diver
    # calls thirty exceptional and five a bad one.
    settings.set("/rtx/fog/fogDistance", 30.0)
    settings.set("/rtx/fog/fogDensity", 1.0)
    settings.set("/rtx/fog/fogHeightDensity", 1.0)
    # Fog that begins at the lens greys out the thing you came to look at.
    # Water does haze at half a metre, but not enough to matter, and starting
    # further out keeps the colour of what is close while still burying the
    # distance.
    settings.set("/rtx/fog/fogStartDistance", 11.0)

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
    sky.CreateIntensityAttr(150.0 * left)
    # Coloured, but not so coloured that it becomes the illuminant. This was
    # (0.05, 0.38, 0.72) — almost pure blue — and at that saturation it was not
    # a fill light, it was the light: everything not in direct sun was rendered
    # in blue, and since most of a reef is not in direct sun, the reef was blue.
    # Measured, the brightest coral in the frame came out (0.14, 0.17, 0.18)
    # against a mustard albedo of (0.72, 0.58, 0.22).
    sky.CreateColorAttr(Gf.Vec3f(0.52, 0.68, 0.84))

    # ── the surface, from below ──────────────────────────────────────────────
    #
    # Seen from underneath, water is a mirror everywhere except a cone straight
    # up — total internal reflection, the "Snell's window" every diver knows.
    # A transmissive surface with water's index of refraction produces that for
    # free, which is worth far more than painting it on.
    surface = UsdGeom.Mesh.Define(stage, "/World/Surface")
    half = across / 2 * 1.5
    surface.CreatePointsAttr([
        Gf.Vec3f(-half, -half, water_level), Gf.Vec3f(half, -half, water_level),
        Gf.Vec3f(half, half, water_level), Gf.Vec3f(-half, half, water_level)])
    surface.CreateFaceVertexCountsAttr([4])
    surface.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    surface.CreateNormalsAttr([Gf.Vec3f(0, 0, -1)] * 4)
    surface.CreateExtentAttr([Gf.Vec3f(-half, -half, water_level - 0.01),
                              Gf.Vec3f(half, half, water_level + 0.01)])
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
    caustics.CreateIntensityAttr(5200.0 * left)
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

    # Read back, not assumed. A carb setting that does not exist accepts a
    # value silently and changes nothing, so every number below could have been
    # doing exactly nothing for as long as it has been here — and the way that
    # presents is a scene that looks vaguely underwater because of the light
    # while every adjustment to the fog does not move the picture at all.
    applied = {name: settings.get("/rtx/fog/" + name)
               for name in ("enabled", "fogDistance", "fogStartDistance",
                            "fogColorIntensity")}

    say("water_made",
        fogApplied=applied,
        visibilityM=17.0, surfaceAtM=water_level,
        daylightLeft=round(left, 3), atDepthM=round(working_depth, 1),
        absorbsInM=list(ATTENUATION_METRES))


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
    for path, base in (("/World/Sun", 1500.0), ("/World/Water", 150.0),
                       ("/World/Caustics", 1600.0)):
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

    light = stage.GetPrimAtPath("/World/Caustics")
    if not light:
        return
    x, y = (follow[0], follow[1]) if follow is not None else (0.0, 0.0)
    # A slow wander, the way a swell moves a caustic net across a bottom.
    x += 5.0 * math.sin(seconds * 0.06)
    y += 4.0 * math.cos(seconds * 0.043)
    for op in UsdGeom.Xformable(light).GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            op.Set(Gf.Vec3d(x, y, op.Get()[2]))
            return
