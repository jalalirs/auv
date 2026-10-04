"""What nobody can promise about a working day, by the names the app uses.

The same catalogue as apps/client/src/renderer/catalog/doubts.ts, so that an
agent and the Sweeps screen ask the same questions in the same words. A test
holds the two together by their keys: a doubt the app offers and the agent
cannot name, or the other way round, is two products pretending to be one.

An agent says which settings of which doubts it wants flown —

    {"current": ["still", "one knot"], "the mooring": ["as drawn", "thirty metres off"]}

— and gets every combination, each flown `repeats` times, because a mission
that works once in one water is not a finding.
"""

from __future__ import annotations

DOUBTS: dict[str, dict] = {
    "current": {
        "name": "The current",
        "settings": {
            "still": {"currentMetresPerSecond": 0, "currentHeadingDeg": 0},
            "gentle": {"currentMetresPerSecond": 0.15, "currentHeadingDeg": 30},
            "half knot": {"currentMetresPerSecond": 0.26, "currentHeadingDeg": 30},
            "one knot": {"currentMetresPerSecond": 0.51, "currentHeadingDeg": 30},
        },
    },
    "fix": {
        "name": "How it knows where it is",
        "settings": {
            "array": {"positioning": {"kind": "lbl", "everyS": 3, "accuracyM": 0.5, "rangeM": 400}},
            "ship": {"positioning": {"kind": "usbl", "everyS": 2, "accuracyPercent": 0.5, "rangeM": 500}},
            "nothing": {"positioning": {"kind": "none"}},
        },
    },
    "water clarity": {
        "name": "How far you can see",
        "settings": {"clear": {}, "murky": {"visibilityM": 5.0}},
    },
    "trouble": {
        "name": "Something gives out",
        "settings": {
            "none": {},
            "thruster": {"failures": [{"kind": "thruster", "which": 2, "atS": 3600}]},
            "no log": {"fitted": {"dvl": False}},
        },
    },
    "the array": {
        "name": "The array, as laid",
        "settings": {
            "as laid": {},
            "one down": {"world": {"remove": ["transponder-2"]}},
            "two down": {"world": {"remove": ["transponder-2", "transponder-3"]}},
        },
    },
    "the mooring": {
        "name": "The mooring, where it was laid",
        "settings": {
            "as drawn": {},
            "ten metres off": {"world": {"move": {"mooring-block": {"dx": 10, "dy": 0}}}},
            "thirty metres off": {"world": {"move": {"mooring-block": {"dx": 30, "dy": 0}}}},
        },
    },
    "how long": {
        "name": "How long the day is",
        "settings": {
            "a shift": {"objective": {"timeLimitS": 2400}},
            "two shifts": {"objective": {"timeLimitS": 4800}},
        },
    },
}


def asked(chosen: dict[str, list[str]]) -> dict:
    """The contract's Doubts shape from the names an agent used.

    Refuses a name it does not know rather than flying without it: a sweep that
    quietly drops "thirty metres off" answers a smaller question than the one
    that was asked, and says nothing about the difference.
    """
    out: dict[str, dict] = {}
    for dimension, settings in chosen.items():
        known = DOUBTS.get(dimension)
        if known is None:
            raise KeyError(f"no doubt called {dimension!r}; "
                           f"there are {sorted(DOUBTS)}")
        out[dimension] = {}
        for setting in settings:
            if setting not in known["settings"]:
                raise KeyError(f"{dimension!r} has no setting {setting!r}; "
                               f"it has {sorted(known['settings'])}")
            out[dimension][setting] = known["settings"][setting]
    return out


def scenarios(chosen: dict[str, list[str]]) -> int:
    """How many distinct questions that is: every combination."""
    count = 1
    for settings in chosen.values():
        count *= max(1, len(settings))
    return count
