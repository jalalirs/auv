"""The order systems run in, worked out from what they read and write.

Two rules, from the declarations in system.py:

    reads X     runs after the system that writes X
    before X    runs before the system that writes X

and where neither says, the order they were listed in. A cycle is an error and
names itself: it means two systems each need the other's answer this tick,
and one of them has to be told to use last tick's.
"""

from __future__ import annotations


def check(systems, world) -> None:
    """Every part a system writes is one the world gave it, and every part it
    reads exists."""
    names = [s.name for s in systems]
    if len(set(names)) != len(names):
        raise ValueError(f"two systems share a name: {names}")
    for s in systems:
        for part in s.writes:
            if not world.has(part):
                raise ValueError(f"{s.name} writes {part!r}, which the world does not have")
            if world.owner_of(part) != s.name:
                raise ValueError(f"{s.name} writes {part!r}, which belongs to "
                                 f"{world.owner_of(part)!r}")
        for part in tuple(s.reads) + tuple(s.before):
            if not world.has(part):
                raise ValueError(f"{s.name} reads {part!r}, which the world does not have")


def order(systems) -> list:
    """The systems in the order a tick runs them."""
    writer = {}
    for s in systems:
        for part in s.writes:
            writer[part] = s
    after = {s.name: set() for s in systems}           # s.name -> names it must follow
    for s in systems:
        for part in s.reads:
            w = writer.get(part)
            if w is not None and w is not s:
                after[s.name].add(w.name)
        for part in s.before:
            w = writer.get(part)
            if w is not None and w is not s:
                after[w.name].add(s.name)
    listed = [s.name for s in systems]
    by_name = {s.name: s for s in systems}
    done, out = set(), []
    while len(out) < len(systems):
        ready = [n for n in listed if n not in done and after[n] <= done]
        if not ready:
            stuck = [n for n in listed if n not in done]
            raise ValueError("these systems each wait on another: "
                             + ", ".join(f"{n} after {sorted(after[n] - done)}" for n in stuck))
        # The first one listed that may run. Listing order is the tie-break,
        # so an order that the declarations leave open is still the same order
        # every time.
        out.append(by_name[ready[0]])
        done.add(ready[0])
    return out


def describe(systems) -> str:
    """The order, one line a system, with what each reads and writes."""
    lines = []
    for i, s in enumerate(systems, 1):
        rate = "every tick" if s.every is None else f"every {s.every:g} s"
        reads = ", ".join(list(s.reads) + [f"{p} (start of tick)" for p in s.before]) or "nothing"
        lines.append(f"{i:2d}. {s.name:<11} {rate:<13} reads {reads}; writes {', '.join(s.writes) or 'nothing'}")
    return "\n".join(lines)
