"""Depth from the trained depth model (ml/depth), run over the place.

The model is an export of a run (`iocean-depth export`): model.onnx and
model.json. It was trained on 10 m cells in 128-cell chips, so the place is
read at 10 m over its own square, cut into 128-cell windows that overlap by a
quarter, and the windows' predictions are blended with a taper so no window's
edge shows. Depth and its stated uncertainty (scaled by the run's calibration)
are then resampled onto the place's grid.

It says depth and how wrong it may be, cell by cell; it does not know land,
and it has never seen this place. A place corrects it with what was measured
here (curve-depth against the place's ICESat-2 photons), the way the satellite
claim has always been corrected.

Needs onnxruntime (CPU is enough).
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance
from . import where

WINDOW, STRIDE = 128, 96


def _taper(n: int) -> np.ndarray:
    """A window's weight: 1 in the middle, falling smoothly to near 0 at its edges."""
    ramp = np.sin(np.linspace(0, np.pi, n)) ** 2 + 1e-3
    return np.outer(ramp, ramp).astype("float32")


def predict(session, meta: dict, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Depth and sigma for a (bands, rows, columns) stack of any size, by
    overlapping windows. NaN where the input is missing."""
    from ..fetch.sentinel_bands import features

    f = features(x)
    mean = np.asarray(meta["mean"], "float32")[:, None, None]
    std = np.asarray(meta["std"], "float32")[:, None, None]
    f = (f - mean) / std
    _, rows, cols = f.shape
    # Pad so windows tile it, by reflection: a window off the edge sees sea
    # that looks like the sea beside it rather than a hole.
    pr = max(WINDOW, int(np.ceil((rows - WINDOW) / STRIDE)) * STRIDE + WINDOW) - rows
    pc = max(WINDOW, int(np.ceil((cols - WINDOW) / STRIDE)) * STRIDE + WINDOW) - cols
    fp = np.pad(f, ((0, 0), (0, max(0, pr)), (0, max(0, pc))), mode="reflect")
    depth = np.zeros(fp.shape[1:], "float64")
    var = np.zeros(fp.shape[1:], "float64")
    weight = np.zeros(fp.shape[1:], "float64")
    w = _taper(WINDOW)
    starts_r = range(0, fp.shape[1] - WINDOW + 1, STRIDE)
    starts_c = range(0, fp.shape[2] - WINDOW + 1, STRIDE)
    for r in starts_r:
        for c in starts_c:
            d, lv = session.run(None, {"features": fp[None, :, r:r + WINDOW, c:c + WINDOW]})
            depth[r:r + WINDOW, c:c + WINDOW] += w * d[0]
            var[r:r + WINDOW, c:c + WINDOW] += w * np.exp(lv[0])
            weight[r:r + WINDOW, c:c + WINDOW] += w
    depth, var = depth[:rows, :cols] / weight[:rows, :cols], var[:rows, :cols] / weight[:rows, :cols]
    sigma = np.sqrt(var) * float(meta.get("sigmaScale", 1.0))
    missing = ~np.all(np.isfinite(x), axis=0)
    depth[missing], sigma[missing] = np.nan, np.nan
    return depth.astype("float32"), sigma.astype("float32")


class LearnedDepth:
    name = "learned-depth"
    gives = ("depth",)

    def __init__(self, model: str, path: str | None = None, scenes: int = 8, cloud: float = 20.0,
                 until: str = "2030-01-01T00:00:00Z", fetch: bool = True) -> None:
        self.model, self.path = pathlib.Path(model).expanduser(), path
        self.scenes, self.cloud, self.until, self.fetch = int(scenes), float(cloud), until, bool(fetch)

    def _bands(self, grid10: Grid, folder: pathlib.Path, bands: list[str]) -> tuple[np.ndarray, list[dict]]:
        """The place's Sentinel-2 band medians at 10 m, cached in its reference folder."""
        cached = folder / "sentinel_bands_10m.npz"
        if cached.is_file():
            d = np.load(cached, allow_pickle=False)
            if d["x"].shape[1:] == (grid10.cells, grid10.cells):
                return d["x"], json.loads(str(d["scenes"]))
        if not self.fetch:
            raise ValueError(f"{self.name}: no {cached.name} in {folder}, and fetching is off")
        from ..fetch.sentinel_bands import stack

        x, scenes = stack(grid10, scenes=self.scenes, bands=tuple(bands), cloud=self.cloud, until=self.until)
        folder.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cached, x=x, scenes=json.dumps(scenes))
        return x, scenes

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        import onnxruntime as ort
        from scipy.ndimage import map_coordinates

        meta = json.loads((self.model / "model.json").read_text())
        session = ort.InferenceSession(str(self.model / "model.onnx"), providers=["CPUExecutionProvider"])
        cell = float(meta.get("cellM", 10.0))
        n10 = int(round(grid.across / cell)) + 1
        grid10 = Grid(grid.latitude, grid.longitude, cell * (n10 - 1), n10)
        x, scenes = self._bands(grid10, where(self.path, cache), meta["bands"])
        depth10, sigma10 = predict(session, meta, x)

        # Onto the place's grid: both squares share a middle; the place's may be
        # a fraction of a cell narrower, so its edge cells clamp to the last 10 m cell.
        X, Y = grid.xy()
        col = np.clip((X / grid10.across + 0.5) * (n10 - 1), 0, n10 - 1)
        row = np.clip((Y / grid10.across + 0.5) * (n10 - 1), 0, n10 - 1)
        depth = map_coordinates(np.nan_to_num(depth10, nan=-1.0), [row, col], order=1)
        sigma = map_coordinates(np.nan_to_num(sigma10, nan=-1.0), [row, col], order=1)
        bad = map_coordinates((~np.isfinite(depth10)).astype("float32"), [row, col], order=1) > 0.01
        value = np.where(bad, np.nan, -depth)
        error = np.where(bad, np.nan, sigma)
        held = meta.get("heldOut", {})
        summary = ", ".join(f"{k} {v['rmsM']} m" for k, v in held.items() if v.get("rmsM") is not None)
        cited = Provenance(
            self.name, "derived",
            f"iOcean's depth model ({meta['run']}, U-Net on Sentinel-2, {len(scenes)} scenes here); trained on "
            f"NOAA reef lidar ({', '.join(meta.get('trainedOn') or [])}), never on this place; held out: {summary}",
            note={"model": meta["run"], "commit": meta.get("commit"), "sigmaScale": meta.get("sigmaScale")})
        return [Layer.of(grid, "depth", value, error, cited)]
