"""A diver's transect filmed through a real reef's photogrammetry model.

    blender -b -P ml/reconstruct/synthetic/from_model.py -- MODEL.obj OUT [--frames N]

The model (KAUST's, from Agisoft Metashape: a textured mesh in local metres,
z up) is the truth. A camera swims along its long side a metre and a half
over the seabed, looking forward and down, weaving as a diver's GoPro does.
The texture already holds the light the photographs were taken in, so it is
drawn as it is (emission), not lit a second time. Written into OUT:

    frames/00000.jpg ...   what the camera saw
    frames/frames.json
    cameras.json           where each frame was taken from, and its lens
    truth.obj              the model as rendered (a copy, for scoring)
"""

import json
import math
import pathlib
import shutil
import sys

import bpy
import mathutils

args = sys.argv[sys.argv.index("--") + 1:]
MODEL, OUT = pathlib.Path(args[0]), pathlib.Path(args[1])
FRAMES = int(args[args.index("--frames") + 1]) if "--frames" in args else 64
WIDE, TALL, FOCAL_PX = 1332, 735, 1300.0
(OUT / "frames").mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.wm.obj_import(filepath=str(MODEL), forward_axis="Y", up_axis="Z")
reef = bpy.context.selected_objects[0]

# Drawn as photographed: the texture, as emission.
for slot in reef.material_slots:
    mat = slot.material
    if mat is None or not mat.use_nodes:
        continue
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    image = next((n for n in nodes if n.type == "TEX_IMAGE"), None)
    out = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")
    if image is None:
        continue
    emit = nodes.new("ShaderNodeEmission")
    links.new(image.outputs["Color"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])

world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.18, 0.25, 1)
scene.world = world

# The path: along the model's longer side, over the middle.
corners = [reef.matrix_world @ mathutils.Vector(c) for c in reef.bound_box]
xs, ys = [c.x for c in corners], [c.y for c in corners]
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
along_y = (y1 - y0) >= (x1 - x0)
depsgraph = bpy.context.evaluated_depsgraph_get()


def seabed(x, y):
    hit, where, *_ = scene.ray_cast(depsgraph, mathutils.Vector((x, y, 100.0)), mathutils.Vector((0, 0, -1)))
    return where.z if hit else None


cam_data = bpy.data.cameras.new("cam")
cam_data.sensor_fit = "HORIZONTAL"
cam_data.sensor_width = 36.0
cam_data.lens = FOCAL_PX * 36.0 / WIDE
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x, scene.render.resolution_y = WIDE, TALL
scene.render.resolution_percentage = 100
scene.render.engine = "CYCLES"
scene.cycles.device = "GPU"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "CUDA"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "CUDA"
scene.cycles.samples = 16
scene.cycles.use_denoising = False
scene.view_settings.view_transform = "Standard"
scene.render.image_settings.file_format = "JPEG"
scene.render.image_settings.quality = 95

margin = 1.2                                    # the camera looks ahead: start it back from the far end
cameras, last_ground = [], None
mid = (x0 + x1) / 2 if along_y else (y0 + y1) / 2
for i in range(FRAMES):
    s = i / (FRAMES - 1)
    weave = 0.35 * math.sin(2 * math.pi * s * 2.5)
    if along_y:
        x, y = mid + weave, y0 + 0.4 + (y1 - y0 - 0.4 - margin) * s
        heading = math.pi / 2                     # looking along +y
    else:
        x, y = x0 + 0.4 + (x1 - x0 - 0.4 - margin) * s, mid + weave
        heading = 0.0
    ground = seabed(x, y)
    ground = last_ground if ground is None else ground
    last_ground = ground
    z = (ground if ground is not None else 0.0) + 1.5 + 0.1 * math.sin(2 * math.pi * s * 4)
    yaw = heading + math.radians(8 * math.cos(2 * math.pi * s * 2.5))
    cam.location = (x, y, z)
    cam.rotation_euler = mathutils.Euler((math.radians(40), 0.0, yaw - math.pi / 2), "XYZ")
    scene.render.filepath = str(OUT / "frames" / f"{i:05d}.jpg")
    bpy.ops.render.render(write_still=True)
    cameras.append({"name": f"{i:05d}.jpg", "centre": [x, y, z],
                    "world_from_camera": [list(row) for row in cam.matrix_world]})

(OUT / "cameras.json").write_text(json.dumps({"width": WIDE, "height": TALL, "focalPx": FOCAL_PX,
                                              "frames": cameras, "model": str(MODEL)}, indent=1))
(OUT / "frames" / "frames.json").write_text(json.dumps(
    {"videos": [MODEL.name], "fromSeconds": 0.0, "toSeconds": FRAMES * 0.5, "everySeconds": 0.5, "frames": FRAMES,
     "size": [WIDE, TALL], "synthetic": True, "from": "KAUST photogrammetry model"}, indent=1))
shutil.copy(MODEL, OUT / "truth.obj")
print(json.dumps({"frames": FRAMES, "box": [x0, x1, y0, y1], "alongY": along_y}))
