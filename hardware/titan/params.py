"""Every dimension of the mini Titan, in millimetres, in one place.

Frame: x forward, y port, z up, right-handed, the simulator's body frame.
Origin at the centre of the dry box.

The vehicle: the Geneinno Titan's construction at about 0.8 scale. A narrow
orange capsule over a black chassis; four vertical thruster pods on long
arms in the wings, two horizontal pods behind the stern; a window in the
nose. The dry part is the LeMotech IP65 box, standing on its side inside the
capsule so the capsule can be narrow, the way the Titan hides its own hull
under its shell. The capsule floods; the box seals.

Bought parts are recorded as the supplier states them. Where a number is a
guess it says so and says what settles it.
"""

# ── the box: LeMotech ABS junction box, IP65, clear polycarbonate lid ────────
# The 3.9" × 2.6" × 1.9" size: 100 × 68 × 50 outside, lying flat, lid up.
# The smallest size in the listing that a Pi Zero (65 × 30) fits in. It is
# what makes this a mini: the vehicle is half the Titan because the box and
# the thrusters are. MEASURE the wall, the lid and the bosses on arrival.
BOX_L = 100.0
BOX_W = 68.0                 # across, y
BOX_H = 50.0                 # tall, z, lid included
BOX_WALL = 2.5               # MEASURE
LID_T = 4.0                  # MEASURE
BOSS_D = 8.0
BOSS_INSET = 6.0
INSIDE_L = BOX_L - 2 * BOX_WALL
INSIDE_W = BOX_W - 2 * BOX_WALL
INSIDE_H = BOX_H - LID_T - BOX_WALL
FLOOR_Z = -BOX_H / 2 + BOX_WALL
LID_Z = BOX_H / 2 - LID_T
BOX_X = 0.0

# ── the thruster: ApisQueen UG500, 36 mm propeller, 47 mm long, 18 g ─────────
# https://www.underwaterthruster.com/products/apisqueen-uq500-mini-brushless-thruster-motor-small-size-and-light-weight-perfect-for-small-size-rovs/
# 5–24 V, 1.3 A at 12 V, about 4 N. Its guard's outside diameter is not
# published; 44 is the guess and the pod ring is printed after measuring.
DUCT_OD = 44.0               # MEASURE on arrival; every pod ring follows it
DUCT_LENGTH = 47.0           # MEASURE
THRUSTER_MASS_G = 26.0       # motor 18.3 plus guard and cable
THRUSTER_THRUST_N = 3.9
THRUSTER_DISPLACED_CM3 = 12.0
POD_WALL = 2.0
POD_OD = DUCT_OD + 2 * POD_WALL
POD_LENGTH = DUCT_LENGTH
BAND_W = 10.0
# The pod-to-chassis joint: two flat tabs face to face, four M3 on a 14 mm
# square. The chassis carries one; the pod ring carries the other. That is
# what lets the chassis be printed before the guard is measured.
TAB_W = 26.0
TAB_H = 22.0
TAB_T = 3.0
TAB_HOLES = 14.0

# ── the capsule: the Titan's body, over the box ──────────────────────────────
GAP = 2.5
SKIN = 2.0
CAPSULE_W = BOX_W + 2 * (GAP + SKIN)               # 77
# 66 tall on 77 wide, the Titan's 0.85. The box is 50, so there is 6 mm
# above the lid and 6 below the floor inside the skin: foam sheets.
CAPSULE_H = 66.0
FOAM_SHEET = 5.0
# 22 past the front wall for the nose, 50 past the rear wall for the tail.
# The voids carry the buoyancy foam.
NOSE_PAST = 22.0
TAIL_PAST = 50.0
CAPSULE_L = BOX_L + NOSE_PAST + TAIL_PAST          # 172
CAPSULE_X = BOX_X + (NOSE_PAST - TAIL_PAST) / 2
TAIL_X = CAPSULE_X - CAPSULE_L / 2
# In plan, a near-stadium: 34 of a possible 38.5.
CAPSULE_CORNER_R = 34.0
CAPSULE_CROWN_R = 20.0
BELLY_R = 12.0
PARTING_Z = 0.0
# Four M4 bosses on the parting line, in the room beyond the box's end walls,
# out at the sides so the nose opening does not show them.
BOSSES = [(BOX_X + 56.0, 25.0), (BOX_X + 56.0, -25.0), (BOX_X - 58.0, 26.0), (BOX_X - 58.0, -26.0)]
BOSS_OD = 7.0
SCREW_D = 2.5                # M3 tapping into nylon
VENTS = [(BOX_X - 85.0, 0.0), (BOX_X - 65.0, 0.0), (BOX_X + 30.0, 0.0), (BOX_X + 60.0, 0.0)]
VENT_D = 4.0
# ── the one connection, on top ───────────────────────────────────────────────
# The Titan has a single plug on its crown and nothing else on its skin. So
# does this: one round tether, the Cat6, with Ethernet on two pairs and 48 V
# on the other two, into a PG9 gland in the box's top wall (its long side
# wall, standing). A domed collar on the cover surrounds the gland head and
# takes the strain: pull the tether and you pull the cover, not the gland.
PORT_X = BOX_X - 8.0
PORT_DOME_D = 28.0
PORT_DOME_H = 12.0           # above the crown
PORT_HOLE_D = 9.0            # the cable passes; the gland head is inside the dome
GLAND_HOLE_D = 15.2          # PG9, through the lid
# Power: 24 V 5 A on the surface on the Cat6's spare pairs. Six UG500 at
# full throttle are under 8 A at 12 V; at 24 V that is 4 A, which drops
# about 5 V over 15 m of Cat6, so the vehicle sees 19 V. The UG500 is rated
# to 24 V and the ESCs are 6S, so nothing steps down except the LM2596 that
# makes 5 V for the Pi. No converter, which is what lets the small box work.

# ── the chassis: the Titan's black base, the arms and the pods ───────────────
PLATE_T = 4.0
PLATE_Z = -CAPSULE_H / 2 - 1.0
PLATE_W = CAPSULE_W + 8.0
ARM_W = 18.0
ARM_T = 5.0
ARM_GAP = 16.0               # open water between the capsule and a wing pod, as on the Titan
VERT_Y = CAPSULE_W / 2 + ARM_GAP + POD_OD / 2
VERT_X = (BOX_X + 38.0, BOX_X - 30.0)
VERT_Z = -4.0
# Stern pods behind the tail and a little below it, as in the Titan's plan
# view, where both are seen whole.
HORIZ_X = TAIL_X - POD_LENGTH / 2 - 3.0
HORIZ_Y = 28.0
HORIZ_Z = -18.0
THRUSTERS = [
    ("vertical-front-port",      (VERT_X[0],  VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("vertical-front-starboard", (VERT_X[0], -VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("vertical-rear-port",       (VERT_X[1],  VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("vertical-rear-starboard",  (VERT_X[1], -VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("horizontal-port",          (HORIZ_X,  HORIZ_Y, HORIZ_Z), (1.0, 0.0, 0.0)),
    ("horizontal-starboard",     (HORIZ_X, -HORIZ_Y, HORIZ_Z), (1.0, 0.0, 0.0)),
]
# Buoyancy: closed-cell foam (a pool noodle, cut) filling the tail void and
# the nose void around the window tunnel. Trim is wheel weights on the plate.
FOAM_TAIL = (TAIL_X + 6.0, BOX_X - BOX_L / 2 - 4.0)     # x from, x to
FOAM_NOSE = (BOX_X + BOX_L / 2 + 4.0, BOX_X + BOX_L / 2 + NOSE_PAST - 4.0)
FOAM_OVER = (BOX_X - BOX_L / 2, BOX_X + BOX_L / 2)      # sheets above the lid and under the floor
FOAM_DENSITY = 0.03          # g/cm³, polyethylene noodle
BALLAST_BAR = (0.0, 0.0, 0.0)

# ── the window, in the box's front wall, seen through the capsule's nose ─────
WINDOW_D = 26.0
WINDOW_T = 3.0
WINDOW_BORE = 20.0
WINDOW_Z = 2.0
BEZEL_OD = 40.0
BEZEL_T = 4.0
BEZEL_SCREWS_R = 16.0
# The nose opening. The window is 22 mm behind the nose skin; a 44 mm
# opening gives the camera 45° either side, against the Wide module's 51°.
NOSE_OPENING_D = 44.0

# ── the stern: closed, with a drain slot ─────────────────────────────────────
STERN_OPENING = (24.0, 6.0)    # a slot low in the stern so the capsule drains

# ── inside the box: two decks ────────────────────────────────────────────────
# Two 4-in-1 drone ESCs (30 × 30, 6S, 3D mode) replace six singles and are
# what make the small box possible. They and the buck lie on the lower
# tray; the Pi, PCA9685 and IMU ride an upper tray on 12 mm standoffs.
TRAY_T = 1.6
TRAY_Z = FLOOR_Z + 2.5            # lower tray's top face
DECK_Z = TRAY_Z + 10.0 + 12.0     # upper tray's top face
TRAY_L = INSIDE_L - 2 * BOSS_INSET - BOSS_D - 3.0
TRAY_W = INSIDE_W - 3.0
TRAY_GRID = 5.0
# (name, x centre, y centre, z underside, length, width, height)
BOARDS = [
    ("4-in-1 ESC A",    BOX_X + 28.0,  14.0, TRAY_Z, 30.0, 30.0, 10.0),
    ("4-in-1 ESC B",    BOX_X + 28.0, -18.0, TRAY_Z, 30.0, 30.0, 10.0),
    ("buck LM2596",     BOX_X - 18.0,  16.0, TRAY_Z, 43.0, 21.0, 12.0),
    ("PoE splitter tap", BOX_X - 18.0, -14.0, TRAY_Z, 30.0, 20.0,  8.0),
    ("Pi Zero 2 W",     BOX_X + 10.0,  14.0, DECK_Z, 65.0, 30.0,  9.0),
    ("PCA9685",         BOX_X + 10.0, -16.0, DECK_Z, 62.0, 25.0, 12.0),
    ("BNO055",          BOX_X - 33.0,   0.0, DECK_Z, 20.0, 27.0,  6.0),
]
CAMERA = (BOX_X + BOX_L / 2 - BOX_WALL - 7.0, 0.0, WINDOW_Z, 25.0, 24.0, 4.0)

# ── overall, derived ─────────────────────────────────────────────────────────
OVERALL_L = (CAPSULE_X + CAPSULE_L / 2) - min(TAIL_X, HORIZ_X - POD_LENGTH / 2)
OVERALL_W = 2 * (VERT_Y + POD_OD / 2)
OVERALL_H = (CAPSULE_H / 2 + PORT_DOME_H) - (HORIZ_Z - POD_OD / 2)
