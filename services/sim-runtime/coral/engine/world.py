"""The world: every part of a dive's state, by name, and who owns each.

A part is whatever holds that piece of state — an array, a small record, or an
instrument object whose methods its owner calls and everyone else only asks.
The world does not care what it is. What it does care about is that each part
has one writer, declared up front, so that "who changed the current?" always
has exactly one answer.

Parts that nothing writes during a dive — the place's seabed, the tank's glass
— are given with no owner and are read-only from the first tick.
"""

from __future__ import annotations


class World:
    """Named parts of the dive's state."""

    def __init__(self) -> None:
        self._parts: dict[str, object] = {}
        self._owners: dict[str, str | None] = {}

    def put(self, name: str, part, owner: str | None = None) -> None:
        """Add a part. `owner` is the system that will write it; None means
        nothing does once the dive is running."""
        if name in self._parts:
            raise ValueError(f"the world already has a {name!r}")
        self._parts[name] = part
        self._owners[name] = owner

    def replace(self, name: str, part) -> None:
        """Hand a part a new value. For whatever builds the dive, before it
        runs, and for an owner whose part is a value rather than an object."""
        if name not in self._parts:
            raise KeyError(f"the world has no {name!r}")
        self._parts[name] = part

    def owner_of(self, name: str) -> str | None:
        return self._owners[name]

    def has(self, name: str) -> bool:
        return name in self._parts

    def names(self) -> list[str]:
        return list(self._parts)

    def __getattr__(self, name: str):
        parts = self.__dict__.get("_parts")
        if parts is not None and name in parts:
            return parts[name]
        raise AttributeError(f"the world has no {name!r}")

    def __getitem__(self, name: str):
        return self._parts[name]
