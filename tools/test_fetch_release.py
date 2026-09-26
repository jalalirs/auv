"""Fetching a release, and knowing whether it worked.

`tools/reference` used to generate a shell script for this:

    [ -s NAME ] || curl -sL --retry 3 -o NAME URL

`-s` is true of any file that is not empty, so a download interrupted part way
left a file the script would never touch again. Looe Key's release came out of
it with three of eight elevation models truncated and three never fetched —
all the right kind of size in a listing, raising only on the first read,
months later.
"""

import importlib.machinery
import importlib.util
import json
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def _tool():
    loader = importlib.machinery.SourceFileLoader(
        "fetch_release", str(HERE / "fetch-release"))
    spec = importlib.util.spec_from_loader("fetch_release", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _a_release(tmp_path, files):
    (tmp_path / "files.json").write_text(json.dumps(
        [{"name": n, "url": "https://example.invalid/" + n, "bytes": b}
         for n, b in files]))
    return tmp_path


@pytest.mark.parametrize("wrote,expected", [
    (100, "complete"), (0, "missing"), (40, "part way"), (140, "too long")])
def test_it_tells_the_four_states_apart(tmp_path, wrote, expected):
    tool = _tool()
    where = _a_release(tmp_path, [("thing.bin", 100)])
    if wrote:
        (where / "thing.bin").write_bytes(b"x" * wrote)
    kind, got = tool.state_of(where, {"name": "thing.bin", "bytes": 100})
    assert kind == expected, (kind, got)
    assert got == wrote


def test_longer_than_the_manifest_is_not_complete(tmp_path):
    """A file longer than it should be is not a short copy of the right file
    to resume — it is a different file, or a resume that appended."""
    tool = _tool()
    where = _a_release(tmp_path, [("thing.bin", 100)])
    (where / "thing.bin").write_bytes(b"x" * 140)
    assert tool.state_of(where, {"name": "thing.bin", "bytes": 100})[0] == "too long"


def test_it_resumes_rather_than_skipping(tmp_path):
    """`curl -C -` is the difference between this and the script it replaces."""
    source = (HERE / "fetch-release").read_text()
    assert '"-C", "-"' in source
    # Matched on the call and not on the prose: this file *quotes* the shell
    # line it replaces, in the docstring, to explain what was wrong with it —
    # and a test that greps for the quoted text fails on the explanation. That
    # mistake has now been made twice in this repository.
    called = source[source.index("def fetch("):]
    assert "[ -s " not in called


def test_reference_no_longer_writes_the_script_that_could_not_fail(tmp_path):
    source = (HERE / "reference").read_text()
    assert "fetch-all.sh" not in source.split("# No generated shell script.")[1]
    assert "tools/fetch-release" in source


def test_a_file_that_weighs_right_and_will_not_open_is_still_wrong(tmp_path):
    """The size check catches every truncation. This catches the rest: a file
    that arrived whole and is corrupt anyway."""
    tool = _tool()
    where = _a_release(tmp_path, [("thing.tif", 4)])
    (where / "thing.tif").write_bytes(b"nope")
    # With rasterio present this is false; without it, it declines to judge.
    try:
        import rasterio  # noqa: F401
    except ImportError:
        assert tool.opens(where, "thing.tif") is True
    else:
        assert tool.opens(where, "thing.tif") is False
    # Anything that is not a raster is not its business.
    (where / "thing.txt").write_bytes(b"nope")
    assert tool.opens(where, "thing.txt") is True


def test_only_narrows_the_manifest(tmp_path):
    tool = _tool()
    where = _a_release(tmp_path, [("DEM-A.tif", 10), ("Ortho-A.tif", 10)])
    assert [f["name"] for f in tool.wanted(where, "DEM")] == ["DEM-A.tif"]
    assert len(tool.wanted(where, None)) == 2


def test_a_manifest_entry_with_no_size_is_not_fetched(tmp_path):
    """There is nothing to check it against, and a file this cannot verify is
    a file it must not claim to have got."""
    tool = _tool()
    (tmp_path / "files.json").write_text(json.dumps(
        [{"name": "a.tif", "url": "https://example.invalid/a", "bytes": None}]))
    assert tool.wanted(tmp_path, None) == []
