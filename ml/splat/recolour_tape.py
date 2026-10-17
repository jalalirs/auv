"""The survey tape taken out of a piece's splats: the splats that fall on the
tape in most of the frames that see them, coloured as the ground around them.

    python recolour_tape.py CHECKPOINT COLMAP_TEXT MASKS OUT_CHECKPOINT FIRST:LAST
        [--every 1] [--share 0.35] [--seen 3]

MASKS holds a mask per frame (white on the tape), made by CoralscapesV2's own
'transect line' and 'transect tools' classes. Each splat is projected into the
piece's frames FIRST..LAST (1-based, name order; every --every-th): seen where
it lands in the picture in front of the camera, on the tape where the mask is
set. A splat on the tape in at least --share of at least --seen frames is the
tape: its colour, base and view-dependent, becomes the mean of its 16 nearest
splats that are not. Run
inside iocean/3dgrut, on the GPU.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from splat_place import colmap_cameras  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("colmap", type=pathlib.Path)
    ap.add_argument("masks", type=pathlib.Path)
    ap.add_argument("out")
    ap.add_argument("frames")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--share", type=float, default=0.35)
    ap.add_argument("--seen", type=int, default=3)
    ap.add_argument("--save-tape", default="", help="also write the tape splats' positions (COLMAP frame) to this .npy")
    ap.add_argument("--grow", type=int, default=6, help="pixels the masks are widened by")
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.frames.split(":"))

    cams = colmap_cameras(a.colmap)
    line = [ln.split() for ln in (a.colmap / "cameras.txt").read_text().splitlines() if ln and not ln.startswith("#")][0]
    fx, fy, cx, cy = (float(v) for v in line[4:8])
    W, H = cams["width"], cams["height"]
    names = sorted(cams["poses"])[lo - 1:hi:a.every]

    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    ck.pop("optimizer", None)
    p = ck["positions"].detach().float().cuda()
    seen = torch.zeros(p.shape[0], dtype=torch.int32, device="cuda")
    on = torch.zeros_like(seen)
    grow = torch.nn.MaxPool2d(2 * a.grow + 1, stride=1, padding=a.grow)
    for name in names:
        mask_path = a.masks / f"{name}.png"
        if not mask_path.exists():
            continue
        m = torch.from_numpy(np.asarray(Image.open(mask_path)) > 127).float().cuda()
        m = grow(m[None, None])[0, 0] > 0
        pose = torch.from_numpy(cams["poses"][name]).float().cuda()
        pc = (p - pose[:3, 3]) @ pose[:3, :3]
        z = pc[:, 2]
        u = (fx * pc[:, 0] / z.clamp(min=1e-6) + cx).long()
        v = (fy * pc[:, 1] / z.clamp(min=1e-6) + cy).long()
        inside = (z > 0.02) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
        seen += inside.int()
        hit = torch.zeros_like(inside)
        hit[inside] = m[v[inside], u[inside]]
        on += hit.int()
    tape = (seen >= a.seen) & (on.float() >= a.share * seen.float())
    tape = tape.cpu().numpy()
    n_tape = int(tape.sum())
    if a.save_tape:
        np.save(a.save_tape, ck["positions"].detach().numpy()[tape])

    if n_tape:
        from scipy.spatial import cKDTree

        pos = ck["positions"].detach().numpy()
        # Only the ground near the tape is needed to colour it.
        lo_b, hi_b = pos[tape].min(0) - 0.05, pos[tape].max(0) + 0.05
        near = ~tape & np.all((pos >= lo_b) & (pos <= hi_b), axis=1)
        tree = cKDTree(pos[near])
        _, nn = tree.query(pos[tape], k=16)
        # The ground's whole colour, base and view-dependent, averaged over the
        # 16 nearest: the base alone came out bright cyan, the sand's own
        # colour being partly in its view-dependent terms.
        index = np.where(near)[0][nn]
        with torch.no_grad():
            for key in ("features_albedo", "features_specular"):
                if ck.get(key) is None or not ck[key].numel():
                    continue
                values = ck[key].detach().numpy()
                new = ck[key].detach().clone()
                new[torch.from_numpy(tape)] = torch.from_numpy(values[index].mean(axis=1)).to(new.dtype)
                ck[key] = torch.nn.Parameter(new.contiguous(), requires_grad=True)
    for key in ("positions", "rotation", "scale", "density"):
        if not isinstance(ck[key], torch.nn.Parameter):
            ck[key] = torch.nn.Parameter(ck[key].detach().contiguous(), requires_grad=True)
    ck["tapeRecoloured"] = n_tape
    torch.save(ck, a.out)
    print(json.dumps({"splats": int(p.shape[0]), "frames": len(names), "tape": n_tape,
                      "seenMedian": int(seen.median().item())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
