"""Stills of the moulded form from look.html, one PNG per view.

    hardware/.venv/bin/python hardware/titan/stills.py [titan|mini] [views…]   → hardware/out/<which>/look-<view>.png
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

WHICH = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("titan", "mini") else "titan"
OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / WHICH
VIEWS = [v for v in sys.argv[1:] if v != WHICH] or ["iso", "quarter", "front", "side", "top", "rear"]


def main() -> int:
    page_url = (OUT / "look.html").as_uri()
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = b.new_page(viewport={"width": 1400, "height": 875}, device_scale_factor=1)
        for v in VIEWS:
            page.goto(f"{page_url}?view={v}&fast", timeout=180000)
            page.wait_for_timeout(4000)
            page.evaluate("document.getElementById('views').style.display='none'")
            page.screenshot(path=str(OUT / f"look-{v}.png"), timeout=300000)
            print(OUT / f"look-{v}.png")
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
