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
    IOCEAN_SENSOR   gopro (default) | none

After the optics, the sensor: the light becomes electrons on a small 4K
sensor (a GoPro's is 1/2.3 inch, 1.55 micrometre pixels), with the shot noise
light has and the read noise electronics add, at the ISO the camera's own
auto-exposure chose, each output pixel the average of the sensor pixels it
was scaled down from; then quantised as the sensor's converter does, and the
colour noise smoothed as a camera's processing smooths it. The sensor's
figures are typical of its class (Clark, "Digital camera sensor performance
summary", clarkvision.com; Foi et al., IEEE TIP 17:1737, 2008, for the
model), chosen, not measured on this camera.

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


@dataclass(frozen=True)
class Sensor:
    """Light into electrons into numbers."""
    kind: str = "gopro"
    full_well_e: float = 4500.0          # electrons a pixel holds at base ISO
    read_noise_e: float = 2.5            # electrons, per read
    base_iso: float = 100.0
    bits: int = 12
    sensor_px: tuple = (3840, 2160)      # what the output is scaled down from
    prnu: float = 0.01                   # pixel to pixel gain, as a share
    chroma_blur_px: float = 1.5          # the camera's colour noise reduction
    vignette: float = 0.3                # how much darker the corners, after the camera's own correction

    def electrons_at(self, iso: float, wide: int, tall: int) -> float:
        """Electrons for a full-scale output pixel at this ISO."""
        binned = (self.sensor_px[0] * self.sensor_px[1]) / max(wide * tall, 1)
        return self.full_well_e * max(binned, 1.0) * self.base_iso / max(iso, self.base_iso)


SENSORS = {
    "gopro": Sensor(),
    # Blue Robotics' Low-Light HD USB camera, the BlueROV2's own: a Sony
    # IMX322, 1/2.9 inch, 1920 x 1080, 2.8 micrometre pixels, so about four
    # times the light a GoPro pixel catches. Typical of that sensor; chosen.
    "imx322": Sensor(kind="imx322", full_well_e=9000.0, read_noise_e=2.5, sensor_px=(1920, 1080),
                     vignette=0.2),
    "none": Sensor(kind="none"),
}


@dataclass
class Camera:
    lens: Lens = field(default_factory=Lens)
    port: Port = field(default_factory=Port)
    filter: Filter = field(default_factory=lambda: FILTERS["none"])
    sensor: Sensor = field(default_factory=lambda: SENSORS["gopro"])
    # A number pins the exposure there, as a camera set by hand; None is the
    # camera's own auto-exposure.
    iso: float | None = None
    told_by: tuple = ()
    # Blur from the camera moving while the shutter is open; the distance the
    # moving part assumes the scene is at, since the capture has no depth.
    motion_blur: bool = True
    blur_depth_m: float = 3.0

    def said(self) -> dict:
        return {"lens": self.lens.model, "lensFovDeg": self.lens.horizontal_fov_deg, "lensIs": self.lens.said,
                "port": self.port.kind, "filter": self.filter.kind, "filterTransmits": list(self.filter.transmits),
                "waterIndex": list(WATER_INDEX), "sensor": self.sensor.kind,
                "sensorIs": None if self.sensor.kind == "none" else
                {"fullWellE": self.sensor.full_well_e, "readNoiseE": self.sensor.read_noise_e,
                 "bits": self.sensor.bits, "pixels": list(self.sensor.sensor_px),
                 "is": "typical of its class; chosen, not measured on this camera"},
                "iso": self.iso if self.iso is not None else "auto", "toldBy": list(self.told_by),
                "motionBlur": self.motion_blur, "blurDepthM": self.blur_depth_m,
                "blurDepthIs": "assumed: the capture has no depth, so the blur from moving (not from turning) "
                               "takes the scene to be this far away"}


# What a camera is when nothing says otherwise: a GoPro behind a flat port.
DEFAULTS = {"lens": "gopro-wide", "port": "flat", "filter": "none", "sensor": "gopro", "iso": "auto",
            "motionBlur": True, "blurDepthM": 3.0}
LENSES = {"gopro-wide": ("equidistant", 118.0), "pinhole": ("pinhole", 47.17)}


def settings_from(vehicle: dict | None = None, dive: dict | None = None, environment=None) -> tuple[dict, tuple]:
    """The camera's settings and who set each layer, the dive over the
    vehicle over the environment over the defaults."""
    env = os.environ if environment is None else environment
    from_env = {key: env[name].strip().lower() for key, name in
                (("lens", "IOCEAN_LENS"), ("port", "IOCEAN_PORT"), ("filter", "IOCEAN_FILTER"),
                 ("sensor", "IOCEAN_SENSOR"), ("iso", "IOCEAN_CAMERA_ISO")) if env.get(name, "").strip()}
    merged, told = dict(DEFAULTS), []
    for name, layer in (("environment", from_env), ("vehicle", vehicle or {}), ("dive", dive or {})):
        if layer:
            merged.update({k: v for k, v in layer.items() if k in DEFAULTS or k == "lensFovDeg"})
            told.append(name)
    return merged, tuple(told)


def camera_from(settings: dict, told_by: tuple = ()) -> Camera:
    lens_name = str(settings.get("lens", "gopro-wide")).lower()
    model, fov = LENSES.get(lens_name, LENSES["gopro-wide"])
    fov = float(settings.get("lensFovDeg", fov))
    said = (Lens.said if lens_name == "gopro-wide" and "lensFovDeg" not in settings
            else f"{model}, {fov:g} degrees across in air")
    port = str(settings.get("port", "flat")).lower()
    iso = settings.get("iso", "auto")
    try:
        iso = None if str(iso).lower() == "auto" else float(iso)
    except ValueError:
        iso = None
    return Camera(lens=Lens(model=model, horizontal_fov_deg=fov, said=said),
                  port=Port(kind=port if port in ("flat", "dome", "none") else "flat"),
                  filter=FILTERS.get(str(settings.get("filter", "none")).lower(), FILTERS["none"]),
                  sensor=SENSORS.get(str(settings.get("sensor", "gopro")).lower(), SENSORS["gopro"]),
                  iso=iso, told_by=told_by,
                  motion_blur=str(settings.get("motionBlur", True)).lower() not in ("false", "0", "no", "off"),
                  blur_depth_m=float(settings.get("blurDepthM", 3.0)))


def for_dive(brief: dict | None = None, vehicle_dir=None) -> Camera:
    """The camera a dive carries: its own `objective.camera` if it says, else
    the vehicle's (`camera` in its dynamics.json), else the environment's."""
    import json
    import pathlib

    vehicle = None
    if vehicle_dir is not None:
        try:
            vehicle = json.loads((pathlib.Path(vehicle_dir) / "dynamics.json").read_text()).get("camera")
        except Exception:
            vehicle = None
    dive = ((brief or {}).get("objective") or {}).get("camera")
    return camera_from(*settings_from(vehicle if isinstance(vehicle, dict) else None,
                                      dive if isinstance(dive, dict) else None))


def from_environment() -> Camera:
    return camera_from(*settings_from())


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


def _linear(encoded: np.ndarray) -> np.ndarray:
    v = encoded.astype("float32") / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _encoded(light: np.ndarray) -> np.ndarray:
    v = np.clip(light, 0.0, 1.0)
    v = np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)
    return (v * 255.0 + 0.5).astype("uint8")


def _blur(channel: np.ndarray, sigma: float) -> np.ndarray:
    try:
        import cv2
        return cv2.GaussianBlur(channel, (0, 0), sigma)
    except ImportError:
        from scipy import ndimage
        return ndimage.gaussian_filter(channel, sigma)


def motion(wide: int, tall: int, across: float, moving, turning, exposure_s: float, depth_m: float):
    """How far, in pixels of the pinhole picture, each point travels while the
    shutter is open: the motion field of a camera translating at `moving` and
    turning at `turning` (both in the camera's own axes, x right, y down, z
    ahead), the scene `depth_m` away (Longuet-Higgins and Prazdny, Proc. R.
    Soc. Lond. B 208:385, 1980)."""
    f = (wide - 1) / 2 / max(across, 1e-6)
    x = np.arange(wide, dtype="float32")[None, :] - (wide - 1) / 2
    y = np.arange(tall, dtype="float32")[:, None] - (tall - 1) / 2
    tx, ty, tz = (float(v) for v in moving)
    wx, wy, wz = (float(v) for v in turning)
    z = max(float(depth_m), 0.1)
    u = (-f * tx + x * tz) / z + x * y * wx / f - (f + x * x / f) * wy + y * wz
    v = (-f * ty + y * tz) / z + (f + y * y / f) * wx - x * y * wy / f - x * wz
    return u * exposure_s, v * exposure_s


def smeared(light: np.ndarray, du: np.ndarray, dv: np.ndarray, most: int = 16) -> np.ndarray:
    """The picture averaged along each pixel's path over the exposure, in light."""
    reach = float(np.sqrt(du * du + dv * dv).max()) if du.size else 0.0
    if reach < 0.5:
        return light
    steps = int(min(most, max(2, np.ceil(reach) + 1)))
    tall, wide = light.shape[:2]
    gx, gy = np.meshgrid(np.arange(wide, dtype="float32"), np.arange(tall, dtype="float32"))
    total = np.zeros_like(light)
    for s in np.linspace(-0.5, 0.5, steps, dtype="float32"):
        mx, my = gx + s * du, gy + s * dv
        total += np.stack([_sample(np.ascontiguousarray(light[..., c]), mx, my) for c in range(3)], axis=-1)
    return total / steps


def through(pixels: np.ndarray, camera: Camera, cached: dict | None = None,
            iso: float = 100.0, seed: int = 0, moving=(0.0, 0.0, 0.0), turning=(0.0, 0.0, 0.0),
            exposure_s: float = 1.0 / 60.0) -> np.ndarray:
    """A pinhole frame (sRGB, H x W x 3, uint8) as this camera takes it:
    the blur of its own motion over the exposure, filter, port and lens,
    vignetting, then the sensor at `iso`."""
    tall, wide = pixels.shape[:2]
    key = (wide, tall, camera.lens, camera.port)
    if cached is not None and key in cached:
        m = cached[key]
    else:
        m = maps(camera, wide, tall)
        if cached is not None:
            cached[key] = m
    light = _linear(pixels[..., :3])
    if camera.motion_blur and (any(moving) or any(turning)):
        across, _ = render_tangents(camera, wide, tall)
        light = smeared(light, *motion(wide, tall, across, moving, turning, exposure_s, camera.blur_depth_m))
    t = np.asarray(camera.filter.transmits, dtype="float32")
    light = light * t[None, None, :]
    light = np.stack([_sample(np.ascontiguousarray(light[..., c]), *m[c]) for c in range(3)], axis=-1)
    # An auto-exposing camera opens up for the light the filter took: more
    # gain, which is fewer electrons for the same picture, which is noise.
    gain = 1.0 / max(float(np.array([0.2126, 0.7152, 0.0722], dtype="float32") @ t), 1e-3)
    sensor = camera.sensor
    if sensor.kind != "none":
        cols = (np.arange(wide, dtype="float32") - (wide - 1) / 2) / ((wide - 1) / 2)
        rows = (np.arange(tall, dtype="float32") - (tall - 1) / 2) / ((wide - 1) / 2)
        r2 = cols[None, :] ** 2 + rows[:, None] ** 2
        corner = 1.0 + ((tall - 1) / (wide - 1)) ** 2
        light = light * (1.0 - sensor.vignette * r2 / corner)[..., None]
        rng = np.random.default_rng(seed)
        # Electrons from the light that reached the sensor, at the exposure
        # the scene was drawn with; the filter's gain is only how many
        # electrons make full scale, so it costs electrons, not light.
        e = np.clip(light, 0, None) * sensor.electrons_at(iso, wide, tall)
        e = e * (1.0 + sensor.prnu * rng.standard_normal((1, wide, 1)).astype("float32"))
        e = e + np.sqrt(e) * rng.standard_normal(e.shape).astype("float32")
        e = e + sensor.read_noise_e * rng.standard_normal(e.shape).astype("float32")
        levels = float(2 ** sensor.bits - 1)
        light = np.round(np.clip(e / sensor.electrons_at(iso * gain, wide, tall), 0, 1) * levels) / levels
        if sensor.chroma_blur_px > 0:
            luma = light @ np.array([0.2126, 0.7152, 0.0722], dtype="float32")
            chroma = light - luma[..., None]
            chroma = np.stack([_blur(np.ascontiguousarray(chroma[..., c]), sensor.chroma_blur_px)
                               for c in range(3)], axis=-1)
            light = luma[..., None] + chroma
        return _encoded(light)
    return _encoded(light * gain)
