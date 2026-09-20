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
# The 6.2" × 3.5" × 2.3" size: 158 × 89 × 58 outside, lying flat, lid up.
# The 200 × 120 × 75 was too wide flat and too tall on its side; this one
# gives the Titan's capsule proportion, 100 wide by 69 tall. MEASURE the
# wall, the lid and the corner bosses on arrival.
BOX_L = 158.0
BOX_W = 89.0                 # across, y
BOX_H = 58.0                 # tall, z, lid included
BOX_WALL = 2.5               # MEASURE
LID_T = 4.0                  # MEASURE
BOSS_D = 9.0
BOSS_INSET = 7.0
INSIDE_L = BOX_L - 2 * BOX_WALL
INSIDE_W = BOX_W - 2 * BOX_WALL
INSIDE_H = BOX_H - LID_T - BOX_WALL
FLOOR_Z = -BOX_H / 2 + BOX_WALL
LID_Z = BOX_H / 2 - LID_T
BOX_X = 0.0

# ── the thruster: Cryfokt 2838 500 KV in a 60 mm duct ───────────────────────
DUCT_OD = 72.0               # MEASURE on arrival; every pod ring follows it
DUCT_LENGTH = 62.0           # MEASURE
THRUSTER_MASS_G = 180.0
THRUSTER_THRUST_N = 15.0
THRUSTER_DISPLACED_CM3 = 60.0
POD_WALL = 2.4
POD_OD = DUCT_OD + 2 * POD_WALL
POD_LENGTH = DUCT_LENGTH
BAND_W = 12.0
# The pod-to-chassis joint: two flat tabs face to face, four M3 on a 24 mm
# square. The chassis carries one; the pod ring carries the other. That is
# what lets the chassis be printed before the duct is measured.
TAB_W = 40.0
TAB_H = 34.0
TAB_T = 4.0
TAB_HOLES = 24.0

# ── the capsule: the Titan's body, over the box ──────────────────────────────
GAP = 3.0
SKIN = 2.5
CAPSULE_W = BOX_W + 2 * (GAP + SKIN)               # 100
# 85 tall on 100 wide, the Titan's 0.85. The box is 58, so there is 11 mm
# above the lid and 11 below the floor inside the skin: foam sheets, which
# is where the last of the buoyancy comes from and why the centre of
# buoyancy sits above the centre of gravity.
CAPSULE_H = 85.0
FOAM_SHEET = 10.0
# 30 past the front wall for the nose, 105 past the rear wall for a tail
# that reaches over the stern pods, as the Titan's does. The tail is void,
# and the void is where the buoyancy foam goes: this size of vehicle with
# six thrusters sinks without it.
NOSE_PAST = 30.0
TAIL_PAST = 90.0
CAPSULE_L = BOX_L + NOSE_PAST + TAIL_PAST          # 293
CAPSULE_X = BOX_X + (NOSE_PAST - TAIL_PAST) / 2    # the capsule's centre, aft of the box's
TAIL_X = CAPSULE_X - CAPSULE_L / 2
# In plan, a near-stadium: 46 of a possible 50, which clears the box's
# corners by 3 mm at the inside skin.
CAPSULE_CORNER_R = 46.0
# The cover is a low dome: the crown fillet is most of its half-height.
CAPSULE_CROWN_R = 26.0
BELLY_R = 16.0               # the chassis' lower half is rounded too
PARTING_Z = 0.0
# Four M4 bosses on the parting line, in the room beyond the box's end walls,
# out at the sides so the nose opening does not show them.
BOSSES = [(BOX_X + 86.0, 33.0), (BOX_X + 86.0, -33.0), (BOX_X - 140.0, 30.0), (BOX_X - 140.0, -30.0)]
BOSS_OD = 8.0
SCREW_D = 2.5                # M3 tapping into nylon
VENTS = [(BOX_X - 150.0, 0.0), (BOX_X - 110.0, 0.0), (BOX_X + 40.0, 0.0), (BOX_X + 70.0, 0.0)]
VENT_D = 5.0
# ── the one connection, on top ───────────────────────────────────────────────
# The Titan has a single plug on its crown and nothing else on its skin. So
# does this: one round tether, the Cat6, with Ethernet on two pairs and 48 V
# on the other two, into a PG9 gland in the box's top wall (its long side
# wall, standing). A domed collar on the cover surrounds the gland head and
# takes the strain: pull the tether and you pull the cover, not the gland.
PORT_X = BOX_X - 12.0
PORT_DOME_D = 32.0
PORT_DOME_H = 14.0           # above the crown
PORT_HOLE_D = 9.0            # the cable passes; the gland head is inside the dome
GLAND_HOLE_D = 15.2          # PG9, through the lid
# Power: 48 V 5 A on the surface, a 48→12 V 20 A converter in the box. Over
# 15 m of Cat6, two 24 AWG wires per leg, 3 A drops about 4 V; fine at 48,
# hopeless at 12, which is why it is 48.

# ── the chassis: the Titan's black base, the arms and the pods ───────────────
PLATE_T = 5.0
PLATE_Z = -CAPSULE_H / 2 - 1.0
PLATE_W = CAPSULE_W + 10.0
ARM_W = 26.0
ARM_T = 7.0
ARM_GAP = 24.0               # open water between the capsule and a wing pod, as on the Titan
VERT_Y = CAPSULE_W / 2 + ARM_GAP + POD_OD / 2
VERT_X = (BOX_X + 62.0, BOX_X - 42.0)
VERT_Z = -6.0
# Stern pods behind the tail and a little below it, as in the Titan's plan
# view, where both are seen whole.
HORIZ_X = TAIL_X - POD_LENGTH / 2 - 4.0
HORIZ_Y = 46.0
HORIZ_Z = -30.0
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
WINDOW_D = 30.0
WINDOW_T = 3.0
WINDOW_BORE = 22.0
WINDOW_Z = 2.0
BEZEL_OD = 46.0
BEZEL_T = 5.0
BEZEL_SCREWS_R = 19.0
# The nose opening. The window is 30 mm behind the nose skin; a 54 mm
# opening gives the camera 42° either side, against the Wide module's 51°,
# so the corners of the frame see the tunnel's edge. Checked once the
# camera is in; the opening can grow to 60 before it shows the bosses.
NOSE_OPENING_D = 54.0

# ── the stern: closed, with a drain slot ─────────────────────────────────────
STERN_OPENING = (30.0, 8.0)    # a slot low in the stern so the capsule drains

# ── inside the box: two decks ────────────────────────────────────────────────
# The floor is too small for everything in one layer, so the ESCs and the
# converter lie on the lower tray and the Pi, PCA9685, IMU and buck ride an
# upper tray on 14 mm standoffs. 10 + 14 + 12 is 36 of the 51 inside.
TRAY_T = 2.0
TRAY_Z = FLOOR_Z + 3.0            # lower tray's top face
DECK_Z = TRAY_Z + 10.0 + 14.0     # upper tray's top face
TRAY_L = INSIDE_L - 2 * BOSS_INSET - BOSS_D - 4.0
TRAY_W = INSIDE_W - 4.0
TRAY_GRID = 5.0
# (name, x centre, y centre, z underside, length, width, height)
BOARDS = [
    ("ESC 1",           BOX_X + 46.0,  30.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 2",           BOX_X + 46.0,   4.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 3",           BOX_X + 46.0, -22.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 4",           BOX_X -  4.0,  30.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 5",           BOX_X -  4.0,   4.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 6",           BOX_X -  4.0, -22.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("48→12 V 20 A",    BOX_X - 48.0,   0.0, TRAY_Z, 40.0, 56.0, 20.0),
    ("Pi Zero 2 W",     BOX_X + 34.0,  18.0, DECK_Z, 65.0, 30.0,  9.0),
    ("PCA9685",         BOX_X + 34.0, -16.0, DECK_Z, 62.0, 25.0, 12.0),
    ("BNO055",          BOX_X - 26.0,  20.0, DECK_Z, 27.0, 20.0,  6.0),
    ("buck LM2596",     BOX_X - 30.0, -14.0, DECK_Z, 43.0, 21.0, 14.0),
]
CAMERA = (BOX_X + BOX_L / 2 - BOX_WALL - 7.0, 0.0, WINDOW_Z, 25.0, 24.0, 4.0)

# ── overall, derived ─────────────────────────────────────────────────────────
OVERALL_L = (CAPSULE_X + CAPSULE_L / 2) - min(TAIL_X, HORIZ_X - POD_LENGTH / 2)
OVERALL_W = 2 * (VERT_Y + POD_OD / 2)
OVERALL_H = (CAPSULE_H / 2 + PORT_DOME_H) - (HORIZ_Z - POD_OD / 2)
