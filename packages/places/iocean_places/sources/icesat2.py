"""ICESat-2 ATL24: depths a laser measured, along the tracks it flew.

Read from what tools/icesat wrote (`icesat_depths.npy`: x east and y north in
metres from the centre it was fetched for, orthometric height, and each
photon's vertical uncertainty). Kept as soundings, because that is what models
are fitted and checked against; gridded too, near the tracks only, for fusion.
"""

from __future__ import annotations

import json

import numpy as np

from ..grid import Grid, metres_per_degree
from ..layer import Layer, Provenance, Soundings
from . import fetched, gridded, where


class IceSat2:
    name = "icesat2"
    gives = ("depth",)

    def __init__(self, path: str | None = None, file: str = "icesat_depths.npy", note: str = "icesat.json",
                 centre: list[float] | None = None, reach: float = 15.0, slope: float = 0.1,
                 most: int = 60, fetch: bool = True) -> None:
        self.path, self.file, self.note, self.centre = path, file, note, centre
        self.reach, self.slope, self.most, self.fetch = float(reach), float(slope), int(most), bool(fetch)

    def _fetched_for(self, folder, grid: Grid) -> tuple[float, float]:
        """The centre the photons' metres are measured from: as given, else
        the reference corpus's own record, else the place's."""
        if self.centre:
            return float(self.centre[0]), float(self.centre[1])
        for name in ("reference.json", f"{folder.name}.json"):
            if (folder / name).is_file():
                c = json.loads((folder / name).read_text()).get("centre")
                if isinstance(c, dict):
                    return float(c["latitude"]), float(c["longitude"])
        return grid.latitude, grid.longitude

    def soundings(self, grid: Grid, cache=None) -> list[Soundings]:
        folder = where(self.path, cache)
        if not (folder / self.file).is_file() and self.fetch:
            # Fetched for this grid's middle, so the photons' metres are from it.
            # Needs NASA_TOKEN (an Earthdata Login token) in the environment or .env.
            from ..fetch.icesat import main
            folder.mkdir(parents=True, exist_ok=True)
            fetched(self.name, main, [folder.name, "--centre", grid.latitude, grid.longitude,
                                      "--across", grid.across, "--most", self.most, "--into", folder.parent])
            self.centre = self.centre or [grid.latitude, grid.longitude]
        points = np.load(folder / self.file)
        said = json.loads((folder / self.note).read_text()) if (folder / self.note).is_file() else {}
        x, y = points[:, 0].astype(float), points[:, 1].astype(float)
        latitude, longitude = self._fetched_for(folder, grid)
        if (latitude, longitude) != (grid.latitude, grid.longitude):
            east, north = metres_per_degree(latitude)
            x, y = grid.to_xy(longitude + x / east, latitude + y / north)
        height = points[:, 2].astype(float)
        sigma = points[:, 3].astype(float) if points.shape[1] > 3 else np.full(len(height), np.nan)
        sigma = np.where(np.isfinite(sigma), sigma, np.nanmedian(sigma) if np.isfinite(sigma).any() else 0.3)
        cited = Provenance(self.name, "measured",
                           f"{said.get('source', 'ICESat-2 ATL24')}: {said.get('what', 'seafloor photons')}, "
                           f"{said.get('photons', len(height)):,} photons from "
                           f"{said.get('passesWithSeafloor', '?')} passes", said.get("licence", "public domain"))
        return [Soundings("depth", x, y, height, sigma, cited)]

    def layers(self, grid: Grid, cache=None) -> list[Layer]:
        return [gridded(grid, one, self.reach, self.slope) for one in self.soundings(grid, cache)]
