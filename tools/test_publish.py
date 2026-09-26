"""Publishing a vehicle, and the list that must not drift.

The control plane keeps a *summary* of how a vehicle moves — what it has to
reason about before a dive — and refuses any field it does not know. A
vehicle package declares far more than that, so `tools/publish` sends a
subset. A subset that drifted from the struct would refuse every new
vehicle with a message about a field nobody had heard of, which is exactly
how this was found.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLISH = ROOT / "tools" / "publish"
CATALOG = ROOT / "services" / "control-plane" / "internal" / "catalog" / "catalog.go"


def what_the_platform_keeps():
    """The json tags of the Go struct the endpoint decodes into."""
    source = CATALOG.read_text()
    start = source.index("type Dynamics struct {")
    body = source[start:source.index("\n}", start)]
    tags = re.findall(r'`json:"([a-zA-Z0-9]+)"`', body)
    return [one for one in tags if one != "versionId"]


def what_publish_sends():
    source = PUBLISH.read_text()
    found = re.search(r"KEPT = \((.*?)\)", source, re.S)
    assert found, "tools/publish no longer names what it sends"
    return re.findall(r"'([a-zA-Z0-9]+)'", found.group(1))


def test_publish_sends_exactly_what_the_platform_keeps():
    assert what_publish_sends() == what_the_platform_keeps()


def test_the_list_is_not_empty_in_either_place():
    """A regex that matched nothing would make the test above pass by
    comparing two empty lists, which is the way this kind of check fails."""
    assert len(what_the_platform_keeps()) >= 8
    assert len(what_publish_sends()) >= 8


@pytest.mark.parametrize("slug", ["bluerov2", "bluerov2-heavy", "remus-100", "seaglider"])
def test_every_hull_in_the_catalogue_can_be_published(slug):
    """Every field the platform keeps is present in the package, and the
    package's extra ones are the ones it is right to leave behind."""
    said = json.loads((ROOT / "catalog" / "vehicles" / slug / "dynamics.json").read_text())
    for key in what_the_platform_keeps():
        assert key in said, f"{slug} declares no {key}"
