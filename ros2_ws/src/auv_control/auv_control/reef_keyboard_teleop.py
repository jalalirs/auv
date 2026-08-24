#!/usr/bin/env python3
"""Terminal keyboard control for the Stonefish MOLA AUV."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty

import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Joy


AXIS_SWAY = 0
AXIS_SURGE = 1
AXIS_YAW = 3
AXIS_HEAVE = 4
BUTTON_LIGHTS = 8
AXIS_COUNT = 8
BUTTON_COUNT = 13
COMMAND_HOLD_SECONDS = 0.70
PUBLISH_HZ = 30.0

HELP = """
Living Reef keyboard control

  W / Up       forward       S / Down     reverse
  A / Left     yaw left      D / Right    yaw right
  Q / E        strafe left / right
  R / F        rise / dive
  + / -        faster / slower
  L            toggle lights
  Space        stop          Ctrl-C       stop and exit

The Stonefish vehicle does not require arming. Hold movement keys down.
""".strip()


class ReefKeyboardTeleop(Node):
    """Publish an eight-axis Joy command understood by MOLA's allocator."""

    def __init__(self, node_name: str = "reef_keyboard_teleop") -> None:
        super().__init__(node_name)
        self.publisher = self.create_publisher(Joy, "/joy", 10)
        self.axes = [0.0] * AXIS_COUNT
        self.buttons = [0] * BUTTON_COUNT
        self.speed = 0.65
        self.command_deadline_ns = 0
        self.neutral_sent = True
        self.button_release_pending = False
        self.create_timer(1.0 / PUBLISH_HZ, self._publish_active_command)

    def movement(self, axis: int, direction: float) -> None:
        axes = [0.0] * AXIS_COUNT
        axes[axis] = direction * self.speed
        self.command_axes(axes)

    def command_axes(self, axes: list[float]) -> None:
        self.axes = list(axes)
        self.command_deadline_ns = (
            self.get_clock().now().nanoseconds
            + int(COMMAND_HOLD_SECONDS * 1_000_000_000)
        )
        self.neutral_sent = False
        self.publish()

    def adjust_speed(self, delta: float) -> None:
        self.speed = min(1.0, max(0.20, self.speed + delta))
        print(f"\rCommand scale: {self.speed:.0%}   ", end="", flush=True)

    def pulse(self, button: int) -> None:
        self.buttons[button] = 1
        self.publish()
        self.buttons[button] = 0
        self.button_release_pending = True

    def stop(self) -> None:
        self.axes = [0.0] * AXIS_COUNT
        self.command_deadline_ns = 0
        self.publish()
        self.neutral_sent = True

    def publish(self) -> None:
        message = Joy()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "keyboard"
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


def handle_key(node: ReefKeyboardTeleop, key: str) -> None:
    movement = {
        "w": (AXIS_SURGE, 1.0),
        "UP": (AXIS_SURGE, 1.0),
        "s": (AXIS_SURGE, -1.0),
        "DOWN": (AXIS_SURGE, -1.0),
        "a": (AXIS_YAW, 1.0),
        "LEFT": (AXIS_YAW, 1.0),
        "d": (AXIS_YAW, -1.0),
        "RIGHT": (AXIS_YAW, -1.0),
        "q": (AXIS_SWAY, 1.0),
        "e": (AXIS_SWAY, -1.0),
        "r": (AXIS_HEAVE, 1.0),
        "f": (AXIS_HEAVE, -1.0),
    }
    normalized = key.lower() if len(key) == 1 else key
    if normalized in movement:
        node.movement(*movement[normalized])
    elif normalized in ("+", "="):
        node.adjust_speed(0.15)
    elif normalized in ("-", "_"):
        node.adjust_speed(-0.15)
    elif normalized == "l":
        node.pulse(BUTTON_LIGHTS)
    elif key == " ":
        node.stop()


def main(args: list[str] | None = None) -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("reef_keyboard_teleop requires an interactive terminal")

    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = ReefKeyboardTeleop()
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
        if rclpy.ok():
            node.stop()
            for _ in range(3):
                rclpy.spin_once(node, timeout_sec=0.02)
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous_terminal)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    main()
