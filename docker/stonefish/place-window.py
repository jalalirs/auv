#!/usr/bin/env python3
"""Keep Stonefish inside Xpra's visible desktop after X display resizing."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import POINTER, byref, c_char_p, c_int, c_uint, c_ulong, c_void_p


def main() -> int:
    display_name = os.environ.get("DISPLAY", ":100").encode()
    wanted_title = os.environ.get("STONEFISH_WINDOW_TITLE", "Stonefish Simulator")
    timeout = float(os.environ.get("STONEFISH_WINDOW_TIMEOUT", "120"))

    x11 = ctypes.CDLL("libX11.so.6")
    x11.XOpenDisplay.argtypes = [c_char_p]
    x11.XOpenDisplay.restype = c_void_p
    x11.XDefaultRootWindow.argtypes = [c_void_p]
    x11.XDefaultRootWindow.restype = c_ulong
    x11.XQueryTree.argtypes = [
        c_void_p,
        c_ulong,
        POINTER(c_ulong),
        POINTER(c_ulong),
        POINTER(POINTER(c_ulong)),
        POINTER(c_uint),
    ]
    x11.XQueryTree.restype = c_int
    x11.XFetchName.argtypes = [c_void_p, c_ulong, POINTER(c_char_p)]
    x11.XFetchName.restype = c_int
    x11.XMoveWindow.argtypes = [c_void_p, c_ulong, c_int, c_int]
    x11.XMoveWindow.restype = c_int
    x11.XMapRaised.argtypes = [c_void_p, c_ulong]
    x11.XFlush.argtypes = [c_void_p]
    x11.XCloseDisplay.argtypes = [c_void_p]
    x11.XFree.argtypes = [c_void_p]

    deadline = time.monotonic() + timeout
    display = None
    while display is None and time.monotonic() < deadline:
        display = x11.XOpenDisplay(display_name)
        if display is None:
            time.sleep(0.25)
    if display is None:
        print(f"Could not open X display {display_name.decode()}", file=sys.stderr)
        return 1

    try:
        root = x11.XDefaultRootWindow(display)
        while time.monotonic() < deadline:
            root_return = c_ulong()
            parent_return = c_ulong()
            children = POINTER(c_ulong)()
            child_count = c_uint()
            if x11.XQueryTree(
                display,
                root,
                byref(root_return),
                byref(parent_return),
                byref(children),
                byref(child_count),
            ):
                try:
                    for index in range(child_count.value):
                        window = children[index]
                        title_pointer = c_char_p()
                        title = ""
                        if x11.XFetchName(display, window, byref(title_pointer)):
                            if title_pointer.value:
                                title = title_pointer.value.decode(errors="replace")
                            if title_pointer:
                                x11.XFree(title_pointer)
                        if wanted_title in title:
                            x11.XMoveWindow(display, window, 0, 0)
                            x11.XMapRaised(display, window)
                            x11.XFlush(display)
                            print(f"Placed {title!r} at 0,0", flush=True)
                            return 0
                finally:
                    if children:
                        x11.XFree(children)
            time.sleep(0.25)
    finally:
        x11.XCloseDisplay(display)

    print(f"Window {wanted_title!r} did not appear within {timeout:g}s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
