"""The model's classes gathered into what a cover map says.

The model labels 95 things; a cover map says how much of the seabed is living
hard coral, soft coral, dead coral, algae, sand and so on. The config names,
for each group, the classes in it; this turns that into a lookup from class id
to group, and refuses a config that leaves a class out or puts one in twice.
"""

from __future__ import annotations

import numpy as np

NOT_SEABED = "not_seabed"


class Groups:
    def __init__(self, id2label: dict[int, str], groups: dict[str, list[str]]) -> None:
        self.names = tuple(groups)
        if NOT_SEABED not in self.names:
            raise ValueError(f"the groups need a {NOT_SEABED!r} group, even an empty one")
        where: dict[str, str] = {}
        for group, labels in groups.items():
            for label in labels:
                if label in where:
                    raise ValueError(f"{label!r} is in both {where[label]!r} and {group!r}")
                where[label] = group
        known = {label for label in id2label.values()}
        unknown = sorted(set(where) - known)
        if unknown:
            raise ValueError(f"the groups name classes the model does not have: {unknown}")
        missing = sorted(known - set(where))
        if missing:
            raise ValueError(f"the model's classes {missing} are in no group")
        size = max(id2label) + 1
        # Class ids the model never says (0, void, in CoralscapesV2's labels)
        # count as not seabed.
        self.lookup = np.full(size, self.names.index(NOT_SEABED), dtype=np.int16)
        for i, label in id2label.items():
            self.lookup[i] = self.names.index(where[label])
        self.seabed = tuple(n for n in self.names if n != NOT_SEABED)

    def of(self, classes: np.ndarray) -> np.ndarray:
        """Group index for every pixel of a class-id image."""
        return self.lookup[np.clip(classes, 0, len(self.lookup) - 1)]

    def shares(self, classes: np.ndarray, valid: np.ndarray | None = None) -> dict[str, float] | None:
        """Each seabed group's share of the seabed pixels, None where there are none."""
        g = self.of(classes)
        seabed = g != self.names.index(NOT_SEABED)
        if valid is not None:
            seabed &= valid
        n = int(seabed.sum())
        if n == 0:
            return None
        counts = np.bincount(g[seabed], minlength=len(self.names))
        return {name: float(counts[self.names.index(name)] / n) for name in self.seabed}
