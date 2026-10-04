"""This package's switches are `IOCEAN_*`; the ones it had are `CORAL_CITY_*`.

`carry()` gives every `CORAL_CITY_X` it finds to `IOCEAN_X`, unless `IOCEAN_X`
is already set, so the new name wins and the old one still works: the agent on
a box configured before the rename, a script somebody keeps, a habit. Run when
this package is imported, before anything reads a switch. The old names go in a later release (docs/plan/iocean-rename.md).
"""

from __future__ import annotations

import os

OLD, NEW = "CORAL_CITY_", "IOCEAN_"


def carry(environ=None) -> list[str]:
    """Copy each old name's value to its new name where that is unset; the new
    names given, for whoever wants to say so."""
    environ = os.environ if environ is None else environ
    given = []
    for name in [one for one in environ if one.startswith(OLD)]:
        new = NEW + name[len(OLD):]
        if new not in environ:
            environ[new] = environ[name]
            given.append(new)
    return given


carry()
