"""Every dimension of the nano vehicle, in millimetres, in one place.

Frame: x forward, y to port (left when looking forward), z up. Right-handed,
the same as the simulator's body frame, so a thruster listed here can be
copied into a dynamics.json without a sign flip.

Bought parts are recorded as the supplier states them, with the source, and
the frame is designed around them. Nothing below is a number somebody liked.
"""

# ── the dry hull: Blue Robotics 3" locking series ────────────────────────────
# https://bluerobotics.com/store/watertight-enclosures/locking-series/wte-locking-tube-r1-vp/
# Cast acrylic. Inner 76.2 ± 2.0, outer 88.9 ± 0.7, 150 mm long, rated 275 m.
TUBE_OD = 88.9
TUBE_ID = 76.2
TUBE_LENGTH = 150.0
# How far a locking flange and its cap reach past the tube end. Not on the
# product page; taken from the enclosure user guide's drawing at a glance and
# TO BE CHECKED against the CAD model before the frame is printed.
CAP_REACH = 20.0
# Where the tube sits along the body. Forward of centre so the two horizontal
# thrusters fit behind its rear cap.
TUBE_X = 15.0
# Clearance around the tube in the cradle, on the diameter.
TUBE_CLEARANCE = 0.6

# ── the body: a Titan at 0.55 scale, from Geneinno's 390 × 347 × 165 ─────────
# 0.55 rather than 0.5 because the tube is 88.9 mm across and a 83 mm tall
# body cannot hold it. 215 × 191 × 91 would be the exact figure.
BODY_L = 220.0       # the skin; the horizontal pods reach a further POD_OVERHANG
BODY_W = 190.0       # 180 would put the front verticals into the tube
BODY_H = 100.0
# The Titan's shape, as sections along x from stern to nose: (x, width,
# height, corner radius). Full width from the stern to just ahead of the
# front verticals, then the nose narrows and drops, which is where the look
# comes from. The nose must still stay taller than the tube.
SECTIONS = [
    (-BODY_L / 2, 176.0, 96.0, 24.0),
    (-60.0,       BODY_W, BODY_H, 26.0),
    ( 70.0,       BODY_W, BODY_H, 26.0),
    ( 95.0,       160.0, 98.0, 24.0),
    ( BODY_L / 2, 126.0, 96.0, 22.0),   # 96: the tube bore is 89.5 and needs 3 mm of skin over it
]
SKIN = 2.5           # MJF PA12; JLC3DP's floor is 1.2
BULKHEAD = 4.0       # the two plates the tube is clamped between
BULKHEAD_X = (TUBE_X - 50.0, TUBE_X + 50.0)

# ── thrusters: 6, the Titan's 4 vertical + 2 horizontal ──────────────────────
# A 30–40 mm micro thruster in a duct. The duct bore is the space the unit
# needs; the exact unit is chosen next and this number follows it.
DUCT_D = 40.0
DUCT_WALL = 3.0
# Vertical, at the four corners, pushing along z.
VERTICAL = [
    ("vertical-front-port",      ( 50.0,  70.0, 0.0)),
    ("vertical-front-starboard", ( 50.0, -70.0, 0.0)),
    ("vertical-rear-port",       (-50.0,  70.0, 0.0)),
    ("vertical-rear-starboard",  (-50.0, -70.0, 0.0)),
]
# Horizontal, in two pods on the stern corners like the Titan's, pushing
# along x. A pod is a duct with its own skin that overhangs the stern.
POD_LENGTH = 50.0
POD_OVERHANG = 20.0
HORIZONTAL = [
    ("horizontal-port",      (-BODY_L / 2 - POD_OVERHANG + POD_LENGTH / 2,  72.0, 0.0)),
    ("horizontal-starboard", (-BODY_L / 2 - POD_OVERHANG + POD_LENGTH / 2, -72.0, 0.0)),
]

# ── the window ───────────────────────────────────────────────────────────────
WINDOW_D = TUBE_ID   # the front cap is the window; the bezel shows the clear part
