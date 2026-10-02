"""Putting the fish into a stage, without a renderer to put them in.

There is no `pxr` on a development machine, so nothing exercised the code that
writes the shoal into USD and a whole afternoon went on a reef that silently
had no fish in it. What it turned out to be was one line handing the binding
three `numpy.float32` where it wanted three Python floats, which raises "did
not match C++ signature" — a sentence about a type nobody wrote down.

So: a stand-in for the parts of `pxr` this uses, strict about exactly that.
It is not a model of USD and it does not check that the scene is right. It
checks the one thing a machine with no renderer on it can check, which is that
the boundary between the arithmetic and the renderer is crossed in the types
the renderer asked for.
"""

import sys
import types

import numpy as np
import pytest

from coral import life

FLAT = -9.0


class StrictlyFloats:
    """Like the real binding: Python floats or nothing."""

    def __init__(self, *values):
        for one in values:
            if isinstance(one, (np.generic, np.ndarray)):
                raise TypeError(
                    f"did not match C++ signature: got {type(one).__name__}")
            if not isinstance(one, float):
                raise TypeError(f"did not match C++ signature: {one!r}")
        self.values = values


class Anything:
    """Everything else, which this is not trying to model."""

    def __init__(self, *_a, **_k):
        self.path = "/stub"

    def __getattr__(self, _name):
        return Anything()

    def __call__(self, *_a, **_k):
        return Anything()

    def GetPath(self):
        return "/stub"

    def GetPrim(self):
        return Anything()


def _fake_pxr():
    gf = types.SimpleNamespace(Vec3f=StrictlyFloats, Quath=StrictlyFloats,
                               Vec3h=StrictlyFloats)
    holds = types.ModuleType("pxr")
    holds.Gf = gf
    holds.Sdf = types.SimpleNamespace(ValueTypeNames=Anything())
    holds.Vt = types.SimpleNamespace(
        Vec3fArray=list, IntArray=list, QuathArray=list, FloatArray=list)
    holds.UsdGeom = types.SimpleNamespace(
        PointInstancer=Anything(), Scope=Anything(), Mesh=Anything(),
        PrimvarsAPI=Anything(), Tokens=Anything(), BasisCurves=Anything())
    holds.UsdShade = types.SimpleNamespace(
        Material=Anything(), Shader=Anything(), MaterialBindingAPI=Anything())
    return holds


@pytest.fixture
def without_a_renderer(monkeypatch):
    monkeypatch.setitem(sys.modules, "pxr", _fake_pxr())


def a_reef(many=120, seed=1):
    counted = [
        {"taxon": "Sparisoma viride", "group": "Actinopterygii", "observations": 80},
        {"taxon": "Abudefduf saxatilis", "group": "Actinopterygii", "observations": 60},
        {"taxon": "Caranx ruber", "group": "Actinopterygii", "observations": 40},
        {"taxon": "Thalassoma bifasciatum", "group": "Actinopterygii", "observations": 30},
    ]
    return life.Shoal(life.as_observed(counted, many), lambda x, y: FLAT,
                      600.0, seed=seed)


def test_the_fish_are_written_in_the_types_the_renderer_asked_for(without_a_renderer):
    """The bug this exists for: `Gf.Vec3f(*row)` over a numpy array."""
    reef = a_reef()
    life.put_them_in(Anything(), reef)


def test_moving_them_is_written_in_those_types_too(without_a_renderer):
    reef = a_reef()
    for _ in range(5):
        reef.step(0.1)
    life.move_them(Anything(), reef)


def test_an_empty_reef_writes_nothing(without_a_renderer):
    empty = life.Shoal({}, lambda x, y: FLAT, 600.0)
    life.put_them_in(Anything(), empty)
    life.move_them(Anything(), empty)


def test_the_stand_in_would_have_caught_it():
    """A test whose stand-in is more forgiving than the thing it stands in for
    is a test that passes when the real one fails, which is how this got
    through in the first place."""
    with pytest.raises(TypeError, match="C\\+\\+ signature"):
        StrictlyFloats(*np.zeros(3, dtype="float32"))
    with pytest.raises(TypeError, match="C\\+\\+ signature"):
        StrictlyFloats(np.float32(1.0), 2.0, 3.0)
    StrictlyFloats(1.0, 2.0, 3.0)


def a_school_with_minds():
    import fishmind

    habitat = fishmind.Habitat(lambda x, y: -0.93, (0.0, 0.0), 2.0, 0.0, box=(0.92, 0.46), scale=0.14)
    return fishmind.School({"amphiprion_ocellaris": 2, "chelmon_rostratus": 2, "chromis_viridis": 6},
                           habitat, seed=1, tank=True)


def test_fish_with_minds_are_drawn_by_species_in_the_types_asked_for(without_a_renderer):
    """Each species its own shape and its own paint, each fish its own size."""
    school = a_school_with_minds()
    school.step(0.05, light=(11.0, 1.0))
    life.put_them_in(Anything(), school)
    life.move_them(Anything(), school)


def test_the_tether_is_drawn_in_the_types_the_renderer_asked_for(without_a_renderer):
    """draw/tether.py, from a cable's nodes, through the same strict stand-in."""
    from draw.tether import TetherDrawing
    from systems.place import Place
    from systems.tether import Umbilical

    cable = Umbilical({"lengthM": 1.8, "diameterM": 0.005, "weightNPerM": -0.004})
    cable.start([0.8, -0.4, -0.03], [0.0, 0.0, -0.4])

    class V:
        position = np.array([0.0, 0.0, -0.4])
        rotation = np.eye(3)

    said = []
    drawing = TetherDrawing([0.0, 0.0, 0.08], 0.05, 1.0, lambda kind, **d: said.append(kind))
    drawing.draw(Anything(), cable, V(), Place(), lambda p: tuple(float(c) for c in p))
    assert "tether_not_drawn" not in said
