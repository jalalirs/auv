"""Blender, headless: a scanned fish down to a few thousand faces, its colour baked.

    blender -b -P tools/fish-models/reduce.py -- <in.glb> <out.glb> <faces> <texture px>

The scans are a million faces each; a reef draws a thousand fish. Decimating
a photogrammetry mesh keeps its UVs only in name: its texture is thousands of
tiny islands, and collapsed edges smear them into speckle. So the reduced
copy gets fresh UVs of its own and the original's colour is baked onto it
(Cycles, selected to active) — the standard way a scan becomes a game asset.
Orientation, size and packing are tools/fish-models/build's, in plain Python.
"""

import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
source, target, faces, pixels = argv[0], argv[1], int(argv[2]), int(argv[3])

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=source)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
scan = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
have = len(scan.data.polygons)

# The copy: welded, reduced, and unwrapped afresh.
bpy.ops.object.duplicate()
fish = bpy.context.view_layer.objects.active
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=1e-5 * max(scan.dimensions))
bpy.ops.object.mode_set(mode="OBJECT")
for _ in range(3):
    now = len(fish.data.polygons)
    if now <= faces * 1.05:
        break
    cut = fish.modifiers.new("reduce", "DECIMATE")
    cut.decimate_type = "COLLAPSE"
    cut.ratio = max(faces / now, 0.01)
    cut.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=cut.name)
while fish.data.uv_layers:
    fish.data.uv_layers.remove(fish.data.uv_layers[0])
fish.data.uv_layers.new(name="baked")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
bpy.ops.object.mode_set(mode="OBJECT")

# A material on the copy holding the image to bake into.
image = bpy.data.images.new("baked", pixels, pixels)
material = bpy.data.materials.new("fish")
material.use_nodes = True
nodes = material.node_tree.nodes
shader = nodes.get("Principled BSDF")
texture = nodes.new("ShaderNodeTexImage")
texture.image = image
material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
nodes.active = texture
fish.data.materials.clear()
fish.data.materials.append(material)

# The scan's colour as light: whatever its material is (a scan is usually
# glTF's unlit, which a diffuse bake reads as black), its texture straight
# into an emission, and that is what is baked.
# A scan without a picture carries its colour as vertex colours or as a
# material's plain colour; those are baked the same way.
painted = scan.data.color_attributes[0].name if getattr(scan.data, "color_attributes", None) and len(scan.data.color_attributes) else None
for slot in scan.material_slots:
    m = slot.material
    if m is None:
        continue
    m.use_nodes = True
    tree = m.node_tree
    pictures = [n for n in tree.nodes if n.type == "TEX_IMAGE"]
    out = [n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"]
    if not out:
        out = [tree.nodes.new("ShaderNodeOutputMaterial")]
    glow = tree.nodes.new("ShaderNodeEmission")
    if pictures:
        tree.links.new(pictures[0].outputs["Color"], glow.inputs["Color"])
    elif painted:
        colours = tree.nodes.new("ShaderNodeVertexColor")
        colours.layer_name = painted
        tree.links.new(colours.outputs["Color"], glow.inputs["Color"])
    else:
        principled = [n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"]
        base = principled[0].inputs["Base Color"].default_value if principled else m.diffuse_color
        glow.inputs["Color"].default_value = tuple(base)
    tree.links.new(glow.outputs["Emission"], out[0].inputs["Surface"])
if not scan.material_slots and painted:
    m = bpy.data.materials.new("painted")
    m.use_nodes = True
    tree = m.node_tree
    colours = tree.nodes.new("ShaderNodeVertexColor")
    colours.layer_name = painted
    glow = tree.nodes.new("ShaderNodeEmission")
    tree.links.new(colours.outputs["Color"], glow.inputs["Color"])
    tree.links.new(glow.outputs["Emission"], tree.nodes["Material Output"].inputs["Surface"])
    scan.data.materials.append(m)

# Bake the scan's colour onto it.
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 4
bake = scene.render.bake
bake.use_selected_to_active = True
bake.use_pass_direct = False
bake.use_pass_indirect = False
bake.use_pass_color = True
bake.cage_extrusion = 0.01 * max(scan.dimensions)
bake.max_ray_distance = 0.03 * max(scan.dimensions)
bake.margin = 4
bpy.ops.object.select_all(action="DESELECT")
scan.select_set(True)
fish.select_set(True)
bpy.context.view_layer.objects.active = fish
bpy.ops.object.bake(type="EMIT")
image.pack()

bpy.ops.object.select_all(action="DESELECT")
fish.select_set(True)
bpy.ops.export_scene.gltf(filepath=target, export_format="GLB", use_selection=True,
                          export_image_format="JPEG", export_apply=True)
print(f"reduced {have} -> {len(fish.data.polygons)} faces, colour baked at {pixels}: {target}")
