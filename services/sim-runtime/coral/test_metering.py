"""A camera that meters the frame rather than computing exposure from depth."""

import math

import numpy as np

from coral import metering


def a_frame(level, wide=160, tall=90, hot=0.0):
    """A flat frame at some level, with an optional small blown patch."""
    frame = np.full((tall, wide, 3), level, dtype="float32")
    if hot > 0.0:
        many = max(1, int(hot * wide * tall))
        frame.reshape(-1, 3)[:many] = 1.0
    return frame


def test_a_flat_frame_reads_as_its_own_level():
    middle, bright = metering.brightness_of(a_frame(0.4))
    assert abs(middle - 0.4) < 0.01 and abs(bright - 0.4) < 0.01


def test_eight_bit_pixels_are_understood():
    """The renderer hands back bytes, not fractions."""
    eight = (a_frame(0.5) * 255).astype("uint8")
    middle, _ = metering.brightness_of(eight)
    assert abs(middle - 0.5) < 0.01


def test_alpha_is_not_light():
    rgba = np.dstack([a_frame(0.3), np.ones((90, 160), dtype="float32")])
    middle, _ = metering.brightness_of(rgba)
    assert abs(middle - 0.3) < 0.01


def test_it_meters_the_middle_and_not_the_edges():
    """What is being photographed is in the middle; the water column above it
    is not, and a frame that averages the whole picture exposes for the water."""
    frame = np.full((90, 160, 3), 0.05, dtype="float32")
    frame[30:60, 50:110] = 0.6
    middle, _ = metering.brightness_of(frame)
    flat = float(frame.mean())
    assert middle > flat * 1.3, (middle, flat)


def test_a_dark_frame_is_opened_up():
    assert metering.next_iso(200.0, middle=0.10, bright=0.20) > 200.0


def test_a_bright_frame_is_stopped_down():
    assert metering.next_iso(200.0, middle=0.80, bright=0.90) < 200.0


def test_highlights_win_over_the_middle():
    """A dim reef with a lamp hotspot in it: opening up for the reef would
    clip the hotspot, and a clipped highlight cannot be recovered."""
    with_hotspot = metering.next_iso(200.0, middle=0.20, bright=0.99)
    without = metering.next_iso(200.0, middle=0.20, bright=0.30)
    assert with_hotspot < without


def test_a_frame_under_the_ceiling_is_not_pushed_up_to_it():
    """A highlight guard is a limit, not a target. Otherwise a dark frame with
    nothing bright in it gets driven to the ceiling by the guard itself."""
    got = metering.next_iso(200.0, middle=metering.AIM, bright=0.50)
    assert abs(got - 200.0) < 1.0, got


def test_the_guard_applies_before_the_highlights_are_gone():
    """It only applied once the frame was already clipping, which is not a
    guard. A sheet whose bright end read 0.78 was judged to have headroom, the
    exposure was raised for the mid-tones, and every view came back with its
    top half-percent at pure white."""
    headroom = metering.next_iso(200.0, middle=0.34, bright=0.78)
    unlimited = 200.0 * math.exp(
        metering.DAMPING * math.log(metering.AIM / 0.34))
    assert headroom < unlimited, (headroom, unlimited)
    # And not below what the highlights themselves allow.
    assert headroom > 200.0


def test_it_stays_inside_what_a_camera_can_do():
    """A dive at four hundred metres with the lamps off is dark, and an
    exposure that can reach any value would hide that."""
    assert metering.next_iso(200.0, 1e-6, 1e-6) <= metering.BRIGHTEST
    assert metering.next_iso(200.0, 1.0, 1.0) >= metering.DIMMEST


def test_it_converges_on_a_scene_seen_through_a_curve():
    """The tonemapper between the scene and the pixel is a curve, so one step
    from one measurement is an estimate. A few rounds have to land."""
    scene = 0.0009          # the light actually coming off the reef

    def through_the_camera(iso):
        # A tonemapper's shape: linear at the bottom, compressing at the top.
        exposed = scene * iso
        return exposed / (1.0 + exposed)

    iso = 200.0
    for _ in range(metering.ROUNDS + 2):
        level = through_the_camera(iso)
        middle, bright = level, level
        if metering.settled(middle, bright):
            break
        iso = metering.next_iso(iso, middle, bright)
    landed = through_the_camera(iso)
    assert abs(math.log2(landed / metering.AIM)) < 0.33, (iso, landed)


def test_a_scene_with_no_light_in_it_stays_dark():
    """Held at the ceiling of what the camera can do, which is the honest
    answer: the picture is dark because there is no light, and a meter that
    brightened it until it looked normal would be destroying the one thing the
    dive was measuring."""
    iso = metering.DIMMEST
    for _ in range(6):
        iso = metering.next_iso(iso, middle=0.001, bright=0.002)
    assert iso <= metering.BRIGHTEST
    assert not metering.settled(0.001, 0.002)


def test_the_meter_stops_and_says_why():
    meter = metering.Meter(200.0)
    meter.read(a_frame(metering.AIM))
    assert meter.done and meter.report()["why"] == "settled"


def test_the_meter_gives_up_after_its_rounds():
    """Better a frame a third of a stop out than a camera still hunting on the
    twentieth frame of a dive."""
    meter = metering.Meter(200.0, rounds=2)
    for _ in range(5):
        meter.read(a_frame(0.02))
    assert meter.done and meter.report()["why"] == "out of rounds"


def test_a_black_frame_is_not_metered_off():
    """Kit has often drawn nothing at all on the first frames of a run, and a
    camera opened all the way for a black rectangle stays there."""
    meter = metering.Meter(200.0)
    assert meter.read(a_frame(0.0)) is None
    assert not meter.done and meter.iso == 200.0


def test_what_it_did_is_on_the_record():
    meter = metering.Meter(200.0)
    meter.read(a_frame(0.08))
    said = meter.report()
    assert said["from"] == 200.0 and said["iso"] > 200.0
    assert said["middleOfFrame"] is not None and said["aim"] == metering.AIM


def test_the_bright_end_survives_being_sampled_down():
    """A meter reads a smaller copy of the frame, because it runs on the frame
    loop. Averaging pixels together to make that copy throws the bright tail
    away: the highlight test is a percentile, and a percentile of an averaged
    image is not the percentile of the image."""
    rng = np.random.default_rng(3)
    frame = rng.uniform(0.1, 0.4, (240, 320, 3)).astype("float32")
    # A scattering of small specular highlights, as a lamp on wet rock makes.
    at = rng.integers(0, 240 * 320, 900)
    frame.reshape(-1, 3)[at] = 0.98

    _, whole = metering.brightness_of(frame)
    _, sampled = metering.brightness_of(frame[::3, ::3])
    assert abs(sampled - whole) < 0.1, (sampled, whole)


# ── the colour the water put on everything ───────────────────────────────────

def _flat(colour, tall=90, wide=160):
    import numpy as np
    frame = np.zeros((tall, wide, 3), dtype="float32")
    for c in range(3):
        frame[..., c] = colour[c]
    return frame


def test_a_neutral_frame_asks_for_nothing():
    got = metering.balance_for(metering.cast_of(_flat((0.4, 0.4, 0.4))))
    assert max(abs(one - 1.0) for one in got) < 0.01, got


def test_a_green_frame_turns_green_down_and_red_up():
    """The cast this whole thing exists for."""
    red, green, blue = metering.balance_for(
        metering.cast_of(_flat((0.18, 0.42, 0.33))))
    assert red > 1.0 and green < 1.0, (red, green, blue)
    assert red > blue > green, (red, green, blue)


def test_balancing_holds_the_luminance():
    """Brightness is the exposure meter's job. Two loops on one number never settle."""
    cast = (0.18, 0.42, 0.33)
    gains = metering.balance_for(metering.cast_of(_flat(cast)),
                                 towards=1.0)
    luma = (0.2126, 0.7152, 0.0722)
    before = sum(w * c for w, c in zip(luma, cast))
    after = sum(w * c * g for w, c, g in zip(luma, cast, gains))
    assert abs(after - before) < 1e-4 * before, (before, after)


def test_it_builds_on_the_gains_already_applied():
    """The frame it read was rendered through the last answer, not through none."""
    first = metering.balance_for(metering.cast_of(_flat((0.18, 0.42, 0.33))))
    # Apply them, and what comes back is closer to neutral than it was.
    once = tuple(c * g for c, g in zip((0.18, 0.42, 0.33), first))
    second = metering.balance_for(metering.cast_of(_flat(once)), already=first)
    def spread(v):
        return max(v) / max(min(v), 1e-6)

    twice = tuple(c * g for c, g in zip((0.18, 0.42, 0.33), second))
    assert spread(twice) < spread(once), (once, twice)


def test_it_settles_rather_than_oscillating():
    """Round after round on the same scene converges instead of ringing."""
    scene = (0.18, 0.42, 0.33)
    gains = (1.0, 1.0, 1.0)
    seen = []
    for _ in range(8):
        shown = tuple(c * g for c, g in zip(scene, gains))
        seen.append(max(shown) / max(min(shown), 1e-6))
        gains = metering.balance_for(metering.cast_of(_flat(shown)),
                                     already=gains)
    assert seen[-1] < seen[0], seen
    assert abs(seen[-1] - seen[-2]) < 0.02, seen


def test_a_reef_keeps_some_of_its_sea():
    """Not full grey-world: a picture of the sea should still look like one."""
    gains = metering.balance_for(metering.cast_of(_flat((0.18, 0.42, 0.33))))
    settled = tuple(c * g for c, g in zip((0.18, 0.42, 0.33), gains))
    assert max(settled) / min(settled) > 1.05, settled


def test_no_gain_past_the_clamp():
    """A camera cannot invent light, however little red is left."""
    for cast in ((0.001, 0.5, 0.4), (0.4, 0.001, 0.3), (0.5, 0.4, 0.0005)):
        for one in metering.balance_for(metering.cast_of(_flat(cast))):
            assert 1.0 / metering.MOST_GAIN <= one <= metering.MOST_GAIN, (cast, one)


def test_a_black_frame_changes_nothing():
    """Nothing to read is not a reason to do something."""
    got = metering.balance_for(metering.cast_of(_flat((0.0, 0.0, 0.0))),
                               already=(1.1, 0.9, 1.0))
    assert got == (1.1, 0.9, 1.0), got
