"""A still of a place from where a dive begins (Blender 4.5, Cycles): its
seabed and its reef as the place's own files have them, under the same water
as tools/coral_lookdev.py, to see what a diver would.

    blender -b -P tools/place_view.py -- PLACE_DIR OUT.png [ahead=4] [up=1.6] [yaw=0] [at=X,Y]

The camera stands `ahead` metres behind the place's dive start (or `at`, in
site metres), `up` metres over the seabed there, looking along `yaw` degrees
(0 is east), tilted down.
Each colony prototype wears its corallite surface (read off coral.usda, which
names it for the renderer's MDL) as a bump projected from three sides.
"""

import json
import math
import os
import re
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
place, out = args[0], args[1]
opts = dict(a.split("=", 1) for a in args[2:])
ahead, up, yaw = float(opts.get("ahead", 4)), float(opts.get("up", 1.6)), math.radians(float(opts.get("yaw", 0)))

site = json.load(open(os.path.join(place, "site.json")))
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "GPU"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "CUDA"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "CUDA"
scene.cycles.samples = 128
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = 1600, 900
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -0.2
scene.view_settings.use_white_balance = True
scene.view_settings.white_balance_temperature = 12000
scene.view_settings.white_balance_tint = 70

bpy.ops.wm.usd_import(filepath=os.path.join(place, "seabed.usda"))
bpy.ops.wm.usd_import(filepath=os.path.join(place, "coral.usda"))

for o in scene.objects:
    if o.type == "MESH":
        for poly in o.data.polygons:
            poly.use_smooth = True

# The seabed wears the place's own colour map (the renderer's MDL is not
# Blender's), laid on by position: the map covers the place's square.
across_m = site["from"]["acrossMetres"]
for o in scene.objects:
    if o.type == "MESH" and "Seabed" in o.name:
        # Faces wound the other way round come in facing down, and a seabed
        # facing down is lit from below, which is black.
        # And normals carried in the file override the faces' own: cleared,
        # so the flipped faces are what shading reads.
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        if o.data.has_custom_normals:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        up_count = sum(1 for poly in o.data.polygons if poly.normal.z > 0)
        if up_count < len(o.data.polygons) / 2:
            o.data.flip_normals()
        print("SEABED", o.name, len(o.data.polygons), "faces, facing up", up_count)
        ground_m = bpy.data.materials.new("ground")
        ground_m.use_nodes = True
        gt = ground_m.node_tree
        gb = gt.nodes["Principled BSDF"]
        gb.inputs["Roughness"].default_value = 0.9
        gc = gt.nodes.new("ShaderNodeTexCoord")
        gm = gt.nodes.new("ShaderNodeMapping")
        gm.inputs["Scale"].default_value = (1 / across_m, 1 / across_m, 1)
        gm.inputs["Location"].default_value = (0.5, 0.5, 0)
        gi = gt.nodes.new("ShaderNodeTexImage")
        colour_map = os.path.join(place, "textures", "site_colour.jpg")
        if os.path.exists(colour_map):
            gi.image = bpy.data.images.load(colour_map)
        gi.extension = "EXTEND"
        gt.links.new(gc.outputs["Object"], gm.inputs["Vector"])
        gt.links.new(gm.outputs["Vector"], gi.inputs["Vector"])
        gt.links.new(gi.outputs["Color"], gb.inputs["Base Color"])
        rough = gt.nodes.new("ShaderNodeTexNoise")
        rough.inputs["Scale"].default_value = 3.0
        rough.inputs["Detail"].default_value = 10.0
        bump = gt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.4
        bump.inputs["Distance"].default_value = 0.05
        gt.links.new(gc.outputs["Object"], rough.inputs["Vector"])
        gt.links.new(rough.outputs["Fac"], bump.inputs["Height"])
        gt.links.new(bump.outputs["Normal"], gb.inputs["Normal"])
        o.data.materials.clear()
        o.data.materials.append(ground_m)

# Corallite surfaces, per prototype material, from what coral.usda names.
text = open(os.path.join(place, "coral.usda")).read()
forms = dict(re.findall(r'def Material "Skin_(\d+)".*?(?:corallite_(\w+?)_normal\.png|def Material)', text, re.S))
for m in bpy.data.materials:
    found = re.match(r"Skin_(\d+)", m.name)
    form = forms.get(found.group(1)) if found else None
    height = os.path.join(place, "textures", f"corallite_{form}_height.png") if form else None
    if not (m.use_nodes and height and os.path.exists(height)):
        continue
    t, links = m.node_tree, m.node_tree.links
    bsdf = next((n for n in t.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        continue
    bsdf.inputs["Roughness"].default_value = 0.45
    coords = t.nodes.new("ShaderNodeTexCoord")
    scale = t.nodes.new("ShaderNodeMapping")
    scale.inputs["Scale"].default_value = (25, 25, 25)            # forty millimetres a tile
    image = t.nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(height)
    image.image.colorspace_settings.name = "Non-Color"
    image.projection, image.projection_blend = "BOX", 0.3
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.0015
    links.new(coords.outputs["Object"], scale.inputs["Vector"])
    links.new(scale.outputs["Vector"], image.inputs["Vector"])
    links.new(image.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

# Water: the dive's depth of it above, as coral_lookdev has it.
world = bpy.data.worlds.new("sea")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.20, 0.42, 0.48, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.18
scene.world = world
x, y, z = site["beginAt"]
if "at" in opts:
    x, y = (float(v) for v in opts["at"].split(","))
bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z / 2))
box = bpy.context.active_object
box.scale = (80, 80, abs(z) + 30)
box.location = (x, y, -(abs(z) + 30) / 2 + 0.01)
m = bpy.data.materials.new("water")
m.use_nodes = True
t = m.node_tree
t.nodes.remove(t.nodes["Principled BSDF"])
absorb = t.nodes.new("ShaderNodeVolumeAbsorption")
absorb.inputs["Color"].default_value = (1 - 1 / 4.0, 1 - 1 / 17.0, 1 - 1 / 26.0, 1)
scatter = t.nodes.new("ShaderNodeVolumeScatter")
scatter.inputs["Density"].default_value = 0.006
scatter.inputs["Color"].default_value = (0.12, 0.42, 0.85, 1)
scatter.inputs["Anisotropy"].default_value = 0.6
both = t.nodes.new("ShaderNodeAddShader")
t.links.new(absorb.outputs[0], both.inputs[0])
t.links.new(scatter.outputs[0], both.inputs[1])
t.links.new(both.outputs[0], t.nodes["Material Output"].inputs["Volume"])
box.data.materials.append(m)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy, sun.data.angle = 15.0, math.radians(8)
sun.rotation_euler = (math.radians(25), math.radians(15), 0)
scene.collection.objects.link(sun)

# The seabed's height under the camera, found by dropping a ray onto the
# seabed as imported: the heightfield file's own row order is not the mesh's,
# and reading it put the camera under the ground.
import mathutils  # noqa: E402

cx, cy = x - ahead * math.cos(yaw), y - ahead * math.sin(yaw)
bpy.context.view_layer.update()
seabed = next(o for o in scene.objects if o.type == "MESH" and "Seabed" in o.name)
box.hide_set(True)
hit, where, *_ = scene.ray_cast(bpy.context.view_layer.depsgraph, mathutils.Vector((cx, cy, 50.0)),
                                mathutils.Vector((0, 0, -1)))
box.hide_set(False)
ground = where.z if hit else z - 3.0
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 16                                                       # a GoPro's wide view
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (cx, cy, ground + up)
cam.rotation_euler = (math.radians(70), 0, yaw - math.pi / 2)
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("CAMERA", cam.location[:], "ground", ground)
