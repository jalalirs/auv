"""Chips: their grid, and ICESat-2 photons into the cells they fell in."""

import numpy as np

from iocean_depth.data import chips


def test_a_chip_is_its_cells_at_its_spacing():
    g = chips.chip_grid(24.5, -81.4, 128, 10.0)
    assert g.cells == 128 and abs(g.cell - 10.0) < 1e-9


def test_photons_go_to_the_cell_they_fell_in_and_a_cell_takes_their_median():
    g = chips.chip_grid(24.5, -81.4, 16, 10.0)
    lon, lat = g.lonlat()
    plon = np.array([lon[5, 5]] * 3 + [lon[10, 2]])
    plat = np.array([lat[5, 5]] * 3 + [lat[10, 2]])
    y = chips.photons_label(g, plon, plat, np.array([-4.0, -5.0, -9.0, -12.0]))
    assert y[5, 5] == -5.0 and y[10, 2] == -12.0 and np.isfinite(y).sum() == 2


def test_labelled_share_is_seabed_a_satellite_can_see():
    y = np.array([[-10.0, -40.0], [2.0, np.nan]])
    assert chips.labelled_share(y, -0.5, -30.0) == 0.25
