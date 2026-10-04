"""Every vehicle the catalogue describes. Generated; do not edit."""

from __future__ import annotations

from ..vehicle import Vehicle

from .bluerov2 import VEHICLE as _bluerov2
from .bluerov2_heavy import VEHICLE as _bluerov2_heavy
from .boxfish_luna import VEHICLE as _boxfish_luna
from .edgetech_2300 import VEHICLE as _edgetech_2300
from .mini_hoot import VEHICLE as _mini_hoot
from .remus_100 import VEHICLE as _remus_100
from .seaglider import VEHICLE as _seaglider

ALL: dict[str, Vehicle] = {
    'bluerov2': _bluerov2,
    'bluerov2-heavy': _bluerov2_heavy,
    'boxfish-luna': _boxfish_luna,
    'edgetech-2300': _edgetech_2300,
    'mini-hoot': _mini_hoot,
    'remus-100': _remus_100,
    'seaglider': _seaglider,
}


def load(slug: str) -> Vehicle:
    try:
        return ALL[slug]
    except KeyError:
        # Not one of ours. A customer's own hull is found by the
        # card its package carries; see iocean/catalogue.py.
        from ..catalogue import from_a_package

        return from_a_package(slug, ALL)


def all() -> list[Vehicle]:  # noqa: A001 — reads well at the call site
    return list(ALL.values())
