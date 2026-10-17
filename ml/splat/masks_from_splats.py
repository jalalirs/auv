"""Tape masks completed from the tape found in 3D: the tape splats projected
into every frame, each a disc about the tape's width at its distance, joined
with the segmenter's mask.  masks_from_splats.py TEXT MASKS OUT IMAGES TAPE.npy [...]"""
import pathlib
import sys

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from splat_place import colmap_cameras  # noqa: E402

text, masks, out, images = (pathlib.Path(p) for p in sys.argv[1:5])
tape = np.concatenate([np.load(f) for f in sys.argv[5:]])
out.mkdir(parents=True, exist_ok=True)
cams = colmap_cameras(text)
line = [ln.split() for ln in (text / "cameras.txt").read_text().splitlines() if ln and not ln.startswith("#")][0]
fx, fy, cx, cy = (float(v) for v in line[4:8])
W, H = cams["width"], cams["height"]
# The tape is about 2.5 cm wide: half of it is 0.0016 COLMAP units at 7.84 m a unit.
half_width = 0.0016
p = torch.from_numpy(tape).float().cuda()
added = []
for name in sorted(cams["poses"]):
    pose = torch.from_numpy(cams["poses"][name]).float().cuda()
    pc = (p - pose[:3, 3]) @ pose[:3, :3]
    z = pc[:, 2]
    keep = z > 0.03
    u = fx * pc[keep, 0] / z[keep] + cx
    v = fy * pc[keep, 1] / z[keep] + cy
    r = (fx * half_width / z[keep]).clamp(1.0, 6)
    inside = (u >= -r) & (u < W + r) & (v >= -r) & (v < H + r)
    u, v, r = u[inside], v[inside], r[inside]
    proj = torch.zeros((H, W), dtype=torch.bool, device="cuda")
    # Discs by radius band: each band dilated once.
    for lo, hi in ((0, 2), (2, 4), (4, 7)):
        sel = (r >= lo) & (r < hi)
        if not sel.any():
            continue
        dots = torch.zeros((1, 1, H, W), device="cuda")
        ui, vi = u[sel].long().clamp(0, W - 1), v[sel].long().clamp(0, H - 1)
        dots[0, 0, vi, ui] = 1
        k = int(lo) * 2 + 3
        proj |= torch.nn.functional.max_pool2d(dots, k, stride=1, padding=k // 2)[0, 0] > 0
    # Only where the picture is brighter than what is around it: the tape is.
    grey = torch.from_numpy(np.asarray(Image.open(images / f"{name}.jpg").convert("L"), dtype=np.float32) / 255.0).cuda()
    g = grey[None, None]
    opened = torch.nn.functional.max_pool2d(-torch.nn.functional.max_pool2d(-g, 9, 1, 4), 9, 1, 4)
    proj &= (g - opened)[0, 0] > 0.04
    m = masks / f"{name}.png"
    seg = torch.from_numpy(np.asarray(Image.open(m)) > 127).cuda() if m.exists() else torch.zeros_like(proj)
    both = proj | seg
    added.append(int((both & ~seg).sum()))
    Image.fromarray((both.cpu().numpy() * 255).astype(np.uint8)).save(out / f"{name}.png")
print("masks", len(added), "pixels added per frame, median", int(np.median(added)))
