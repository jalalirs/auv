"""What a person sees while a vehicle is in the water.

Deliberately small. A dive is a thing to watch, and every panel added to the
screen is water taken away from it — so this reports the handful of numbers you
cannot fly without and nothing else. What it does show, it shows honestly:
whether anything is at the controls is stated rather than implied by the
trajectory, because a vehicle sinking under nobody's command and a vehicle
sinking under a bad one look identical from outside.
"""

from __future__ import annotations

import omni.ui as ui

# Deep water, two greys, and two colours that must never be mistaken for each
# other: whether anything is at the controls is the one thing on this screen you
# cannot afford to misread, so waiting is warm and flying is cold, and they are
# not neighbours.
#
# Written the way omni.ui reads them, which is 0xAABBGGRR and not the RGB it
# looks like. Getting that backwards is how "flying" and "waiting" ended up the
# same amber.
INK = 0xE6120D08    # RGB(8, 13, 18)     deep water
FAINT = 0xFF706A66  # RGB(102, 106, 112) labels
PLAIN = 0xFFD6D2CC  # RGB(204, 210, 214) numbers
LIVE = 0xFFF4C740   # RGB(64, 199, 244)  something is flying this
WARN = 0xFF4FA8F0   # RGB(240, 168, 79)  nobody is


class Hud:
    """One window, bottom left, over the water."""

    def __init__(self) -> None:
        self.window = ui.Window(
            "coral-city-hud",
            width=360, height=260,
            flags=(ui.WINDOW_FLAGS_NO_TITLE_BAR | ui.WINDOW_FLAGS_NO_RESIZE
                   | ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_MOVE
                   | ui.WINDOW_FLAGS_NO_CLOSE | ui.WINDOW_FLAGS_NO_COLLAPSE),
        )
        self.window.position_x = 24
        self.window.position_y = 24
        self.window.frame.set_style({"Window": {"background_color": INK}})

        self.place = None
        self.vehicle = None
        self.status = None
        self.rows = {}
        self._build()

    def _build(self) -> None:
        with self.window.frame:
            with ui.VStack(spacing=2, style={"margin": 16}):
                self.place = ui.Label("", height=22, style={
                    "color": PLAIN, "font_size": 19})
                self.vehicle = ui.Label("", height=18, style={
                    "color": FAINT, "font_size": 13})
                ui.Spacer(height=14)
                for key, label in (("depth", "depth"), ("speed", "speed"),
                                   ("heave", "vertical thrust"),
                                   ("elapsed", "elapsed")):
                    with ui.HStack(height=22):
                        ui.Label(label, width=130,
                                 style={"color": FAINT, "font_size": 14})
                        self.rows[key] = ui.Label(
                            "—", style={"color": PLAIN, "font_size": 17})
                ui.Spacer(height=14)
                self.status = ui.Label("", height=20, style={
                    "color": WARN, "font_size": 14})
                ui.Spacer(height=10)
                ui.Label("WASD  move    Q E  turn    SPACE C  rise, dive",
                         height=16, style={"color": FAINT, "font_size": 12})

    def opened(self, place: str, vehicle: str) -> None:
        self.place.text = place
        self.vehicle.text = vehicle

    def waiting(self, seconds: float) -> None:
        self.status.text = f"waiting for autonomy… {seconds:.0f}s"
        self.status.style = {"color": WARN, "font_size": 14}

    def flying(self, commands: int) -> None:
        self.status.text = f"autonomy flying — {commands} commands"
        self.status.style = {"color": LIVE, "font_size": 14}

    def by_hand(self) -> None:
        self.status.text = "you have the controls"
        self.status.style = {"color": LIVE, "font_size": 14}

    def untended(self) -> None:
        self.status.text = "nobody is flying this vehicle"
        self.status.style = {"color": WARN, "font_size": 14}

    def finished(self) -> None:
        self.status.text = "the dive is over"
        self.status.style = {"color": FAINT, "font_size": 14}

    def show(self, state: dict) -> None:
        thrust = state.get("thrust") or [0.0] * 6
        heave = sum(thrust[4:6]) / 2.0 if len(thrust) >= 6 else 0.0
        self.rows["depth"].text = f"{state['depthM']:.3f} m"
        self.rows["speed"].text = f"{state['speedMs']:.3f} m/s"
        self.rows["heave"].text = f"{heave:+.3f}"
        self.rows["elapsed"].text = f"{state['t']:.1f} s"

    def close(self) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None
