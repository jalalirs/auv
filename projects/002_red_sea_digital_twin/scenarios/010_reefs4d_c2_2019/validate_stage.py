#!/usr/bin/env python3
"""Validate the composed reef scene and its external visual asset."""

from pathlib import Path
import sys

from pxr import Usd, UsdGeom, UsdShade


stage_path = Path(sys.argv[1]).resolve()
stage = Usd.Stage.Open(str(stage_path), load=Usd.Stage.LoadAll)
if stage is None:
    raise RuntimeError(f"failed to open {stage_path}")
if stage.GetDefaultPrim().GetPath().pathString != "/RedSeaTwin":
    raise ValueError("unexpected default prim")
if UsdGeom.GetStageMetersPerUnit(stage) != 1.0:
    raise ValueError("stage is not expressed in meters")
if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
    raise ValueError("stage is not Z-up")

mesh = UsdGeom.Mesh.Get(stage, "/RedSeaTwin/Site/MeasuredReef/Geometry")
if not mesh:
    raise ValueError("measured reef reference did not resolve")
points = mesh.GetPointsAttr().Get()
faces = mesh.GetFaceVertexCountsAttr().Get()
st = UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
material, _ = UsdShade.MaterialBindingAPI(mesh).ComputeBoundMaterial()
if len(points) < 100_000 or len(faces) < 400_000:
    raise ValueError("visual reef LOD is unexpectedly small")
if not st or st.GetInterpolation() != UsdGeom.Tokens.faceVarying:
    raise ValueError("reef texture coordinates are missing or not face-varying")
if not material:
    raise ValueError("reef material is not bound")

for camera in ("Overview", "CloseInspection", "TopSurvey"):
    if not UsdGeom.Camera.Get(stage, f"/RedSeaTwin/Render/{camera}"):
        raise ValueError(f"missing camera: {camera}")

print(
    f"Validated {stage_path}: {len(points)} vertices, {len(faces)} faces, "
    f"material={material.GetPath()}"
)
