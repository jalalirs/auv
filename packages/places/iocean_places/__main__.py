"""python -m iocean_places build <recipe.json> --into <place dir>"""

from __future__ import annotations

import argparse
import json
import sys

from .build import build
from .recipe import Recipe


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="iocean_places", description="build a place from whatever data there is")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build a place from its recipe")
    b.add_argument("recipe")
    b.add_argument("--into", required=True)
    b.add_argument("--cache", default=None)
    asked = ap.parse_args(argv)
    site = build(Recipe.read(asked.recipe), asked.into, asked.cache)
    print(json.dumps({k: site[k] for k in ("name", "deepestM", "shallowestM", "beginAt")}))
    print(json.dumps(site["from"]["depth"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
