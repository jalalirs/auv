"""The thin pipe a vehicle has to the surface.

Underwater there is no radio. What there is, is sound: a few kilobits a second
on a good day, seconds of latency because sound crosses a kilometre of water in
two thirds of one, and a channel that drops packets when the range is long or
the water is noisy. That constraint is not a detail — it is most of what shapes
real AUV autonomy. A vehicle that could ask the ship whenever it was unsure
would be a different vehicle from the ones anybody builds.

Nothing here modelled it. A controller that phones home for a decision got its
answer instantly and losslessly, which is the one arrangement that cannot
happen, and a benchmark run that way rewards exactly the controller that would
fail at sea.

What is modelled: the time a message takes, whether it arrives at all, and that
the channel is half duplex so two things cannot be in it at once. What is not:
multipath, Doppler on a moving platform, and the way a modem renegotiates its
rate — each of which is real and each of which makes the channel worse rather
than better, so a controller that copes here is not being flattered.
"""

from __future__ import annotations


import numpy as np

# How fast sound goes in seawater. It varies with temperature, salinity and
# pressure by a few per cent; a few per cent of two thirds of a second is not
# what decides whether a controller can work this way.
SOUND_MS = 1500.0


class Modem:
    """An acoustic link between a vehicle and whoever is listening."""

    def __init__(self, said: dict | None = None, seed: int = 0) -> None:
        said = dict(said or {})
        # A WHOI micro-modem does 80 bps reliably and a few kilobits when the
        # water allows. Two thousand is a fair day at a few hundred metres.
        self.bits_per_second = float(said.get("bitsPerSecond", 2000.0))
        self.range_m = float(said.get("rangeM", 2000.0))
        # How often a message is simply lost at half the rated range. Real
        # links are worse than this in shallow water, where the surface and
        # the bottom both send copies of everything.
        self.loss_share = float(said.get("lossShare", 0.08))
        self._draw = np.random.RandomState(seed % (2 ** 32))

        self.sent = 0
        self.lost = 0
        self.bytes_sent = 0
        # When the channel is next free. Half duplex: one thing at a time.
        self.free_at = 0.0
        self.waiting: list[tuple[float, object]] = []

    def loss_at(self, metres: float) -> float:
        """How likely a message is to be lost, at this range.

        Rises with range and goes to certainty past the rated one. Sound
        spreads and absorbs; a modem does not have a cliff edge, but it does
        have a range past which nothing useful gets through.
        """
        if metres <= 0.0:
            return 0.0
        if metres >= self.range_m:
            return 1.0
        share = self.loss_share * (metres / (0.5 * self.range_m)) ** 2
        return max(0.0, min(1.0, share))

    def carries(self, size_bytes: int, metres: float) -> float:
        """How long a message of this size takes to cross this much water."""
        return metres / SOUND_MS + (size_bytes * 8.0) / max(1.0, self.bits_per_second)

    def send(self, t: float, size_bytes: int, metres: float, payload=None) -> float | None:
        """Put a message in the water. Returns when it lands, or None if lost.

        Refused rather than queued when the channel is busy: a modem that
        accepted everything and delivered it later would let a controller talk
        as much as it liked, which is the assumption this file exists to break.
        """
        if t < self.free_at:
            return None
        self.sent += 1
        self.bytes_sent += int(size_bytes)
        flight = self.carries(size_bytes, metres)
        self.free_at = t + flight
        if self._draw.random_sample() < self.loss_at(metres):
            self.lost += 1
            return None
        self.waiting.append((t + flight, payload))
        return t + flight

    def arrived(self, t: float) -> list:
        """Everything that has landed by now, in the order it was sent."""
        landed = [one for when, one in self.waiting if when <= t]
        self.waiting = [(when, one) for when, one in self.waiting if when > t]
        return landed

    def busy(self, t: float) -> bool:
        return t < self.free_at

    def said(self) -> dict:
        return {"bitsPerSecond": self.bits_per_second,
                "rangeM": self.range_m,
                "sent": self.sent,
                "lost": self.lost,
                "bytesSent": self.bytes_sent,
                "lostShare": None if self.sent == 0 else round(self.lost / self.sent, 3)}
