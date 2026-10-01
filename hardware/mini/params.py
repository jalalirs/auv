"""mini-hoot, every dimension in millimetres, in one place.

Frame: x forward, y port, z up, right-handed. Origin at the centre of the dry
tube. Bought parts as their makers state them; a guess says it is one.

The vehicle: the moulded Titan form around a Blue Robotics 3" tube, its dome
the nose, four vertical thrusters in wing pods and four horizontal ones at
the hull's corners at 45 degrees (the BlueROV2 Heavy's layout, so it can move
sideways). See spec.md.
"""

# ── the dry part: Blue Robotics 3" locking series ────────────────────────────
TUBE_OD = 88.9               # datasheet: 3.0" ID, 3.5" OD acrylic
TUBE_ID = 76.2
TUBE_L = 200.0               # chosen: Pi 5 + Navigator ahead, battery behind
FLANGE_OD = 100.0            # assumed until a flange is in hand
FLANGE_T = 15.0
DOME_R = 44.5                # the 3" dome, taken as a hemisphere: assumed
FRONT_FACE_X = TUBE_L / 2 + FLANGE_T          # 115
REAR_FACE_X = -FRONT_FACE_X

# ── the shell: red lid over black chassis, floods ────────────────────────────
HULL_NOSE = 110.0            # the shell stops at the front flange; the dome is the nose
HULL_TAIL = -150.0
HULL_W = 110.0               # 3" flange 100 + 2.5 skin + 2.5 room each side
TAIL_W = 90.0
TAPER_FROM = -60.0
HULL_H = 110.0
NOSE_CORNER_R = 10.0
TAIL_CORNER_R = 34.0
TOP_EDGE_R = 30.0
BELLY_EDGE_R = 30.0
SKIN = 2.5
PARTING_Z = 20.0
LID_NOSE_X = 92.0            # black ring of shell round the front flange, red behind it
NOSE_OPENING_R = 51.0        # the shell's mouth round the flange

# ── thrusters: 8 × ApisQueen UG500 ──────────────────────────────────────────
DUCT_OD = 44.0               # assumed: guard diameter unpublished
DUCT_LENGTH = 47.0           # datasheet
THRUST_FWD_N = 4.0           # datasheet, about
THRUST_REV_N = 3.0           # assumed: three quarters of forward, as most props
THRUSTER_MASS_G = 26.0       # 18 motor + guard + cable, assumed
BORE_D = DUCT_OD + 1.0
POD_OD = BORE_D + 5.0
POD_H = DUCT_LENGTH
POD_EDGE_R = 2.0
POD_LIP = 1.8
SPOKE_W = 3.5
HUB_D = 16.0
VERT_X = (30.0, -75.0)
VERT_Y = 98.0
VERT_Z = 0.0
# Toed in, as on the BlueROV2: a thruster pointed along the radius from the
# centre gives no yaw, one pointed across it gives the most. Heading is the
# direction it pushes the vehicle, degrees from forward towards port.
CORNER = [                   # (name, x, y, z, heading)
    ("front-port",      95.0,  72.0, -40.0,  -45.0),
    ("front-starboard", 95.0, -72.0, -40.0,   45.0),
    ("rear-port",     -140.0,  62.0, -40.0, -135.0),
    ("rear-starboard", -140.0, -62.0, -40.0,  135.0),
]
VERTICAL = [
    ("vertical-front-port",      VERT_X[0],  VERT_Y, VERT_Z),
    ("vertical-front-starboard", VERT_X[0], -VERT_Y, VERT_Z),
    ("vertical-rear-port",       VERT_X[1],  VERT_Y, VERT_Z),
    ("vertical-rear-starboard",  VERT_X[1], -VERT_Y, VERT_Z),
]
ARM_ROOT = {"front": (5.0, 40.0, -10.0), "rear": (-50.0, 40.0, -10.0)}
ARM_ROOT_R = 15.0
ARM_TIP_R = 11.0
ARM_FLATTEN = 1.5
BLEND_HULL = 12.0
BLEND_POD = 6.0
BLEND_CORNER = 10.0

# ── details ──────────────────────────────────────────────────────────────────
WING_Z = -10.0               # a tail plate over the rear thrusters
WING_T = 5.0
WING_PLAN = [(-100.0, 40.0), (-128.0, 80.0), (-176.0, 96.0), (-180.0, 88.0), (-168.0, 52.0), (-172.0, 0.0)]
FIN_PROFILE = [(-80.0, 50.0), (-138.0, 50.0), (-141.0, 64.0), (-131.0, 66.0)]
FIN_W = 26.0
KNOB_X = -10.0
KNOB_D = 24.0
KNOB_H = 5.0
VENT_D = 3.0
LIGHT_D = 18.0
LIGHT_REACH = 34.0
LIGHT_DZ = -8.0
TETHER_Z = -12.0
TETHER_HOLE_D = 8.0
CAMERA_X = FRONT_FACE_X + 6.0
COVER_COLOUR = "#c8161d"
# A real black plastic, about 4% reflectance. "#151617" was under 1%,
# darker than velvet, and the flanks rendered as a silhouette in any light.
CHASSIS_COLOUR = "#3b3d41"
