"""Reading the water the vehicle is flying in.

The platform has modelled the water properly since the beginning: EOS-80
density from salinity and temperature, a profile with depth, compression under
pressure. Every bit of it was visible only to the physics. A controller could
not read the water it was in and a mission could not bring a profile home —
which for a glider section is the entire deliverable.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from runner import Dive  # noqa: E402


class Column:
    """Just the parts of a dive a cast reads."""

    ctd = {"everyS": 1.0, "name": "ctd"}
    salinity_psu = 40.6
    temperature_c = None
    stated_density = None
    temperature_profile = [(0.0, 30.0), (100.0, 22.0), (700.0, 21.0)]

    def __init__(self):
        self.simulated = 0.0
        self.position = np.array([12.0, -34.0, 0.0])
        self.profile = []
        self.ctd_last_t = None

    temperature_at = Dive.temperature_at
    density_at = Dive.density_at
    read_the_ctd = Dive.read_the_ctd


def test_a_cast_reads_the_column_it_is_in():
    c = Column()
    for depth in (0.0, 50.0, 200.0, 600.0):
        c.position[2] = -depth
        c.simulated += 2.0
        c.read_the_ctd()
    assert len(c.profile) == 4, c.profile
    # Warm at the top, cold at the bottom, which is what a column is.
    assert c.profile[0]["temperatureC"] > c.profile[-1]["temperatureC"]
    # And denser with depth, because the water above weighs on it.
    assert c.profile[-1]["densityKgM3"] > c.profile[0]["densityKgM3"]


def test_it_casts_at_its_own_rate_and_not_every_step():
    """An instrument that sampled every physics step is an instrument nobody
    owns, and a profile with two hundred readings a second is not a profile."""
    c = Column()
    for _ in range(20):
        c.simulated += 0.05
        c.read_the_ctd()
    assert len(c.profile) == 1, f"one second, one cast: {len(c.profile)}"


def test_a_cast_remembers_where_it_was_taken():
    """A section is the column against distance, so a reading without a place
    is half a reading."""
    c = Column()
    c.read_the_ctd()
    assert c.profile[0]["atM"] == [12.0, -34.0]


def test_a_vehicle_with_no_ctd_takes_no_casts():
    c = Column()
    c.ctd = None
    c.read_the_ctd()
    assert c.profile == []
