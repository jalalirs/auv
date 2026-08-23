#!/usr/bin/env python3
"""Low-latency terminal keyboard control for DAVE's manual-control bridge."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy


AXIS_SWAY = 0
AXIS_SURGE = 1
AXIS_YAW = 4
AXIS_HEAVE = 5

BUTTON_STABILIZE = 0
BUTTON_FASTER = 1
BUTTON_SLOWER = 2
BUTTON_DEPTH_HOLD = 3
BUTTON_DISARM = 8
BUTTON_ARM = 9

AXIS_COUNT = 6
BUTTON_COUNT = 17
COMMAND_HOLD_SECONDS = 0.70
PUBLISH_HZ = 30.0

HELP = """
BlueROV2 keyboard control

  W / Up       forward       S / Down     reverse
  A / Left     yaw left      D / Right    yaw right
  Q / E        strafe left / right
  R / F        rise / dive
  C / X        arm / disarm
  H / J        depth hold / stabilize
  + / -        faster / slower
  Space        stop          Ctrl-C       stop, disarm, exit

Hold a movement key down. The terminal's key repeat keeps the command alive.
Keep the Foxglove overview and forward camera visible while driving.
""".strip()


class KeyboardTeleop(Node):
    """Publish keyboard input as sensor_msgs/Joy for DAVE."""

    def __init__(self) -> None:
        super().__init__("auv_keyboard_teleop")
        self.publisher = self.create_publisher(Joy, "/keyboard/joy", 10)
        self.axes = [0.0] * AXIS_COUNT
        self.buttons = [0] * BUTTON_COUNT
        self.button_release_pending = False
        self.command_deadline_ns = 0
        self.neutral_sent = True
        self.create_timer(1.0 / PUBLISH_HZ, self._publish_active_command)

    def movement(self, axis: int, value: float) -> None:
        self.axes = [0.0] * AXIS_COUNT
        self.axes[axis] = value
        self.command_deadline_ns = (
            self.get_clock().now().nanoseconds
            + int(COMMAND_HOLD_SECONDS * 1_000_000_000)
        )
        self.neutral_sent = False
        self.publish()

    def pulse(self, button: int) -> None:
        self.buttons[button] = 1
        self.publish()
        self.buttons[button] = 0
        self.button_release_pending = True

    def stop(self, disarm: bool = False) -> None:
        self.axes = [0.0] * AXIS_COUNT
        self.command_deadline_ns = 0
        if disarm:
            self.buttons[BUTTON_DISARM] = 1
        self.publish()
        self.buttons = [0] * BUTTON_COUNT
        self.neutral_sent = True

    def publish(self) -> None:
        message = Joy()
        message.header.stamp = self.get_clock().now().to_msg()
        message.axes = list(self.axes)
        message.buttons = list(self.buttons)
        self.publisher.publish(message)

    def _publish_active_command(self) -> None:
        if self.button_release_pending:
            self.publish()
            self.button_release_pending = False

        now_ns = self.get_clock().now().nanoseconds
        if self.command_deadline_ns > now_ns:
            self.publish()
        elif not self.neutral_sent:
            self.stop()


def read_key(file_descriptor: int) -> str:
    """Read one key, decoding ANSI arrow-key escape sequences."""
    first = os.read(file_descriptor, 1)
    if first != b"\x1b":
        return first.decode(errors="ignore")

    sequence = first
    for _ in range(2):
        ready, _, _ = select.select([file_descriptor], [], [], 0.03)
        if not ready:
            break
        sequence += os.read(file_descriptor, 1)

    return {
        b"\x1b[A": "UP",
        b"\x1b[B": "DOWN",
        b"\x1b[C": "RIGHT",
        b"\x1b[D": "LEFT",
    }.get(sequence, "")


def handle_key(node: KeyboardTeleop, key: str) -> None:
    movement = {
        "w": (AXIS_SURGE, -1.0),
        "UP": (AXIS_SURGE, -1.0),
        "s": (AXIS_SURGE, 1.0),
        "DOWN": (AXIS_SURGE, 1.0),
        "a": (AXIS_YAW, 1.0),
        "LEFT": (AXIS_YAW, 1.0),
        "d": (AXIS_YAW, -1.0),
        "RIGHT": (AXIS_YAW, -1.0),
        "q": (AXIS_SWAY, 1.0),
        "e": (AXIS_SWAY, -1.0),
        "r": (AXIS_HEAVE, -1.0),
        "f": (AXIS_HEAVE, 1.0),
    }
    buttons = {
        "c": BUTTON_ARM,
        "x": BUTTON_DISARM,
        "h": BUTTON_DEPTH_HOLD,
        "j": BUTTON_STABILIZE,
        "+": BUTTON_FASTER,
        "=": BUTTON_FASTER,
        "-": BUTTON_SLOWER,
        "_": BUTTON_SLOWER,
    }

    normalized = key.lower() if len(key) == 1 else key
    if normalized in movement:
        node.movement(*movement[normalized])
    elif normalized in buttons:
        node.pulse(buttons[normalized])
    elif key == " ":
        node.stop()


def main(args: list[str] | None = None) -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("keyboard_teleop requires an interactive terminal")

    rclpy.init(args=args)
    node = KeyboardTeleop()
    file_descriptor = sys.stdin.fileno()
    previous_terminal = termios.tcgetattr(file_descriptor)
    print(HELP, flush=True)

    try:
        tty.setcbreak(file_descriptor)
        while rclpy.ok():
            ready, _, _ = select.select([file_descriptor], [], [], 0.02)
            if ready:
                handle_key(node, read_key(file_descriptor))
            rclpy.spin_once(node, timeout_sec=0.0)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop(disarm=True)
        for _ in range(3):
            rclpy.spin_once(node, timeout_sec=0.02)
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous_terminal)
        node.destroy_node()
        rclpy.shutdown()
        print("\nStopped and disarmed.", flush=True)


if __name__ == "__main__":
    main()
