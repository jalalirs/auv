"""The camera between the water and the picture: filter, port, lens.

The renderer draws a pinhole picture: straight lines straight, the same
magnification everywhere, nothing between the lens and the sea. An underwater
camera is none of that. A GoPro's lens is a fisheye, so lines bow and the edge
of the frame holds far more of the world than the middle; behind a flat port,
water refracts every ray at the glass, so the view narrows by about a quarter
and the corners stretch; and because water bends blue a little more than
red, the edges of the frame fringe. A filter in front (red for blue water,
magenta for green) takes light out by colour before any of it.

So the picture is drawn wider than the camera sees, as a pinhole, and every
pixel of the real camera's frame looks up where its ray, traced out through
lens, port and water, lands in that pinhole picture: per colour channel,
because the port is not the same for each. The maps are worked out once per
frame size; applying them is a remap.

    IOCEAN_LENS     gopro-wide (default) | pinhole
    IOCEAN_PORT     flat (default) | dome | none
    IOCEAN_FILTER   none (default) | red | magenta

The GoPro's field of view is its published one (HERO, Wide, 16:9: 118 by 69
degrees in air), with an equidistant fisheye (image radius proportional to
angle) standing in for its calibration, which we do not have. Chosen, and
said so in what a dive reports.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np

# Refractive index of sea water at the three channels' middles (about 600,
# 540 and 460 nm), at 20 degrees and 35 per mille: Quan and Fry, Applied
# Optics 34:3477, 1995, read off their fit. The spread is what fringes the
# corners behind a flat port.
WATER_INDEX = (1.3369, 1.3399, 1.3449)


@dataclass(frozen=True)
class Lens:
    """How angle off the axis becomes radius on the sensor, in air."""
    model: str = "equidistant"
    horizontal_fov_deg: float = 118.0
    said: str = "GoPro HERO, Wide, 16:9: 118 degrees across in air, GoPro's published figure; " \
                "an equidistant fisheye standing in for its calibration"

    def angle_of(self, radius_px: np.ndarray, half_width_px: float) -> np.ndarray:
        """Angle off the axis, in air, of a ray landing `radius_px` from the centre."""
        half = math.radians(self.horizontal_fov_deg) / 2
        if self.model == "pinhole":
            return np.arctan(radius_px / half_width_px * math.tan(half))
        return radius_px / half_width_px * half          # equidistant: r = f theta


@dataclass(frozen=True)
class Port:
    """The window between the lens and the water."""
    kind: str = "flat"

    def into_water(self, angle_in_air: np.ndarray, index: float) -> np.ndarray:
        """The ray's angle off the axis once it is in the water."""
        if self.kind == "flat":
            return np.arcsin(np.clip(np.sin(angle_in_air) / index, -1.0, 1.0))
        # A dome centred on the lens: every ray crosses the glass square on,
        # so none bends. "none" is a camera with no housing at all.
        return angle_in_air


@dataclass(frozen=True)
class Filter:
    """Light taken out by colour before the lens, as a share per channel."""
    kind: str = "none"
    transmits: tuple = (1.0, 1.0, 1.0)


# Typical underwater filters: a red one for clear blue water, a magenta one
# for green. Shares per channel read off makers' transmission curves at the
# channels' middles; approximate, and they are filters, not measurements.
FILTERS = {
    "none": Filter("none", (1.0, 1.0, 1.0)),
    "red": Filter("red", (0.90, 0.45, 0.30)),
    "magenta": Filter("magenta", (0.85, 0.40, 0.75)),
}


@dataclass
class Camera:
    lens: Lens = field(default_factory=Lens)
    port: Port = field(default_factory=Port)
    filter: Filter = field(default_factory=lambda: FILTERS["none"])

    def said(self) -> dict:
        return {"lens": self.lens.model, "lensFovDeg": self.lens.horizontal_fov_deg, "lensIs": self.lens.said,
                "port": self.port.kind, "filter": self.filter.kind, "filterTransmits": list(self.filter.transmits),
                "waterIndex": list(WATER_INDEX)}


def from_environment() -> Camera:
    lens = os.environ.get("IOCEAN_LENS", "gopro-wide").strip().lower()
    port = os.environ.get("IOCEAN_PORT", "flat").strip().lower()
    filt = os.environ.get("IOCEAN_FILTER", "none").strip().lower()
    return Camera(lens=Lens(model="pinhole" if lens == "pinhole" else "equidistant"),
                  port=Port(kind=port if port in ("flat", "dome", "none") else "flat"),
                  filter=FILTERS.get(filt, FILTERS["none"]))


def _directions(camera: Camera, wide: int, tall: int):
    """For every output pixel and channel: the ray's tangents (x, y) in the water."""
    cols = np.arange(wide, dtype="float64") - (wide - 1) / 2
    rows = np.arange(tall, dtype="float64") - (tall - 1) / 2
    x, y = np.meshgrid(cols, rows)
    radius = np.hypot(x, y)
    azimuth = np.arctan2(y, x)
    in_air = camera.lens.angle_of(radius, (wide - 1) / 2)
    out = []
    for index in WATER_INDEX:
        theta = camera.port.into_water(in_air, index)
        t = np.tan(np.clip(theta, 0.0, math.radians(89.0)))
        out.append((t * np.cos(azimuth), t * np.sin(azimuth)))
    return out


def render_tangents(camera: Camera, wide: int, tall: int) -> tuple[float, float]:
    """How wide the pinhole picture must be drawn, as the tangents of its half
    angles across and up, so every ray the camera takes is inside it."""
    reach_x = reach_y = 0.0
    for tx, ty in _directions(camera, wide, tall):
        reach_x = max(reach_x, float(np.abs(tx).max()))
        reach_y = max(reach_y, float(np.abs(ty).max()))
    # Drawn 16:9 like every frame: wide enough across for both.
    across = max(reach_x, reach_y * wide / tall) * 1.01
    return across, across * tall / wide


def maps(camera: Camera, wide: int, tall: int):
    """Per channel, where in the pinhole picture each output pixel looks."""
    across, up = render_tangents(camera, wide, tall)
    out = []
    for tx, ty in _directions(camera, wide, tall):
        mx = (tx / across + 1.0) * (wide - 1) / 2
        my = (ty / up + 1.0) * (tall - 1) / 2
        out.append((mx.astype("float32"), my.astype("float32")))
    return out


def _sample(channel: np.ndarray, mx: np.ndarray, my: np.ndarray) -> np.ndarray:
    try:
        import cv2
        return cv2.remap(channel, mx, my, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    except ImportError:
        x0 = np.clip(np.floor(mx).astype(int), 0, channel.shape[1] - 2)
        y0 = np.clip(np.floor(my).astype(int), 0, channel.shape[0] - 2)
        fx, fy = np.clip(mx - x0, 0, 1), np.clip(my - y0, 0, 1)
        c = channel.astype("float32")
        top = c[y0, x0] * (1 - fx) + c[y0, x0 + 1] * fx
        bottom = c[y0 + 1, x0] * (1 - fx) + c[y0 + 1, x0 + 1] * fx
        return (top * (1 - fy) + bottom * fy).astype(channel.dtype)


def through(pixels: np.ndarray, camera: Camera, cached: dict | None = None) -> np.ndarray:
    """A pinhole frame (sRGB, H x W x 3, uint8) as this camera takes it."""
    tall, wide = pixels.shape[:2]
    key = (wide, tall, camera.lens, camera.port)
    if cached is not None and key in cached:
        m = cached[key]
    else:
        m = maps(camera, wide, tall)
        if cached is not None:
            cached[key] = m
    frame = pixels[..., :3]
    if camera.filter.kind != "none":
        # In light, not in the encoding, and brightness given back as the
        # camera's own exposure would: a filter changes colour, and an
        # auto-exposing camera opens up for the light it takes.
        from metering import balanced
        t = np.asarray(camera.filter.transmits, dtype="float64")
        frame = balanced(frame, tuple(t / (np.array([0.2126, 0.7152, 0.0722]) @ t)))
    out = np.stack([_sample(np.ascontiguousarray(frame[..., c]), *m[c]) for c in range(3)], axis=-1)
    return out
