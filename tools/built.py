"""What built this place, recorded so it can be built again.

Five places, each made by a hand-typed command with a dozen arguments, and no
record anywhere of what those arguments were. Every rebuild was reconstructed
from memory or from a shell history, and a place rebuilt with one argument
different is a place whose record no longer describes it.

So each tool that writes `site.json` writes down how it was called. `tools/
rebuild` replays them in order.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys


def carry_the_record_forward(site: dict, was: pathlib.Path) -> dict:
    """Keep what the old site.json knew about how this place was built.

    `make-site` writes a whole new record from nothing, which is right for
    everything in it except this one field: the place was also surveyed and
    had its water aimed, by tools that run afterwards and write themselves
    down. Overwriting the record with only `make-site` in it leaves a place
    that `tools/rebuild` will rebuild as bare ground — no reef, no dive start,
    no medium — and it will say it rebuilt it from its own record while doing
    so, because as far as the record goes it did.

    That is exactly what happened to Looe Key: eighty-three thousand surveyed
    colonies, rebuilt to nought, by a tool reporting success.
    """
    if not was.is_file():
        return site
    try:
        before = json.loads(was.read_text()).get("builtBy") or {}
    except (OSError, ValueError):
        return site
    keep = site.setdefault("builtBy", {})
    for tool, call in before.items():
        keep.setdefault(tool, call)
    return site


def record_call(site: dict, tool: str) -> dict:
    """Put this invocation into the place's own record, under `builtBy`."""
    site.setdefault("builtBy", {})[tool] = {
        "argv": [str(one) for one in sys.argv[1:]],
        "cwd": str(pathlib.Path.cwd()),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
    }
    return site
