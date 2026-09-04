"""The decision to stop and come home.

Every other controller is trying to do the job. This one is watching whether
the job can still be paid for, and it is the only controller allowed to take
the vehicle from a hand on the keys — because a vehicle that dies on the
bottom while its pilot was busy is the failure this exists to prevent, and
asking permission is exactly what there is no time for.

It holds one judgement, made continuously and stated plainly: does what is
left in the battery still cover getting home, with the reserve untouched. Home
is the dock if the place has one and it is reachable; the surface if it is
not. The surface is always reachable — it is straight up — so there is always
somewhere to go, and the choice between the two is made once and then kept, so
a vehicle does not dither between them as the numbers cross.

When it takes the vehicle it says which it chose and why, and it does not give
it back on its own. A person can take it back; nothing else can.
"""

from __future__ import annotations

import math

import numpy as np

from .base import Command, Controller, Observation
from .pursue import PursueController


class Failsafe(Controller):
    """Watches the energy, and comes home when it must."""

    name = "failsafe"
    kind = "builtin"
    says = "Watches what is left against the way home, and takes the vehicle when it must."

    def __init__(self, capability: np.ndarray, mass: np.ndarray, trim_n: float, dt: float) -> None:
        super().__init__()
        self.pursue = PursueController(capability, mass, trim_n, dt)
        self.pursue.name = "failsafe"
        self.declare("marginFraction", 0.25, 0.0, 2.0, "",
                     "how much more than the journey home it insists on having")
        self.declare("surfaceAtM", 0.4, 0.0, 5.0, "m", "the depth it calls the surface")
        self.declare("armed", 1.0, 0.0, 1.0, "", "0 lets the dive spend everything it has")
        self.battery = None
        self.dock: np.ndarray | None = None
        self.decided: str | None = None      # "dock" | "surface"
        self.why = ""
        self.needed_s = 0.0
        self.left_s = 0.0

    # ── what it is given ─────────────────────────────────────────────────────

    def watch(self, battery, dock=None) -> None:
        self.battery = battery
        self.dock = None if dock is None else np.array(dock, dtype=float)

    def limit(self, authority: np.ndarray) -> None:
        self.pursue.limit(authority)

    def engage(self, seen: Observation) -> None:
        self.pursue.engage(seen)

    # ── the judgement ────────────────────────────────────────────────────────

    def must_come_home(self, seen: Observation) -> bool:
        """Whether what is left still covers the way home. Asked every step."""
        if self.decided is not None:
            return True
        if self.battery is None or self["armed"] < 0.5:
            return False
        speed = max(0.15, float(self.pursue["cruiseMs"]))
        rise = max(0.0, seen.depth - self["surfaceAtM"])
        to_surface = rise / max(0.05, 0.5 * speed)
        to_dock = None
        if self.dock is not None:
            flat = float(np.hypot(*(self.dock[:2] - seen.position[:2])))
            deep = abs(float(-self.dock[2]) - seen.depth)
            to_dock = flat / speed + deep / max(0.05, 0.5 * speed)

        margin = 1.0 + self["marginFraction"]
        # What there is left to spend, at the rate it is being spent. The
        # reserve is not part of it: getting home is not what a reserve is for.
        watts = max(self.battery.hotel_w, self.battery.watts)
        spendable = max(0.0, self.battery.remaining_wh
                        - self.battery.capacity_wh * self.battery.reserve)
        self.left_s = spendable * 3600.0 / max(1e-6, watts)

        # The dock, while the dock is still a thing that can be reached. Below
        # that it stops being an option and the surface is the only home there
        # is — which is why the two are decided in this order and not by
        # whichever is nearer.
        if to_dock is not None and self.left_s <= to_dock * margin:
            if to_dock <= self.left_s:
                self.needed_s = to_dock * margin
                self.decided = "dock"
                self.why = (f"{self.battery.fraction * 100:.0f}% left, "
                            f"{to_dock:.0f} s to the dock and {self.left_s:.0f} s of it")
                self.pursue.steer([{"x": float(self.dock[0]), "y": float(self.dock[1]),
                                    "depthM": float(-self.dock[2])}])
                self.pursue.engage(seen)
                return True

        if self.left_s <= to_surface * margin:
            self.needed_s = to_surface * margin
            self.decided = "surface"
            near = ("no dock in this place" if self.dock is None
                    else "the dock is too far")
            self.why = (f"{self.battery.fraction * 100:.0f}% left, {near}, "
                        f"{to_surface:.0f} s to the surface and {self.left_s:.0f} s of it")
            self.pursue.steer([])
            self.pursue.engage(seen)
            return True

        self.needed_s = (to_surface if to_dock is None else min(to_surface, to_dock)) * margin
        return False

    def observe(self, seen: Observation) -> Command:
        if self.decided == "surface":
            # Straight up, and nothing else: the shortest way out of the water
            # is the one that spends least, and there is nothing left to spend.
            self.pursue.station_depth = self["surfaceAtM"]
            self.pursue.route = []
        return self.pursue.observe(seen)

    def stand_down(self) -> None:
        """A person has taken the vehicle back."""
        self.decided = None
        self.why = ""

    def status(self) -> dict:
        return {"decided": self.decided, "why": self.why,
                "homeIs": None if self.dock is None else [round(float(v), 2) for v in self.dock],
                "needsS": round(self.needed_s, 0), "hasS": round(self.left_s, 0)}
