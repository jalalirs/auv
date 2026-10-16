"""Splats trained on overlapping pieces of one video, joined into one set.

    python join_splats.py COLMAP_TEXT OUT_CHECKPOINT CKPT:FIRST:LAST [CKPT:FIRST:LAST ...]
        [--near UNITS --far WHOLE_CKPT] [--clear UNITS]

Every piece was trained on frames cut from one COLMAP model, so all of them
are in that model's frame. Each keeps the splats whose nearest camera, out of
the whole video's, is one of the frames FIRST..LAST (1-based, in name order)
it owns; the overlap each piece was trained on beyond those frames is there so
its own edge is good, and is dropped here. Run inside iocean/3dgrut.

With --near, a piece gives only the splats within that distance of a camera
(COLMAP units), and everything farther comes from --far, a model trained on
the whole video. A piece makes up splats for the far water and reef it saw
from its own stretch only; seen from another piece's frames those came out
as black shapes over the top of the picture (49 of 756 frames). The whole
video's model saw the far field from everywhere.

With --clear, no splat within that distance of any camera of the whole video
is kept. Each piece hangs floaters in the water just in front of its own
cameras; harmless in its own frames, from another piece's frames they are
dark shapes over the reef ahead (piece b alone drew frames 446-468 clean,
joined with c it did not). The reef is never nearer a camera than 1.4 m.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from splat_place import colmap_cameras  # noqa: E402

PER_SPLAT = ("positions", "rotation", "scale", "density", "features_albedo", "features_specular")


def nearest_camera(points: torch.Tensor, centres: torch.Tensor, batch: int = 1 << 20) -> torch.Tensor:
    out = torch.empty(points.shape[0], dtype=torch.long)
    for s in range(0, points.shape[0], batch):
        out[s:s + batch] = torch.cdist(points[s:s + batch], centres).argmin(1)
    return out


def nearest_distance(points: torch.Tensor, centres: torch.Tensor, batch: int = 1 << 20) -> torch.Tensor:
    out = torch.empty(points.shape[0])
    for s in range(0, points.shape[0], batch):
        out[s:s + batch] = torch.cdist(points[s:s + batch], centres).min(1).values
    return out


def main() -> int:
    args = sys.argv[1:]
    near, far, clear = None, None, None
    if "--near" in args:
        i = args.index("--near"); near = float(args[i + 1]); del args[i:i + 2]
    if "--far" in args:
        i = args.index("--far"); far = args[i + 1]; del args[i:i + 2]
    if "--clear" in args:
        i = args.index("--clear"); clear = float(args[i + 1]); del args[i:i + 2]
    sys.argv = [sys.argv[0]] + args
    text, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    cams = colmap_cameras(text)
    names = sorted(cams["poses"])
    centres = torch.tensor(np.array([cams["poses"][n][:3, 3] for n in names]), dtype=torch.float32)
    joined, first, said = {k: [] for k in PER_SPLAT}, None, []
    for spec in sys.argv[3:]:
        path, lo, hi = spec.rsplit(":", 2)
        lo, hi = int(lo), int(hi)
        ck = torch.load(path, map_location="cpu", weights_only=False)
        ck.pop("optimizer", None)
        with torch.no_grad():
            owner = nearest_camera(ck["positions"].float(), centres) + 1        # 1-based frame
            keep = (owner >= lo) & (owner <= hi)
            if near is not None or clear is not None:
                gap = nearest_distance(ck["positions"].float(), centres)
                if near is not None:
                    keep &= gap < near
                if clear is not None:
                    keep &= gap >= clear
            for k in PER_SPLAT:
                joined[k].append(ck[k].detach()[keep])
        said.append({"piece": path, "frames": [lo, hi], "splats": int(keep.shape[0]), "kept": int(keep.sum())})
        if first is None:
            first = ck
        else:
            del ck
    if far is not None:
        ck = torch.load(far, map_location="cpu", weights_only=False)
        ck.pop("optimizer", None)
        with torch.no_grad():
            gap = nearest_distance(ck["positions"].float(), centres)
            keep = gap >= max(near, clear or 0.0)
            for k in PER_SPLAT:
                joined[k].append(ck[k].detach()[keep])
        said.append({"piece": far, "frames": "beyond near", "splats": int(keep.shape[0]), "kept": int(keep.sum())})
        del ck
    for k in PER_SPLAT:
        first[k] = torch.nn.Parameter(torch.cat(joined[k]).contiguous(), requires_grad=True)
    for k in ("densify_grad_norm_accum", "densify_grad_norm_denom"):
        first.pop(k, None)
    first["joinedFrom"] = said
    first["joinedNear"] = near
    first["joinedClear"] = clear
    torch.save(first, out)
    print(json.dumps({"pieces": said, "splats": int(first["positions"].shape[0])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
