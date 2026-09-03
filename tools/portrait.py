"""A picture of a thing, from its own package.

Run inside Blender, on the machine with the GPUs:

    blender -b -P tools/portrait.py -- <model.usd> <out.jpg> [width] [height]

Imports the USD a package carries, frames it, lights it plainly, and renders
one picture. That is the picture a card shows: a render of the thing itself and
nothing else, because a card with somebody else's photograph on it is a card
that lies about what you are about to dive in.

Neutral ground, one soft key light and a fill, the camera three-quarters from
the front and a little above — the way a vehicle is photographed on a bench.
"""

from __future__ import annotations

import math
import pathlib
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
model, out = pathlib.Path(argv[0]).resolve(), pathlib.Path(argv[1]).resolve()
W = int(argv[2]) if len(argv) > 2 else 1280
H = int(argv[3]) if len(argv) > 3 else 720

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 128
scene.cycles.use_denoising = True
scene.cycles.device = "GPU"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.refresh_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.image_settings.file_format = "JPEG"
scene.render.image_settings.quality = 90
scene.render.filepath = str(out)
scene.view_settings.view_transform = "AgX"

bpy.ops.wm.usd_import(filepath=str(model), import_cameras=False, import_lights=False)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit(f"{model} has no meshes")

# Where the thing is and how big, in world space, from every vertex it has.
lo = Vector((math.inf,) * 3); hi = Vector((-math.inf,) * 3)
for o in meshes:
    for corner in o.bound_box:
        p = o.matrix_world @ Vector(corner)
        lo = Vector(min(a, b) for a, b in zip(lo, p)); hi = Vector(max(a, b) for a, b in zip(hi, p))
centre = (lo + hi) / 2
size = max(hi - lo)
print(f"portrait: {len(meshes)} meshes, {size:.3f} units across, centre {tuple(round(c, 3) for c in centre)}")

# A plain ground under it, at its lowest point.
bpy.ops.mesh.primitive_plane_add(size=size * 12, location=(centre.x, centre.y, lo.z))
ground = bpy.context.active_object
gm = bpy.data.materials.new("Ground"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.07, 0.10, 0.14, 1)
gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
ground.data.materials.append(gm)

world = bpy.data.worlds.new("Studio"); scene.world = world; world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.05, 0.08, 0.12, 1); bg.inputs["Strength"].default_value = 1.0

def light(name, kind, where, energy, size_):
    data = bpy.data.lights.new(name, kind); data.energy = energy
    if kind == "AREA":
        data.size = size_
    obj = bpy.data.objects.new(name, data); scene.collection.objects.link(obj)
    obj.location = centre + Vector(where) * size
    obj.rotation_euler = (centre - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj

light("Key", "AREA", (-1.6, -1.8, 1.8), 900 * size * size, size * 1.6)
light("Fill", "AREA", (2.2, -0.8, 0.9), 300 * size * size, size * 2.2)
light("Rim", "AREA", (0.6, 2.2, 1.4), 500 * size * size, size * 1.2)

cam = bpy.data.cameras.new("Cam"); cam.lens = 50.0
co = bpy.data.objects.new("Cam", cam); scene.collection.objects.link(co); scene.camera = co
co.location = centre + Vector((-1.15, -1.55, 0.7)) * size * 1.35
co.rotation_euler = (centre - co.location).to_track_quat("-Z", "Y").to_euler()

bpy.ops.render.render(write_still=True)
print("PORTRAIT_DONE")
