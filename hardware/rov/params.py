"""Every dimension of the mini ROV, in millimetres, in one place.

Frame: x forward, y port, z up, right-handed, the simulator's body frame.
Origin at the centre of the dry box.

The vehicle: a bought IP65 box is the hull, lying flat with its clear lid
up. A printed cradle holds it and carries four thrusters: two vertical on
the sides for heave and roll, two horizontal at the stern for surge and
yaw. The camera looks forward through a window in the front wall; the
tether enters the rear wall through two glands. No battery: power comes
down the tether, the DGX Spark does the thinking.

Bought parts are recorded as the supplier states them. Where a number is a
guess it says so and says what settles it.
"""

# ── the box: LeMotech ABS junction box, IP65, clear polycarbonate lid ────────
# Amazon.sa, 20 Sep 2026, 60 SAR. Stated 200 × 120 × 75 outside; the lid is
# about 5 mm of that and the wall about 3. Corner bosses take the lid screws.
BOX_L = 200.0
BOX_W = 120.0
BOX_H = 75.0                 # body plus lid
BOX_WALL = 3.0               # MEASURE
LID_T = 5.0                  # MEASURE
BOX_R = 6.0                  # outside corner radius in plan
BOSS_D = 10.0                # the lid-screw bosses in the four inside corners
BOSS_INSET = 8.0             # boss centre from each inside wall
INSIDE_L = BOX_L - 2 * BOX_WALL
INSIDE_W = BOX_W - 2 * BOX_WALL
INSIDE_H = BOX_H - LID_T - BOX_WALL
FLOOR_Z = -BOX_H / 2 + BOX_WALL          # inside floor
LID_Z = BOX_H / 2 - LID_T                # underside of the lid

# ── the thruster: Cryfokt 2838 500 KV in a 60 mm duct ───────────────────────
# Amazon.sa, 185–191 SAR. Listing says 500 KV, 12–24 V, 60 mm propeller,
# 300 m. The duct's outside diameter, length and mounting are not stated;
# the numbers below are the common F2838 duct and are MEASURED on arrival.
# The saddle clamps the duct with a band, so only DUCT_OD matters for fit.
DUCT_OD = 72.0               # MEASURE
DUCT_LENGTH = 62.0           # MEASURE
THRUSTER_MASS_G = 180.0      # MEASURE; the class is 150–200 with duct
THRUSTER_THRUST_N = 15.0     # about 1.5 kgf at 12 V and 20 A, from the class
THRUSTER_DISPLACED_CM3 = 60.0
BAND_W = 12.0                # the printed saddle's clamp band
BAND_T = 3.0

# ── the cradle: what the box sits in ─────────────────────────────────────────
CRADLE_T = 4.0               # floor plate
CHEEK_T = 4.0                # the two side walls
CHEEK_H = 40.0               # up from the floor plate; the box is strapped in
CLEARANCE = 0.8              # box to cradle, each side
CRADLE_L = BOX_L + 2 * (CHEEK_T + CLEARANCE)
CRADLE_W = BOX_W + 2 * (CHEEK_T + CLEARANCE)
CRADLE_FLOOR_Z = -BOX_H / 2 - CLEARANCE - CRADLE_T   # top of the floor plate is just under the box
STRAP_SLOTS_X = (-60.0, 60.0)      # 25 mm webbing straps over the lid, through slots in the cheeks
STRAP_W = 26.0
STRAP_T = 3.0
# Lightening: the floor plate is a frame with a spine and two cross bars.
FLOOR_RIM = 14.0
SPINE_W = 20.0

# ── thrusters, placed ────────────────────────────────────────────────────────
# Vertical, one each side at mid-length, outboard of the cheeks, axis z.
VERT_Y = CRADLE_W / 2 + DUCT_OD / 2 + BAND_T + 1.0
VERT_Z = 0.0
# Horizontal, at the stern, either side of the centreline, axis x, so the
# jet clears the box and the two together give yaw.
HORIZ_X = -(BOX_L / 2 + CHEEK_T + CLEARANCE + DUCT_LENGTH / 2 + 4.0)
HORIZ_Y = 45.0
HORIZ_Z = -10.0
THRUSTERS = [
    ("vertical-port",        ( 0.0,  VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("vertical-starboard",   ( 0.0, -VERT_Y, VERT_Z), (0.0, 0.0, 1.0)),
    ("horizontal-port",      (HORIZ_X,  HORIZ_Y, HORIZ_Z), (1.0, 0.0, 0.0)),
    ("horizontal-starboard", (HORIZ_X, -HORIZ_Y, HORIZ_Z), (1.0, 0.0, 0.0)),
]
# The stern thrusters hang from an arm off the rear of each cheek.
ARM_W = 22.0
ARM_T = 6.0

# ── the window, in the front wall ────────────────────────────────────────────
# A 30 mm disc of 3 mm cast acrylic from SACO, on a 26 × 2 O-ring, in a
# printed bezel screwed to the wall with four M3 and sealed with silicone.
WINDOW_D = 30.0
WINDOW_T = 3.0
WINDOW_BORE = 22.0
WINDOW_Z = 8.0               # above centre so the camera clears the tray
BEZEL_OD = 46.0
BEZEL_T = 5.0
BEZEL_SCREWS_R = 19.0

# ── the tether, in the rear wall: two PG7 glands ────────────────────────────
GLAND_HOLE_D = 12.7
GLANDS = [(-BOX_L / 2, 25.0, 5.0), (-BOX_L / 2, -25.0, 5.0)]   # x, y, z on the rear wall

# ── the ballast: steel bar under the floor plate ─────────────────────────────
# The box displaces 1.8 litres and everything in and on it weighs less, so
# this vehicle needs weight, not foam. Two mild steel bars in channels
# under the floor, as low as anything on the vehicle. 150 × 20 × 8 is 188 g.
BALLAST_BAR = (150.0, 20.0, 8.0)
BALLAST_Y = 30.0

# ── inside: the tray and the boards ──────────────────────────────────────────
TRAY_T = 2.0
TRAY_Z = FLOOR_Z + 4.0       # top face; standoffs under it clear the floor's texture
TRAY_L = INSIDE_L - 2 * BOSS_INSET - BOSS_D - 4.0
TRAY_W = INSIDE_W - 4.0
TRAY_GRID = 5.0
# (name, x centre, y centre, z underside, length, width, height)
BOARDS = [
    ("Pi Zero 2 W",     55.0,   0.0, TRAY_Z, 65.0, 30.0,  9.0),
    ("PCA9685",         55.0,  38.0, TRAY_Z, 62.0, 25.0, 12.0),
    ("BNO055",          55.0, -38.0, TRAY_Z, 27.0, 20.0,  6.0),
    ("buck LM2596",     -5.0,  40.0, TRAY_Z, 43.0, 21.0, 14.0),
    ("ESC 1",          -10.0,  12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 2",          -10.0, -12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 3",          -58.0,  12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("ESC 4",          -58.0, -12.0, TRAY_Z, 45.0, 22.0, 10.0),
    ("power terminals", -5.0, -40.0, TRAY_Z, 40.0, 18.0, 14.0),
]
CAMERA_X = BOX_L / 2 - BOX_WALL - 7.0
CAMERA = (CAMERA_X, 0.0, WINDOW_Z, 25.0, 24.0, 4.0)    # x, y, z, w, h, t

# ── overall, derived ─────────────────────────────────────────────────────────
OVERALL_L = (BOX_L / 2 + BEZEL_T) - (HORIZ_X - DUCT_LENGTH / 2)
OVERALL_W = 2 * (VERT_Y + DUCT_OD / 2)
OVERALL_H = BOX_H + 2 * CLEARANCE + CRADLE_T + BALLAST_BAR[2] + 4.0
