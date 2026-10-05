#!/usr/bin/env python3
"""Render the promo's timeline (tools/promo/timeline.html) to a film.

    hardware/.venv/bin/python tools/promo/render.py                 # the whole film
    hardware/.venv/bin/python tools/promo/render.py --stills 3,15   # a few frames to look at
    hardware/.venv/bin/python tools/promo/render.py --fps 6         # a quick, rough pass

Serves ~/iocean/forum/promo (the timeline beside its assets/) and steps the
page through time in Google Chrome — Chrome rather than Playwright's own
Chromium, because the films are H.264 and Chromium will not play it — taking
one screenshot a frame after every film on screen has seeked to its frame.
Then encodes, and lays the music under it: the piano track runs 85 s, so its
middle is crossfaded back in to carry it to the end, and it fades with the
last card.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import pathlib
import shutil
import subprocess
import sys
import threading

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path.home() / "iocean" / "forum" / "promo"


class Quiet(http.server.SimpleHTTPRequestHandler):
    """Files, quietly, and in ranges: a browser seeks a film by asking for the
    bytes it needs, and a server that answers every request with the whole
    file leaves a seek waiting on everything before it."""

    def log_message(self, *args) -> None:
        pass

    def send_head(self):
        asked = self.headers.get("Range")
        path = pathlib.Path(self.translate_path(self.path))
        if not asked or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        first, _, last = asked.replace("bytes=", "").partition("-")
        start = int(first) if first else max(0, size - int(last))
        end = min(size - 1, int(last)) if (first and last) else size - 1
        handle = open(path, "rb")
        handle.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._left = end - start + 1
        return handle

    def copyfile(self, source, outputfile) -> None:
        left = getattr(self, "_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            chunk = source.read(min(1 << 20, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)
        self._left = None

    def handle(self) -> None:
        # A film the browser stops reading half way is not an error.
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        pass


def serve() -> int:
    handler = functools.partial(Quiet, directory=str(ROOT))
    server = Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def music(seconds: float, out: pathlib.Path) -> None:
    track = ROOT / "assets" / "music.mp3"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(track), "-ss", "24", "-i", str(track),
        "-filter_complex",
        f"[0:a][1:a]acrossfade=d=5:c1=tri:c2=tri,atrim=0:{seconds:.2f},"
        f"afade=t=in:st=0:d=1.5,afade=t=out:st={seconds - 5:.2f}:d=5[a]",
        "-map", "[a]", "-c:a", "aac", "-b:a", "192k", str(out)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--stills", default=None, help="seconds, comma separated: write PNGs of those moments only")
    ap.add_argument("--out", default=str(ROOT / "iocean-promo.mp4"))
    ap.add_argument("--workers", type=int, default=4, help="browsers rendering parts of it at once")
    ap.add_argument("--frames", default=None, help="a:b — render only frames a..b-1 into frames/ (a worker)")
    asked = ap.parse_args()

    shutil.copy(HERE / "timeline.html", ROOT / "timeline.html")
    port = serve()
    frames = ROOT / "frames"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.goto(f"http://127.0.0.1:{port}/timeline.html")
        page.evaluate("window.ready")
        duration = page.evaluate("window.DURATION")
        if asked.stills:
            (ROOT / "stills").mkdir(exist_ok=True)
            for s in asked.stills.split(","):
                page.evaluate(f"window.renderAt({float(s)})")
                page.screenshot(path=str(ROOT / "stills" / f"t{float(s):06.2f}.png"))
                print("still", s, flush=True)
            browser.close()
            return 0
        end = asked.end if asked.end is not None else duration
        n = int(round((end - asked.start) * asked.fps))
        if asked.frames is None and asked.workers > 1:
            browser.close()
            if frames.exists():
                shutil.rmtree(frames)
            frames.mkdir()
            share = -(-n // asked.workers)
            jobs = [subprocess.Popen([sys.executable, __file__, "--fps", f"{asked.fps:g}", "--start", f"{asked.start}",
                                      "--end", f"{end}", "--frames", f"{a}:{min(n, a + share)}"])
                    for a in range(0, n, share)]
            if any(job.wait() for job in jobs):
                raise SystemExit("a worker failed")
            return encode(asked, n)
        if asked.frames is None:
            if frames.exists():
                shutil.rmtree(frames)
            frames.mkdir()
        first, last = (int(v) for v in asked.frames.split(":")) if asked.frames else (0, n)
        for k in range(first, last):
            t = asked.start + k / asked.fps
            page.evaluate(f"window.renderAt({t:.5f})")
            page.screenshot(path=str(frames / f"f{k:05d}.jpg"), type="jpeg", quality=94)
            if k % 150 == 0:
                print(f"{t:6.1f} s of {end:.0f}", flush=True)
        browser.close()
    if asked.frames:
        return 0
    return encode(asked, n)


def encode(asked, n: int) -> int:
    frames = ROOT / "frames"
    silent = ROOT / "silent.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", f"{asked.fps:g}", "-i", str(frames / "f%05d.jpg"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(silent)], check=True)
    seconds = n / asked.fps
    sound = ROOT / "music.m4a"
    music(seconds, sound)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(sound), "-c:v", "copy", "-c:a", "copy",
                    "-shortest", "-movflags", "+faststart", asked.out], check=True)
    print("written", asked.out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
