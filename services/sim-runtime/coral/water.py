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
SCATTER = (0.015, 0.14, 0.30)


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
    settings.set("/rtx/post/tonemap/fNumber", 4.0)
    settings.set("/rtx/post/tonemap/iso", 200.0)

    # ── the water ────────────────────────────────────────────────────────────
    #
    # The renderer's global fog, which is a general atmospheric effect being
    # used for the thing it is actually a good model of: a participating medium
    # that absorbs and scatters over distance.
    settings.set("/rtx/fog/enabled", True)
    settings.set("/rtx/fog/fogColor", list(SCATTER))
    settings.set("/rtx/fog/fogColorIntensity", 1.35)
    # Visibility, near enough. Twenty metres is a good day on a reef; a diver
    # calls thirty exceptional and five a bad one.
    settings.set("/rtx/fog/fogDistance", 11.0)
    settings.set("/rtx/fog/fogDensity", 1.0)
    settings.set("/rtx/fog/fogHeightDensity", 1.0)
    settings.set("/rtx/fog/fogStartDistance", 0.5)

    # ── the sun ──────────────────────────────────────────────────────────────
    #
    # Angled rather than overhead, so the seabed has relief in it. A light
    # straight down flattens everything it touches.
    sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
    # Bright, because the fog is between the sun and everything it lights and
    # takes most of it. The first attempt used a daylight intensity and produced
    # a seabed that was a black silhouette in green water: correct absorption,
    # nothing left to absorb.
    # What is left of the sun at the depth this dive happens at.
    #
    # Full daylight lights the seabed like a beach, because it is the light
    # above the surface and not the light that got down here. The fog gives the
    # colour of depth and this gives its dimness; without both, a reef at
    # fifteen metres photographs like a sandbar at noon.
    left = is_it_deep(max(0.0, working_depth))
    sun.CreateIntensityAttr(1300.0 * left)
    sun.CreateAngleAttr(2.0)
    sun.CreateColorAttr(Gf.Vec3f(0.86, 0.96, 0.98))
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-52.0, 0.0, 18.0))

    # Everything the water scatters back, which is what stops the shadows being
    # black. Underwater there is no such thing as an unlit surface: the medium
    # itself glows in every direction.
    sky = UsdLux.DomeLight.Define(stage, "/World/Water")
    sky.CreateIntensityAttr(190.0 * left)
    # Strongly coloured, not a neutral fill. Everything not in direct sun is
    # lit by water, and water is blue-green: a grey ambient makes a reef look
    # like a quarry with a blue filter over it.
    sky.CreateColorAttr(Gf.Vec3f(0.05, 0.38, 0.72))

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
    caustics.CreateColorAttr(Gf.Vec3f(0.72, 0.94, 1.0))
    caustics.CreateNormalizeAttr(False)
    caustics.GetPrim().CreateAttribute(
        "inputs:texture:file", Sdf.ValueTypeNames.Asset).Set("/isaac-sim/coral/caustics.png")
    # No rotation. A rect light already faces its own -Z, which is downward
    # here; turning it a half turn about X — which looked like the obvious way
    # to point it at the seabed — pointed it at the sky, and the caustics lit
    # the underside of the surface from above where nobody could see them.
    moving = UsdGeom.Xformable(caustics.GetPrim())
    moving.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, water_level - 0.5))

    say("water_made",
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
    for path, base in (("/World/Sun", 1300.0), ("/World/Water", 190.0),
                       ("/World/Caustics", 5200.0)):
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
