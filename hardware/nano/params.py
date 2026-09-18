"""Every dimension of the nano vehicle, in millimetres, in one place.

Frame: x forward, y to port (left when looking forward), z up. Right-handed,
the same as the simulator's body frame, so a thruster listed here can be
copied into a dynamics.json without a sign flip.

Bought parts are recorded as the supplier states them, with the source, and
the printed parts are designed around them. Nothing below is a number
somebody liked; where one is a guess it says so and says what would settle it.
"""

# ── the dry hull: Blue Robotics 3" locking series ────────────────────────────
# https://bluerobotics.com/store/watertight-enclosures/locking-series/wte-locking-tube-r1-vp/
# Cast acrylic. Inner 76.2 ± 2.0, outer 88.9 ± 0.7, 150 mm long, rated 275 m.
TUBE_OD = 88.9
TUBE_ID = 76.2
TUBE_LENGTH = 150.0
# How far a locking flange and its cap reach past the tube end. Not on the
# product page; a guess from the user guide's drawing. TO BE CHECKED against
# the CAD before the chassis is printed: it sets where the window is.
CAP_REACH = 20.0
TUBE_X = -1.0                # tube centre; the front cap face sits 2 mm inside the nose
TUBE_CLEARANCE = 0.6         # on the diameter, in the cradle
TUBE_FRONT = TUBE_X + TUBE_LENGTH / 2 + CAP_REACH   # the window's face, x = 100
TUBE_REAR = TUBE_X - TUBE_LENGTH / 2 - CAP_REACH    # the rear cap's face, x = -90

# ── the thruster: ApisQueen UG500 ────────────────────────────────────────────
# https://www.underwaterthruster.com/products/apisqueen-uq500-mini-brushless-thruster-motor-small-size-and-light-weight-perfect-for-small-size-rovs/
# 36 mm propeller, 47 mm long, 18.33 g, 400 g of thrust at most, 1.3 A at
# 12 V, 520 KV, 5–24 V, CW and CCW, $23.91. No ESC in the box.
# The motor body diameter and the mount pattern are not published. The hub
# below carries slots that take any pattern from 12 to 19 mm across, which
# covers every small outrunner, and the first unit to arrive is measured.
THRUSTER_PROP_D = 36.0
THRUSTER_LENGTH = 47.0
THRUSTER_MOTOR_D = 28.0      # a guess: a 2205-class outrunner. Measure it.
THRUSTER_THRUST_N = 3.92     # 400 gf
THRUSTER_MASS_G = 18.33
DUCT_D = 40.0                # 2 mm of tip clearance each side of the propeller
DUCT_WALL = 3.0
POD_OD = DUCT_D + 2 * DUCT_WALL
POD_LENGTH = 50.0
HUB_D = 24.0
HUB_T = 3.0
SPOKES = 3
SPOKE_W = 3.0

# ── the capsule: the Titan's orange body over the tube ───────────────────────
# A stadium in plan, half of it above the parting line as the orange cover
# and half below as part of the black chassis. 0.55 of the Titan's 390 × 347
# × 165 would be 215 × 191 × 91; the tube sets the capsule at 100 × 100.
CAPSULE_L = 207.0
CAPSULE_W = 100.0
CAPSULE_H = 100.0            # full height, top of cover to bottom of cradle
CAPSULE_X = 3.5              # centre; nose at 107, stern at -100
CAPSULE_SKIN = 2.5           # MJF PA12; JLC3DP's floor is 1.2
# The plan is a rounded rectangle, not a stadium: the tube's flat front cap
# has to sit inside the nose, and a semicircular nose would meet its corners.
CAPSULE_CORNER_R = 20.0
CAPSULE_CROWN_R = 18.0       # the fillet that domes the top
WINDOW_D = 82.0              # the opening the bezel frames, over the front cap
BEZEL_OD = 94.0
BEZEL_T = 5.0

# ── the chassis: the Titan's black base with the arms ────────────────────────
PLATE_L = 225.0
PLATE_W = 150.0
PLATE_X = -5.0               # spans -117.5 to 107.5
PLATE_Z = (-52.0, -46.0)     # bottom and top of the plate
ARM_W = 22.0

# ── thrusters, placed: the Titan's 4 vertical + 2 horizontal ─────────────────
# Vertical, in pods on the wings, outside the capsule, pushing along z.
# ±75 puts the pod's inner wall 2 mm off the capsule's side.
POD_Z = -20.0                # the vertical pods hang low, as the Titan's do
VERTICAL = [
    ("vertical-front-port",      ( 60.0,  75.0, POD_Z)),
    ("vertical-front-starboard", ( 60.0, -75.0, POD_Z)),
    ("vertical-rear-port",       (-50.0,  75.0, POD_Z)),
    ("vertical-rear-starboard",  (-50.0, -75.0, POD_Z)),
]
# Horizontal, in two pods off the stern corners, pushing along x.
HORIZONTAL = [
    ("horizontal-port",      (-105.0,  70.0, -25.0)),
    ("horizontal-starboard", (-105.0, -70.0, -25.0)),
]
# Where the cover screws to the chassis: four M3 bosses on the parting line.
BOSSES = [(70.0, 38.0), (70.0, -38.0), (-70.0, 38.0), (-70.0, -38.0)]
BOSS_D = 8.0
BOSS_H = 10.0
SCREW_D = 2.6                # M3 tapping into nylon

# ── vents, the tether eye, and ballast ───────────────────────────────────────
# The cover floods through the parting line and the stern; the vents let the
# air out of the crown, or the vehicle's buoyancy changes with its attitude.
VENT_D = 4.0
VENTS_X = [-60.0, -30.0, 0.0, 30.0, 60.0]
# Where the tether clips on, on the crown, a little behind the centre of
# buoyancy so a tug lifts the nose.
TETHER_EYE = (-15.0, 0.0)
# Two steel bars under the plate, one each side, as low as anything on the
# vehicle so they buy righting moment as well as trim. 140 × 12 × 6 mm of
# mild steel is 79 g each; the rails take that and are open at one end.
BALLAST_BAR = (140.0, 12.0, 6.0)
BALLAST_Y = 52.0
BALLAST_X = -10.0

# ── lights: two, either side of the window on the chassis nose ───────────────
LIGHT_D = 20.0
LIGHT_L = 24.0
LIGHTS = [(96.0, 46.0, -36.0), (96.0, -46.0, -36.0)]

# ── the overall envelope, derived ────────────────────────────────────────────
OVERALL_L = (CAPSULE_X + CAPSULE_L / 2) - (HORIZONTAL[0][1][0] - POD_LENGTH / 2)
OVERALL_W = 2 * (abs(VERTICAL[0][1][1]) + POD_OD / 2)
OVERALL_H = CAPSULE_H
