"""Every dimension of the fish's head, in millimetres, in one place.

Frame: x forward (the nose is +x), y port, z up, right-handed. The origin is
on the bulkhead plane: the rear face of the dry shell, where the drive plate
seals against it. Nose at +x, tail at -x.

The tail behind the drive plate is OpenFish's (TU Delft, CC BY-SA 4.0,
hardware/reference/openfish): its ribs 7-9, mould and silicone are printed
and cast unchanged. What this file describes is everything ahead of them,
redrawn because OpenFish's head is built around a Pololu 25D motor, a spur
pair and a Huco right-angle gearbox, none of which Amazon.sa sells.

Bought parts are recorded as the supplier states them. Where a number is a
guess it says so and says what settles it.
"""

# ── the motor: JGA25-370 (sold as 25GA-370), 12 V, "500 rpm" ─────────────────
# Amazon.sa listing, 19 Sep 2026. The class datasheet (Seeed 114090046) says
# 399 rpm free-run at 12 V, 1.2 A stall, 2.2 kg·cm stall, 19 mm gearbox.
# Body Ø24.4 with a Ø25 gearbox, 2 × M3 on 17 mm across the face, Ø4 D-shaft.
MOTOR_D = 25.0
MOTOR_LENGTH = 54.0          # gearbox 19 + motor 30.8 + end cap; MEASURE on arrival
SHAFT_D = 4.0
SHAFT_LENGTH = 12.0          # MEASURE; the crank needs 8 of it past the seal
MOTOR_HOLES = 17.0           # centre to centre, M3
MOTOR_BOSS_D = 7.0           # the ring around the shaft on the gearbox face
MOTOR_AXIS_Z = 0.0           # on the tail's cable midline, see CABLE_Z
MOTOR_STALL_KGCM = 2.2

# ── the shaft seal: a rotary lip seal, the RC-submarine way ──────────────────
# A 4 × 10 × 4 NBR TC lip seal in a pocket on the wet side of the drive
# plate, lip facing the water, greased. AliExpress; not yet ordered. A 4 × 8
# × 3 is the fallback and the pocket parameter follows whichever arrives.
SEAL_OD = 10.0
SEAL_T = 4.0

# ── the dry shell ────────────────────────────────────────────────────────────
# Stations along x from the bulkhead plane to the nose: (x, width, height,
# corner radius). Taken from the OpenFish head's own stations (measured from
# Part_1/2.STL: 61.5 × 75 at its widest, 40 × 55 at its rear) and shortened
# because our motor lies along x and needs no gearbox behind it.
SKIN = 3.0
STATIONS = [
    (0.0,   58.0, 72.0, 22.0),
    (40.0,  61.0, 75.0, 24.0),
    (90.0,  61.0, 75.0, 24.0),
    (130.0, 58.0, 72.0, 22.0),   # fuller here than OpenFish so the BTS7960's corners clear
    (160.0, 46.0, 58.0, 18.0),
    (180.0, 34.0, 44.0, 14.0),   # the nose face, flat, carrying the window
]
NOSE_X = STATIONS[-1][0]
NOSE_WALL = 4.0

# The rear collar: an external flange the drive plate and the tail bay bolt
# to, so the opening stays the full inner section and the BTS7960, which is
# 50 mm square, can pass through it. It reads as a gill line.
COLLAR_W = 70.0
COLLAR_H = 84.0
COLLAR_R = 26.0
COLLAR_T = 6.0
COLLAR_SCREWS = [(0.0, 36.0), (0.0, -36.0), (29.0, 18.0), (-29.0, 18.0), (29.0, -18.0), (-29.0, -18.0)]
COLLAR_SCREW_D = 3.2         # M3 clearance; brass M3 inserts in the shell side
ORING_MEAN = 66.0            # a face O-ring, 2 mm section, in a groove on the plate
ORING_SECTION = 2.0

# ── the drive plate: the module that can be tested in a bucket on its own ────
PLATE_T = 8.0                # 4 for the seal pocket, 4 of wall under it

# ── the crank, on the wet side ───────────────────────────────────────────────
# One pin; both cables tie to it. Three tapped positions so the tail's
# amplitude can be chosen against the motor's torque: OpenFish had about
# 5 kg·cm at its crank, we have 2.2, so start at the small radius.
CRANK_D = 30.0
CRANK_T = 6.0
CRANK_RADII = (6.0, 9.0, 12.0)
CRANK_X = -(PLATE_T + 4.0)   # 4 mm off the plate's wet face
GRUB_M = 3.0

# ── the tail bay: wet, carries the crank, the cable guides and the ribs ──────
BAY_LENGTH = 45.0            # bulkhead plane to the first rib
BAY_STATIONS = [
    (0.0, 58.0, 72.0, 22.0),
    (-BAY_LENGTH, 53.0, 72.0, 22.0),   # OpenFish rib 6 is 53.3 × 71.7
]
# The cables: OpenFish ribs 7-9 carry them in Ø1.5 holes on the horizontal
# midline, 21.6 mm apart (measured from the STLs: ±10.6 to ±11.0).
CABLE_Y = 10.8
CABLE_Z = 0.0
CABLE_HOLE_D = 2.0
GUIDE_X = -30.0              # a wall with two Ø2 holes; the cables run straight from it
# OpenFish's first rib bolts on with 2 × M3, 17 mm apart (measured from the
# head's rear face). Kept, so their rib 6 fits our bay if it is wanted.
RIB_SCREWS_Y = 8.5
RIB_SCREWS_Z = -18.5
# The silicone cover overlaps the bay by this much and is taped, as OpenFish's.
OVERLAP = 12.0

# ── the window ───────────────────────────────────────────────────────────────
# A 30 mm disc of 3 mm cast acrylic in a pocket on the nose face, over a
# 26 × 2 O-ring, held by a printed bezel with four M2 screws. The Camera
# Module 3 Wide (120°) sits 6 mm behind it; the Ø22 bore does not vignette.
WINDOW_D = 30.0
WINDOW_T = 3.0
WINDOW_BORE = 22.0
WINDOW_Z = 2.0               # a little above centre, so the camera looks level
BEZEL_OD = 40.0
BEZEL_T = 2.0
BEZEL_SCREWS_R = 17.0

# ── the tether: two PG7 glands on the crown ──────────────────────────────────
# One gland seals one round cable. The Cat6 (6 mm) and the power pair
# (2 × 1 mm², about 5.5 mm as a bundle) each get one. PG7's thread is
# 12.5 mm; the hole is 12.7 and the locknut goes inside.
GLAND_HOLE_D = 12.7
GLAND_BOSS_D = 20.0
GLAND_BOSS_H = 6.0
GLANDS = [(105.0, 0.0), (85.0, 0.0)]     # x along the crown

# ── the electronics tray ─────────────────────────────────────────────────────
TRAY_W = 48.0
TRAY_T = 2.0
TRAY_Z = -28.0               # the tray's top face
TRAY_X = (4.0, 150.0)          # the cavity is too shallow for it past 150
TRAY_GRID = 5.0              # M2.5 holes on a grid: everything screws or zip-ties down
RAIL_W = 3.0
# The boards, as boxes: (name, x from, y centre, z of underside, length, width, height).
# The motor (Ø25 on the axis) owns x 0..54 above z = -12.5, so the two flat
# boards sit under it; the BTS7960 is 30 mm tall and goes ahead of the
# motor; the Pi rides on standoffs above the BTS7960.
BOARDS = [
    ("buck LM2596",   6.0,  12.0, TRAY_Z + 1.0, 43.0, 21.0, 14.0),
    ("BNO055",        8.0, -14.0, TRAY_Z + 1.0, 27.0, 20.0,  6.0),
    # 6 mm standoffs lift the 50 mm board's corners clear of the cavity's
    # 21 mm corner radius; on the tray they clipped it.
    ("BTS7960",      56.0,   0.0, TRAY_Z + 6.0, 50.0, 50.0, 30.0),
    ("Pi Zero 2 W",  58.0,   0.0, TRAY_Z + 6.0 + 30.0 + 3.0, 65.0, 30.0,  9.0),
]
# The camera hangs from a cantilever off the tray's front post, so it sits
# in the narrow nose where no tray can: board centre, then board w, h, t.
CAMERA = (NOSE_X - NOSE_WALL - 8.0, 0.0, WINDOW_Z, 25.0, 24.0, 4.0)
CAMERA_POST_X = TRAY_X[1] - 2.0
CAMERA_ARM_Z = WINDOW_Z + 14.0

# ── overall, derived ─────────────────────────────────────────────────────────
HEAD_LENGTH = NOSE_X + BAY_LENGTH      # nose to first rib
