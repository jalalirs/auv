"""Stand the colonies on the ground.

Reads colonies.json — what tools/benthos found standing on the surveyed seabed,
each with a position, a footprint, a height and, when the orthomosaic has been
read, a colour — and puts a colony at every one of them. Nothing here decides
where a colony goes or how big it is; the survey did.

Instancing rather than objects: ten thousand colonies on one tile, hundreds of
thousands on the square, and Blender handles that as points carrying an index
into a small collection of prototypes, not as a hundred thousand objects.

The prototypes are a first set and are meant to be replaced by scans: a lumpy
dome for a low colony or a head, a fan and a plume for the octocorals. If a
glTF scan is in assets/, it is used for the heads. Colours come from the
colony's own colour when the survey gave one, and from the reference
photographs' palette for this reef otherwise.
"""

from __future__ import annotations

import json
import math
import pathlib

import bpy
import numpy as np

# What each kind looks like when the orthomosaic has not said. From the Looe Key
# photographs: mustard Porites and Orbicella, grey-olive pavement lumps, purple
# fans and tan plumes.
COLOUR = {"stony": (0.72, 0.58, 0.22), "head": (0.66, 0.52, 0.24),
          "low": (0.36, 0.35, 0.27), "octocoral": (0.46, 0.30, 0.50)}
PLUME = (0.62, 0.50, 0.28)
KINDS = ["low", "stony", "head", "octocoral"]


def _dome(name, rng, lumps=0.12, rows=14, sides=24):
    """Half an ellipsoid, roughened. A boulder coral or a rock."""
    verts, faces = [(0.0, 0.0, 1.0)], []
    for r in range(1, rows + 1):
        polar = (r / rows) * (math.pi / 2)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            wob = 1.0 + lumps * (math.sin(5 * a + 3 * polar) * math.sin(3 * a - 4 * polar) + rng.normal(0, 0.35))
            verts.append((math.sin(polar) * math.cos(a) * wob, math.sin(polar) * math.sin(a) * wob,
                          math.cos(polar) * wob))
    for s in range(sides):
        faces.append((0, 1 + s, 1 + (s + 1) % sides))
    for r in range(rows - 1):
        b, n = 1 + r * sides, 1 + (r + 1) * sides
        for s in range(sides):
            t = (s + 1) % sides
            faces.append((b + s, n + s, n + t, b + t))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    for p in mesh.polygons:
        p.use_smooth = True
    mesh.update()
    return mesh


def _fan(name, rng):
    """A sea fan: a flat net in one plane on a short stalk, one unit tall."""
    verts, edges = [(0, 0, 0), (0, 0, 0.12)], [(0, 1)]

    def grow(base, direction, length, depth):
        if depth > 7 or length < 0.02:
            return
        tip = (base[0] + direction[0] * length, 0.0, base[2] + direction[1] * length)
        verts.append(tip); edges.append((verts.index(base), len(verts) - 1))
        for sign in (-1, 1):
            a = math.atan2(direction[1], direction[0]) + sign * math.radians(rng.uniform(18, 34))
            grow(tip, (math.cos(a), math.sin(a)), length * rng.uniform(0.66, 0.8), depth + 1)

    grow((0, 0, 0.12), (0.0, 1.0), 0.28, 0)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, [])
    obj = bpy.data.objects.new(name, mesh)
    # Skin the wire so it renders: a thin tube along every edge.
    mod = obj.modifiers.new("skin", "SKIN")
    for v in obj.data.skin_vertices[0].data:
        v.radius = (0.022, 0.022)
    return obj


def _plume(name, rng):
    """A sea plume: several whips off one holdfast, furred with branchlets."""
    verts, edges = [(0, 0, 0)], []
    for _ in range(int(rng.integers(3, 7))):
        a = rng.uniform(0, 2 * math.pi); lean = rng.uniform(0.15, 0.4)
        last = 0
        for k in range(1, 9):
            t = k / 8
            p = (math.cos(a) * lean * t ** 0.7, math.sin(a) * lean * t ** 0.7, t)
            verts.append(p); edges.append((last, len(verts) - 1)); last = len(verts) - 1
            for side in (-1, 1):
                b = a + side * math.pi / 2
                q = (p[0] + math.cos(b) * 0.06, p[1] + math.sin(b) * 0.06, p[2] + 0.05)
                verts.append(q); edges.append((last, len(verts) - 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, [])
    obj = bpy.data.objects.new(name, mesh)
    mod = obj.modifiers.new("skin", "SKIN")
    for v in obj.data.skin_vertices[0].data:
        v.radius = (0.018, 0.018)
    return obj


def _material(name, colour):
    m = bpy.data.materials.new(name); m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85
    # Colour per instance when the survey gave one, through the point attribute.
    attr = m.node_tree.nodes.new("ShaderNodeAttribute"); attr.attribute_name = "colour"
    attr.attribute_type = "INSTANCER"
    mix = m.node_tree.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    has = m.node_tree.nodes.new("ShaderNodeAttribute"); has.attribute_name = "has_colour"
    has.attribute_type = "INSTANCER"
    m.node_tree.links.new(has.outputs["Fac"], mix.inputs["Factor"])
    mix.inputs[6].default_value = (*colour, 1.0)
    m.node_tree.links.new(attr.outputs["Color"], mix.inputs[7])
    m.node_tree.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    return m


def _scan(ground_dir):
    """A scanned coral, if one has been put in assets/. Normalised to a unit dome."""
    scans = sorted((ground_dir / "assets").glob("*.glb")) if (ground_dir / "assets").exists() else []
    if not scans:
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(scans[0]))
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not new:
        return None
    obj = new[0]
    # Sit it on the ground and scale it so its footprint is one unit across and it stands one unit tall.
    xs, ys, zs = zip(*[obj.matrix_world @ v.co for v in obj.data.vertices])
    w = max(max(xs) - min(xs), max(ys) - min(ys)); hgt = max(zs) - min(zs)
    for v in obj.data.vertices:
        v.co.x = (v.co.x - (max(xs) + min(xs)) / 2) / w; v.co.y = (v.co.y - (max(ys) + min(ys)) / 2) / w
        v.co.z = (v.co.z - min(zs)) / hgt
    obj.matrix_world.identity()
    # The scan is a dry skeleton and comes in bone white; it takes the reef's colour.
    obj.data.materials.clear()
    obj.data.materials.append(_material("head", COLOUR["head"]))
    return obj


def stand(scene, ground_dir: pathlib.Path, floor_at, exaggeration: float) -> None:
    listed = json.loads((ground_dir / "colonies.json").read_text())
    colonies = listed["colonies"]
    if not colonies:
        print("no colonies to stand"); return
    rng = np.random.default_rng(7)

    # ── prototypes, in a collection the instancer picks from by index ────────
    protos = bpy.data.collections.new("Colonies")
    scene.collection.children.link(protos)
    things = []
    low = bpy.data.objects.new("low", _dome("low", rng, lumps=0.18)); low.data.materials.append(_material("low", COLOUR["low"]))
    stony = bpy.data.objects.new("stony", _dome("stony", rng, lumps=0.10)); stony.data.materials.append(_material("stony", COLOUR["stony"]))
    scan = _scan(ground_dir)
    head = scan if scan is not None else bpy.data.objects.new("head", _dome("head", rng, lumps=0.14))
    if scan is None:
        head.data.materials.append(_material("head", COLOUR["head"]))
    else:
        head.name = "head"
        for sl in head.material_slots:
            sl.link = "DATA"
    fan = _fan("fan", rng); fan.data.materials.append(_material("fan", COLOUR["octocoral"]))
    plume = _plume("plume", rng); plume.data.materials.append(_material("plume", PLUME))
    for o in (low, stony, head, fan, plume):
        protos.objects.link(o)
        if o.name in scene.collection.objects:
            scene.collection.objects.unlink(o)
    protos.hide_render = True; protos.hide_viewport = True
    # kind index -> prototype index; octocorals split fan/plume by a coin
    index_of = {"low": 0, "stony": 1, "head": 2, "octocoral": 3}

    # ── the points ───────────────────────────────────────────────────────────
    xs = np.array([c["x"] for c in colonies]); ys = np.array([c["y"] for c in colonies])
    zs = np.array([floor_at(x, y) for x, y in zip(xs, ys)])
    kind = np.array([index_of.get(c["kind"], 0) for c in colonies])
    coin = rng.random(len(colonies)) < 0.5
    kind = np.where((kind == 3) & coin, 4, kind)
    d = np.array([c["diameterM"] for c in colonies]); hgt = np.array([c["heightM"] for c in colonies])
    # domes are unit radius, unit tall; the scan is unit wide; fans and plumes unit tall.
    # A boulder coral is never taller than it is wide: a detected height above
    # its footprint is a ledge or a spur edge caught by the detector, not a
    # colony, and it is clamped rather than rendered as a pillar.
    sx = np.where(kind <= 1, d / 2, np.where(kind == 2, d, np.maximum(d, 0.3)))
    sz = np.where(kind <= 2, np.clip(hgt, 0.04, 0.7 * np.maximum(d, 0.08)), np.clip(hgt * 1.6, 0.35, 1.4))
    # Colour: the orthomosaic is a dehazed, near-grey product, so it is trusted
    # for how light or dark a colony is and not for its hue. The hue is the
    # kind's, from the photographs; the survey's luminance scales it.
    palette = np.array([COLOUR["low"], COLOUR["stony"], COLOUR["head"], COLOUR["octocoral"], PLUME])
    hue = palette[kind]
    lum = np.array([np.mean(c["colour"]) if c.get("colour") else 0.5 for c in colonies])
    lum_ref = np.median(lum[lum > 0]) if (lum > 0).any() else 0.5
    gain = np.clip(lum / max(lum_ref, 1e-3), 0.55, 1.45)[:, None]
    col = np.clip(hue * gain, 0, 1)
    has = np.ones(len(colonies))

    mesh = bpy.data.meshes.new("ColonyPoints")
    mesh.from_pydata(np.c_[xs, ys, zs].tolist(), [], [])
    for name, typ, values in (("proto", "INT", kind.astype(int)), ("has_colour", "FLOAT", has),
                              ("rot", "FLOAT", rng.uniform(0, 2 * math.pi, len(colonies)))):
        attr = mesh.attributes.new(name, typ, "POINT"); attr.data.foreach_set("value", values.tolist())
    sc = mesh.attributes.new("scale", "FLOAT_VECTOR", "POINT")
    sc.data.foreach_set("vector", np.c_[sx, sx, sz].ravel().tolist())
    cl = mesh.attributes.new("colour", "FLOAT_COLOR", "POINT")
    cl.data.foreach_set("color", np.c_[col, np.ones(len(colonies))].ravel().tolist())
    points = bpy.data.objects.new("ColonyPoints", mesh)
    scene.collection.objects.link(points)

    # ── geometry nodes: instance on points, pick by index ────────────────────
    tree = bpy.data.node_groups.new("StandColonies", "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n_in = tree.nodes.new("NodeGroupInput"); n_out = tree.nodes.new("NodeGroupOutput")
    coll = tree.nodes.new("GeometryNodeCollectionInfo"); coll.inputs["Collection"].default_value = protos
    coll.inputs["Separate Children"].default_value = True; coll.inputs["Reset Children"].default_value = True
    inst = tree.nodes.new("GeometryNodeInstanceOnPoints"); inst.inputs["Pick Instance"].default_value = True
    a_proto = tree.nodes.new("GeometryNodeInputNamedAttribute"); a_proto.data_type = "INT"; a_proto.inputs["Name"].default_value = "proto"
    a_scale = tree.nodes.new("GeometryNodeInputNamedAttribute"); a_scale.data_type = "FLOAT_VECTOR"; a_scale.inputs["Name"].default_value = "scale"
    a_rot = tree.nodes.new("GeometryNodeInputNamedAttribute"); a_rot.data_type = "FLOAT"; a_rot.inputs["Name"].default_value = "rot"
    rot = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(a_rot.outputs["Attribute"], rot.inputs["Z"])
    tree.links.new(n_in.outputs["Geometry"], inst.inputs["Points"])
    tree.links.new(coll.outputs["Instances"], inst.inputs["Instance"])
    tree.links.new(a_proto.outputs["Attribute"], inst.inputs["Instance Index"])
    tree.links.new(a_scale.outputs["Attribute"], inst.inputs["Scale"])
    tree.links.new(rot.outputs["Vector"], inst.inputs["Rotation"])
    tree.links.new(inst.outputs["Instances"], n_out.inputs["Geometry"])
    mod = points.modifiers.new("stand", "NODES"); mod.node_group = tree

    kinds = {k: int((kind == i).sum()) for k, i in index_of.items() if k != "octocoral"}
    kinds["octocoral"] = int(((kind == 3) | (kind == 4)).sum())
    print(f"stood {len(colonies)} colonies: {kinds}; scan used for heads: {scan is not None}")
