"""Every vehicle the catalogue describes. Generated; do not edit."""

from __future__ import annotations

from ..vehicle import Vehicle

from .bluerov2 import VEHICLE as _bluerov2
from .bluerov2_heavy import VEHICLE as _bluerov2_heavy
from .remus_100 import VEHICLE as _remus_100

ALL: dict[str, Vehicle] = {
    'bluerov2': _bluerov2,
    'bluerov2-heavy': _bluerov2_heavy,
    'remus-100': _remus_100,
}


def load(slug: str) -> Vehicle:
    try:
        return ALL[slug]
    except KeyError:
        raise KeyError(f"no vehicle '{slug}' in the catalogue; there are {', '.join(ALL)}") from None


def all() -> list[Vehicle]:  # noqa: A001 — reads well at the call site
    return list(ALL.values())
