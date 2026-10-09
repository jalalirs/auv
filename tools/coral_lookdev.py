"""Look-development renders of close-up coral colonies, to hold against
photographs of real ones (Blender 4.5, Cycles).

    blender -b -P tools/coral_lookdev.py -- OUT.png COLONY.ply [COLONY.ply ...]

Each colony is a PLY with a colour per vertex (tools/coral_hd). The material
adds what is finer than the mesh: a brain coral's tissue has a fine grain on
it, a Porites is pitted all over with corallites about a millimetre and a half
across. The scene is a rubble seabed under clear Red Sea water, lit from above,
seen from a diver's metre away, with the water as tools/flyover_water.py has it
(absorption lengths 4, 17, 26 m in red, green, blue; a little blue scatter).
Colonies are set out in a row along x, a metre apart.
"""

import math
import os
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
out, colonies = args[0], args[1:]
# White balance as a diver's camera sets it: the scene's white point, in kelvin.
balance = float(next((a.split("=")[1] for a in colonies if a.startswith("wb=")), "12000"))
tint = float(next((a.split("=")[1] for a in colonies if a.startswith("tint=")), "50"))
exposure = float(next((a.split("=")[1] for a in colonies if a.startswith("ev=")), "-0.4"))
textures = next((a.split("=", 1)[1] for a in colonies if a.startswith("tex=")), None)
colonies = [a for a in colonies if "=" not in a]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "GPU"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "CUDA"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "CUDA"
scene.cycles.samples = 160
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
scene.view_settings.view_transform = "AgX"
scene.view_settings.exposure = exposure
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.use_white_balance = True
scene.view_settings.white_balance_temperature = balance
scene.view_settings.white_balance_tint = tint


def node(tree, kind, **inputs):
    n = tree.nodes.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def coral_material(name: str, pitted: bool, layer: str):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t, links = m.node_tree, m.node_tree.links
    bsdf = t.nodes["Principled BSDF"]
    colour = t.nodes.new("ShaderNodeVertexColor")
    colour.layer_name = layer
    # Living tissue is wet and a little glossy, and it shows on the tops.
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Subsurface Weight"].default_value = 0.08
    bsdf.inputs["Subsurface Radius"].default_value = (0.004, 0.003, 0.002)
    coords = t.nodes.new("ShaderNodeTexCoord")
    form = os.path.basename(name).split("-")[0]
    height_map = os.path.join(textures, f"corallite_{form}_height.png") if textures else None
    if height_map and os.path.exists(height_map):
        # The polyp-scale surface (tools/corallite), forty millimetres a
        # tile, projected from three sides so it needs no unwrapping.
        scale = t.nodes.new("ShaderNodeMapping")
        scale.inputs["Scale"].default_value = (1 / 0.04, 1 / 0.04, 1 / 0.04)
        links.new(coords.outputs["Object"], scale.inputs["Vector"])
        image = t.nodes.new("ShaderNodeTexImage")
        image.image = bpy.data.images.load(height_map)
        image.image.colorspace_settings.name = "Non-Color"
        image.projection = "BOX"
        image.projection_blend = 0.3
        links.new(scale.outputs["Vector"], image.inputs["Vector"])
        height = image.outputs["Color"]
        strength = 0.9
    elif pitted:
        # Corallites: a Voronoi cell a millimetre and a half across, its
        # centre sunk, the walls between standing.
        cells = node(t, "ShaderNodeTexVoronoi", Scale=650.0)
        cells.feature = "F1"
        links.new(coords.outputs["Object"], cells.inputs["Vector"])
        height = cells.outputs["Distance"]
        strength = 0.55
    else:
        grain = node(t, "ShaderNodeTexNoise", Scale=900.0, Detail=4.0)
        links.new(coords.outputs["Object"], grain.inputs["Vector"])
        height = grain.outputs["Fac"]
        strength = 0.25
    bump = node(t, "ShaderNodeBump", Strength=strength, Distance=0.0015 if height_map and os.path.exists(height_map) else 0.0008)
    links.new(height, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    # A little of the same detail in the colour, so pits read darker.
    mix = t.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.35
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.55, 0.55, 0.55, 1)
    links.new(height, ramp.inputs["Fac"])
    links.new(colour.outputs["Color"], mix.inputs["A"])
    links.new(ramp.outputs["Color"], mix.inputs["B"])
    # Crevices darker than the light alone makes them: sediment and shadowed
    # tissue collect there. Cycles' ambient occlusion over a few centimetres.
    occlusion = node(t, "ShaderNodeAmbientOcclusion", Distance=0.03)
    occlusion.samples = 8
    darken = t.nodes.new("ShaderNodeMix")
    darken.data_type = "RGBA"
    darken.blend_type = "MULTIPLY"
    darken.inputs["Factor"].default_value = 0.6
    links.new(mix.outputs["Result"], darken.inputs["A"])
    links.new(occlusion.outputs["AO"], darken.inputs["B"])
    links.new(darken.outputs["Result"], bsdf.inputs["Base Color"])
    return m


def seabed():
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    plane = bpy.context.active_object
    mod = plane.modifiers.new("subdivide", "SUBSURF")
    mod.subdivision_type = "SIMPLE"
    mod.levels = mod.render_levels = 6
    m = bpy.data.materials.new("rubble")
    m.use_nodes = True
    t, links = m.node_tree, m.node_tree.links
    bsdf = t.nodes["Principled BSDF"]
    coords = t.nodes.new("ShaderNodeTexCoord")
    stones = node(t, "ShaderNodeTexVoronoi", Scale=18.0)
    grain = node(t, "ShaderNodeTexNoise", Scale=60.0, Detail=8.0)
    patch = node(t, "ShaderNodeTexNoise", Scale=1.5, Detail=3.0)
    for n in (stones, grain, patch):
        links.new(coords.outputs["Object"], n.inputs["Vector"])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.30, 0.29, 0.22, 1)       # turf-covered rubble
    ramp.color_ramp.elements[1].color = (0.62, 0.58, 0.48, 1)       # sand
    links.new(patch.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    add = t.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    links.new(stones.outputs["Distance"], add.inputs[0])
    links.new(grain.outputs["Fac"], add.inputs[1])
    bump = node(t, "ShaderNodeBump", Strength=0.6, Distance=0.02)
    links.new(add.outputs["Value"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    plane.data.materials.append(m)


def water():
    world = bpy.data.worlds.new("sea")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.20, 0.42, 0.48, 1)
    bg.inputs[1].default_value = 0.18
    scene.world = world
    # Six metres of water over the seabed, as on a Red Sea reef slope, and
    # ten either side: the sun comes down through the six, not through thirty.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 1.75))
    bpy.context.active_object.scale = (20, 20, 5.5)
    box = bpy.context.active_object
    m = bpy.data.materials.new("water")
    m.use_nodes = True
    t, links = m.node_tree, m.node_tree.links
    t.nodes.remove(t.nodes["Principled BSDF"])
    absorb = node(t, "ShaderNodeVolumeAbsorption", Density=1.0)
    absorb.inputs["Color"].default_value = (1 - 1 / 4.0, 1 - 1 / 17.0, 1 - 1 / 26.0, 1)
    scatter = node(t, "ShaderNodeVolumeScatter", Density=0.006, Anisotropy=0.6)
    scatter.inputs["Color"].default_value = (0.12, 0.42, 0.85, 1)
    both = t.nodes.new("ShaderNodeAddShader")
    links.new(absorb.outputs[0], both.inputs[0])
    links.new(scatter.outputs[0], both.inputs[1])
    links.new(both.outputs[0], t.nodes["Material Output"].inputs["Volume"])
    box.data.materials.append(m)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 15.0
    sun.data.angle = math.radians(8)                 # light through water is softened
    sun.rotation_euler = (math.radians(25), math.radians(15), 0)
    scene.collection.objects.link(sun)


seabed()
water()
for k, path in enumerate(colonies):
    bpy.ops.wm.ply_import(filepath=path)
    obj = bpy.context.selected_objects[0]
    obj.location = (k * 1.0 - (len(colonies) - 1) * 0.5, 0, -0.01)
    obj.name = f"coral{k}"
    bpy.ops.object.shade_smooth()
    layer = obj.data.color_attributes[0].name if obj.data.color_attributes else "Col"
    obj.data.materials.append(coral_material(os.path.basename(path), "porites" in path.lower(), layer))

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 35
scene.collection.objects.link(cam)
scene.camera = cam
# Framed to what is there: a single colony fills about two thirds of the
# frame whatever its size, a row of them the row.
corals = [o for o in scene.objects if o.type == "MESH" and o.name not in ("Plane", "Cube")]
size = max(max(o.dimensions[0], o.dimensions[1]) for o in corals) if corals else 1.0
span = max(size * 1.6, len(colonies) * 1.0 if len(colonies) > 1 else 0)
cam.location = (0, -1.05 * span, 0.62 * span)
cam.rotation_euler = (math.radians(58), 0, 0)
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
