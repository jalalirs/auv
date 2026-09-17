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
    got = metering.next_iso(200.0, middle=0.46, bright=0.50)
    assert abs(got - 200.0) < 1.0, got


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
