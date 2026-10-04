"""iocean, for agents."""

from . import names  # noqa: F401  — the old CORAL_CITY_ settings, given their IOCEAN_ names

from .platform import Platform, Refused
from .provenance import said, unknown

__all__ = ["Platform", "Refused", "said", "unknown"]
