"""Where a place is: a square of sea, its middle, its size and its cells.

Every layer of a place is a grid on the same square, so that two sources for
the same square metre can be compared cell by cell. The frame is the one the
rest of the platform uses: metres from the middle of the site, x east, y north,
z up with 0 at the water surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# What a degree is worth, in metres, at a given latitude. Good to a fraction of
# a percent over a site of a few kilometres, which is the size of thing this
# makes; a projection would be more correct and would also mean a dependency and
# a coordinate system to explain.
def metres_per_degree(latitude: float) -> tuple[float, float]:
    radians = math.radians(latitude)
    north = 111_132.92 - 559.82 * math.cos(2 * radians) + 1.175 * math.cos(4 * radians)
    east = 111_412.84 * math.cos(radians) - 93.5 * math.cos(3 * radians)
    return east, north


@dataclass(frozen=True)
class Grid:
    """A square of sea, `across` metres a side, `cells` along each side,
    centred on (latitude, longitude). Rows run south to north and columns west
    to east, as the heightfields of every place on this platform do."""

    latitude: float
    longitude: float
    across: float
    cells: int

    @property
    def cell(self) -> float:
        """Metres between neighbouring samples."""
        return self.across / max(1, self.cells - 1)

    def xy(self) -> tuple[np.ndarray, np.ndarray]:
        """Each cell's place in the site's frame: metres east and north of
        the middle, as two (cells, cells) arrays."""
        # Written the way the tools have always written it, so a cell here is
        # the same float as a cell there and a place rebuilt matches bit for bit.
        line = (np.arange(self.cells) / (self.cells - 1) - 0.5) * self.across
        return np.meshgrid(line, line)

    def nearest(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        """The row and column of the cell nearest each point (site metres)."""
        n = self.cells - 1
        row = np.clip(np.round((np.asarray(y) / self.across + 0.5) * n).astype(int), 0, n)
        col = np.clip(np.round((np.asarray(x) / self.across + 0.5) * n).astype(int), 0, n)
        return row, col

    def inside(self, x, y) -> np.ndarray:
        """Which points (site metres) are on the square."""
        return (np.abs(np.asarray(x)) < self.across / 2) & (np.abs(np.asarray(y)) < self.across / 2)

    def lonlat(self) -> tuple[np.ndarray, np.ndarray]:
        """Each cell's longitude and latitude."""
        east, north = metres_per_degree(self.latitude)
        x, y = self.xy()
        return self.longitude + x / east, self.latitude + y / north

    def bounds(self) -> tuple[float, float, float, float]:
        """West, south, east, north, in degrees."""
        east, north = metres_per_degree(self.latitude)
        half_lon, half_lat = self.across / 2 / east, self.across / 2 / north
        return (self.longitude - half_lon, self.latitude - half_lat,
                self.longitude + half_lon, self.latitude + half_lat)

    def to_xy(self, longitude, latitude) -> tuple[np.ndarray, np.ndarray]:
        """Degrees to the site's metres."""
        east, north = metres_per_degree(self.latitude)
        return ((np.asarray(longitude) - self.longitude) * east,
                (np.asarray(latitude) - self.latitude) * north)

    def said(self) -> dict:
        return {"centre": [self.latitude, self.longitude], "acrossM": self.across, "cells": self.cells,
                "cellM": round(self.cell, 4)}
