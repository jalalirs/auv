"""Every dimension of the mini Titan, in millimetres, in one place.

Frame: x forward, y port, z up, right-handed, the simulator's body frame.
Origin at the centre of the dry box.

The vehicle: the Geneinno Titan's construction at about 0.8 scale. An orange
capsule over a black chassis; four vertical thruster pods in the wings, two
horizontal pods on the stern corners; a window in the nose. The dry part is
the LeMotech IP65 box hidden inside the capsule, the way the Titan hides its
own pressure hull under its shell. The capsule floods; the box seals.

Bought parts are recorded as the supplier states them. Where a number is a
guess it says so and says what settles it.
"""

# ── the box: LeMotech ABS junction box, IP65, clear polycarbonate lid ────────
BOX_L = 200.0
BOX_W = 120.0
BOX_H = 75.0
BOX_WALL = 3.0               # MEASURE
LID_T = 5.0                  # MEASURE
BOX_R = 6.0
BOSS_D = 10.0
BOSS_INSET = 8.0
INSIDE_L = BOX_L - 2 * BOX_WALL
INSIDE_W = BOX_W - 2 * BOX_WALL
FLOOR_Z = -BOX_H / 2 + BOX_WALL
LID_Z = BOX_H / 2 - LID_T
# The box sits forward of the capsule's centre so the stern pods have room.
BOX_X = 10.0

# ── the thruster: Cryfokt 2838 500 KV in a 60 mm duct ───────────────────────
DUCT_OD = 72.0               # MEASURE on arrival; every pod follows it
DUCT_LENGTH = 62.0           # MEASURE
THRUSTER_MASS_G = 180.0
THRUSTER_THRUST_N = 15.0
THRUSTER_DISPLACED_CM3 = 60.0
POD_WALL = 3.0
POD_OD = DUCT_OD + 2 * POD_WALL
POD_LENGTH = DUCT_LENGTH + 8.0
BAND_W = 12.0
# The pod-to-chassis joint: two flat tabs face to face, four M3 on a 24 mm
# square. The chassis carries its tab; the pod ring carries the other. That
# is what lets the chassis be printed before the duct is measured: only the
# ring changes when it is.
TAB_W = 40.0                 # along the arm's direction of travel
TAB_H = 34.0
TAB_T = 4.0
TAB_HOLES = 24.0

# ── the capsule: the Titan's body, over the box ──────────────────────────────
GAP = 3.0                    # box to capsule inside, each side
SKIN = 2.5
CAPSULE_L = BOX_L + 2 * (GAP + SKIN) + 14.0    # 14 extra at the nose for the window bezel to sit in
CAPSULE_W = BOX_W + 2 * (GAP + SKIN)
CAPSULE_H = BOX_H + 2 * (GAP + SKIN)
CAPSULE_X = BOX_X + 7.0
CAPSULE_CORNER_R = 28.0      # in plan
CAPSULE_CROWN_R = 20.0       # the dome of the cover
PARTING_Z = 0.0              # cover above, chassis below
# Four M4 bosses on the parting line, outside the box, hold the cover on.
BOSSES = [(BOX_X + 80.0, 58.0), (BOX_X + 80.0, -58.0), (BOX_X - 80.0, 58.0), (BOX_X - 80.0, -58.0)]
BOSS_OD = 10.0
SCREW_D = 3.4                # M4 tapping into PETG
# Vents in the crown so the capsule floods and empties without trapping air.
VENTS = [(BOX_X - 70.0, 0.0), (BOX_X - 35.0, 0.0), (BOX_X + 35.0, 0.0), (BOX_X + 70.0, 0.0)]
VENT_D = 5.0
# A tether eye on the crown, behind the centre of buoyancy.
TETHER_EYE = (BOX_X - 30.0, 0.0)

# ── the chassis: the Titan's black base, the arms and the pods ───────────────
PLATE_T = 5.0
PLATE_Z = -CAPSULE_H / 2 - 1.0          # top of the base plate, just under the capsule
ARM_W = 26.0
ARM_T = 6.0
# Vertical pods at the four wing corners, outboard of the capsule.
VERT_Y = CAPSULE_W / 2 + POD_OD / 2 + 6.0
VERT_X = (BOX_X + 62.0, BOX_X - 62.0)
VERT_Z = -12.0
# Horizontal pods on the stern corners, behind the capsule.
HORIZ_X = CAPSULE_X - CAPSULE_L / 2 - POD_LENGTH / 2 + 10.0
HORIZ_Y = 66.0
HORIZ_Z = -20.0
THRUSTERS = [
    ("vertical-front-port",      (VERT_X[0],  VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("vertical-front-starboard", (VERT_X[0], -VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("vertical-rear-port",       (VERT_X[1],  VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("vertical-rear-starboard",  (VERT_X[1], -VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("horizontal-port",          (HORIZ_X,  HORIZ_Y, HORIZ_Z), (1.0, 0.0, 0.0)),
    ("horizontal-starboard",     (HORIZ_X, -HORIZ_Y, HORIZ_Z), (1.0, 0.0, 0.0)),
]
# Ballast rails under the plate: two channels for steel bars.
BALLAST_BAR = (150.0, 20.0, 8.0)
BALLAST_Y = 34.0

# ── the window, in the box's front wall, framed by the capsule's nose ────────
WINDOW_D = 30.0
WINDOW_T = 3.0
WINDOW_BORE = 22.0
WINDOW_Z = 8.0
BEZEL_OD = 46.0
BEZEL_T = 5.0
BEZEL_SCREWS_R = 19.0
NOSE_OPENING_D = 52.0        # the capsule's nose opening, showing the bezel

# ── the tether: two PG7 glands in the box's rear wall ────────────────────────
GLAND_HOLE_D = 12.7
GLANDS = [(BOX_X - BOX_L / 2, 25.0, 5.0), (BOX_X - BOX_L / 2, -25.0, 5.0)]
STERN_OPENING = (70.0, 36.0)  # the capsule's stern opening for the glands and cables

# ── inside the box ───────────────────────────────────────────────────────────
TRAY_T = 2.0
TRAY_Z = FLOOR_Z + 4.0
TRAY_L = INSIDE_L - 2 * BOSS_INSET - BOSS_D - 4.0
TRAY_W = INSIDE_W - 4.0
TRAY_GRID = 5.0
BOARDS = [
    ("Pi Zero 2 W",     BOX_X + 55.0,   0.0, TRAY_Z, 65.0, 30.0,  9.0),
    ("PCA9685",         BOX_X + 55.0,  38.0, TRAY_Z, 62.0, 25.0, 12.0),
    ("BNO055",          BOX_X + 55.0, -38.0, TRAY_Z, 27.0, 20.0,  6.0),
    ("buck LM2596",     BOX_X - 5.0,   40.0, TRAY_Z, 43.0, 21.0, 14.0),
    ("ESC 1",           BOX_X - 10.0,  12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 2",           BOX_X - 10.0, -12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 3",           BOX_X - 58.0,  12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 4",           BOX_X - 58.0, -12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 5",           BOX_X - 58.0,  40.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 6",           BOX_X - 58.0, -40.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("power terminals", BOX_X - 5.0,  -40.0, TRAY_Z, 40.0, 18.0, 14.0),
]
CAMERA = (BOX_X + BOX_L / 2 - BOX_WALL - 7.0, 0.0, WINDOW_Z, 25.0, 24.0, 4.0)

# ── overall, derived ─────────────────────────────────────────────────────────
OVERALL_L = (CAPSULE_X + CAPSULE_L / 2 + BEZEL_T) - (HORIZ_X - POD_LENGTH / 2)
OVERALL_W = 2 * (VERT_Y + POD_OD / 2)
OVERALL_H = CAPSULE_H + 2.0 + PLATE_T + BALLAST_BAR[2] + 4.0
