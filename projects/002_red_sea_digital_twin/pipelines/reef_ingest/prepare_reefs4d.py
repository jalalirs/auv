#!/usr/bin/env python3
"""Create a textured, traceable OpenUSD visual derivative from Reefs4D PLY."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np
import pymeshlab
from pxr import Gf, Kind, Sdf, Usd, UsdGeom, UsdShade, Vt


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_usd(
    output: Path,
    texture_name: str,
    points: np.ndarray,
    faces: np.ndarray,
    normals: np.ndarray,
    texcoords: np.ndarray,
) -> None:
    stage = Usd.Stage.CreateNew(str(output))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    root = UsdGeom.Xform.Define(stage, "/ReefAsset")
    root.GetPrim().SetMetadata("kind", Kind.Tokens.component)
    root.GetPrim().CreateAttribute(
        "redsea:assetId", Sdf.ValueTypeNames.String, custom=True
    ).Set("reefs4d.c2.2019.visual")
    root.GetPrim().CreateAttribute(
        "redsea:sourceDoi", Sdf.ValueTypeNames.String, custom=True
    ).Set("10.5281/zenodo.14616671")
    root.GetPrim().CreateAttribute(
        "redsea:truthClass", Sdf.ValueTypeNames.String, custom=True
    ).Set("derived_observation")
    stage.SetDefaultPrim(root.GetPrim())

    mesh = UsdGeom.Mesh.Define(stage, "/ReefAsset/Geometry")
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(True)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points.astype(np.float32)))
    mesh.CreateFaceVertexCountsAttr(
        Vt.IntArray.FromNumpy(np.full(len(faces), 3, dtype=np.int32))
    )
    mesh.CreateFaceVertexIndicesAttr(
        Vt.IntArray.FromNumpy(faces.reshape(-1).astype(np.int32))
    )
    mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(normals.astype(np.float32)))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateExtentAttr(
        Vt.Vec3fArray(
            [
                Gf.Vec3f(*points.min(axis=0).astype(float)),
                Gf.Vec3f(*points.max(axis=0).astype(float)),
            ]
        )
    )

    st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    )
    st.Set(Vt.Vec2fArray.FromNumpy(texcoords.astype(np.float32)))

    material = UsdShade.Material.Define(stage, "/ReefAsset/Looks/ReefMaterial")
    surface = UsdShade.Shader.Define(
        stage, "/ReefAsset/Looks/ReefMaterial/PreviewSurface"
    )
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.82)
    surface.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)

    reader = UsdShade.Shader.Define(
        stage, "/ReefAsset/Looks/ReefMaterial/PrimvarReader"
    )
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader_result = reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

    texture = UsdShade.Shader.Define(
        stage, "/ReefAsset/Looks/ReefMaterial/DiffuseTexture"
    )
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(
        Sdf.AssetPath(f"./{texture_name}")
    )
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader_result)
    texture_rgb = texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture_rgb
    )
    material.CreateSurfaceOutput().ConnectToSource(
        surface.ConnectableAPI(), "surface"
    )
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    stage.GetRootLayer().Save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--texture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-faces", type=int, default=450_000)
    parser.add_argument(
        "--expected-input-md5", default="71c328e0e991078ac12507af83a971e2"
    )
    args = parser.parse_args()

    for path in (args.input, args.texture):
        if not path.is_file():
            raise FileNotFoundError(path)
    if md5(args.input) != args.expected_input_md5:
        raise ValueError("source PLY checksum does not match the manifest")
    if args.target_faces < 10_000:
        raise ValueError("target face count is too low for the visual derivative")

    started = time.monotonic()
    mesh_set = pymeshlab.MeshSet()
    mesh_set.load_new_mesh(str(args.input))
    source = mesh_set.current_mesh()
    source_vertices = source.vertex_number()
    source_faces = source.face_number()
    source_bounds_min = source.vertex_matrix().min(axis=0)
    source_bounds_max = source.vertex_matrix().max(axis=0)
    if not source.has_wedge_tex_coord():
        raise ValueError("source mesh has no face-varying texture coordinates")

    if source_faces > args.target_faces:
        mesh_set.apply_filter(
            "meshing_decimation_quadric_edge_collapse_with_texture",
            targetfacenum=args.target_faces,
            qualitythr=0.35,
            extratcoordw=2.0,
            preserveboundary=True,
            boundaryweight=2.0,
            preservenormal=True,
            planarquadric=True,
        )
    mesh_set.apply_filter("compute_normal_per_vertex")
    visual = mesh_set.current_mesh()

    points = visual.vertex_matrix()
    faces = visual.face_matrix()
    normals = visual.vertex_normal_matrix()
    texcoords = visual.wedge_tex_coord_matrix()
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError(f"expected triangles, got face matrix {faces.shape}")
    if texcoords.shape != (len(faces) * 3, 2):
        raise ValueError(
            f"expected three UV coordinates per face, got {texcoords.shape}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    texture_output = args.output_dir / args.texture.name
    shutil.copyfile(args.texture, texture_output)
    usd_output = args.output_dir / "C22019_visual_lod0.usdc"
    write_usd(usd_output, texture_output.name, points, faces, normals, texcoords)

    result = {
        "schema_version": 1,
        "asset_id": "reefs4d.c2.2019.visual.lod0",
        "truth_class": "derived_observation",
        "source": {
            "doi": "10.5281/zenodo.14616671",
            "file": args.input.name,
            "md5": args.expected_input_md5,
            "vertices": source_vertices,
            "faces": source_faces,
            "bounds_min_m": source_bounds_min.tolist(),
            "bounds_max_m": source_bounds_max.tolist(),
        },
        "derivation": {
            "tool": "PyMeshLab",
            "tool_version": pymeshlab.__version__,
            "filter": "meshing_decimation_quadric_edge_collapse_with_texture",
            "target_faces": args.target_faces,
            "parameters": {
                "qualitythr": 0.35,
                "extratcoordw": 2.0,
                "preserveboundary": True,
                "boundaryweight": 2.0,
                "preservenormal": True,
                "planarquadric": True,
            },
        },
        "output": {
            "usd": usd_output.name,
            "usd_sha256": sha256(usd_output),
            "texture": texture_output.name,
            "texture_sha256": sha256(texture_output),
            "vertices": visual.vertex_number(),
            "faces": visual.face_number(),
            "bounds_min_m": points.min(axis=0).tolist(),
            "bounds_max_m": points.max(axis=0).tolist(),
        },
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    manifest_output = args.output_dir / "derived.json"
    manifest_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
