"""The keyboard, as a pair of hands on an ROV.

What a pilot can ask for is a body-frame wrench and nothing else — the same six
numbers a program sends on /cmd_vel. That is deliberate. If flying by hand went
through some private path into the thrusters, then a manoeuvre a person could
fly would be one no autonomy could, and the whole point of the simulator is that
what happens here is what would happen out there.

The layout is the one every pilot of anything already knows: WASD moves you
about the horizon, Q and E turn you, Space and C take you up and down. Held, not
tapped — a thruster runs while you are asking for it and stops when you let go,
because that is what a thruster does.
"""

from __future__ import annotations

import carb.input
import omni.appwindow

# How hard each key pushes, as a fraction of what the vehicle can do. Not full
# scale: an ROV at maximum thrust is uncontrollable by hand, and a first attempt
# to fly one should feel like flying rather than like a fight.
FIRM = 0.55
TURN = 0.35

# Surge, sway, heave, roll, pitch, yaw — the vehicle's own frame, with x
# forward, y to starboard and z up.
LAYOUT = {
    "W": (0, +1.0), "S": (0, -1.0),
    "D": (1, +1.0), "A": (1, -1.0),
    "SPACE": (2, +1.0), "C": (2, -1.0),
    "E": (5, -1.0), "Q": (5, +1.0),
}


class Controls:
    """Which keys are down, and what the vehicle is being asked to do."""

    def __init__(self) -> None:
        self.held: set[str] = set()
        self._input = carb.input.acquire_input_interface()
        window = omni.appwindow.get_default_app_window()
        self._keyboard = window.get_keyboard()
        self._subscription = self._input.subscribe_to_keyboard_events(
            self._keyboard, self._on_key)

    def _on_key(self, event, *_) -> bool:
        name = event.input.name
        if event.type == carb.input.KeyboardEventType.KEY_PRESS:
            self.held.add(name)
        elif event.type == carb.input.KeyboardEventType.KEY_RELEASE:
            self.held.discard(name)
        # False, so that everything else in the application still sees the key.
        # A shell that swallowed input would be one nobody could take a
        # screenshot in.
        return False

    @property
    def flying(self) -> bool:
        return bool(self.held & set(LAYOUT))

    def wrench(self) -> list[float]:
        """What the hands are asking for, in the vehicle's body frame."""
        asked = [0.0] * 6
        for key in self.held:
            axis_and_sign = LAYOUT.get(key)
            if axis_and_sign is None:
                continue
            axis, sign = axis_and_sign
            asked[axis] += sign * (TURN if axis >= 3 else FIRM)
        # Opposite keys held together cancel, which is correct and is also how
        # you stop: let go of one and the other is still pushing.
        return [max(-1.0, min(1.0, value)) for value in asked]

    def close(self) -> None:
        if self._subscription is not None:
            self._input.unsubscribe_to_keyboard_events(
                self._keyboard, self._subscription)
            self._subscription = None
