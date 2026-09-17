"""Colonies somebody scanned.

Every coral on this platform was a procedural shape: correct in size and place,
and not in form. Take the water away and they read as painted stones, which is
what they were. There has been a real one in the repository since September,
unused.
"""

import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import scanned  # noqa: E402

REFERENCE = pathlib.Path.home() / "coral-city" / "reference" / "looe-key"

# Found the way the code finds it, not by a filename spelled out here. The
# specimen was called `usnm_58_orbicella_coronata.glb` until tools/scans
# started naming files from the museum's own title, and six tests quietly
# skipped rather than failing, which is the worse of the two.
_MASSIVE = scanned.found_in(REFERENCE).get("massive") or []
SPECIMEN = _MASSIVE[0] if _MASSIVE else REFERENCE / "assets" / "nothing.glb"
have_it = pytest.mark.skipif(not SPECIMEN.exists(),
                             reason="no Smithsonian scan is fetched here; "
                                    "tools/scans fetches them")


@have_it
def test_a_scan_loads_as_geometry():
    points, faces = scanned.read_glb(SPECIMEN)
    assert len(points) > 10_000, "a scan is not a handful of vertices"
    assert faces.shape[1] == 3
    assert faces.max() < len(points), "an index past the end of the points"


@have_it
def test_it_is_simplified_without_falling_apart():
    """A hundred thousand triangles is a lot for one colony seen from three
    metres, and a reef is sixty prototypes."""
    points, faces = scanned.read_glb(SPECIMEN)
    fewer_points, fewer = scanned.simplify(points, faces, 6000)
    # Clustering lands near a budget rather than on it; near is what a budget
    # wants. Under it, and not under it by half.
    assert 3000 <= len(fewer) <= 6000, len(fewer)
    assert fewer.max() < len(fewer_points)
    # And it is still the whole object, not a slab of it. Every axis keeps its
    # span, which is the thing the first simplifier got wrong: it kept the
    # largest triangles, and the largest triangles are the flat ones.
    assert np.all(np.ptp(fewer_points, axis=0) > 0.95 * np.ptp(points, axis=0))


@have_it
def test_a_colony_stands_the_right_way_up_and_the_right_size():
    """Museum scans arrive in whatever units and orientation the scanner had.
    A reef asks for a size, and the size it asks for is what the survey said
    rather than what the specimen happened to be. The size is of the colony,
    which is the part above the ground."""
    points, _ = scanned.as_a_colony(SPECIMEN, 0.8)
    showing = points[points[:, 2] >= 0.0]
    assert abs(float(np.ptp(showing[:, :2], axis=0).max()) - 0.8) < 0.01
    assert float(points[:, 2].max()) > 0.0, "it should stand up from the ground"


@have_it
def test_the_museum_pedestal_goes_under_the_seabed():
    """This specimen is a third plinth by height: a skirt of constant radius
    up to a sharp step, and the dome above it. Sat on its lowest point it
    renders as a coral on a plinth, which is not a thing on a reef."""
    points, _ = scanned.as_a_colony(SPECIMEN, 1.0)
    buried = -float(points[:, 2].min())
    tall = float(points[:, 2].max())
    assert buried > 0.1 * tall, "the base should be under the ground"
    assert buried < tall, "and most of the colony should be above it"
    # What is left standing is a dome, not a cylinder: it narrows towards the
    # top. A mounding coral is a broad dome, so this asks about the crown and
    # not the shoulder, which on this specimen is still nearly full width.
    showing = points[points[:, 2] >= 0.0]
    crown = showing[:, 2] > 0.8 * tall
    near = np.hypot(showing[:, 0], showing[:, 1])
    assert near[crown].max() < 0.8 * near.max()
    # And no flange: the widest part is not a lip sitting on the seabed.
    at_the_foot = showing[:, 2] < 0.1 * tall
    assert near[at_the_foot].max() < 1.05 * near[~at_the_foot & ~crown].max()


@have_it
def test_it_is_centred_on_what_shows():
    """So that where a reef puts a colony is where the colony is. Centred on
    the part above the seabed, because a wider buried base would otherwise
    pull the visible colony off the mark."""
    points, _ = scanned.as_a_colony(SPECIMEN, 1.0)
    showing = points[points[:, 2] >= 0.0]
    assert abs(float(showing[:, 0].mean())) < 0.02
    assert abs(float(showing[:, 1].mean())) < 0.02


@have_it
def test_a_scan_is_named_by_what_it_is():
    """A specimen nobody can identify is a specimen nobody should be placing on
    a reef as though they could."""
    found = scanned.found_in(REFERENCE)
    assert SPECIMEN in found["massive"], found


@have_it
def test_a_growth_form_can_have_several_specimens():
    """Three different Acropora on a reef, not three copies of one. Three
    copies of one museum piece is worse than a blob, because it reads as
    variation."""
    found = scanned.found_in(REFERENCE)
    assert any(len(paths) > 1 for paths in found.values()), found
    for form, paths in found.items():
        assert len(set(paths)) == len(paths), f"{form} lists a specimen twice"


def test_a_place_with_no_corpus_gets_no_scans():
    assert scanned.found_in(pathlib.Path("/nowhere")) == {}
