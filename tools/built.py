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
import pathlib
import sys


def record_call(site: dict, tool: str) -> dict:
    """Put this invocation into the place's own record, under `builtBy`."""
    site.setdefault("builtBy", {})[tool] = {
        "argv": [str(one) for one in sys.argv[1:]],
        "cwd": str(pathlib.Path.cwd()),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
    }
    return site
