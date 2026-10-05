#!/usr/bin/env python3
"""Film the client's screens for the promo, frame by frame, with a cursor.

    hardware/.venv/bin/python tools/promo/capture.py [shot ...]

Drives apps/client's promo harness (promo.html, the real screens over the Red
Sea place) in headless Chromium at 1920x1080 and keeps every frame as a JPEG,
then encodes each shot to an MP4 in ~/iocean/forum/promo/shots. Every frame is
a screenshot taken after the step that makes it, so the motion is as smooth as
the steps are small and nothing depends on how fast this machine is. The
cursor is drawn into the page: the real one is not in a headless screenshot.
"""

from __future__ import annotations

import math
import pathlib
import shutil
import subprocess
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173/promo.html"
OUT = pathlib.Path.home() / "iocean" / "forum" / "promo" / "shots"
FPS = 30
CSS_W, CSS_H, SCALE = 1600, 900, 1.2

CURSOR = """
(() => {
  if (document.getElementById('promo-cursor')) return;
  const c = document.createElement('div');
  c.id = 'promo-cursor';
  c.style.cssText = 'position:fixed;left:0;top:0;width:26px;height:26px;z-index:99999;pointer-events:none;' +
    'transform:translate(-4px,-2px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))';
  c.innerHTML = '<svg width="26" height="26" viewBox="0 0 26 26"><path d="M4 2 L4 21 L9 16.5 L12.5 24 L15.5 22.7 L12 15.3 L19 15.3 Z" ' +
    'fill="#ffffff" stroke="#0d1b24" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  const r = document.createElement('div');
  r.id = 'promo-ripple';
  r.style.cssText = 'position:fixed;left:0;top:0;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;' +
    'border:2px solid rgba(255,255,255,.9);background:rgba(255,255,255,.18);z-index:99998;pointer-events:none;opacity:0';
  document.body.append(r, c);
  window.__cursor = (x, y) => { c.style.left = x + 'px'; c.style.top = y + 'px'; };
  window.__ripple = (x, y, k) => { r.style.left = x + 'px'; r.style.top = y + 'px';
    r.style.opacity = String(Math.max(0, 1 - k)); r.style.transform = 'scale(' + (0.4 + 0.9 * k) + ')'; };
})();
"""


def ease(k: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, k)))


class Shot:
    def __init__(self, page, name: str):
        self.page, self.name = page, name
        self.dir = OUT / name
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir.mkdir(parents=True)
        self.n = 0
        self.at = (CSS_W * 0.62, CSS_H * 0.55)

    def frame(self) -> None:
        self.page.screenshot(path=str(self.dir / f"f{self.n:05d}.jpg"), type="jpeg", quality=93)
        self.n += 1

    def cursor(self) -> None:
        self.page.evaluate(CURSOR)
        self.page.evaluate("([x, y]) => window.__cursor(x, y)", list(self.at))

    def hold(self, seconds: float) -> None:
        for _ in range(int(round(seconds * FPS))):
            self.frame()

    def where(self, target) -> tuple[float, float]:
        if isinstance(target, tuple):
            return target
        box = self.page.locator(target).first.bounding_box()
        return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    def move(self, target, seconds: float = 0.8) -> None:
        x0, y0 = self.at
        x1, y1 = self.where(target)
        steps = max(1, int(round(seconds * FPS)))
        for k in range(1, steps + 1):
            e = ease(k / steps)
            # A slight arc, the way a hand moves a mouse.
            bow = math.sin(math.pi * k / steps) * 0.06 * math.hypot(x1 - x0, y1 - y0)
            x, y = x0 + (x1 - x0) * e, y0 + (y1 - y0) * e - bow
            self.page.mouse.move(x, y)
            self.page.evaluate("([x, y]) => window.__cursor(x, y)", [x, y])
            self.frame()
        self.at = (x1, y1)

    def click(self, target=None, double: bool = False, seconds: float = 0.5) -> None:
        if target is not None:
            self.move(target)
        x, y = self.at
        if double:
            self.page.mouse.dblclick(x, y)
        else:
            self.page.mouse.click(x, y)
        steps = int(round(seconds * FPS))
        for k in range(steps):
            self.page.evaluate("([x, y, k]) => window.__ripple(x, y, k)", [x, y, k / steps])
            self.frame()
        self.page.evaluate("([x, y]) => window.__ripple(x, y, 1)", [x, y])

    def select(self, target, value: str) -> None:
        self.move(target)
        self.page.locator(target).first.select_option(value)
        self.hold(0.6)

    def scroll(self, target, dy: float, seconds: float = 0.8) -> None:
        steps = max(1, int(round(seconds * FPS)))
        for k in range(steps):
            self.page.locator(target).first.evaluate("(el, d) => el.scrollBy(0, d)", dy / steps)
            self.frame()

    def js(self, code: str, arg=None) -> None:
        self.page.evaluate(code, arg)

    def encode(self) -> pathlib.Path:
        out = OUT / f"{self.name}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(self.dir / "f%05d.jpg"),
                        "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", str(out)], check=True)
        print(f"{self.name}: {self.n} frames -> {out}", flush=True)
        return out


def open_page(browser, query: str):
    page = browser.new_page(viewport={"width": CSS_W, "height": CSS_H}, device_scale_factor=SCALE)
    page.goto(f"{BASE}?{query}")
    page.wait_for_timeout(2500)
    return page


# ── the shots ────────────────────────────────────────────────────────────────

def layout(browser) -> None:
    """A pipeline drawn onto the Red Sea place, from the beach out to the slope."""
    page = open_page(browser, "page=layout&layout=proposed")
    s = Shot(page, "layout")
    s.cursor()
    s.click("button:has-text('all')")
    s.hold(0.6)
    s.click("text=Pipeline")
    s.hold(0.4)
    chart = page.locator("canvas").first.bounding_box()
    at = lambda fx, fy: (chart["x"] + chart["width"] * fx, chart["y"] + chart["height"] * fy)
    route = [at(0.47, 0.54), at(0.58, 0.52), at(0.70, 0.50), at(0.86, 0.49)]
    s.move(route[0], 1.0)
    s.click()
    for point in route[1:-1]:
        s.move(point, 0.7)
        s.click()
    s.move(route[-1], 0.7)
    s.click(double=True)
    s.hold(1.5)
    s.move(at(0.62, 0.3), 0.8)
    s.hold(1.0)
    s.encode()


def designer(browser) -> None:
    """The inspection planned: the line, the vehicle, and what it will take."""
    page = open_page(browser, "page=designer")
    s = Shot(page, "designer")
    s.cursor()
    s.hold(0.8)
    s.move("text=Follow a pipeline", 1.0)
    s.click()
    s.hold(1.0)
    s.move("select", 0.9)
    s.hold(0.4)
    s.page.locator("select").first.select_option(label="Boxfish Luna")
    s.hold(1.6)
    s.page.locator("select").first.select_option(label="REMUS 100")
    s.hold(1.4)
    s.click("button:has-text('Fly it')")
    s.hold(0.6)
    s.encode()


def fly(browser) -> None:
    """Everything that could go differently on the day: four currents, one dive each."""
    page = open_page(browser, "page=fly")
    s = Shot(page, "fly")
    s.cursor()
    s.hold(0.6)
    s.select("select >> nth=2", "wary")
    # Still is what the plan says; three more currents make it a doubt.
    for label in ("A gentle set", "Half a knot", "One knot"):
        s.click(f"button:has-text('{label}')", seconds=0.35)
    s.hold(0.5)
    s.scroll("main", 1400, 1.4)
    s.hold(0.3)
    s.select("select >> nth=-1", "1")
    s.hold(0.4)
    s.click("button:has-text('Sweep it')")
    s.hold(0.8)
    s.encode()


def results(browser) -> None:
    """The four dives queued on the GPU hosts, flown, and back."""
    page = open_page(browser, "page=results")
    s = Shot(page, "results")
    s.cursor()
    names = ["still", "gentle", "half a knot", "one knot"]
    for k, name in enumerate(names):
        s.js("([id, name]) => window.promo.run(id, {state: 'queued', requestedAt: new Date().toISOString()}, name)",
             [f"run_c{k}", f"Inspect the landfall · REMUS 100 · {name}"])
        s.hold(0.25)
    s.hold(0.8)
    for k in range(4):
        s.js("(id) => window.promo.run(id, {state: 'running'})", f"run_c{k}")
        s.hold(0.35)
    s.hold(1.0)
    import json
    outcomes = json.loads((OUT.parent / "currents.json").read_text()) if (OUT.parent / "currents.json").exists() else {}
    for k, name in enumerate(names):
        task = outcomes.get(name)
        s.js("([id, task]) => window.promo.run(id, task ? {state: 'succeeded', outcome: {task}} : {state: 'succeeded'})",
             [f"run_c{k}", task])
        s.hold(0.5)
    s.hold(2.0)
    s.encode()


SHOTS = {"layout": layout, "designer": designer, "fly": fly, "results": results}


def main(names: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in names or list(SHOTS):
            SHOTS[name](browser)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
