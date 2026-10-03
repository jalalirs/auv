"""A vehicle's drawn hull as USD: meshes, the preview materials any viewer
draws, and the physical ones Isaac's RTX renderer reads beside them.

    from hull_usd import Hull
    hull = Hull("BoxfishLuna", doc="...")
    hull.look("Paint", "#f2c40c", rough=0.3, clearcoat=1.0,
              rtx=("OmniPBR", {"diffuse_color_constant": (0.86, 0.55, 0.0)}))
    hull.add("Body", mesh, "Paint")
    hull.save(path)                       # .usd (crate), dressed

Meshes are trimesh meshes in the vehicle's own frame: metres, x forward, z up,
the origin at the centre of gravity — the frame dynamics.json places the
thrusters, lights and sensors in, so what is drawn is where the physics is.

hardware/mini/package.py writes mini-hoot's hull with its own copy of this
(from CAD in millimetres, mirrored); this is the general one.
"""

from __future__ import annotations

import pathlib


class Hull:
    def __init__(self, root: str, doc: str = "") -> None:
        self.root = root
        self.doc = doc
        self.looks: list[tuple] = []
        self.meshes: list[tuple] = []

    def look(self, name: str, colour: str, rough: float, metal: float = 0.0, opacity: float = 1.0,
             clearcoat: float = 0.0, emissive=None, rtx=None) -> None:
        """A material: `colour` as #rrggbb for the preview surface; `rtx` as
        (MDL module, inputs) for the renderer, inputs' colours linear."""
        self.looks.append((name, colour, rough, metal, opacity, clearcoat, emissive, rtx))

    def add(self, name: str, mesh, look: str) -> None:
        self.meshes.append((name, mesh, look))

    def text(self) -> str:
        out = ['#usda 1.0\n(\n    defaultPrim = "%s"\n    metersPerUnit = 1\n    upAxis = "Z"\n'
               '    doc = "%s"\n)\n\ndef Xform "%s"\n{\n' % (self.root, self.doc.replace('"', "'"), self.root),
               '    def Scope "Looks"\n    {\n']
        for name, colour, rough, metal, opacity, clearcoat, emissive, _ in self.looks:
            r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
            em = f"\n                color3f inputs:emissiveColor = ({emissive})" if emissive else ""
            out.append(f"""        def Material "{name}"
        {{
            token outputs:surface.connect = </{self.root}/Looks/{name}/S.outputs:surface>
            def Shader "S"
            {{
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = ({r ** 2.2:.4f}, {g ** 2.2:.4f}, {b ** 2.2:.4f})
                float inputs:roughness = {rough}
                float inputs:metallic = {metal}
                float inputs:opacity = {opacity}
                float inputs:clearcoat = {clearcoat}
                float inputs:ior = 1.49{em}
                token outputs:surface
            }}
        }}
""")
        out.append("    }\n")
        for name, m, look in self.meshes:
            pts = ", ".join(f"({a:.5f}, {b:.5f}, {c:.5f})" for a, b, c in m.vertices)
            nrm = ", ".join(f"({a:.4f}, {b:.4f}, {c:.4f})" for a, b, c in m.vertex_normals)
            idx = ", ".join(str(i) for i in m.faces.reshape(-1))
            out.append(f"""    def Mesh "{name}" (prepend apiSchemas = ["MaterialBindingAPI"])
    {{
        uniform token subdivisionScheme = "none"
        int[] faceVertexCounts = [{", ".join(["3"] * len(m.faces))}]
        int[] faceVertexIndices = [{idx}]
        point3f[] points = [{pts}]
        normal3f[] normals = [{nrm}] (interpolation = "vertex")
        rel material:binding = </{self.root}/Looks/{look}>
    }}
""")
        out.append("}\n")
        return "".join(out)

    def save(self, path) -> pathlib.Path:
        """Authored as text, kept as crate (a fifth of the size), and dressed
        with the renderer's materials."""
        from pxr import Usd

        path = pathlib.Path(path)
        text = path.with_suffix(".usda")
        text.write_text(self.text())
        if path.suffix == ".usda":
            stage = Usd.Stage.Open(str(path))
        else:
            Usd.Stage.Open(str(text)).Export(str(path))
            text.unlink()
            stage = Usd.Stage.Open(str(path))
        self.dress(stage)
        stage.GetRootLayer().Save()
        return path

    def dress(self, stage) -> int:
        from pxr import Gf, Sdf, UsdShade

        done = 0
        for name, *_, rtx in self.looks:
            if rtx is None:
                continue
            module, inputs = rtx
            material = UsdShade.Material.Get(stage, f"/{self.root}/Looks/{name}")
            shader = UsdShade.Shader.Define(stage, material.GetPath().AppendChild("M"))
            shader.SetSourceAsset(Sdf.AssetPath(f"{module}.mdl"), "mdl")
            shader.SetSourceAssetSubIdentifier(module, "mdl")
            for key, value in inputs.items():
                if isinstance(value, bool):
                    shader.CreateInput(key, Sdf.ValueTypeNames.Bool).Set(value)
                elif isinstance(value, tuple):
                    shader.CreateInput(key, Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*value))
                else:
                    shader.CreateInput(key, Sdf.ValueTypeNames.Float).Set(float(value))
            out = shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
            for which in ("surface", "volume", "displacement"):
                getattr(material, f"Create{which.title()}Output")("mdl").ConnectToSource(out)
            done += 1
        return done
