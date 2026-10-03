"""Each thruster's propeller, turning at the speed its command gives it.

Reads    thrust: the angle each propeller is at, and its speed (systems/thrusters.py)

A three-bladed propeller is put at every thruster the vehicle package lists,
facing the way it pushes, at the diameter the package states — a package that
states none gets none drawn, because a hull that already has propellers
modelled in it would get two. Each frame turns it to the angle it is at in
simulated time.

At full speed a propeller turns sixty times a second, which no film frame
rate can show as turning: a camera sees a blur, and a frame-by-frame drawing
of the blades would strobe — stand still, crawl backwards, or flash as they
catch the light in a new place every frame (Luna's stern did, in its first
film). So the blades are drawn only while a frame can resolve them: while
they move less than STROBES_FROM_DEG between frames, fading out by
GONE_BY_DEG. Past that a propeller is the blur a camera sees — a disc as wide
as the blades, more solid the faster they turn.
"""

from __future__ import annotations

import math

import numpy as np

BLADES = 3
# Steps along a blade and across it. Small: eight propellers on a vehicle a
# third of a metre long are a few pixels each in most frames.
ALONG, ACROSS = 6, 3
HUB = 0.22                 # the hub, as a share of the radius
DISC_SIDES = 32
# How solid the blur gets at full speed. Not wholly: a real disc of spinning
# blades is mostly water.
MOST_BLUR = 0.55
# How far the blades may turn between one film frame and the next and still be
# drawn, degrees: a sixth of the gap between blades is where a frame stops
# showing which way they went.
STROBES_FROM_DEG = 15.0
GONE_BY_DEG = 40.0
FRAME_S = 1.0 / 24.0


def blade_mesh(radius: float):
    """Three twisted blades and a hub, axis along +z, as (points, triangles).

    Each blade is a thin surface whose pitch angle falls from root to tip, as
    a propeller's does (a constant pitch P gives atan(P / 2πr)), and whose
    chord is widest a third of the way out.
    """
    points, faces = [], []
    pitch = 1.1 * 2.0 * radius               # pitch about the diameter, as small props are
    for b in range(BLADES):
        about = 2.0 * math.pi * b / BLADES
        base = len(points)
        for i in range(ALONG + 1):
            r = radius * (HUB + (1.0 - HUB) * i / ALONG)
            chord = radius * (0.55 - 0.35 * abs(i / ALONG - 0.33))
            twist = math.atan2(pitch, 2.0 * math.pi * max(r, 1e-6))
            for j in range(ACROSS + 1):
                s = (j / ACROSS - 0.5) * chord
                # Across the chord: around the circle, and along the axis by
                # the twist.
                a = about + s * math.cos(twist) / max(r, 1e-6)
                z = s * math.sin(twist)
                points.append((r * math.cos(a), r * math.sin(a), z))
        for i in range(ALONG):
            for j in range(ACROSS):
                p = base + i * (ACROSS + 1) + j
                q = p + ACROSS + 1
                faces += [(p, q, p + 1), (p + 1, q, q + 1)]
    # The hub: a short cylinder, capped.
    base = len(points)
    hub, half = HUB * radius, 0.35 * radius
    sides = 10
    for k in range(sides):
        a = 2.0 * math.pi * k / sides
        points.append((hub * math.cos(a), hub * math.sin(a), -half))
        points.append((hub * math.cos(a), hub * math.sin(a), half))
    for k in range(sides):
        a0, a1 = base + 2 * k, base + 2 * ((k + 1) % sides)
        faces += [(a0, a1, a0 + 1), (a0 + 1, a1, a1 + 1)]
    return np.array(points, dtype=float), np.array(faces, dtype=int)


def disc_mesh(radius: float):
    """A flat disc the size of the blades, for their blur."""
    points = [(0.0, 0.0, 0.0)] + [(radius * math.cos(2 * math.pi * k / DISC_SIDES),
                                   radius * math.sin(2 * math.pi * k / DISC_SIDES), 0.0)
                                  for k in range(DISC_SIDES)]
    faces = [(0, 1 + k, 1 + (k + 1) % DISC_SIDES) for k in range(DISC_SIDES)]
    return np.array(points, dtype=float), np.array(faces, dtype=int)


def facing(direction) -> tuple:
    """The quaternion (w, x, y, z) that turns +z onto `direction`."""
    d = np.asarray(direction, dtype=float)
    d = d / max(float(np.linalg.norm(d)), 1e-12)
    z = np.array([0.0, 0.0, 1.0])
    c = float(np.dot(z, d))
    if c > 1.0 - 1e-9:
        return (1.0, 0.0, 0.0, 0.0)
    if c < -1.0 + 1e-9:
        return (0.0, 1.0, 0.0, 0.0)
    axis = np.cross(z, d)
    axis = axis / np.linalg.norm(axis)
    half = math.acos(c) / 2.0
    s = math.sin(half)
    return (math.cos(half), float(axis[0] * s), float(axis[1] * s), float(axis[2] * s))


def blur(rpm: float, most_rpm: float) -> float:
    """How solid the blur disc is at this speed: nothing standing still, and
    MOST_BLUR at full speed, rising as the speed does."""
    if most_rpm <= 0:
        return 0.0
    return MOST_BLUR * min(1.0, abs(float(rpm)) / float(most_rpm))


def blades_seen(rpm: float, frame_s: float = FRAME_S) -> float:
    """How much of the blades a frame shows: all of them while they turn less
    than STROBES_FROM_DEG a frame, none past GONE_BY_DEG."""
    step = abs(float(rpm)) / 60.0 * 360.0 * float(frame_s)
    return float(np.clip((GONE_BY_DEG - step) / (GONE_BY_DEG - STROBES_FROM_DEG), 0.0, 1.0))


def disc_seen(rpm: float, most_rpm: float, frame_s: float = FRAME_S) -> float:
    """How solid the blur is: where the blades are not, and more so the faster
    they turn."""
    return blur(rpm, most_rpm) + (1.0 - blades_seen(rpm, frame_s)) * MOST_BLUR * 0.35 * (
        1.0 - min(1.0, abs(float(rpm)) / max(float(most_rpm), 1e-9)))


def put_in(stage, vehicle_path: str, thrusters, diameter_m: float, units_per_metre: float = 1.0):
    """Put a propeller at every thruster, under the vehicle, once.

    Returns what `turn` needs: the spin operation of each and the blur
    material's opacity input."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    radius = 0.5 * float(diameter_m) * units_per_metre
    blades, blade_faces = blade_mesh(radius)
    disc, disc_faces = disc_mesh(radius * 1.02)
    scope = f"{vehicle_path}/Propellers"
    UsdGeom.Scope.Define(stage, scope)
    looks = UsdGeom.Scope.Define(stage, f"{scope}/Looks")

    def see_through(name, colour, rough, start):
        """A material whose opacity is set each frame: the preview surface's,
        and the renderer's beside it, which is what a dive is drawn with."""
        look = UsdShade.Material.Define(stage, f"{looks.GetPath()}/{name}")
        preview = UsdShade.Shader.Define(stage, f"{look.GetPath()}/S")
        preview.CreateIdAttr("UsdPreviewSurface")
        preview.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*colour))
        preview.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
        opacity = preview.CreateInput("opacity", Sdf.ValueTypeNames.Float)
        opacity.Set(start)
        look.CreateSurfaceOutput().ConnectToSource(preview.ConnectableAPI(), "surface")
        mdl = UsdShade.Shader.Define(stage, f"{look.GetPath()}/M")
        mdl.SetSourceAsset(Sdf.AssetPath("OmniPBR.mdl"), "mdl")
        mdl.SetSourceAssetSubIdentifier("OmniPBR", "mdl")
        mdl.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*colour))
        mdl.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(rough)
        mdl.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(True)
        mdl_opacity = mdl.CreateInput("opacity_constant", Sdf.ValueTypeNames.Float)
        mdl_opacity.Set(start)
        look.CreateSurfaceOutput("mdl").ConnectToSource(mdl.CreateOutput("out", Sdf.ValueTypeNames.Token))
        return look, (opacity, mdl_opacity)

    def mesh(path, points, faces):
        m = UsdGeom.Mesh.Define(stage, path)
        m.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in points]))
        m.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(faces)))
        m.CreateFaceVertexIndicesAttr(Vt.IntArray([int(v) for f in faces for v in f]))
        m.CreateDoubleSidedAttr(True)
        m.CreateSubdivisionSchemeAttr("none")
        return m

    handles = []
    for i, unit in enumerate(thrusters):
        holder = UsdGeom.Xform.Define(stage, f"{scope}/P{i}")
        x, y, z = (float(v) * units_per_metre for v in unit.position)
        holder.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
        w, qx, qy, qz = facing(unit.direction)
        holder.AddOrientOp().Set(Gf.Quatf(w, qx, qy, qz))
        spin = holder.AddRotateZOp()
        spin.Set(0.0)
        # Each propeller's blades and blur have their own materials, because
        # each is as visible as that propeller is fast.
        metal, blade_opacity = see_through(f"Blade{i}", (0.05, 0.05, 0.055), 0.35, 1.0)
        body = mesh(f"{scope}/P{i}/Blades", blades, blade_faces)
        UsdShade.MaterialBindingAPI.Apply(body.GetPrim()).Bind(metal)
        look, disc_opacity = see_through(f"Blur{i}", (0.08, 0.08, 0.09), 0.5, 0.0)
        smear = mesh(f"{scope}/P{i}/Blur", disc, disc_faces)
        UsdShade.MaterialBindingAPI.Apply(smear.GetPrim()).Bind(look)
        handles.append((spin, blade_opacity, disc_opacity))
    return handles


def turn(handles, thrust, frame_s: float = FRAME_S) -> None:
    """Turn each propeller to where it is; show its blades as far as a frame
    `frame_s` long can resolve them, and its blur as fast as it goes."""
    for (spin, blade_opacity, disc_opacity), angle, rpm, most in zip(
            handles, thrust.angle, thrust.rpm, thrust.max_rpm):
        spin.Set(float(math.degrees(angle)))
        for knob in blade_opacity:
            knob.Set(blades_seen(rpm, frame_s))
        for knob in disc_opacity:
            knob.Set(disc_seen(rpm, most, frame_s))
