"""A picture of a place and what has been laid out on it, drawn from numbers.

This is the cheap half of looking. Drawing a line on a plot and *rendering* what
a camera would see from a point in the water are two different operations with
two different costs: this one reads a heightfield and some coordinates and
answers in milliseconds, and the other one needs a GPU, a scene, a hull and a
camera with a position and an orientation. An agent placing a transect asks this
twenty times and the renderer once.

So it is deliberately not a render. Nothing here knows what anything looks like.
It knows how deep the water is and where the marks are, which is what answers
"did my line land where I meant, and does it clear the edge of the reef".

No dependencies, including no image library: a PNG is a zlib stream with four
chunks round it, and a package a customer has to `pip install` things for before
their assistant can reach the platform is a package with a step between us and
the sale.
"""

from __future__ import annotations

import struct
import zlib

# A chart is square because a place is. Big enough to see a two-metre mark on a
# three-kilometre site, small enough to hand to a model without a fuss.
SIDE = 512

# Deep to shallow. Not a rainbow: a rainbow makes a ridge out of a gradient and
# an agent reading depth off it would read a feature that is not there.
DEEP = (10, 26, 48)
SHALLOW = (86, 176, 208)
DRY = (196, 186, 160)


def _png(pixels: bytearray, width: int, height: int) -> bytes:
    """Those pixels as a PNG. RGB, no alpha, one filter byte a row."""
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        start = row * width * 3
        raw += pixels[start:start + width * 3]

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


class Chart:
    """Somewhere to draw, in site metres."""

    def __init__(self, across: float, side: int = SIDE) -> None:
        self.across = float(across)
        self.side = side
        self.pixels = bytearray(side * side * 3)

    # ── where things are ─────────────────────────────────────────────────────

    def at(self, x: float, y: float) -> tuple[int, int]:
        """Site metres to pixels. +x east is right, +y north is *up*, which on
        an image means a smaller row — the flip a chart gets wrong once."""
        half = self.across / 2.0
        column = int(round((x + half) / self.across * (self.side - 1)))
        row = int(round((half - y) / self.across * (self.side - 1)))
        return column, row

    def put(self, column: int, row: int, colour: tuple[int, int, int]) -> None:
        if 0 <= column < self.side and 0 <= row < self.side:
            at = (row * self.side + column) * 3
            self.pixels[at], self.pixels[at + 1], self.pixels[at + 2] = colour

    # ── what is drawn on it ──────────────────────────────────────────────────

    def seabed(self, depths: list[float], rows: int, columns: int) -> None:
        """Shade by depth, from the place's own heightfield.

        The heightfield is z, so it is negative under water and its *most*
        negative value is the deepest point rather than the shallowest.
        """
        wet = [z for z in depths if z is not None]
        if not wet:
            return
        lowest, highest = min(wet), max(wet)
        span = (highest - lowest) or 1.0
        for row in range(self.side):
            # The heightfield's row 0 is south, and the image's row 0 is north.
            source_row = int((1 - row / (self.side - 1)) * (rows - 1))
            for column in range(self.side):
                source_column = int(column / (self.side - 1) * (columns - 1))
                z = depths[source_row * columns + source_column]
                if z is None:
                    continue
                if z > 0:
                    self.put(column, row, DRY)
                    continue
                part = (z - lowest) / span
                self.put(column, row, (
                    int(DEEP[0] + (SHALLOW[0] - DEEP[0]) * part),
                    int(DEEP[1] + (SHALLOW[1] - DEEP[1]) * part),
                    int(DEEP[2] + (SHALLOW[2] - DEEP[2]) * part)))

    def disc(self, x: float, y: float, radius_px: int,
             colour: tuple[int, int, int]) -> None:
        column, row = self.at(x, y)
        for dy in range(-radius_px, radius_px + 1):
            for dx in range(-radius_px, radius_px + 1):
                if dx * dx + dy * dy <= radius_px * radius_px:
                    self.put(column + dx, row + dy, colour)

    def line(self, x0: float, y0: float, x1: float, y1: float,
             colour: tuple[int, int, int], width: int = 1) -> None:
        a, b = self.at(x0, y0), self.at(x1, y1)
        steps = max(abs(a[0] - b[0]), abs(a[1] - b[1]), 1)
        for step in range(steps + 1):
            part = step / steps
            column = int(round(a[0] + (b[0] - a[0]) * part))
            row = int(round(a[1] + (b[1] - a[1]) * part))
            for dy in range(-(width // 2), width // 2 + 1):
                for dx in range(-(width // 2), width // 2 + 1):
                    self.put(column + dx, row + dy, colour)

    def box(self, corners: list[dict], colour: tuple[int, int, int]) -> None:
        points = [(float(c["x"]), float(c["y"])) for c in corners
                  if c.get("x") is not None and c.get("y") is not None]
        for at in range(len(points)):
            x0, y0 = points[at]
            x1, y1 = points[(at + 1) % len(points)]
            self.line(x0, y0, x1, y1, colour)

    def rule(self) -> float:
        """A scale bar along the bottom, and the metres it stands for.

        A chart without one is a picture: an agent cannot tell a plot fifty
        metres across from one five hundred metres across, and the whole
        question it is being asked is about distances.
        """
        want = self.across / 5.0
        step = 10 ** int(len(str(int(want))) - 1)
        metres = max(step, (int(want / step)) * step)
        pixels = int(metres / self.across * (self.side - 1))
        base, left = self.side - 14, 14
        for column in range(left, left + pixels + 1):
            for row in range(base, base + 3):
                self.put(column, row, (240, 240, 240))
        for row in range(base - 4, base + 7):
            self.put(left, row, (240, 240, 240))
            self.put(left + pixels, row, (240, 240, 240))
        return metres

    def png(self) -> bytes:
        return _png(self.pixels, self.side, self.side)


# What each kind of thing is drawn as. Not a legend anybody has to memorise:
# the tool says in words what it drew, beside the picture.
MARKS = {
    "transponder": (255, 196, 66),
    "buoy": (255, 120, 90),
    "block": (170, 170, 180),
    "post": (200, 220, 120),
    "ship": (230, 230, 240),
    "line": (120, 220, 200),
    "cell": (160, 200, 255),
}
OTHER = (255, 255, 255)
