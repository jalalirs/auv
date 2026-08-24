#!/usr/bin/env python3
"""Drive the reef AUV from keys pressed in the streamed Xpra desktop."""

from __future__ import annotations

import time

import rclpy
from rclpy.signals import SignalHandlerOptions
from Xlib import X, XK, display as xdisplay

from auv_control.reef_keyboard_teleop import (
    AXIS_COUNT,
    AXIS_HEAVE,
    AXIS_SURGE,
    AXIS_SWAY,
    AXIS_YAW,
    BUTTON_LIGHTS,
    PUBLISH_HZ,
    ReefKeyboardTeleop,
)


MOVEMENT_KEYS = {
    "w": (AXIS_SURGE, 1.0),
    "Up": (AXIS_SURGE, 1.0),
    "s": (AXIS_SURGE, -1.0),
    "Down": (AXIS_SURGE, -1.0),
    "a": (AXIS_YAW, 1.0),
    "Left": (AXIS_YAW, 1.0),
    "d": (AXIS_YAW, -1.0),
    "Right": (AXIS_YAW, -1.0),
    "q": (AXIS_SWAY, 1.0),
    "e": (AXIS_SWAY, -1.0),
    "r": (AXIS_HEAVE, 1.0),
    "f": (AXIS_HEAVE, -1.0),
}
ACTION_KEYS = ("equal", "minus", "l", "space")


def keycodes(
    display: xdisplay.Display,
) -> tuple[dict[int, tuple[int, float]], dict[int, str]]:
    movement: dict[int, tuple[int, float]] = {}
    actions: dict[int, str] = {}
    for name, command in MOVEMENT_KEYS.items():
        code = display.keysym_to_keycode(XK.string_to_keysym(name))
        if code:
            movement[code] = command
    for name in ACTION_KEYS:
        code = display.keysym_to_keycode(XK.string_to_keysym(name))
        if code:
            actions[code] = name
    return movement, actions


def pressed(keymap: list[int], keycode: int) -> bool:
    return bool(keymap[keycode // 8] & (1 << (keycode % 8)))


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = ReefKeyboardTeleop("reef_x11_teleop")
    display = xdisplay.Display()
    root = display.screen().root
    movement, actions = keycodes(display)
    grabbed_codes = set(movement) | set(actions)

    for code in grabbed_codes:
        root.grab_key(
            code,
            X.AnyModifier,
            False,
            X.GrabModeAsync,
            X.GrabModeAsync,
        )
    root.change_attributes(event_mask=X.KeyPressMask | X.KeyReleaseMask)
    display.sync()
    node.get_logger().info(
        "Browser keyboard controls active: WASD/QE/RF, arrows, +/-, L, Space"
    )

    event_held: set[int] = set()
    try:
        while rclpy.ok():
            while display.pending_events():
                event = display.next_event()
                if event.type == X.KeyPress and event.detail not in event_held:
                    event_held.add(event.detail)
                    action = actions.get(event.detail)
                    if action == "equal":
                        node.adjust_speed(0.15)
                    elif action == "minus":
                        node.adjust_speed(-0.15)
                    elif action == "l":
                        node.pulse(BUTTON_LIGHTS)
                    elif action == "space":
                        node.stop()
                elif event.type == X.KeyRelease:
                    event_held.discard(event.detail)

            keymap = display.query_keymap()
            axes = [0.0] * AXIS_COUNT
            for code, (axis, direction) in movement.items():
                if pressed(keymap, code):
                    axes[axis] += direction * node.speed
            axes = [min(1.0, max(-1.0, value)) for value in axes]

            if any(axes):
                node.command_axes(axes)
            elif not node.neutral_sent:
                node.stop()

            rclpy.spin_once(node, timeout_sec=0.0)
            time.sleep(1.0 / PUBLISH_HZ)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        for code in grabbed_codes:
            root.ungrab_key(code, X.AnyModifier)
        display.sync()
        display.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
