"""A reconstruction's own frame: level, in metres, centred on its reef, and
the camera's path in it. The frame a reconstruction asset is stored in, before
anybody maps it anywhere (mapping and Resolve place it afterwards).

    python asset_frame.py SPLAT_PLACE_DIR OUT_ALIGN_JSON

SPLAT_PLACE_DIR is splat_place.py's output (frame.npz: centre, rotation, scale;
cameras.json: every camera, world_from_camera in the export's frame). Written:
an align JSON in the shape bake_splats.py reads, {usdMatrix, frames: [{name,
eye, matrix}], focalMm, apertureMm, image}, with the frame's origin at the
reef's centre on its own ground plane and z up.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np


def main() -> int:
    place, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    fz = np.load(place / "frame.npz")
    L = float(fz["scale"]) * fz["rotation"]                    # export frame -> asset frame, linear
    b = -L @ fz["centre"]
    usd = np.eye(4)
    usd[:3, :3], usd[3, :3] = L.T, b
    cams = json.loads((place / "cameras.json").read_text())
    frames = []
    for name in sorted(cams["poses"]):
        m = np.array(cams["poses"][name])
        R = m[:3, :3]
        x, y_down, z_fwd = (fz["rotation"] @ R[:, i] for i in range(3))
        pose = np.eye(4)
        pose[:3, 0], pose[:3, 1], pose[:3, 2], pose[:3, 3] = x, -y_down, -z_fwd, L @ m[:3, 3] + b
        frames.append({"name": name, "eye": [float(v) for v in pose[:3, 3]], "matrix": pose.tolist()})
    out.write_text(json.dumps({"usdMatrix": usd.tolist(), "frames": frames,
                               "focalMm": 20.955 * cams["fx"] / cams["width"], "apertureMm": 20.955,
                               "image": [cams["width"], cams["height"]]}, indent=1))
    print(json.dumps({"frames": len(frames), "scale": float(fz["scale"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
