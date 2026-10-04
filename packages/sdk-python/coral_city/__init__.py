"""iocean's controller SDK under the name it had before: Coral City.

Kept so that a controller written as `from coral_city import Controller` — or
`from coral_city.interface import Observation` — still imports, and gets the
very same objects `iocean` hands out. Not a copy: a copy would make
`coral_city.Observation` a different class from `iocean.Observation`, and a
controller written against one would be refused by a runtime holding the other.

Every `coral_city.X` is answered with the module `iocean.X`, loaded once. New
code imports `iocean`. This name goes in a later release
(docs/plan/iocean-rename.md).
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys

import iocean as _iocean
from iocean import *  # noqa: F401,F403


class _TheOldName(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Answers `coral_city.X` with `iocean.X` itself."""

    PREFIX = __name__ + "."

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(self.PREFIX):
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        return importlib.import_module("iocean." + spec.name[len(self.PREFIX):])

    def exec_module(self, module):
        # Already run, as iocean's: running it again would make a second copy.
        pass


if not any(isinstance(one, _TheOldName) for one in sys.meta_path):
    sys.meta_path.insert(0, _TheOldName())

# What iocean's own namespace has that a star import leaves out.
for _name in dir(_iocean):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_iocean, _name))
