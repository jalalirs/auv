"""Marine snow: the particles a lamp finds, and the backscatter they make.

The defining look of ROV footage, and the thing whose absence makes a frame
read as a render however good the reef in it is. A lamp beside a lens lights
the water between them, and what lights up is aggregates — marine snow, the
flocs of dead plankton, faecal pellets and mucus that drift down through every
ocean there is.

**Why they are drawn rather than fogged.** Backscatter is not a haze. It is
individual particles, in focus at arm's length and out of it further away,
moving with the water and not with the vehicle, and brightest exactly where
the lamp's cone crosses the lens's view. A fog cannot do any of that; it has
no particles to be. So these are real geometry in the water, lit by the same
lamps as the reef, and the backscatter is what happens rather than something
painted on.

**How many.** Marine snow is aggregates above about half a millimetre, and in
the open ocean's clearest water there are between five hundred and thirteen
thousand of them in every cubic metre — Pilskaln et al., "High concentrations
of marine snow and diatom algal mats in the North Pacific Subtropical Gyre",
Deep-Sea Research I, 2005. A four-metre sphere around a camera at the low end
of that is a quarter of a million particles, which is not a thing to draw.

It is also not a thing that needs drawing. Aggregates follow a power law in
size, so the number above two millimetres — the smallest that registers as
anything at all at arm's length — is about a sixtieth of the number above a
half. Sixteen a cubic metre, and a few thousand in the volume a lamp reaches.

The ones too small to draw are not missing. They are the scattering the
medium already does: the veil, whose brightness scales with exactly the same
turbidity this does. Drawing them as well would be counting the same
particles twice.
"""

from __future__ import annotations

import numpy as np

# Aggregates above half a millimetre, per cubic metre, in the clearest
# oligotrophic water. The low end of the measured range, because the high end
# was algal mats in bloom.
ABOVE_HALF_MM = 700.0

# How the count falls with size. A Junge distribution: n(d) goes as d to the
# minus four, so the number *above* a size goes as d to the minus three.
JUNGE_ABOVE = 3.0

# The smallest aggregate worth drawing. Below two millimetres a particle at
# arm's length is under a pixel and under a lamp it is a hint rather than a
# speck; those are the ones the veil is already made of.
SMALLEST_DRAWN_MM = 2.0

# And the largest. A power law has no top to it, so one draw in a few thousand
# came out at five centimetres — which at a metre from the lens is a white
# square the size of a thumbnail, and there were several in every frame.
# Marine snow does reach a centimetre or two; it does not reach five.
LARGEST_DRAWN_MM = 8.0

# And no aggregate closer to the lens than this.
#
# A particle at a hand's breadth is thirty milliradians across and fills forty
# pixels, which is not a speck of anything — and a wide-angle lens under water
# cannot focus that close anyway, so what is really there is a soft smudge
# rather than an object. This is roughly where the port is and where the lens
# gives up.
NEAREST_M = 0.5

# Which water this count belongs to: the clearest there is.
CLEAREST_GREEN_M = 40.0

# Marine snow sinks, slowly, and this is the middle of the measured range —
# tens of metres a day, which is about half a millimetre a second. Slow enough
# that a frame shows drift rather than rain, which is what the footage shows.
SINKS_M_PER_S = 0.0006


def per_cubic_metre(lengths=None) -> float:
    """How many aggregates worth drawing are in a cubic metre of this water.

    Scaled off the green attenuation length, which is this platform's measure
    of how much is suspended in a water — the same number the veil's
    brightness comes off, because it is the same particles doing both.
    """
    above = ABOVE_HALF_MM * (SMALLEST_DRAWN_MM / 0.5) ** -JUNGE_ABOVE
    if lengths is None:
        return above
    green = max(0.5, float(lengths[1]))
    return above * (CLEAREST_GREEN_M / green)


def sizes(count: int, draw) -> np.ndarray:
    """Aggregate diameters in metres, drawn from the same power law.

    Inverse transform: if the number above d goes as d to the minus three,
    then a uniform draw u maps to d = smallest x u to the minus a third. Most
    come out near the cut and a few are much larger, which is what a size
    distribution with a heavy tail looks like and what the footage shows —
    mostly grains, occasionally something with structure to it.
    """
    u = np.clip(draw.random_sample(count), 1e-6, 1.0)
    drawn = SMALLEST_DRAWN_MM * u ** (-1.0 / JUNGE_ABOVE)
    return np.minimum(drawn, LARGEST_DRAWN_MM) / 1000.0


class Snow:
    """A box of aggregates that travels with the camera.

    The box moves and the particles do not: as the camera goes forward, the
    ones that fall out of the back are wrapped round to the front, so the
    count stays put and no particle is ever created in front of the lens where
    it would be seen to appear. What the camera passes through is a continuous
    body of water rather than a cloud that follows it about.
    """

    def __init__(self, reaches_m: float = 4.0, lengths=None, seed: int = 0,
                 most: int = 6000) -> None:
        self.reaches = float(reaches_m)
        side = 2.0 * self.reaches
        volume = side ** 3
        wanted = int(round(per_cubic_metre(lengths) * volume))
        self.asked = wanted
        self.count = min(int(most), max(0, wanted))
        self.draw = np.random.RandomState(seed % (2 ** 32))
        self.at = (self.draw.random_sample((self.count, 3)) - 0.5) * side
        self.size = sizes(self.count, self.draw)
        # Which way each one is facing, once. They never turn — an aggregate
        # of mucus and dead plankton has no reason to — but they must not all
        # face the *same* way.
        #
        # Unrotated, every cube presents the same face to the camera and the
        # frame fills with identical squares. It was the squareness that read
        # as wrong, more than the size: a speck at arm's length is allowed to
        # be a few pixels, and it is not allowed to be a perfect square that
        # is the same perfect square as every other one.
        self.facing = self.draw.random_sample((self.count, 4)) * 2.0 - 1.0
        norm = np.linalg.norm(self.facing, axis=1, keepdims=True)
        self.facing /= np.maximum(norm, 1e-9)
        self.middle = np.zeros(3)
        # Settled once here, so that following a camera that has not moved
        # leaves everything exactly where it was.
        self._wrap()

    def per_cubic_metre(self) -> float:
        """What was actually drawn, which is not always what was asked for."""
        side = 2.0 * self.reaches
        return self.count / (side ** 3) if self.reaches > 0 else 0.0

    def drift(self, seconds: float, current=(0.0, 0.0, 0.0)) -> None:
        """Sink, and go where the water goes."""
        if self.count == 0:
            return
        move = np.array([float(current[0]), float(current[1]),
                         float(current[2]) - SINKS_M_PER_S]) * float(seconds)
        self.at += move[None, :]
        self._wrap()

    def follow(self, camera) -> None:
        """Keep the box on the camera without moving the water inside it."""
        self.middle = np.array([float(v) for v in camera])
        self._wrap()

    def _wrap(self) -> None:
        if self.count == 0:
            return
        side = 2.0 * self.reaches
        # Relative to the box's middle, wrapped into it, and back to the world.
        near = self.at - self.middle[None, :]
        near = (near + self.reaches) % side - self.reaches
        # And pushed out of the lens's own near field, radially, so nothing
        # sits closer than a camera can make sense of.
        far = np.linalg.norm(near, axis=1, keepdims=True)
        too_close = far[:, 0] < NEAREST_M
        if too_close.any():
            direction = near[too_close] / np.maximum(far[too_close], 1e-9)
            near[too_close] = direction * NEAREST_M
        self.at = near + self.middle[None, :]

    def where(self) -> np.ndarray:
        return self.at


# ── drawing it ───────────────────────────────────────────────────────────────
#
# One prototype and a point instancer, which is how everything numerous on
# this platform is drawn. The prototype is a cube rather than a sphere: at two
# millimetres nothing on it can be resolved, what matters is that it catches
# the lamp and has some area, and a cube is eight points where a sphere is
# hundreds. Six thousand spheres is a million triangles for a thing that is
# under a pixel across.

def draw(stage, field, at: str = "/World/Snow") -> bool:
    """Put the aggregates in the scene, as geometry the lamps can find."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    if field is None or field.count == 0:
        return False

    instancer = UsdGeom.PointInstancer.Define(stage, at)
    shapes = UsdGeom.Scope.Define(stage, f"{at}/Bodies")
    grain = UsdGeom.Mesh.Define(stage, f"{shapes.GetPath()}/Grain")
    half = 0.5
    corners = [(-half, -half, -half), (half, -half, -half),
               (half, half, -half), (-half, half, -half),
               (-half, -half, half), (half, -half, half),
               (half, half, half), (-half, half, half)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    grain.CreatePointsAttr(Vt.Vec3fArray(
        [Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in corners]))
    grain.CreateFaceVertexCountsAttr(Vt.IntArray([4] * len(faces)))
    grain.CreateFaceVertexIndicesAttr(
        Vt.IntArray([int(i) for face in faces for i in face]))
    grain.CreateExtentAttr([Gf.Vec3f(-half, -half, -half),
                            Gf.Vec3f(half, half, half)])

    # Pale and matt, because that is what a floc of dead plankton and mucus
    # is. Not emissive: the whole point is that the lamp finds it, so a
    # particle outside the lamp's cone has to be as dark as the water.
    material = UsdShade.Material.Define(stage, f"{at}/Looks/Snow")
    shader = UsdShade.Shader.Define(stage, f"{at}/Looks/Snow/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.62, 0.60, 0.55))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.9)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    material.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(grain.GetPrim()).Bind(material)

    instancer.CreatePrototypesRel().SetTargets([grain.GetPath()])
    instancer.CreateProtoIndicesAttr(Vt.IntArray([0] * field.count))
    instancer.CreateScalesAttr(Vt.Vec3fArray(
        [Gf.Vec3f(float(s), float(s), float(s)) for s in field.size]))
    instancer.CreateOrientationsAttr(Vt.QuathArray(
        [Gf.Quath(float(w), float(x), float(y), float(z))
         for w, x, y, z in field.facing]))
    move(stage, field, at)
    return True


def move(stage, field, at: str = "/World/Snow") -> None:
    """Where they are now. Called every frame the water is stirred."""
    from pxr import Gf, UsdGeom, Vt

    if field is None or field.count == 0:
        return
    instancer = UsdGeom.PointInstancer.Get(stage, at)
    if not instancer:
        return
    # Python floats at the boundary, for the same reason the fish do it: a
    # numpy float32 into Gf.Vec3f raises about a C++ signature nobody wrote.
    instancer.CreatePositionsAttr(Vt.Vec3fArray(
        [Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in field.where()]))
