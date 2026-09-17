"""A light meter, instead of a formula.

The exposure used to be computed from depth: how much daylight is left at the
vehicle's depth, and an ISO off that. It is a good formula and it is not a
light meter, and the difference shows the moment anything else in the frame is
producing light. A lamp set correctly for a wreck at six hundred metres blows
the frame out at six, because at six metres the formula has already decided the
scene is bright and the lamp is on top of that. Every lamp setting on this
platform has been a compromise between two depths for that reason.

So: meter the frame. Point the camera, look at what is actually in the picture,
and set the exposure from that. Which is what anybody with a camera does.

**Once, and then held.** Not a renderer's automatic exposure, which tracks
continuously and brightens a dark scene until it looks normal. That destroys
exactly the information a dive is meant to carry — how much light there is at
fifteen metres — and makes two runs of one dive disagree because the camera
happened to be pointing somewhere else. A diver meters on the way down and
shoots; the picture gets darker as they go deeper, and that is the truth.

The arithmetic is here, with no renderer in it, because it is the part that can
be wrong in a way nobody notices.
"""

from __future__ import annotations

import math

# Where a scene should sit. Middle grey is 0.18 in linear light and about 0.46
# through a display curve, and the frame this meters is already through one.
AIM = 0.42

# And what must not blow. Underwater the bright things are sand and whatever is
# closest to a lamp, and both are small parts of a frame, so this is a high
# percentile rather than the maximum: a dozen specular pixels on a lamp housing
# are not a reason to underexpose a reef.
CEILING = 0.90
HIGHLIGHT = 99.5

# What a camera on this platform can actually do. Not unbounded: an exposure
# that can reach any value hides a scene that has no light in it, which is a
# thing a dive at four hundred metres with the lamps off genuinely is.
DIMMEST = 25.0
BRIGHTEST = 12_000.0

# How hard to move each time. The tonemapper between the scene and the pixel is
# a curve, so the step from a measurement is an estimate and not an answer;
# under-stepping converges, over-stepping rings.
DAMPING = 0.8
ROUNDS = 4


def brightness_of(pixels) -> tuple[float, float]:
    """What is in this frame: the middle of it, and the bright end of it.

    The middle is a centre-weighted average, which is what a camera meters on,
    because the thing being photographed is usually in the middle and the water
    column above it usually is not. Luminance is Rec. 709, on the frame as it
    comes out of the renderer.
    """
    import numpy as np

    frame = np.asarray(pixels, dtype="float32")
    if frame.ndim == 3 and frame.shape[2] >= 3:
        frame = frame[:, :, :3]
    if frame.max() > 1.5:
        frame = frame / 255.0
    light = (0.2126 * frame[..., 0] + 0.7152 * frame[..., 1]
             + 0.0722 * frame[..., 2])

    tall, wide = light.shape
    y = (np.arange(tall, dtype="float32") - (tall - 1) / 2) / max(tall / 2, 1)
    x = (np.arange(wide, dtype="float32") - (wide - 1) / 2) / max(wide / 2, 1)
    # A soft centre weight, not a spot: falls to about a fifth at the corners.
    weight = np.exp(-1.6 * (y[:, None] ** 2 + x[None, :] ** 2))

    middle = float((light * weight).sum() / weight.sum())
    bright = float(np.percentile(light, HIGHLIGHT))
    return middle, bright


def next_iso(iso_now: float, middle: float, bright: float,
             aim: float = AIM, ceiling: float = CEILING) -> float:
    """The ISO to try next, given what the last frame came out at.

    Two answers and the smaller wins: the one that puts the middle of the frame
    where a photographer would put it, and the one that keeps the bright end
    off the ceiling. Highlights that clip cannot be recovered and a slightly
    dark frame can, which is the whole reason a camera errs this way.
    """
    iso_now = max(float(iso_now), 1e-6)

    for_the_middle = iso_now * math.exp(
        DAMPING * math.log(aim / max(middle, 1e-4)))
    for_the_highlights = iso_now * math.exp(
        DAMPING * math.log(ceiling / max(bright, 1e-4)))

    # Always, not only when the frame is already clipping. A guard that waits
    # until the highlights are gone is not a guard: the first version only
    # applied when `bright > ceiling`, so a frame with its bright end at 0.78
    # was read as having headroom, the exposure was raised for the mid-tones,
    # and every view in the sheet came back with its top percentile at pure
    # white. The limit is on where the exposure may go, which is a question
    # about the next frame and not about this one.
    #
    # The smaller wins. Clipped highlights cannot be recovered and a slightly
    # dark frame can, which is the whole reason a camera errs this way.
    return float(min(BRIGHTEST,
                     max(DIMMEST, min(for_the_middle, for_the_highlights))))


def settled(middle: float, bright: float,
            aim: float = AIM, ceiling: float = CEILING) -> bool:
    """Close enough to stop. A third of a stop, which nobody can see."""
    if bright > ceiling * 1.02:
        return False
    return abs(math.log2(max(middle, 1e-4) / aim)) < 0.33


class Meter:
    """The loop: look, adjust, look again, and then stop looking.

    Stops on purpose. A meter that kept running would be the renderer's own
    automatic exposure by another name, and would undo the reason this platform
    turned that off: a dive is a measurement of how much light there is down
    there, and a camera that hides the answer is not carrying it.
    """

    def __init__(self, iso: float, rounds: int = ROUNDS,
                 aim: float = AIM, ceiling: float = CEILING) -> None:
        self.iso = float(iso)
        self.began_at = float(iso)
        self.left = int(rounds)
        self.aim = float(aim)
        self.ceiling = float(ceiling)
        self.done = False
        self.middle = None
        self.bright = None
        self.why = None

    def read(self, pixels) -> float | None:
        """One frame in. The ISO to set, or None if nothing should change.

        A frame with no light in it at all is not metered off: at the start of
        a run the renderer has often not drawn anything yet, and exposing for a
        black rectangle would open the camera all the way and then hold it
        there for the rest of the dive.
        """
        if self.done:
            return None
        middle, bright = brightness_of(pixels)
        if bright < 1e-4:
            return None
        self.middle, self.bright = middle, bright
        self.left -= 1

        if settled(middle, bright, self.aim, self.ceiling):
            self.done, self.why = True, "settled"
            return None
        if self.left <= 0:
            self.done, self.why = True, "out of rounds"

        was, self.iso = self.iso, next_iso(self.iso, middle, bright,
                                           self.aim, self.ceiling)
        return self.iso if abs(self.iso - was) > 0.5 else None

    def report(self) -> dict:
        """What it did, for the log. An exposure nobody can account for is a
        number somebody will later take for a measurement."""
        return {"iso": round(self.iso, 1), "from": round(self.began_at, 1),
                "middleOfFrame": None if self.middle is None else round(self.middle, 3),
                "brightEnd": None if self.bright is None else round(self.bright, 3),
                "aim": self.aim, "why": self.why or "still looking"}
