"""Cut a box out of a large textured OBJ (Agisoft Metashape's), keeping its
texture coordinates, without reading it all into memory.

    python crop_obj.py MODEL.obj OUT.obj --box X0 X1 Y0 Y1

Two passes: the first keeps the vertices inside the box and numbers them
anew, the second keeps the faces whose vertices are all inside, with their
texture coordinates renumbered too. The material file and texture are the
model's own; OUT.obj names the same .mtl, which is copied beside it.
"""

import argparse
import pathlib
import shutil

ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("out")
ap.add_argument("--box", nargs=4, type=float, required=True, metavar=("X0", "X1", "Y0", "Y1"))
a = ap.parse_args()
x0, x1, y0, y1 = a.box
model, out = pathlib.Path(a.model), pathlib.Path(a.out)

keep_v, keep_vt = {}, {}
v_lines, vt_lines = [], []
mtllib = None
v_n = vt_n = 0
with model.open() as f:
    for line in f:
        if line.startswith("v "):
            v_n += 1
            p = line.split()
            x, y = float(p[1]), float(p[2])
            if x0 <= x <= x1 and y0 <= y <= y1:
                keep_v[v_n] = len(keep_v) + 1
                v_lines.append(line)
        elif line.startswith("mtllib"):
            mtllib = line.split(None, 1)[1].strip()

faces = []
with model.open() as f:
    for line in f:
        if line.startswith("vt "):
            vt_n += 1
            vt_lines.append(line)            # kept for now; pruned below
        elif line.startswith("f "):
            parts = line.split()[1:]
            vs = [int(p.split("/")[0]) for p in parts]
            if all(v in keep_v for v in vs):
                faces.append(parts)

used_vt = {}
for parts in faces:
    for p in parts:
        bits = p.split("/")
        if len(bits) > 1 and bits[1]:
            t = int(bits[1])
            if t not in used_vt:
                used_vt[t] = len(used_vt) + 1

with out.open("w") as o:
    o.write(f"# cropped from {model.name} to x {x0}..{x1}, y {y0}..{y1}\n")
    if mtllib:
        o.write(f"mtllib {mtllib}\n")
        shutil.copy(model.parent / mtllib, out.parent / mtllib)
    o.writelines(v_lines)
    for t in sorted(used_vt, key=used_vt.get):
        o.write(vt_lines[t - 1])
    o.write("usemtl Coral_mapping\n")
    for parts in faces:
        new = []
        for p in parts:
            bits = p.split("/")
            v = str(keep_v[int(bits[0])])
            t = str(used_vt[int(bits[1])]) if len(bits) > 1 and bits[1] else ""
            new.append(f"{v}/{t}" if t else v)
        o.write("f " + " ".join(new) + "\n")
print(f"vertices {len(keep_v)} of {v_n}, faces {len(faces)}, texture coordinates {len(used_vt)} of {vt_n}")
