"""A reef whose 3D is known, filmed the way a diver films a transect: the test
the fusion of the coral library and the video is scored on.

    blender -b -P ml/reconstruct/synthetic/reef.py -- LIBRARY OUT [--seed N] [--frames N]

Colonies from the coral library (massive, brain, a few branching) stand on a
rippled, textured sand patch eight metres by four. A camera swims along it a
metre and a half above, looking forward and down, weaving a little, as a
diver's GoPro does. Written into OUT:

    frames/00000.jpg ...   what the camera saw (Cycles)
    frames/frames.json     how the frames were made, for iocean-reconstruct
    labels/00000.png ...   each pixel's class, in the cover model's ids
                           (45 massive alive, 48 meandering coral alive,
                           12 acropora alive, 69 sand), from the scene itself
    labels/classes.json
    truth.ply              every surface, in metres, z up, with each vertex's
                           class and colony
    cameras.json           where each frame was taken from, and its lens
"""

import json
import math
import pathlib
import random
import sys

import bpy
import mathutils
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
LIBRARY, OUT = pathlib.Path(args[0]), pathlib.Path(args[1])
SEED = int(args[args.index("--seed") + 1]) if "--seed" in args else 7
FRAMES = int(args[args.index("--frames") + 1]) if "--frames" in args else 64
WIDE, TALL, FOCAL_PX = 1332, 735, 1300.0
CLASS = {"massive": 45, "brain": 48, "branching": 12, "sand": 69}
CLASS_NAMES = {45: "massive alive", 48: "meandering coral alive", 12: "acropora alive", 69: "sand"}

random.seed(SEED)
rng = np.random.default_rng(SEED)
(OUT / "frames").mkdir(parents=True, exist_ok=True)
(OUT / "labels").mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def read_ply(path):
    data = path.read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    head = data[:end].decode().split("\n")
    nv = int(next(h for h in head if h.startswith("element vertex")).split()[-1])
    nf = int(next(h for h in head if h.startswith("element face")).split()[-1])
    vert = np.frombuffer(data, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"),
                                      ("b", "u1")], count=nv, offset=end)
    face = np.frombuffer(data, dtype=[("n", "u1"), ("i", "<i4", 3)], count=nf, offset=end + vert.nbytes)
    v = np.stack([vert["x"], vert["y"], vert["z"]], 1).astype(float)
    c = np.stack([vert["r"], vert["g"], vert["b"]], 1) / 255.0
    return v, face["i"].astype(int), c


def mesh_object(name, v, f, colours=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(v.tolist(), [], f.tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    if colours is not None:
        layer = mesh.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        flat = np.c_[colours, np.ones(len(colours))].astype("float32").ravel()
        layer.data.foreach_set("color", flat)
    return obj


def vertex_colour_material(name, rough=0.7):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    attr = nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    return mat


# ── the sand: rippled, and textured finely enough for features to land on ───
nx, ny = 320, 160
xs, ys = np.linspace(-4, 4, nx), np.linspace(-2, 2, ny)
gx, gy = np.meshgrid(xs, ys)
height = (0.03 * np.sin(gx * 9 + 0.6 * np.sin(gy * 2)) + 0.04 * np.sin(gx * 0.7 + gy * 0.9)
          + 0.015 * rng.normal(0, 1, gx.shape)).astype(float)
gv = np.c_[gx.ravel(), gy.ravel(), height.ravel()]
gf = []
for r in range(ny - 1):
    for c in range(nx - 1):
        a = r * nx + c
        gf += [[a, a + 1, a + nx + 1], [a, a + nx + 1, a + nx]]
gf = np.array(gf)
tone = np.clip(0.62 + 0.12 * rng.normal(0, 1, len(gv)), 0.3, 0.9)
gc = np.c_[tone * 0.92, tone * 0.86, tone * 0.74]
ground = mesh_object("sand", gv, gf, gc)
sand = vertex_colour_material("sand", 0.9)
# A fine mottle over the vertex colour, so stereo has texture between vertices.
nodes, links = sand.node_tree.nodes, sand.node_tree.links
noise = nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 140.0
noise.inputs["Detail"].default_value = 8.0
mix = nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
mix.blend_type = "MULTIPLY"
mix.inputs["Factor"].default_value = 0.55
links.new(nodes["Color Attribute"].outputs["Color"], mix.inputs["A"])
links.new(noise.outputs["Color"], mix.inputs["B"])
links.new(mix.outputs["Result"], nodes["Principled BSDF"].inputs["Base Color"])
ground.data.materials.append(sand)
ground.pass_index = CLASS["sand"]


def ground_at(x, y):
    col = int(round((x + 4) / 8 * (nx - 1)))
    row = int(round((y + 2) / 4 * (ny - 1)))
    return float(height[min(max(row, 0), ny - 1), min(max(col, 0), nx - 1)])


# ── the colonies ─────────────────────────────────────────────────────────────
library = json.loads((LIBRARY / "library.json").read_text())
choices = [("massive", e) for e in library["kinds"]["massive"]] * 3 + \
          [("brain", e) for e in library["kinds"]["brain"]] * 2 + \
          [("branching", e) for e in library["kinds"]["branching"]]
placed, colonies = [], []
truth_v, truth_f, truth_class, truth_colony = [gv], [gf], [np.full(len(gv), CLASS["sand"])], [np.full(len(gv), -1)]
offset = len(gv)
tries = 0
while len(colonies) < 16 and tries < 400:
    tries += 1
    kind, entry = random.choice(choices)
    x, y = random.uniform(-3.4, 3.4), random.uniform(-1.5, 1.5)
    scale = random.uniform(0.7, 1.4)
    v, f, c = read_ply(LIBRARY / entry["file"])
    v = v - [*(v[:, :2].max(0) + v[:, :2].min(0)) / 2, v[:, 2].min()]
    radius = scale * float(np.abs(v[:, :2]).max())
    if any(math.hypot(x - px, y - py) < radius + pr + 0.1 for px, py, pr in placed):
        continue
    yaw = random.uniform(0, 2 * math.pi)
    turn = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
    world = (v * scale) @ turn.T + [x, y, ground_at(x, y) - 0.01]
    k = len(colonies)
    obj = mesh_object(f"colony{k}", world, f, c)
    obj.data.materials.append(vertex_colour_material(f"colony{k}"))
    obj.pass_index = CLASS[kind]
    placed.append((x, y, radius))
    colonies.append({"id": k, "kind": kind, "file": entry["file"], "x": x, "y": y, "scale": scale,
                     "yawDeg": math.degrees(yaw), "class": CLASS[kind]})
    truth_v.append(world)
    truth_f.append(f + offset)
    truth_class.append(np.full(len(world), CLASS[kind]))
    truth_colony.append(np.full(len(world), k))
    offset += len(world)

# ── light and water ──────────────────────────────────────────────────────────
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(25), math.radians(15), 0)
scene.collection.objects.link(sun)
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.08, 0.32, 0.42, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
scene.world = world

# ── the camera's swim ────────────────────────────────────────────────────────
cam_data = bpy.data.cameras.new("cam")
cam_data.sensor_fit = "HORIZONTAL"
cam_data.sensor_width = 36.0
cam_data.lens = FOCAL_PX * 36.0 / WIDE
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x, scene.render.resolution_y = WIDE, TALL
scene.render.resolution_percentage = 100

poses = []
for i in range(FRAMES):
    s = i / (FRAMES - 1)
    x = -3.6 + 7.2 * s
    y = 0.35 * math.sin(2 * math.pi * s * 2.5)
    z = ground_at(x, y) + 1.5 + 0.1 * math.sin(2 * math.pi * s * 4)
    # Forward along +x, down 50 degrees from level, a little yaw with the weave.
    yaw = math.radians(8 * math.cos(2 * math.pi * s * 2.5))
    pitch = math.radians(40)                   # from straight down: 50 below the horizon
    rot = mathutils.Euler((pitch, 0.0, yaw - math.pi / 2), "XYZ")
    poses.append(((x, y, z), rot))


def configure_cycles():
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "CUDA"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "CUDA"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 95
    scene.render.filter_size = 1.5


def configure_labels():
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "OBJECT"
    scene.display.render_aa = "OFF"
    scene.view_settings.view_transform = "Raw"
    scene.render.dither_intensity = 0.0          # or the 8-bit ids come out one or two off
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.0, 0.0, 0.0)   # open water: class 0, nothing
    scene.render.film_transparent = False
    for obj in scene.objects:
        if obj.type == "MESH":
            obj.color = (obj.pass_index / 255.0, 0.0, 0.0, 1.0)


cameras = []
configure_cycles()
for i, (where, rot) in enumerate(poses):
    cam.location, cam.rotation_euler = where, rot
    scene.render.filepath = str(OUT / "frames" / f"{i:05d}.jpg")
    bpy.ops.render.render(write_still=True)
    m = cam.matrix_world
    cameras.append({"name": f"{i:05d}.jpg", "centre": list(where),
                    "world_from_camera": [list(row) for row in m]})
configure_labels()
for i, (where, rot) in enumerate(poses):
    cam.location, cam.rotation_euler = where, rot
    scene.render.filepath = str(OUT / "labels" / f"{i:05d}.png")
    bpy.ops.render.render(write_still=True)

# The label renders hold each pixel's class in their red channel (written raw,
# so red = class exactly); prior.label_points reads the red channel.
(OUT / "labels" / "classes.json").write_text(json.dumps(
    {"id2label": {str(k): v for k, v in CLASS_NAMES.items()}, "model": "the scene itself (synthetic/reef.py)"},
    indent=1))
(OUT / "cameras.json").write_text(json.dumps(
    {"width": WIDE, "height": TALL, "focalPx": FOCAL_PX, "frames": cameras, "colonies": colonies,
     "seed": SEED}, indent=1))
(OUT / "frames" / "frames.json").write_text(json.dumps(
    {"videos": ["synthetic"], "fromSeconds": 0.0, "toSeconds": FRAMES * 0.5, "everySeconds": 0.5,
     "frames": FRAMES, "size": [WIDE, TALL], "synthetic": True}, indent=1))

v = np.concatenate(truth_v)
f = np.concatenate(truth_f)
cls = np.concatenate(truth_class)
col = np.concatenate(truth_colony)
head = ("ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
        "property uchar class\nproperty int colony\n"
        f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n")
vert = np.zeros(len(v), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("class", "u1"), ("colony", "<i4")])
vert["x"], vert["y"], vert["z"], vert["class"], vert["colony"] = v[:, 0], v[:, 1], v[:, 2], cls, col
face = np.zeros(len(f), dtype=[("n", "u1"), ("i", "<i4", 3)])
face["n"], face["i"] = 3, f
(OUT / "truth.ply").write_bytes(head.encode() + vert.tobytes() + face.tobytes())
print(json.dumps({"frames": FRAMES, "colonies": len(colonies), "truthVertices": int(len(v))}))
