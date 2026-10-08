"""What covers the seabed, from underwater imagery: a cover map made of a
photo mosaic (`cover-map`), or the frames of a video transect (`cover-transect`).

A cover map is what `iocean-cover map` (ml/cover) writes from a photo mosaic:
cover.tif, one band per group (hard coral, soft coral, dead coral, algae,
sand...) holding its share of each cell's seabed, then a `seabed` band holding
how much of the cell is imaged seabed; and cover.json, which says which model
made it, from which tiles, and how the model did when it was checked.

Each group becomes a layer, `cover.<group>`, a share from 0 to 1 per cell.
The map is far finer than a place (0.5 m against 2 m or more), so each place
cell takes its groups' shares weighted by how much imaged seabed each map
cell holds, and a place cell less than `minSeabed` imaged is left without a
value rather than read off a corner.

How wrong a share may be is the model's check: its mean error per frame on
imagery it never saw, for each group (`error: "checked"`, the default). That
holds only where the imagery is like what it was checked on; anywhere else
the recipe must say so with a number (`error: 0.15`), or the build refuses.
At Looe Key the model checked on the Red Sea is right on average and wrong by
depth zone, which a Red Sea error would hide.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from ..grid import Grid
from ..layer import Layer, Provenance
from . import where
from .raster import grid_transform


def onto_weighted(grid: Grid, shares: np.ndarray, seabed: np.ndarray, transform, crs) -> tuple[np.ndarray, np.ndarray]:
    """Shares (groups, rows, columns) and the seabed fraction of each map cell
    onto the grid: each grid cell's shares weighted by seabed, and how much of
    the grid cell is imaged seabed. Rows south first, as layers are."""
    from rasterio.warp import Resampling, reproject

    n = grid.cells
    weight = np.nan_to_num(seabed, nan=0.0).astype("float32")
    seabed_on = np.zeros((n, n), "float32")
    reproject(weight, seabed_on, src_transform=transform, src_crs=crs, dst_transform=grid_transform(grid),
              dst_crs="EPSG:4326", resampling=Resampling.average)
    out = np.zeros((len(shares), n, n), "float32")
    for k, share in enumerate(shares):
        premultiplied = (np.nan_to_num(share, nan=0.0) * weight).astype("float32")
        reproject(premultiplied, out[k], src_transform=transform, src_crs=crs,
                  dst_transform=grid_transform(grid), dst_crs="EPSG:4326", resampling=Resampling.average)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(seabed_on > 0, out / seabed_on, np.nan)
    return out[:, ::-1].copy(), seabed_on[::-1].copy()


class CoverMap:
    name = "cover-map"
    gives = ("cover.*",)

    def __init__(self, map: str, path: str | None = None, error: str | float = "checked",
                 minSeabed: float = 0.5, groups: list[str] | None = None, citation: str = "") -> None:
        self.map, self.path, self.error = map, path, error
        self.min_seabed, self.groups, self.citation = float(minSeabed), groups, citation

    def _folder(self, cache) -> pathlib.Path:
        f = pathlib.Path(self.map).expanduser()
        return f if f.is_absolute() else where(self.path, cache) / f

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        import rasterio

        folder = self._folder(cache)
        about = json.loads((folder / "cover.json").read_text())
        with rasterio.open(folder / "cover.tif") as src:
            bands = list(src.descriptions)
            data = src.read()
            transform, crs = src.transform, src.crs
        names = [b for b in bands if b != "seabed"]
        if self.groups:
            unknown = sorted(set(self.groups) - set(names))
            if unknown:
                raise ValueError(f"{self.name}: the map has no {unknown}; it has {names}")
            names = [n for n in names if n in self.groups]
        shares = np.stack([data[bands.index(n)] for n in names])
        on, seabed = onto_weighted(grid, shares, data[bands.index("seabed")], transform, crs)
        on[:, seabed < self.min_seabed] = np.nan

        checked = about.get("checked") or {}
        if self.error == "checked":
            if not checked.get("meanAbsError"):
                raise ValueError(f"{self.name}: {folder.name} carries no check of its model; "
                                 "say how wrong its shares may be with a number (error: 0.15)")
            errors = {n: float(checked["meanAbsError"][n]) for n in names}
            how = (f"error per group its mean error per frame on {checked.get('on', 'its check')}: "
                   + ", ".join(f"{n} {errors[n]:.1%}" for n in names if errors[n] >= 0.005))
        else:
            errors = {n: float(self.error) for n in names}
            how = f"error {float(self.error):.0%} a share, chosen: the imagery is not like what the model was checked on"
        imaged = float((seabed >= self.min_seabed).mean())
        cited = Provenance(
            self.name, "derived",
            (self.citation + "; " if self.citation else "")
            + f"{about.get('model')} ({about.get('licence', '')}) over {len(about.get('tiles', []))} mosaic tiles, "
            f"read at {about.get('metresPerPixel')} m a pixel, {about.get('seabedM2', 0):,.0f} m2 of seabed; {how}",
            about.get("licence", ""),
            {"coverMap": folder.name, "model": about.get("model"), "revision": about.get("revision"),
             "made": about.get("made"), "imagedShareOfSquare": round(imaged, 4)})
        return [Layer.of(grid, f"cover.{n}", on[k], errors[n], cited) for k, n in enumerate(names)]


class CoverTransect:
    """A video transect's frames (what `iocean-cover video` writes, frames.csv
    and transect.json) along its line: each place cell within `reach` metres
    of a frame takes its frames' shares, each weighted by how much of the frame
    is seabed. The frames sit where an even pace between the transect's marked
    ends puts them, which is how a diver swims a tape; `reach` is how far that
    may be out, and how much reef one frame sees. Cells no frame reaches are
    left without a value.

    Errors as a cover map's: the model's check where the video is like what it
    was checked on (a Red Sea GoPro transect is exactly that), a number
    otherwise."""

    name = "cover-transect"
    gives = ("cover.*",)

    def __init__(self, transect: str, path: str | None = None, error: str | float = "checked",
                 reach: float = 3.0, minSeabed: float = 0.3, citation: str = "") -> None:
        self.transect, self.path, self.error = transect, path, error
        self.reach, self.min_seabed, self.citation = float(reach), float(minSeabed), citation

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        import csv

        from scipy.spatial import cKDTree

        folder = pathlib.Path(self.transect).expanduser()
        folder = folder if folder.is_absolute() else where(self.path, cache) / folder
        about = json.loads((folder / "transect.json").read_text())
        rows = list(csv.DictReader(open(folder / "frames.csv")))
        if not rows or "latitude" not in rows[0]:
            raise ValueError(f"{self.name}: {folder.name} has no positions; make it with the transect's ends "
                             "(iocean-cover video --begin LAT,LON --end LAT,LON)")
        names = [k for k in rows[0] if k not in ("t", "seabed", "latitude", "longitude")]
        keep = [r for r in rows if float(r["seabed"]) >= self.min_seabed]
        lat = np.array([float(r["latitude"]) for r in keep])
        lon = np.array([float(r["longitude"]) for r in keep])
        x, y = grid.to_xy(lon, lat)
        seabed = np.array([float(r["seabed"]) for r in keep])
        shares = np.array([[float(r[n]) for n in names] for r in keep])

        gx, gy = grid.xy()
        cells = np.column_stack([gx.ravel(), gy.ravel()])
        reach = max(self.reach, grid.cell / 2)
        near = cKDTree(np.column_stack([x, y])).query_ball_point(cells, reach)
        total = np.zeros((len(cells), len(names)))
        weight = np.zeros(len(cells))
        for c, frames in enumerate(near):
            if frames:
                w = seabed[frames]
                total[c] = (shares[frames] * w[:, None]).sum(0)
                weight[c] = w.sum()
        with np.errstate(invalid="ignore", divide="ignore"):
            value = np.where(weight[:, None] > 0, total / weight[:, None], np.nan)
        value = value.reshape(gx.shape + (len(names),))

        checked = about.get("checked") or {}
        if self.error == "checked":
            if not checked.get("meanAbsError"):
                raise ValueError(f"{self.name}: {folder.name} carries no check of its model; "
                                 "say how wrong its shares may be with a number (error: 0.15)")
            errors = {n: float(checked["meanAbsError"][n]) for n in names}
            how = f"error per group its mean error per frame on {checked.get('on', 'its check')}"
        else:
            errors = {n: float(self.error) for n in names}
            how = f"error {float(self.error):.0%} a share, chosen"
        cited = Provenance(
            self.name, "derived",
            (self.citation + "; " if self.citation else "")
            + f"{about.get('model')} ({about.get('licence', '')}) over {len(keep)} frames of a video transect"
            + (f" {about['lengthM']:g} m long" if about.get("lengthM") else "")
            + f", placed at an even pace between its marked ends, within {reach:g} m; {how}",
            about.get("licence", ""),
            {"transect": folder.name, "model": about.get("model"), "revision": about.get("revision"),
             "videos": about.get("videos"), "begin": about.get("begin"), "end": about.get("end")})
        return [Layer.of(grid, f"cover.{n}", value[..., k], errors[n], cited) for k, n in enumerate(names)]
