"""Baked splats cut into parts along the reef, each small enough to package.

    python split_splats.py BAKED_CHECKPOINT OUT_PREFIX [--most 9000000]

USD reads a .usdz only below 2 GB, and a NuRec export at half precision is
about 120 bytes a splat: 22.9 million splats joined from three pieces of one
video would be 2.7 GB. Cut along the reef's long axis (the place's x after
baking) into as few parts as keep each under --most, each written as
OUT_PREFIX-<n>.pt for its own NuRec export. Run inside iocean/3dgrut.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import torch

PER_SPLAT = ("positions", "rotation", "scale", "density", "features_albedo", "features_specular")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("prefix")
    ap.add_argument("--most", type=int, default=9_000_000)
    a = ap.parse_args()
    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    ck.pop("optimizer", None)
    n = ck["positions"].shape[0]
    parts = max(1, int(np.ceil(n / a.most)))
    order = torch.argsort(ck["positions"].detach()[:, 0])
    said = []
    for i, which in enumerate(torch.tensor_split(order, parts)):
        part = dict(ck)
        for k in PER_SPLAT:
            part[k] = torch.nn.Parameter(ck[k].detach()[which].contiguous(), requires_grad=True)
        x = ck["positions"].detach()[which, 0]
        torch.save(part, f"{a.prefix}-{i}.pt")
        said.append({"part": i, "splats": int(which.shape[0]), "xM": [round(float(x.min()), 2), round(float(x.max()), 2)]})
    print(json.dumps({"splats": n, "parts": said}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
