"""Put the water over the ground.

Cycles does the thing Isaac Sim's fog was standing in for: a participating
medium with absorption that differs by wavelength. Red is gone in a few metres,
green in about seventeen, blue in about twenty-six — clear coastal water — and
that is set as absorption lengths, not as a colour somebody liked. The surface
is a sheet with water's index of refraction, so Snell's window and the mirror
underside come for free.

Colour and dimness with depth are the water's. What the camera does about it is
a separate question, and here the camera is white balanced the way every reef
photograph is, and exposed for the depth the flight spends most of its time at.
"""

from __future__ import annotations

import math

import bpy

# Metres to 1/e, per channel. Jerlov type 1C, clear coastal.
ATTENUATION_M = (4.0, 17.0, 26.0)
# Scatter: what makes the distance glow blue. The first setting, 0.012 with a
# pale colour, filled forty metres of water with white haze and washed the
# reef out; the medium scatters little and what it scatters is blue.
SCATTER_DENSITY = 0.005
SCATTER_COLOUR = (0.12, 0.42, 0.85)


def flood(scene, across: float, sun_object, world) -> None:
    half = across / 2 * 1.5
    # ── the surface ──────────────────────────────────────────────────────────
    mesh = bpy.data.meshes.new("Surface")
    mesh.from_pydata([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [], [(0, 1, 2, 3)])
    surface = bpy.data.objects.new("Surface", mesh)
    scene.collection.objects.link(surface)
    m = bpy.data.materials.new("Water"); m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)
    bsdf.inputs["Roughness"].default_value = 0.02
    bsdf.inputs["IOR"].default_value = 1.333
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    # A little swell, so the surface is not a mirror plane.
    wave = nt.nodes.new("ShaderNodeTexNoise"); wave.inputs["Scale"].default_value = 0.03; wave.inputs["Detail"].default_value = 4.0
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35; bump.inputs["Distance"].default_value = 0.4
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"]); nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    surface.data.materials.append(m)
    surface.visible_shadow = False   # the fog below is what light through the surface looks like

    # ── the water column ─────────────────────────────────────────────────────
    depth = 60.0
    vm = bpy.data.meshes.new("Column")
    vm.from_pydata([(-half, -half, -depth), (half, -half, -depth), (half, half, -depth), (-half, half, -depth),
                    (-half, -half, 0.01), (half, -half, 0.01), (half, half, 0.01), (-half, half, 0.01)], [],
                   [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    column = bpy.data.objects.new("Column", vm)
    scene.collection.objects.link(column)
    wm = bpy.data.materials.new("Column"); wm.use_nodes = True
    nt = wm.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    out = nt.nodes["Material Output"]
    absorb = nt.nodes.new("ShaderNodeVolumeAbsorption")
    # sigma = density * (1 - colour): colour = 1 - 1/length at density 1
    absorb.inputs["Color"].default_value = (*(1 - 1 / l for l in ATTENUATION_M), 1.0)
    absorb.inputs["Density"].default_value = 1.0
    scatter = nt.nodes.new("ShaderNodeVolumeScatter")
    scatter.inputs["Color"].default_value = (*SCATTER_COLOUR, 1.0)
    scatter.inputs["Density"].default_value = SCATTER_DENSITY
    scatter.inputs["Anisotropy"].default_value = 0.6
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(absorb.outputs["Volume"], add.inputs[0]); nt.links.new(scatter.outputs["Volume"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Volume"])
    column.data.materials.append(wm)
    column.visible_shadow = False
    column.visible_camera = True

    # ── light and camera ─────────────────────────────────────────────────────
    # Daylight, high, because everything below the surface takes its share now.
    sun_object.data.energy = 12.0
    sun_object.rotation_euler = (math.radians(35), 0.0, math.radians(-55))
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.45, 0.65, 0.95, 1)
    bg.inputs["Strength"].default_value = 1.0
    # Exposed for ten metres down, white balanced. The water keeps its blue with
    # distance because the absorption is in the medium, not in the light.
    scene.view_settings.exposure = 0.4
    scene.cycles.volume_step_rate = 2.0
    scene.cycles.volume_max_steps = 256
    scene.cycles.volume_bounces = 1
    print("flooded: absorption lengths", ATTENUATION_M, "m; scatter density", SCATTER_DENSITY)
