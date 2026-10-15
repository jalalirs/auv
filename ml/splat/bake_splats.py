"""Splats moved into a place's frame in their own data, so the renderer draws
them with no transform at all.

    python bake_splats.py CHECKPOINT SPLATS_USDZ ALIGN_JSON OUT_CHECKPOINT OUT_ALIGN_JSON

Isaac Sim draws a ParticleField under a scaled, rotated prim badly: with the
whole video's 7.66 m-per-unit scale on the prim the far reef came out as haze
(12.9 dB against the video where 3DGRUT's own render of the same splats is
24.1; 14.5 with the scale taken off). So the place's transform, and the
export's own normalizing transform under it, go into the splats themselves:

  positions     p' = L p + b
  orientations  q' = q_R * q            (3DGRUT's quaternions are w, x, y, z)
  scales        log s' = log s + log k  (L = k R, a similarity)
  colour        the SH bands above DC rotated by R (3DGRUT's own
                sh_rotation.rotate_specular); DC does not turn

Run inside iocean/3dgrut. The checkpoint written keeps every key the
exporter reads; export it with
    python -m threedgrut.export.scripts.export_usd --checkpoint OUT --output X.usdc --no-transform --no-cameras
and OUT_ALIGN_JSON is ALIGN_JSON with an identity usdMatrix and "baked": true.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from splat_place import gaussians_transform  # noqa: E402


def quaternion_of(R: np.ndarray) -> np.ndarray:
    """A rotation matrix as a unit quaternion (w, x, y, z)."""
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    else:
        i = int(np.argmax(np.diag(R)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = np.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k]) * 2
        q = [0.0] * 4
        q[0] = (R[k, j] - R[j, k]) / s
        q[1 + i] = 0.25 * s
        q[1 + j] = (R[j, i] + R[i, j]) / s
        q[1 + k] = (R[k, i] + R[i, k]) / s
    q = np.array(q)
    return q / np.linalg.norm(q)


def times(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Hamilton product of (w, x, y, z) quaternions, a broadcast over b."""
    aw, ax, ay, az = a.unbind(-1)
    bw, bx, by, bz = b.unbind(-1)
    return torch.stack([aw * bw - ax * bx - ay * by - az * bz,
                        aw * bx + ax * bw + ay * bz - az * by,
                        aw * by - ax * bz + ay * bw + az * bx,
                        aw * bz + ax * by - ay * bx + az * bw], -1)


def place_from_colmap(usdz: pathlib.Path, align: dict) -> tuple[np.ndarray, np.ndarray]:
    """The whole transform, column convention: the export's own (row-vector M)
    then the place's (usdMatrix, rows L^T and b)."""
    M = gaussians_transform(usdz)
    U = np.array(align["usdMatrix"])
    A, m = M[:3, :3].T, M[3, :3]
    L, b = U[:3, :3].T, U[3, :3]
    return L @ A, L @ m + b


def main() -> int:
    ckpt_in, usdz, align_in, ckpt_out, align_out = (pathlib.Path(p) for p in sys.argv[1:6])
    # Opacity taken to the power 1/k^thin: an experiment on whether the
    # renderer integrates a splat's opacity over its size in world units.
    thin = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
    align = json.loads(align_in.read_text())
    L, b = place_from_colmap(usdz, align)
    k = float(np.cbrt(np.linalg.det(L)))
    R = L / k
    off = float(np.abs(R @ R.T - np.eye(3)).max())
    if off > 1e-4:
        raise SystemExit(f"the transform is not a similarity (R R^T off identity by {off:.2g})")

    ck = torch.load(ckpt_in, map_location="cpu", weights_only=False)
    with torch.no_grad():
        p = ck["positions"].double()
        ck["positions"] = (p @ torch.from_numpy(L).T + torch.from_numpy(b)).to(ck["positions"].dtype)
        q = torch.nn.functional.normalize(ck["rotation"].double(), dim=-1)
        ck["rotation"] = times(torch.from_numpy(quaternion_of(R)), q).to(ck["rotation"].dtype)
        ck["scale"] = (ck["scale"].double() + np.log(k)).to(ck["scale"].dtype)
        if thin:
            alpha = torch.sigmoid(ck["density"].double()).clamp(1e-6, 1 - 1e-6)
            alpha = 1 - (1 - alpha) ** (1.0 / k ** thin)
            ck["density"] = torch.logit(alpha.clamp(1e-6, 1 - 1e-6)).to(ck["density"].dtype)
        if ck.get("features_specular") is not None and ck["features_specular"].numel():
            from threedgrut.export.sh_rotation import rotate_specular
            spec = ck["features_specular"]
            degree = int(round(np.sqrt(spec.shape[1] // 3 + 1))) - 1
            ck["features_specular"] = rotate_specular(spec.double(), torch.from_numpy(R), degree).to(spec.dtype)
    # The exporter loads them as the model's parameters, as they were saved.
    for key in ("positions", "rotation", "scale", "density", "features_specular"):
        if key in ck and not isinstance(ck[key], torch.nn.Parameter):
            ck[key] = torch.nn.Parameter(ck[key].contiguous(), requires_grad=True)
    torch.save(ck, ckpt_out)
    baked = dict(align, usdMatrix=np.eye(4).tolist(), baked=True,
                 bakedTransform={"linear": L.tolist(), "offset": b.tolist(), "scale": k})
    align_out.write_text(json.dumps(baked, indent=1))
    print(json.dumps({"splats": int(p.shape[0]), "scale": round(k, 4), "rotationOff": off}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
