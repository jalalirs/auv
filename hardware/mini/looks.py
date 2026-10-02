"""mini-hoot's materials for the renderer that draws a dive.

    hardware/.venv/bin/python hardware/mini/looks.py catalog/vehicles/mini-hoot/mini-hoot.usd

The hull carries a preview surface on every material, which any viewer can
draw. This adds the physical one beside it (MDL that Isaac's RTX renderer
reads): a red lid with a clear coat like moulded plastic, a satin black
chassis, a dome that is acrylic and refracts, anodised flanges. package.py
calls it on every hull it writes; run on its own it dresses an existing one
without rebuilding the shapes.
"""

from __future__ import annotations

import sys

# name in /MiniHoot/Looks: (module, inputs). Colours are linear.
LOOKS = {
    "Lid": ("OmniSurface", {"diffuse_reflection_color": (0.58, 0.008, 0.012), "diffuse_reflection_roughness": 0.0,
                            "specular_reflection_roughness": 0.38, "specular_reflection_weight": 0.5,
                            "coat_weight": 1.0, "coat_roughness": 0.04, "coat_ior": 1.5}),
    "Chassis": ("OmniPBR", {"diffuse_color_constant": (0.040, 0.043, 0.049), "reflection_roughness_constant": 0.42}),
    "Thruster": ("OmniPBR", {"diffuse_color_constant": (0.056, 0.062, 0.070), "reflection_roughness_constant": 0.38}),
    "Metal": ("OmniPBR", {"diffuse_color_constant": (0.20, 0.21, 0.23), "metallic_constant": 1.0,
                          "reflection_roughness_constant": 0.3}),
    "Dome": ("OmniGlass", {"glass_color": (0.97, 0.99, 1.0), "glass_ior": 1.49, "thin_walled": False,
                           "frosting_roughness": 0.0}),
    "Camera": ("OmniPBR", {"diffuse_color_constant": (0.01, 0.01, 0.012), "reflection_roughness_constant": 0.15}),
    "Lens": ("OmniPBR", {"diffuse_color_constant": (0.85, 0.85, 0.80), "reflection_roughness_constant": 0.1}),
    "Sensor": ("OmniPBR", {"diffuse_color_constant": (0.025, 0.026, 0.03), "reflection_roughness_constant": 0.45}),
    "SensorFace": ("OmniPBR", {"diffuse_color_constant": (0.04, 0.16, 0.45), "reflection_roughness_constant": 0.3}),
}


def dress(stage) -> int:
    from pxr import Gf, Sdf, UsdShade

    done = 0
    for name, (module, inputs) in LOOKS.items():
        prim = stage.GetPrimAtPath(f"/MiniHoot/Looks/{name}")
        if not prim:
            # A hull written before the material was: made here, so whatever
            # is bound to it is drawn.
            prim = UsdShade.Material.Define(stage, f"/MiniHoot/Looks/{name}").GetPrim()
        material = UsdShade.Material(prim)
        shader = UsdShade.Shader.Define(stage, prim.GetPath().AppendChild("M"))
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


def main() -> int:
    from pxr import Usd

    stage = Usd.Stage.Open(sys.argv[1])
    print(f"dressed {dress(stage)} materials")
    stage.GetRootLayer().Save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
