"""Fly a camera over a place's ground, dry, in Blender.

Run inside Blender, on the machine with the GPUs:

    blender -b -P tools/flyover.py -- <ground dir> <out dir> [frames] [exaggeration] [colour.png] [layers]

Layers are a comma list: "ground" alone is the bathymetry; "ground,corals"
stands the colonies from colonies.json on it; "ground,corals,water" puts the
water over both. The flight is identical in every case, so the three videos
can be laid side by side and compared frame for frame.

The ground directory is what tools/ground produced: a 1 m heightfield with the
survey feathered in, the habitat classes, and a colour map. No water is drawn.
This exists because every earlier view of the site was through thirty metres of
scattering water, which is the right instrument for judging a dive and the
wrong one for judging the ground under it.

The flight hangs off the reef itself — a line fitted through the spur-and-groove
polygons — rather than off fractions of the site: over the deep water looking
up the slope, along the reef band, down the slope to the deep edge, and low
across the spurs where the survey is.

Vertical exaggeration is a parameter. The slope from the reef to thirty metres
is four degrees, and at true scale under an even sun it is a plane; charts
stretch it for exactly this reason. Whatever it is set to is written in the
render's caption by whoever made the video, because a stretched seabed shown as
real is a lie.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

import bpy
from mathutils import Vector

# Blender does not put a -P script's own directory on the path; the layer
# modules live beside this file.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
argv = sys.argv[sys.argv.index("--") + 1:]
# Absolute, because Blender resolves a relative image path against the blend
# file, and there is no blend file yet: the texture silently fails to load and
# the whole seabed renders magenta.
ground_dir, out_dir = pathlib.Path(argv[0]).resolve(), pathlib.Path(argv[1]).resolve()
FRAMES = int(argv[2]) if len(argv) > 2 else 720
EX = float(argv[3]) if len(argv) > 3 else 1.0
COLOUR = argv[4] if len(argv) > 4 else "chart_4096.png"
LAYERS = set((argv[5] if len(argv) > 5 else "ground").split(","))
FPS, W, H, SAMPLES = 24, 1280, 720, 48
SPUR_AND_GROOVE = 7   # tools/ground: HABITAT_ORDER index + 1

field = json.loads((ground_dir / "seabed_1m.json").read_text())
rows, cols, across = field["rows"], field["columns"], float(field["acrossMetres"])
h = np.fromfile(ground_dir / field["file"], dtype="<f4").reshape(rows, cols).astype(float) * EX
step = across / (cols - 1)
habitat = np.load(ground_dir / "habitat_4096.npy")


def floor_at(x: float, y: float) -> float:
    """Bilinear height of the (exaggerated) seabed at a site coordinate."""
    fx = (x + across / 2) / step; fy = (y + across / 2) / step
    i = int(np.clip(math.floor(fy), 0, rows - 2)); j = int(np.clip(math.floor(fx), 0, cols - 2))
    tx = float(np.clip(fx - j, 0, 1)); ty = float(np.clip(fy - i, 0, 1))
    return float((h[i, j] * (1 - tx) + h[i, j + 1] * tx) * (1 - ty)
                 + (h[i + 1, j] * (1 - tx) + h[i + 1, j + 1] * tx) * ty)


# ── scene ────────────────────────────────────────────────────────────────────
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPTIX"
scene.cycles.device = "GPU"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.refresh_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, FRAMES
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(out_dir / "frames" / "frame_")
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"

# ── the seabed ───────────────────────────────────────────────────────────────
mesh = bpy.data.meshes.new("Seabed")
xs = np.linspace(-across / 2, across / 2, cols); ys = np.linspace(-across / 2, across / 2, rows)
X, Y = np.meshgrid(xs, ys)
verts = np.c_[X.ravel(), Y.ravel(), h.ravel()]
a = (np.arange(rows - 1)[:, None] * cols + np.arange(cols - 1)[None, :]).ravel()
faces = np.c_[a, a + 1, a + cols + 1, a + cols]
mesh.from_pydata(verts.tolist(), [], faces.tolist())
uv = mesh.uv_layers.new(name="st")
loops = np.array([l.vertex_index for l in mesh.loops])
uv.data.foreach_set("uv", np.c_[(verts[loops, 0] + across / 2) / across,
                                (verts[loops, 1] + across / 2) / across].ravel())
for p in mesh.polygons:
    p.use_smooth = True
mesh.update()
seabed = bpy.data.objects.new("Seabed", mesh)
scene.collection.objects.link(seabed)

material = bpy.data.materials.new("Ground"); material.use_nodes = True
nodes = material.node_tree
bsdf = nodes.nodes["Principled BSDF"]
tex = nodes.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(str(ground_dir / COLOUR))
tex.interpolation = "Cubic"
nodes.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.92
# Grain finer than the heightfield, so the ground is not a smooth sheet between samples.
noise = nodes.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 1.6; noise.inputs["Detail"].default_value = 12.0
bump = nodes.nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.35; bump.inputs["Distance"].default_value = 0.15
nodes.links.new(noise.outputs["Fac"], bump.inputs["Height"])
nodes.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
seabed.data.materials.append(material)

# ── light: one low sun from the north-west, so the spurs throw shadows ───────
sun = bpy.data.lights.new("Sun", "SUN")
sun.energy = 5.0; sun.angle = math.radians(1.5); sun.color = (1.0, 0.96, 0.90)
sun_object = bpy.data.objects.new("Sun", sun)
scene.collection.objects.link(sun_object)
sun_object.rotation_euler = (math.radians(68), 0.0, math.radians(-55))
world = bpy.data.worlds.new("Sky"); scene.world = world; world.use_nodes = True
background = world.node_tree.nodes["Background"]
background.inputs["Color"].default_value = (0.55, 0.65, 0.80, 1)
background.inputs["Strength"].default_value = 0.7

# ── the flight, hung off the reef ────────────────────────────────────────────
# Through the surveyed ground when there is any, because that is where the relief
# is real; otherwise through the spur-and-groove polygons.
survey_file = ground_dir / "survey_1m.npy"
if survey_file.exists() and np.load(survey_file).sum() > 5000:
    survey = np.load(survey_file)
    ii, jj = np.nonzero(survey)
    tex_step = across / (survey.shape[1] - 1)
    print(f"flight aimed at the survey: {100 * survey.mean():.1f}% of the square")
else:
    ii, jj = np.nonzero(habitat == SPUR_AND_GROOVE)
    if len(ii) < 100:
        ii, jj = np.nonzero(habitat > 0)
    tex_step = across / habitat.shape[1]
px = -across / 2 + jj * tex_step; py = -across / 2 + ii * tex_step
c = np.array([px.mean(), py.mean()])
_, _, vt = np.linalg.svd(np.c_[px - c[0], py - c[1]][::max(1, len(px) // 20000)], full_matrices=False)
along = vt[0]; along = along if along[0] > 0 else -along           # south-west to north-east
acrs = np.array([-along[1], along[0]])
# Seaward is whichever side of the band is deeper.
def _depth_at(v):
    return -floor_at(*(c + v))
acrs = acrs if _depth_at(acrs * 150) > _depth_at(-acrs * 150) else -acrs
t_along = np.c_[px - c[0], py - c[1]] @ along
lo, hi = np.percentile(t_along, [3, 97])
print(f"reef band centre {c.round(1)} runs along {along.round(2)}, from {lo:.0f} to {hi:.0f} m; "
      f"seaward is {acrs.round(2)}")


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    return t * t * (3 - 2 * t)


EDGE = across / 2 - 40.0


def inside(p):
    """Held inside the square: a camera that flies off the edge films sky."""
    return np.clip(p, -EDGE, EDGE)


def pose(at: float):
    """Where the camera is and what it looks at, this far into the flight."""
    if at < 0.22:
        # Over the deep water, looking up the slope at the reef.
        t = smooth(at / 0.22)
        eye = inside(c + along * lerp(hi + 40, hi - 120, t) + acrs * lerp(520.0, 380.0, t))
        look = c + along * lerp(hi - 250, hi - 350, t) + acrs * 60.0
        return (eye[0], eye[1], lerp(170.0, 120.0, t) * EX ** 0.5, "sea"), (look[0], look[1])
    if at < 0.50:
        # Along the band at survey height, looking down and ahead.
        t = smooth((at - 0.22) / 0.28)
        along_t = lerp(hi - 60, lo + 40, t)
        eye = inside(c + along * along_t + acrs * 45.0)
        look = c + along * (along_t - 70.0)
        return (eye[0], eye[1], 40.0, "bottom"), (look[0], look[1])
    if at < 0.78:
        # From the crest straight down the slope to the deep edge, so the
        # bottom falls away under the camera.
        t = smooth((at - 0.50) / 0.28)
        start = c + along * (lo + 60)
        # As far seaward as the square allows, and no further.
        reach = 420.0
        for k in range(2):
            edge_hit = (EDGE - np.abs(start[k])) / max(abs(acrs[k]), 1e-6)
            reach = min(reach, edge_hit)
        out = lerp(-10.0, reach, t)
        eye = start + acrs * out
        look = start + acrs * min(out + 90.0, reach + 30.0)
        return (eye[0], eye[1], 28.0, "bottom"), (look[0], look[1])
    # Low across the spurs, from the sand up onto the reef.
    t = smooth((at - 0.78) / 0.22)
    along_t = lerp(hi - 120, hi - 260, t)
    eye = inside(c + along * along_t + acrs * lerp(70.0, -50.0, t))
    look = eye - acrs * 45.0 - along * 10.0
    return (eye[0], eye[1], lerp(14.0, 7.0, t), "bottom"), (look[0], look[1])


# ── what stands on the ground, and what is over it ───────────────────────────
if "corals" in LAYERS:
    import flyover_corals
    flyover_corals.stand(scene, ground_dir, floor_at, EX)
if "water" in LAYERS:
    import flyover_water
    flyover_water.flood(scene, across, sun_object, world)

camera = bpy.data.cameras.new("Camera")
camera.lens = 24.0; camera.sensor_width = 36.0; camera.clip_end = 5000.0
camera_object = bpy.data.objects.new("Camera", camera)
scene.collection.objects.link(camera_object); scene.camera = camera_object

# The whole path first, then smoothed, then keyed. A camera whose height
# follows the seabed under it frame by frame inherits every bump of a 1 cm
# survey and shakes; a real flight, or a real vehicle, rides over them. Two
# seconds of smoothing on where the camera is and what it looks at.
eyes, looks = [], []
for f in range(1, FRAMES + 1):
    (x, y, up, above), (lx, ly) = pose((f - 1) / max(1, FRAMES - 1))
    z = up if above == "sea" else floor_at(x, y) + up
    eyes.append((x, y, z)); looks.append((lx, ly, floor_at(lx, ly)))
eyes, looks = np.array(eyes), np.array(looks)


def smoothed(track, seconds=2.0):
    half = int(seconds * FPS / 2)
    if half < 1:
        return track
    kernel = np.exp(-0.5 * (np.arange(-half, half + 1) / (half / 2.5)) ** 2); kernel /= kernel.sum()
    padded = np.pad(track, ((half, half), (0, 0)), mode="edge")
    return np.stack([np.convolve(padded[:, k], kernel, mode="valid") for k in range(track.shape[1])], -1)


eyes_s, looks_s = smoothed(eyes), smoothed(looks)
# Smoothing must not push the camera into a spur: keep at least 1.5 m of clearance.
for i, (x, y, z) in enumerate(eyes_s):
    eyes_s[i, 2] = max(z, floor_at(x, y) + 1.5)
# With the water on, a dive's camera is in the water. The plan view from the air
# stays, because looking down through the surface at the whole reef is a view a
# dive cannot have and is worth keeping; from the reef leg on, the camera is held
# at least two metres under the surface. Same x and y as the other two videos.
if "water" in LAYERS:
    for i in range(FRAMES):
        if (i / max(1, FRAMES - 1)) >= 0.22:
            x, y, z = eyes_s[i]
            eyes_s[i, 2] = max(min(z, -2.0), floor_at(x, y) + 1.5)
            looks_s[i, 2] = min(looks_s[i, 2], eyes_s[i, 2] - 0.5)
for f in range(1, FRAMES + 1):
    x, y, z = eyes_s[f - 1]; lx, ly, lz = looks_s[f - 1]
    camera_object.location = (x, y, z)
    camera_object.rotation_euler = Vector((lx - x, ly - y, lz - z)).to_track_quat("-Z", "Y").to_euler()
    camera_object.keyframe_insert("location", frame=f)
    camera_object.keyframe_insert("rotation_euler", frame=f)
for curve in camera_object.animation_data.action.fcurves:
    for k in curve.keyframe_points:
        k.interpolation = "LINEAR"

(out_dir / "frames").mkdir(parents=True, exist_ok=True)
(out_dir / "flight.json").write_text(json.dumps({
    "frames": FRAMES, "fps": FPS, "exaggeration": EX, "colour": COLOUR, "layers": sorted(LAYERS),
    "reefBandCentre": c.round(1).tolist(), "along": along.round(3).tolist(),
    "seaward": acrs.round(3).tolist()}, indent=1))
bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / "flyover.blend"))
bpy.ops.render.render(animation=True)
print("RENDER_DONE")
