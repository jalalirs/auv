"""Every vehicle the catalogue describes. Generated; do not edit."""

from __future__ import annotations

from ..vehicle import Vehicle

from .bluerov2 import VEHICLE as _bluerov2
from .bluerov2_heavy import VEHICLE as _bluerov2_heavy
from .remus_100 import VEHICLE as _remus_100
from .seaglider import VEHICLE as _seaglider

ALL: dict[str, Vehicle] = {
    'bluerov2': _bluerov2,
    'bluerov2-heavy': _bluerov2_heavy,
    'remus-100': _remus_100,
    'seaglider': _seaglider,
}


def load(slug: str) -> Vehicle:
    try:
        return ALL[slug]
    except KeyError:
        # Not one of ours. A customer's own hull is found by the
        # card its package carries; see coral_city/catalogue.py.
        from ..catalogue import from_a_package

        return from_a_package(slug, ALL)


def all() -> list[Vehicle]:  # noqa: A001 — reads well at the call site
    return list(ALL.values())
