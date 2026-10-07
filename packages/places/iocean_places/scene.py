"""What a dive opens: the seabed as a mesh, its material, where to begin.

Taken out of tools/make-site (r8) so that the tool and this module write the
same place. `write_place` is the module's own entry: a fused depth layer in,
the heightfield, the USD and the record of where every cell came from out.
"""

from __future__ import annotations

import pathlib


# What the seabed is made of.
#
# UsdPreviewSurface rather than a renderer's own material, because it is part of
# OpenUSD and every renderer understands it, a place should not need this
# platform's renderer to be looked at. The maps are photographed sand under CC0,
# which is a real surface with real grain rather than a shader somebody tuned
# until it looked about right.
SEABED_MATERIAL = """
    def Scope "Looks"
    {
        def Material "Seabed"
        {
            token outputs:surface.connect = </World/Looks/Seabed/Surface.outputs:surface>

            def Shader "Surface"
            {
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor.connect = </World/Looks/Seabed/Colour.outputs:rgb>
                float inputs:roughness.connect = </World/Looks/Seabed/Roughness.outputs:r>
                normal3f inputs:normal.connect = </World/Looks/Seabed/Bumps.outputs:rgb>
                float inputs:metallic = 0
                token outputs:surface
            }

            def Shader "Place"
            {
                uniform token info:id = "UsdPrimvarReader_float2"
                token inputs:varname = "st"
                float2 outputs:result
            }

            def Shader "Colour"
            {
                uniform token info:id = "UsdUVTexture"
                asset inputs:file = @textures/seabed_colour.jpg@
                float2 inputs:st.connect = </World/Looks/Seabed/Place.outputs:result>
                token inputs:wrapS = "repeat"
                token inputs:wrapT = "repeat"
                # Darkened, and pulled towards the colour wet sand actually is.
                # A dry beach photographed in sunlight is the brightest thing in
                # any scene it is in, and dropped straight onto a seabed it
                # makes the whole reef read as a sandbar at noon.
                float4 inputs:scale = (1.05, 1.0, 0.92, 1)
                color3f outputs:rgb
            }

            def Shader "Roughness"
            {
                uniform token info:id = "UsdUVTexture"
                asset inputs:file = @textures/seabed_rough.jpg@
                float2 inputs:st.connect = </World/Looks/Seabed/Place.outputs:result>
                token inputs:wrapS = "repeat"
                token inputs:wrapT = "repeat"
                float outputs:r
            }

            def Shader "Bumps"
            {
                uniform token info:id = "UsdUVTexture"
                asset inputs:file = @textures/seabed_normal.jpg@
                float2 inputs:st.connect = </World/Looks/Seabed/Place.outputs:result>
                token inputs:wrapS = "repeat"
                token inputs:wrapT = "repeat"
                float4 inputs:scale = (2, 2, 2, 1)
                float4 inputs:bias = (-1, -1, -1, 0)
                normal3f outputs:rgb
            }
        }
    }
"""

# The ground of a place that has a record, rather than a place in general.
#
# Two scales at once, which UsdPreviewSurface cannot do and is the reason this
# one material is not part of OpenUSD. The low frequency is the place itself:
# tools/ground's colour map, which over a surveyed reef is the orthomosaic and
# elsewhere is habitat class laid down from the satellite's pattern. It is
# 24 cm a texel over a kilometre, so on its own it is a smear at close range.
# The high frequency is a tiled photograph of a real surface, repeating every
# few metres, which is what gives the ground grain and, through its normal map,
# relief that the lamps and the sun can find.
#
# So: colour from the survey, relief from the photograph, and neither one
# pretending to be the other. What you see on the seabed at a metre is mostly
# shading off relief rather than change in albedo, which is why this works.
#
# OmniPBR is Omniverse's, not OpenUSD's. A place therefore carries the preview
# surface as well, and anything that cannot read MDL still opens it.
GROUND_MATERIAL = """
    def Scope "Looks"
    {
        def Material "Seabed"
        {
            token outputs:mdl:surface.connect = </World/Looks/Seabed/Surface.outputs:out>
            token outputs:surface.connect = </World/Looks/Seabed/Fallback.outputs:surface>

            def Shader "Surface"
            {
                uniform token info:implementationSource = "sourceAsset"
                uniform asset info:mdl:sourceAsset = @coral_ground.mdl@
                uniform token info:mdl:sourceAsset:subIdentifier = "coral_ground"

                asset inputs:site_colour = @textures/site_colour.jpg@
                asset inputs:hardness = @textures/hardness.png@
                # Written by tools/aim-water after the place knows where its
                # dives begin. White until then, which is water that takes
                # nothing.
                # Raw, because this one is not a photograph: every texel is
                # already exp(-distance / attenuation length). Read as sRGB it
                # comes back through a curve it has no business going through.
                # Said here and not in the MDL — `base::file_texture` has no
                # gamma parameter, and asking it for one fails the whole
                # module to compile.
                asset inputs:swum_map = @textures/site_survives.png@ (
                    colorSpace = "raw"
                )

                # %(soft)s, in the grooves and the sediment.
                #
                # Named rather than written in, because it is not always a
                # photograph. Below the reach of the waves there is nothing to
                # photograph that is right: every soft-seabed texture in every
                # library is rippled sand, and the ripples in it were made by
                # surface waves. See tools/sediment.py.
                asset inputs:soft_colour = @textures/%(soft_colour_file)s@
                asset inputs:soft_normal = @textures/%(soft_normal_file)s@
                asset inputs:soft_rough = @textures/%(soft_rough_file)s@
                asset inputs:soft_height = @textures/%(soft_height_file)s@
                color3f inputs:soft_average = (%(soft_average)s)

                # %(hard)s, on the spurs and the pavement.
                asset inputs:hard_colour = @textures/hard_colour.jpg@
                asset inputs:hard_normal = @textures/hard_normal.jpg@
                asset inputs:hard_rough = @textures/hard_rough.jpg@
                asset inputs:hard_height = @textures/hard_disp.jpg@
                color3f inputs:hard_average = (%(hard_average)s)

                # %(tile).0f metres a repeat over %(across).0f. The eye finds a
                # period long before it stops seeing the grain, and once it has
                # found one that is all it sees.
                float inputs:repeats = %(repeats).4f
                float inputs:grain = %(grain).2f
                float inputs:relief = %(relief).2f
                float inputs:lift = %(lift).3f
                float inputs:blend_depth = 0.12

                # The water between this ground and the camera, done here
                # because the renderer has nowhere else to put it. The runtime
                # sets all four as a dive opens and moves `eye` as it flies;
                # what is written here is what a place looks like opened in
                # something that does not know to.
                float3 inputs:eye = (0, 0, 0)
                color3f inputs:attenuation = (4, 17, 13)
                color3f inputs:veiling = (0.24, 0.55, 0.45)
                float inputs:veil = 0
                float inputs:show_distance = 0
                # The net the surface throws. Declared here so the runtime
                # can write it as a dive opens: it sets the water on every
                # shader that has an `eye`, and skips any input the prim does
                # not already carry.
                asset inputs:caustics = @@
                float inputs:caustics_across = 90
                float inputs:caustics_strength = 0
                # The site's own width and about how deep it is, so the
                # material can turn its texture coordinates back into a place.
                # Six attempts to read a position out of this renderer came
                # back as the ordinary seabed or a constant; the texture
                # coordinate is already laid nought-to-one over the site and
                # has been working since the colour map went on.
                float inputs:site_eye_u = %(eye_u).5f
                float inputs:site_eye_v = %(eye_v).5f
                float inputs:eye_depth_m = %(eye_z).2f
                float inputs:site_across = %(across).1f
                float inputs:floor_at_m = %(floor).2f
                token outputs:out
            }

            # For anything that cannot read MDL. It gets the site's own colour
            # and none of the grain, which is the right half to keep: a place
            # should be openable without this platform's renderer.
            def Shader "Fallback"
            {
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor.connect = </World/Looks/Seabed/Colour.outputs:rgb>
                float inputs:roughness = 0.85
                float inputs:metallic = 0
                token outputs:surface
            }

            def Shader "Place"
            {
                uniform token info:id = "UsdPrimvarReader_float2"
                token inputs:varname = "st"
                float2 outputs:result
            }

            def Shader "Colour"
            {
                uniform token info:id = "UsdUVTexture"
                asset inputs:file = @textures/site_colour.jpg@
                float2 inputs:st.connect = </World/Looks/Seabed/Place.outputs:result>
                token inputs:wrapS = "clamp"
                token inputs:wrapT = "clamp"
                color3f outputs:rgb
            }
        }
    }
"""

UNTEXTURED_MATERIAL = """
    def Scope "Looks"
    {
        def Material "Seabed"
        {
            token outputs:surface.connect = </World/Looks/Seabed/Surface.outputs:surface>
            def Shader "Surface"
            {
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = (0.72, 0.68, 0.58)
                float inputs:roughness = 0.9
                float inputs:metallic = 0
                token outputs:surface
            }
        }
    }
"""


def where_a_dive_begins(height, across: float, off_bottom: float = 3.0) -> dict:
    """A start on ground that has nothing growing on it.

    Flat, at the depth most of the site is at, and inside the middle half so
    a vehicle can fly in any direction without meeting the edge. Flatness
    matters more than anywhere else down here: there is no reef to look at,
    so what a dive is for is the bottom itself, and a start on the wall of a
    canyon is a start looking at a wall.
    """
    import numpy as np

    rows, columns = height.shape
    # The middle half of the site, so there is room on every side.
    lo_r, hi_r = rows // 4, rows - rows // 4
    lo_c, hi_c = columns // 4, columns - columns // 4
    inside = height[lo_r:hi_r, lo_c:hi_c]

    # How rough each patch is, over about a tenth of the site.
    step = max(1, min(inside.shape) // 24)
    coarse = inside[::step, ::step]
    rough = np.zeros_like(coarse)
    rough[1:-1, 1:-1] = (
        np.abs(coarse[1:-1, 1:-1] - coarse[:-2, 1:-1])
        + np.abs(coarse[1:-1, 1:-1] - coarse[2:, 1:-1])
        + np.abs(coarse[1:-1, 1:-1] - coarse[1:-1, :-2])
        + np.abs(coarse[1:-1, 1:-1] - coarse[1:-1, 2:]))
    rough[0, :] = rough[-1, :] = rough[:, 0] = rough[:, -1] = np.inf

    # And how far from the depth the site mostly sits at.
    typical = float(np.median(inside))
    off = np.abs(coarse - typical)
    scored = rough + off
    # A start needs water over it. Where the middle of a site is an island
    # and its reef flat, the typical depth is the surface, and the flattest
    # ground near it is dry land; so ground too shallow to float three metres
    # off and a metre under is not a start.
    scored[coarse > -(off_bottom + 1.0)] = np.inf
    if not np.isfinite(scored).any():
        return {}
    r, c = np.unravel_index(int(np.argmin(scored)), scored.shape)

    row = lo_r + r * step
    column = lo_c + c * step
    y = (row / max(1, rows - 1) - 0.5) * across
    x = (column / max(1, columns - 1) - 0.5) * across
    floor = float(height[min(row, rows - 1), min(column, columns - 1)])
    return {
        "beginAt": [round(float(x), 1), round(float(y), 1),
                    round(floor + off_bottom, 2)],
        "beginBecause": ("flat ground at the depth most of this site is at "
                         "(%.0f m), three metres off the bottom, inside the "
                         "middle half so a vehicle can fly any way from it. "
                         "There is no reef here to begin at: this place is "
                         "below the light, and that is what it is for."
                         % abs(floor)),
    }


def average_of(path: pathlib.Path) -> str:
    """What a texture's own colour is, so a material can divide it out.

    In linear, because that is the space the renderer multiplies in. Left in,
    a grain tints the whole seabed towards whatever beach it was photographed
    on, which is a thing nobody notices until the reef is the wrong colour and
    nobody can say why.
    """
    import numpy as np
    from PIL import Image

    grain = np.asarray(Image.open(path).convert("RGB"), dtype="float64") / 255.0
    linear = np.where(grain <= 0.04045, grain / 12.92,
                      ((grain + 0.055) / 1.055) ** 2.4)
    return ", ".join(f"{c:.4f}" for c in linear.reshape(-1, 3).mean(axis=0))


def write_usd(where: pathlib.Path, name: str, height, across: float,
              tile: float, texture: str | None, photograph: bool = False,
              ground: dict | None = None) -> dict:
    """The seabed, as a mesh, in a USD anybody can open."""
    import numpy as np

    rows, columns = height.shape
    # Spaced so the patch spans exactly what was asked for, centred on nothing:
    # the origin is the middle of the site, which is where a dive begins.
    ys = np.linspace(-across / 2, across / 2, rows, dtype="float32")
    xs = np.linspace(-across / 2, across / 2, columns, dtype="float32")
    grid_x, grid_y = np.meshgrid(xs, ys)

    points = np.stack([grid_x, grid_y, height], axis=-1).reshape(-1, 3)

    # Normals from the surface itself rather than from the triangles, so that a
    # seabed reads as a surface with slopes on it instead of a field of facets.
    dy, dx = np.gradient(height.astype("float64"),
                         across / max(1, rows - 1), across / max(1, columns - 1))
    normals = np.stack([-dx, -dy, np.ones_like(dx)], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    normals = normals.reshape(-1, 3).astype("float32")

    # Two triangles per cell, wound so the outside is up.
    top_left = (np.arange(rows - 1)[:, None] * columns + np.arange(columns - 1)[None, :])
    a = top_left.ravel()
    b, c, d = a + 1, a + columns, a + columns + 1
    faces = np.empty((a.size * 2, 3), dtype="int32")
    faces[0::2] = np.stack([a, c, b], axis=-1)
    faces[1::2] = np.stack([b, c, d], axis=-1)

    # Texture coordinates in metres over a tile, not zero-to-one over the site.
    #
    # A photograph of sand stretched across a kilometre is a kilometre-wide
    # photograph of sand: every grain is three metres across and the seabed
    # reads as a painted backdrop. Repeating it every few metres is what makes
    # it ground.
    #
    # The ground material is the exception, and it is zero-to-one over the
    # site: it has a map of this particular seabed to lay down, which only
    # goes on once, and it does its own tiling of the detail on top. Doing the
    # tiling here and the site map in the shader would work equally well until
    # somebody changed the tile size and moved the reef.
    if ground is not None:
        u = (grid_x / across + 0.5).reshape(-1).astype("float32")
        v = (grid_y / across + 0.5).reshape(-1).astype("float32")
    else:
        u = (grid_x / tile).reshape(-1).astype("float32")
        v = (grid_y / tile).reshape(-1).astype("float32")

    def numbers(values, per):
        out, row = [], []
        for i, value in enumerate(values.reshape(-1)):
            row.append(f"{value:.4g}")
            if (i + 1) % per == 0:
                out.append(", ".join(row)); row = []
        if row:
            out.append(", ".join(row))
        return "\n        ".join(out)

    def triples(values):
        return ", ".join(f"({x:.4g}, {y:.4g}, {z:.4g})" for x, y, z in values)

    def pairs(us, vs):
        return ", ".join(f"({a:.5g}, {b:.5g})" for a, b in zip(us, vs))

    lowest, highest = float(height.min()), float(height.max())
    if ground is not None:
        import numpy as np

        # A reef photographed through ten metres of water comes back flat and
        # blue-grey; tools/ground has already taken the water out of the
        # orthomosaic, so this only lifts it, and gently.
        #
        # And a place surveyed finer than the photograph is tiled over gets no
        # tiled photograph at all.
        #
        # The stock surfaces exist because a site sampled every two metres has
        # nothing between its samples, and a seabed with nothing between its
        # samples is a smooth plane at close range. A patch cut from the
        # SQUID-5 release is sampled every *centimetre* and coloured every
        # two and a half millimetres, so there is nothing missing to stand in
        # for, and tiling a photograph of a Normandy beach over it at one
        # metre does not add detail, it replaces measured detail with
        # invented detail. The first square metre rendered from that patch
        # came out as stock pebbles with the reef nowhere in it.
        #
        # Ten centimetres: finer than that and the survey is resolving what
        # the tile would have been standing in for.
        surveyed_fine = (across / max(1, height.shape[0] - 1)) < 0.10
        material = GROUND_MATERIAL % dict(
            ground, tile=tile, across=across, repeats=across / max(tile, 1e-6),
            grain=0.0 if surveyed_fine else 0.85,
            relief=0.0 if surveyed_fine else 1.0,
            lift=1.05,
            floor=float(np.median(height)),
            # The middle of the site until a dive says otherwise. A dive
            # rewrites these when it opens the place, because a parameter of
            # this shape arrives where a per-frame float3 does not.
            eye_u=0.5, eye_v=0.5, eye_z=float(np.median(height)) + 3.0)
    elif texture:
        material = SEABED_MATERIAL
    else:
        material = UNTEXTURED_MATERIAL
    if photograph and ground is None:
        # The sand correction exists because a dry beach photographed in
        # sunlight is the brightest thing in any scene. This is a reef
        # photographed through twenty metres of water, which is the opposite
        # problem, and correcting it again takes it further from the truth.
        material = material.replace("float4 inputs:scale = (1.05, 1.0, 0.92, 1)",
                                    "float4 inputs:scale = (1.25, 1.2, 1.1, 1)")
        material = material.replace('token inputs:wrapS = "repeat"',
                                    'token inputs:wrapS = "clamp"')
        material = material.replace('token inputs:wrapT = "repeat"',
                                    'token inputs:wrapT = "clamp"')
    body = f'''#usda 1.0
(
    doc = "{name}: real seafloor, from a bathymetric survey. Metres, Z up, z=0 at the water surface."
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    def Mesh "Seabed" (
        prepend apiSchemas = ["MaterialBindingAPI"]
    )
    {{
        uniform token subdivisionScheme = "none"
        int[] faceVertexCounts = [{", ".join(["3"] * len(faces))}]
        int[] faceVertexIndices = [{", ".join(str(i) for i in faces.reshape(-1))}]
        point3f[] points = [{triples(points)}]
        normal3f[] normals = [{triples(normals)}] (
            interpolation = "vertex"
        )
        texCoord2f[] primvars:st = [{pairs(u, v)}] (
            interpolation = "vertex"
        )
        float3[] extent = [({-across/2:.1f}, {-across/2:.1f}, {lowest:.2f}), ({across/2:.1f}, {across/2:.1f}, {highest:.2f})]
        rel material:binding = </World/Looks/Seabed>
    }}
{material}
}}
'''
    (where / "seabed.usda").write_text(body)

    # The same heights again, as numbers rather than as a mesh.
    #
    # A dive needs to know how deep the bottom is under the vehicle: to land on
    # it, to hold an altitude above it, to score a transect that was supposed to
    # stay two metres off it. Asking the renderer would mean a ray cast into
    # geometry that exists only when somebody is watching; asking physics would
    # mean colliders on a scene that has none. The site knows, so the site says,
    # and a batch dive with nothing drawn gets exactly the same answer as a
    # dive somebody is flying.
    height.astype("<f4").tofile(where / "seabed.f32")
    return {"lowest": lowest, "highest": highest,
            "points": int(points.shape[0]), "triangles": int(faces.shape[0]),
            "heightfield": {"rows": rows, "columns": columns,
                            "format": "little-endian float32, row major, "
                                      "south to north then west to east",
                            "file": "seabed.f32"}}


def write_place(where: pathlib.Path, name: str, depth, grid, tile: float = 10.0,
                texture: str | None = None) -> dict:
    """Write a place's seabed from a fused depth layer: seabed.f32, seabed.usda,
    and beside them the per-cell provenance (error.f32, sources.u8)."""
    import numpy as np

    where = pathlib.Path(where)
    where.mkdir(parents=True, exist_ok=True)
    height = np.asarray(depth.value, dtype="float32")
    np.asarray(depth.error, dtype="<f4").tofile(where / "error.f32")
    np.asarray(depth.source, dtype="u1").tofile(where / "sources.u8")
    written = write_usd(where, name, height, grid.across, tile, texture)
    return {"heightfield": {"rows": int(height.shape[0]), "columns": int(height.shape[1]),
                            "format": "little-endian float32, row major, south to north then west to east",
                            "file": "seabed.f32"},
            "errorFile": "error.f32", "sourcesFile": "sources.u8", "usd": written}
