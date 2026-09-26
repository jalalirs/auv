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


# ── a server that will not resume ────────────────────────────────────────────
#
# USGS's does not always. Asked to continue a Looe Key elevation model from
# 0.46 GB it sent the whole body again, curl appended it, and the file went
# past its stated 0.77 GB on the way to 1.07 — at which point every further
# try resumed *that*. Four tries in a row made it worse.

class _Curl:
    """A fake curl that appends the whole body however it is asked."""

    def __init__(self, where, name, body, fails=0):
        self.here = where / name
        self.body = body
        self.fails = fails
        self.calls = 0

    def __call__(self, argv, **kw):
        self.calls += 1
        import subprocess
        if self.fails >= self.calls:
            return subprocess.CompletedProcess(argv, 56)
        with self.here.open("ab") as out:
            out.write(self.body)
        return subprocess.CompletedProcess(argv, 0)


def test_a_resume_that_overshoots_is_thrown_away_and_started_again(tmp_path):
    tool = _tool()
    where = _a_release(tmp_path, [("thing.bin", 100)])
    (where / "thing.bin").write_bytes(b"x" * 60)
    # The server ignores the range and sends all 100 bytes every time: 60 + 100
    # is too long, and resuming that would only make it longer.
    tool.subprocess.run = _Curl(where, "thing.bin", b"y" * 100)
    kind, got = tool.fetch(where, {"name": "thing.bin", "bytes": 100,
                                   "url": "https://example.invalid/thing.bin"},
                           say=lambda *a: None)
    assert (kind, got) == ("complete", 100)
    # And the spoiled part-file is kept rather than silently deleted.
    assert (where / "thing.bin.too-long").is_file()
    assert (where / "thing.bin").read_bytes() == b"y" * 100


def test_it_does_not_resume_the_same_overshoot_four_times(tmp_path):
    """The bug, precisely: the length was checked before the loop and not
    inside it, so a file that overshot on try one was resumed on tries two,
    three and four."""
    tool = _tool()
    where = _a_release(tmp_path, [("thing.bin", 100)])
    (where / "thing.bin").write_bytes(b"x" * 60)
    curl = _Curl(where, "thing.bin", b"y" * 140)     # always too long
    tool.subprocess.run = curl
    kind, got = tool.fetch(where, {"name": "thing.bin", "bytes": 100,
                                   "url": "https://example.invalid/thing.bin"},
                           say=lambda *a: None)
    assert kind == "too long"
    # Every try started from nothing, so the file never grew beyond one body.
    assert got == 140, "a try resumed an already-too-long file"
    assert curl.calls == tool.TRIES


def test_a_try_that_gains_nothing_and_succeeds_starts_again(tmp_path):
    """curl content and the file no bigger means the far end answered the
    range with nothing. Asking again the same way gets the same nothing."""
    tool = _tool()
    where = _a_release(tmp_path, [("thing.bin", 100)])
    (where / "thing.bin").write_bytes(b"x" * 60)
    tool.subprocess.run = _Curl(where, "thing.bin", b"")
    kind, got = tool.fetch(where, {"name": "thing.bin", "bytes": 100,
                                   "url": "https://example.invalid/thing.bin"},
                           say=lambda *a: None)
    assert (kind, got) == ("missing", 0)
    assert (where / "thing.bin.too-long").read_bytes() == b"x" * 60


def test_a_dropped_connection_is_still_resumed(tmp_path):
    """Ordinary. A large transfer over a long link drops, and that is what
    resuming is for — it must not be confused with a server that will not."""
    tool = _tool()
    where = _a_release(tmp_path, [("thing.bin", 100)])
    (where / "thing.bin").write_bytes(b"x" * 60)
    curl = _Curl(where, "thing.bin", b"y" * 40, fails=1)
    tool.subprocess.run = curl
    kind, got = tool.fetch(where, {"name": "thing.bin", "bytes": 100,
                                   "url": "https://example.invalid/thing.bin"},
                           say=lambda *a: None)
    assert (kind, got) == ("complete", 100)
    assert not (where / "thing.bin.too-long").exists(), "nothing was thrown away"


def test_a_size_is_shown_in_a_unit_that_shows_it(tmp_path):
    """Everything was printed in GB to two places, so a 3 kB metadata file
    and a 4 MB one both read "0.00 of 0.00 GB"."""
    tool = _tool()
    assert tool.size(3_000) == "3.00 kB"
    assert tool.size(4_200_000) == "4.20 MB"
    assert tool.size(1_290_000_000) == "1.29 GB"
    assert tool.size(512) == "512 B"
