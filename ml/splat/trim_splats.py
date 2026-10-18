"""A reef's splats trimmed to the reef, for laying into one of our places.

    python trim_splats.py BAKED_CHECKPOINT OUT_CHECKPOINT PLACEMENT SURFACE_DIR --translate X,Y,Z
        [--above 1.5] [--below 2.0] [--edge 1.0] [--gain R,G,B]

A dive video's splats hold the video's water as well as its reef: from the
diver's own path it reads as water, from a vehicle anywhere else it is a blue
cloud standing over the reef (the first Al Fahal dives). Our places have
water of their own, so only the reef is kept:

  kept     splats over the reef's measured ground (SURFACE_DIR, laid in by
           PLACEMENT) and no more than --above metres over it nor --below
           metres under it
  faded    opacity taken down over the strip's outer --edge metres, so its
           edge is not a wall
  gain     colour times R,G,B, base and view-dependent terms alike, so the
           reef's sand can be brought to the place's sand at that depth

BAKED_CHECKPOINT is in the reef's local frame: the place's metres less
--translate (place_in_map.py puts that move on the layer). Run inside
iocean/3dgrut.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np
import torch
from scipy import ndimage

SH_C0 = 0.28209479177387814


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("out")
    ap.add_argument("placement", type=pathlib.Path)
    ap.add_argument("surface", type=pathlib.Path)
    ap.add_argument("--translate", required=True)
    ap.add_argument("--above", type=float, default=1.5)
    ap.add_argument("--below", type=float, default=2.0)
    ap.add_argument("--edge", type=float, default=1.0)
    ap.add_argument("--gain", default="1,1,1")
    a = ap.parse_args()
    T = np.array([float(v) for v in a.translate.split(",")])
    gain = np.array([float(v) for v in a.gain.split(",")])

    placed = json.loads(a.placement.read_text())
    P = np.array(placed["matrix"])
    dz = float(placed["dz"])
    said = json.loads((a.surface / "surface.json").read_text())
    grid = np.fromfile(a.surface / "surface.f32", dtype="<f4").reshape(said["rows"], said["columns"])
    cell, (ox, oy) = float(said["cellM"]), said["origin"]
    known = np.isfinite(grid)
    edge_m = ndimage.distance_transform_edt(known) * cell          # metres in from the strip's edge

    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    ck.pop("optimizer", None)
    pos = ck["positions"].detach().double().numpy()
    world = pos + T                                                 # the place's metres
    own = (world - P[:3, 3]) @ P[:3, :3]                            # back into the strip's own frame
    u = np.round((own[:, 0] - ox) / cell).astype(int)
    v = np.round((own[:, 1] - oy) / cell).astype(int)
    inside = (u >= 0) & (u < said["columns"]) & (v >= 0) & (v < said["rows"])
    ground = np.full(len(pos), np.nan)
    ground[inside] = grid[v[inside], u[inside]] + dz
    over = world[:, 2] - ground
    keep = inside & np.isfinite(ground) & (over <= a.above) & (over >= -a.below)
    fade = np.zeros(len(pos))
    fade[inside] = np.clip(edge_m[v[inside], u[inside]] / max(a.edge, 1e-6), 0.0, 1.0)

    idx = torch.from_numpy(np.flatnonzero(keep))
    with torch.no_grad():
        for key in ("positions", "rotation", "scale", "density", "features_albedo", "features_specular"):
            if ck.get(key) is not None and ck[key].numel():
                ck[key] = ck[key].detach()[idx]
        alpha = torch.sigmoid(ck["density"].double()) * torch.from_numpy(fade[keep])[:, None]
        ck["density"] = torch.logit(alpha.clamp(1e-6, 1 - 1e-6)).to(ck["positions"].dtype)
        if not np.allclose(gain, 1.0):
            g = torch.from_numpy(gain)
            albedo = ck["features_albedo"].double()
            ck["features_albedo"] = ((g * (0.5 + SH_C0 * albedo) - 0.5) / SH_C0).to(ck["positions"].dtype)
            spec = ck.get("features_specular")
            if spec is not None and spec.numel():
                n = spec.shape[0]
                ck["features_specular"] = (spec.double().reshape(n, -1, 3) * g).reshape(n, -1).to(spec.dtype)
        for key in ("positions", "rotation", "scale", "density", "features_albedo", "features_specular"):
            if ck.get(key) is not None:
                ck[key] = torch.nn.Parameter(ck[key].contiguous(), requires_grad=True)
    ck["trimmed"] = {"above": a.above, "below": a.below, "edge": a.edge, "gain": gain.tolist()}
    torch.save(ck, a.out)
    print(json.dumps({"splats": int(len(pos)), "kept": int(keep.sum()),
                      "droppedOutside": int((~inside | ~np.isfinite(ground)).sum()),
                      "droppedAbove": int((inside & np.isfinite(ground) & (over > a.above)).sum()),
                      "droppedBelow": int((inside & np.isfinite(ground) & (over < -a.below)).sum()),
                      "faded": int((keep & (fade < 1.0)).sum()), "gain": gain.tolist()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
