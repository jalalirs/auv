"""mini-hoot as an iocean vehicle package.

    hardware/.venv/bin/python hardware/mini/shape.py     # the meshes first
    hardware/.venv/bin/python hardware/mini/package.py   → catalog/vehicles/mini-hoot/

Writes dynamics.json (mass, buoyancy and inertia summed from the parts, the
eight thrusters where shape.py put them), the hull as USD, and the picture.
Every number says whether it was measured, derived, chosen or assumed; none
is measured yet, because nothing has been built.

The catalogue's frame is x forward, y to starboard, z up, metres from the
centre of gravity. The drawing's is y to port, in millimetres, from the
centre of the tube. Both conversions happen here and nowhere else.
"""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib
import shutil
import sys

import numpy as np
import trimesh

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
OUT = HERE.parent / "out" / "mini"
PKG = ROOT / "catalog" / "vehicles" / "mini-hoot"
spec = importlib.util.spec_from_file_location("mini_params", HERE / "params.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

# Where the navigation sensors sit, in the drawing's frame (sensors.md).
# Three single-beam echosounders, ahead and 25 degrees either side: their
# 25-degree cones touch, so the 75 degrees ahead are heard without a gap.
# Splayed at 45 they left two blind wedges from 12 to 32 degrees off the
# nose, and the first tank run met its pillar in one of them.
PINGS = [("ahead", (88.0, 0.0), 0.0), ("port", (74.0, 30.0), 25.0), ("starboard", (74.0, -30.0), -25.0)]
PING_Z = -S.HULL_H / 2 - 21.0
PINGS_AT = (76.0, 0.0, PING_Z)
DVL_AT = (-20.0, 0.0, -S.HULL_H / 2 - 12.5)

FRESH = 0.998     # g/cm³
PA12 = 1.01       # MJF PA12, g/cm³
LEAD = 11.3
FOAM = 0.08      # closed-cell PVC foam, g/cm³


def budget():
    """Mass against buoyancy, part by part: (name, g, cm³, centre mm, kind, note)."""
    rows = []
    for name in ("cover", "chassis"):
        m = trimesh.load(OUT / f"{name}.stl")
        v = m.volume / 1000
        rows.append((f"{name} (printed PA12)", v * PA12, v, m.center_mass, "derived", "volume from the drawing"))
    tube_v = math.pi * (S.TUBE_OD / 20) ** 2 * S.TUBE_L / 10
    flange_v = 2 * math.pi * (S.FLANGE_OD / 20) ** 2 * S.FLANGE_T / 10
    dome_v = 2 / 3 * math.pi * (S.DOME_R / 10) ** 3
    rows += [
        ("3\" tube, two flanges, rear cap, dome", 640.0, tube_v + flange_v + dome_v, (0, 0, 0), "assumed",
         "the sealed volume displaces; mass from catalogue weights, not weighed"),
        ("Pi 5, Navigator, 2 × 4-in-1 ESC, camera, tilt servo, wiring", 240.0, 0.0, (20, 0, 5), "assumed", "inside the tube"),
        ("4S1P 21700 pack", 280.0, 0.0, (-55, 0, -22), "assumed", "4 × 70 g cells, low in the tube aft"),
        ("8 × UG500", 8 * S.THRUSTER_MASS_G, 8 * 12.0, (-20, 0, -20), "assumed", "four at 0, four at -40"),
        ("penetrators, Bar02, lights, tether stub", 90.0, 25.0, (-60, 0, -10), "assumed", ""),
        # The navigation sensors (sensors.md). Displacement is weight in air
        # less weight in water, both from the makers.
        ("Water Linked DVL A50, under the belly", 170.0, 65.0, DVL_AT, "assumed",
         "the maker's figures, not weighed: 66 x 25 mm; 170 g in air, 105 g in water"),
        ("3 x Blue Robotics Ping2, under the nose: ahead and 25 degrees either side", 3 * 187.0, 3 * 87.0, PINGS_AT, "assumed",
         "the maker's figures, not weighed: 71 x 47 x 41 mm; 187 g in air, 100 g in water, each"),
    ]
    mass = sum(r[1] for r in rows)
    disp = sum(r[2] for r in rows)
    # Lead on the belly until it floats by a few grams: positive enough to
    # come up if it dies, small enough not to fight the verticals.
    keep_g = 20.0
    # Trim: lead on the belly if it floats too well, foam under the lid if it
    # does not. The sensors made it heavy — three echosounders and a DVL are
    # 200 g in water, all of it low — and the lead this used to ask for went
    # negative, which is a number and not a part. Foam high up is the honest
    # answer, and it lifts the centre of buoyancy, which steadies it.
    want = disp * FRESH - mass - keep_g
    if want >= 0:
        name, rho, z = "lead trim on the belly", LEAD, -S.HULL_H / 2 + 3
        grams = want / (1 - FRESH / LEAD)
        volume = grams / LEAD
    else:
        name, rho, z = "closed-cell foam under the lid (80 kg/m³)", FOAM, S.HULL_H / 2 - 12
        volume = -want / (FRESH - FOAM)
        grams = volume * FOAM

    # And along the hull where it levels the vehicle: the weight straight under
    # the buoyancy. Left at an arbitrary station it flew forty degrees nose-up
    # in the first tank dive. CG minus CB along x is linear in the station, so
    # two trials find it; a builder does the same with the part on the bench.
    def tilt(at_x):
        trial = rows + [(name, grams, volume, (at_x, 0, z))]
        cg_x = sum(r[1] * r[3][0] for r in trial) / sum(r[1] for r in trial)
        cb_x = sum(r[2] * r[3][0] for r in trial) / sum(r[2] for r in trial)
        return cg_x - cb_x
    a, b = tilt(0.0), tilt(100.0)
    at_x = 0.0 if abs(b - a) < 1e-12 else -a * 100.0 / (b - a)
    if not (S.HULL_TAIL + 20 <= at_x <= S.HULL_NOSE - 20):
        raise SystemExit(f"no station levels it: the {name} would have to sit at x = {at_x:.0f} mm")
    rows.append((name, grams, volume, (at_x, 0, z), "derived",
                 f"to leave +{keep_g:.0f} g, at x = {at_x:.0f} mm so it floats level"))
    return rows


def centre(rows, i):
    w = sum(r[i] for r in rows)
    return np.sum([np.asarray(r[3], float) * r[i] for r in rows], axis=0) / w


def to_catalogue(p_mm, cg_mm):
    """Drawing (mm, y port, tube centre) to catalogue (m, y starboard, CG)."""
    d = (np.asarray(p_mm, float) - cg_mm) / 1000.0
    return [round(float(d[0]), 4), round(float(-d[1]), 4), round(float(d[2]), 4)]


def inertia(rows, cg_mm):
    """Point masses for the parts, plus each part's own spread as a box."""
    spread = {  # part extents in mm, for its own moment
        0: (240, 110, 50), 1: (310, 250, 110), 2: (275, 89, 89), 3: (120, 60, 40), 4: (80, 45, 45),
        5: (300, 240, 80), 6: (250, 100, 60), 7: (66, 66, 25), 8: (71, 47, 41), 9: (120, 60, 6),
    }
    I = np.zeros((3, 3))
    for i, r in enumerate(rows):
        m = r[1] / 1000
        c = (np.asarray(r[3], float) - cg_mm) / 1000
        I += m * (np.dot(c, c) * np.eye(3) - np.outer(c, c))
        a, b, h = (np.asarray(spread.get(i, (50, 50, 50)), float) / 1000)
        I += m / 12 * np.diag([b * b + h * h, a * a + h * h, a * a + b * b])
    return I


def quadratic(scaled_diagonal: list) -> dict:
    """The quadratic drag: surge, sway and heave from mini-hoot's own hull
    (the .usd this file writes), the rotations scaled from the BlueROV2
    (hardware/hull_coefficients.py says why). Scaled throughout when there
    is no hull yet to read."""
    sys.path.insert(0, str(HERE.parent))
    import hull_coefficients

    got = hull_coefficients.drag_for(PKG / "mini-hoot.usd")
    if got is None:
        return {"note": "Assumed: the BlueROV2's scaled by frontal area per axis.", "diagonal": scaled_diagonal}
    drag, note = got
    return {"note": note, "diagonal": [round(-abs(d), 3) for d in drag] + list(scaled_diagonal[3:])}


def dynamics():
    rows = budget()
    mass_g = sum(r[1] for r in rows)
    disp_cm3 = sum(r[2] for r in rows)
    cg = centre(rows, 1)
    cb = centre(rows, 2)
    I = inertia(rows, cg)
    cat = lambda p: to_catalogue(p, cg)  # noqa: E731
    # Scaled from the BlueROV2 the runtime already flies, by displaced volume
    # for added mass and by frontal area for drag. Assumed, and the first
    # thing a tow in the tank should measure.
    vol_ratio = disp_cm3 / 11054.0
    area = [0.25 * 0.135 / (0.338 * 0.254), 0.342 * 0.135 / (0.457 * 0.254), 0.342 * 0.25 / (0.457 * 0.338)]
    rot = (0.342 / 0.457) ** 4
    blue_am = [-5.5, -12.7, -14.57, -0.12, -0.12, -0.12]
    blue_lin = [-4.03, -6.22, -5.18, -0.07, -0.07, -0.07]
    blue_quad = [-18.18, -21.66, -36.99, -1.55, -1.55, -1.55]
    am = [round(v * vol_ratio, 3) for v in blue_am[:3]] + [round(v * rot * vol_ratio, 4) for v in blue_am[3:]]
    lin = [round(blue_lin[i] * area[i], 3) for i in range(3)] + [round(v * rot, 4) for v in blue_lin[3:]]
    quad = [round(blue_quad[i] * area[i], 3) for i in range(3)] + [round(v * rot, 4) for v in blue_quad[3:]]
    units = []
    for name, px, py, pz in S.VERTICAL:
        units.append({"name": name, "position": cat((px, py, pz)), "direction": [0, 0, 1]})
    for name, px, py, pz, hdg in S.CORNER:
        a = math.radians(hdg)
        units.append({"name": name, "position": cat((px, py, pz)),
                      "direction": [round(math.cos(a), 3), round(-math.sin(a), 3), 0]})
    front_light = [(px + S.LIGHT_REACH, py, pz + S.LIGHT_DZ) for _, px, py, pz in S.VERTICAL if px > 0]
    capacity_wh = 4.2 * 14.4
    return rows, {
        "massKg": round(mass_g / 1000, 3),
        "displacedVolumeM3": round(disp_cm3 / 1e6, 6),
        "envelope": {"maxDepthM": 10.0, "maxSpeedMs": 0.9, "minAltitudeM": 0.05,
                     "note": "10 m is the tether; the 3\" acrylic tube is rated far deeper. Top speed derived from four horizontals at 45 degrees against the assumed drag."},
        "hull": {
            "note": "mini-hoot: the moulded Titan form around a Blue Robotics 3-inch tube whose dome is the nose. Drawn in hardware/mini/shape.py; not yet built.",
            "dimensionsM": [0.342, 0.25, 0.135],
            "dimensionsFrom": "derived: the bounding box of the drawing, thrusters and dome included",
            "shape": "A flooded nylon shell: red lid, black chassis, four wing pods on swept arms and four toed-in corner ducts. Bluff, like a Titan, not a fairing.",
        },
        "provenance": {
            "note": "Nothing on this vehicle is measured: it has not been built. Mass and buoyancy are summed from the parts in hardware/mini/package.py; hydrodynamic coefficients are the BlueROV2's scaled to this size and are the first thing a tow in the tank should replace.",
            "budget": [{"part": r[0], "grams": round(r[1], 1), "displacedCm3": round(r[2], 1), "kind": r[4], "note": r[5]} for r in rows],
        },
        "centreOfGravityM": [0, 0, 0],
        "centreOfBuoyancyM": [round(float(v), 4) for v in (np.asarray(to_catalogue(cb, cg)))],
        "inertiaTensor": [round(float(v), 5) for v in I.reshape(-1)],
        "addedMass": {"note": "Diagonal, surge sway heave roll pitch yaw. Assumed: the BlueROV2's scaled by displaced volume.", "diagonal": am},
        "linearDamping": {"note": "Assumed: the BlueROV2's scaled by frontal area per axis.", "diagonal": lin},
        "quadraticDamping": quadratic(quad),
        "thrusters": {
            "note": "Eight ApisQueen UG500. Four vertical in the wing pods give heave, roll and pitch; four horizontal at the hull's corners, toed in at 45 degrees as on the BlueROV2, give surge, sway and yaw. Fully actuated: it can hold a spot against a current from any side.",
            "model": "ApisQueen UG500",
            "maxForwardN": S.THRUST_FWD_N,
            "maxReverseN": S.THRUST_REV_N,
            "timeConstantS": 0.1,
            # How fast the propellers turn at full command, and how big they
            # are: what the drawing spins, and later what the wash is worked
            # out from. Neither is published for the UG500.
            "maxRpm": 3600,
            "rpmFrom": "assumed: ApisQueen do not publish the UG500's speed; a Blue Robotics T200's 3,600 rpm at 16 V",
            "propellerDiameterM": round((S.DUCT_OD - 6.0) / 1000.0, 3),
            "propellerFrom": "assumed: the largest propeller that turns inside the 44 mm guard",
            "units": units,
        },
        "tether": {"_": "10 m of thin twisted pair, data only: the battery powers the vehicle. Slightly buoyant, as tank tethers are made, so its slack floats above the vehicle instead of sinking across it.",
                   "diameterM": 0.005, "lengthM": 10.0, "weightNPerM": -0.004, "dragNormal": 1.2,
                   # Leaves the crown straight up for this far before it is free to bend:
                   # the strain relief on the plug, which is what keeps it off the lid.
                   "leadOutM": 0.05,
                   # Tied on at the top, through the knob on the crown, as the
                   # Titan's plug is: a cable pulling from above holds the
                   # vehicle level, one from the stern pitches it.
                   "attachM": cat((S.KNOB_X, 0.0, S.HULL_H / 2 + S.KNOB_H))},
        "sensors": [
            {"kind": "underwater_camera", "name": "forward", "position": cat((S.CAMERA_X, 0, 0)), "orientation": [0, 0, 0],
             "focalLengthMm": 21, "widthPx": 1920, "heightPx": 1080, "watts": 2.5,
             "wattsNote": "Blue Robotics Low-Light HD USB camera behind the dome, about 80 degrees across; it encodes H.264 itself"},
            {"kind": "imu", "name": "body", "position": [0, 0, 0], "watts": 0.2, "wattsNote": "on the Navigator"},
            {"kind": "barometer", "name": "depth", "position": cat((-S.TUBE_L / 2 - S.FLANGE_T, -20, -20)), "watts": 0.05,
             "wattsNote": "a Bar02 through the rear cap, 0.16 mm resolution"},
            {"kind": "imaging_sonar", "name": "echosounders", "position": cat((88.0, 0.0, PING_Z)), "orientation": [0, 0, 0],
             "beams": 3, "horizontalFovDeg": 50, "beamWidthDeg": 25, "verticalFovDeg": 25,
             "rangeM": [0.3, 5.0], "pingsPerSecond": 10, "rangeNoiseM": 0.01, "missesShare": 0.05,
             "note": "Three Blue Robotics Ping2 single-beam echosounders, ahead and 25 degrees either side so their 25 degree cones touch: 75 degrees ahead without a gap, 115 kHz. Range set to 5 m for a tank (it reaches 100 m); 0.3 m nearest and 1 cm noise are assumed until measured in the tank, where the glass echoes.",
             "watts": 1.5, "wattsNote": "100 mA at 5 V each, typical"},
            {"kind": "dvl", "name": "bottom_track", "position": cat(DVL_AT),
             "note": "Water Linked DVL A50: four beams at 22.5 degrees, 1 MHz, 5 cm to 50 m altitude, 4-15 Hz.",
             "watts": 4.0, "wattsNote": "assumed: about 4 W"},
        ],
        "topicContract": {
            "note": "What the vehicle publishes and acts on, identical in the simulator and on the bench: the Pi bridges ArduSub to these topics.",
            "publishes": [
                {"topic": "/camera/image_raw", "type": "sensor_msgs/msg/Image"},
                {"topic": "/imu/data", "type": "sensor_msgs/msg/Imu"},
                {"topic": "/depth", "type": "sensor_msgs/msg/FluidPressure"},
                {"topic": "/sonar/scan", "type": "sensor_msgs/msg/LaserScan"},
                {"topic": "/dvl/twist", "type": "geometry_msgs/msg/TwistWithCovarianceStamped"},
                {"topic": "/dvl/range", "type": "sensor_msgs/msg/Range"},
            ],
            "subscribes": [
                {"topic": "/thruster_cmd", "type": "std_msgs/msg/Float64MultiArray",
                 "note": "Eight normalised commands in [-1, 1], in the order the thruster units are listed."},
                {"topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist",
                 "note": "A body-frame wrench for stacks that would rather not allocate thrust themselves."},
            ],
        },
        "power": {"note": "A 4S1P 21700 pack (Molicel P42A, 4.2 Ah). About two hours at 25 W.",
                  "capacityWh": round(capacity_wh, 1), "nominalVoltage": 14.4, "hotelW": 10.5,
                  "thrusterMaxW": 160.0, "powerExponent": 1.5, "reserveFraction": 0.15,
                  "hotelNote": "Pi 5 8 W, Navigator 0.5 W, camera 2 W"},
        "lights": {"note": "Two small LED lights in the front pods' noses. Assumed: none chosen yet.",
                   "fitted": [{"name": "port" if p[1] > 0 else "starboard", "kind": "led", "position": cat(p),
                               "aim": [1.0, 0.0, -0.1], "lumens": 500.0, "watts": 5.0, "coneDeg": 100.0, "colourK": 5000}
                              for p in front_light]},
        "computer": {"kind": "raspberry-pi-5", "watts": 8.0, "tops": 0.0, "ramGb": 4,
                     "note": "The body: ArduSub on a Navigator keeps it level and at depth at 400 Hz. The brain is a DGX Spark on the far end of the tether."},
    }, cg


USD_HEAD = """#usda 1.0
(
    defaultPrim = "MiniHoot"
    metersPerUnit = 1
    upAxis = "Z"
    doc = "mini-hoot, drawn in hardware/mini/shape.py. Origin at the centre of gravity, x forward, metres."
)

def Xform "MiniHoot"
{
"""


def material(name, colour, rough, metal=0.0, opacity=1.0, clearcoat=0.0, emissive=None):
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    em = f"\n            color3f inputs:emissiveColor = ({emissive})" if emissive else ""
    return f"""    def Material "{name}"
    {{
        token outputs:surface.connect = </MiniHoot/Looks/{name}/S.outputs:surface>
        def Shader "S"
        {{
            uniform token info:id = "UsdPreviewSurface"
            color3f inputs:diffuseColor = ({r ** 2.2:.4f}, {g ** 2.2:.4f}, {b ** 2.2:.4f})
            float inputs:roughness = {rough}
            float inputs:metallic = {metal}
            float inputs:opacity = {opacity}
            float inputs:clearcoat = {clearcoat}
            float inputs:ior = 1.49{em}
            token outputs:surface
        }}
    }}
"""


def usd_mesh(name, m, cg, mat):
    v = (m.vertices - cg) / 1000.0
    v[:, 1] *= -1                       # y to starboard: a mirror, so the winding turns over too
    f = m.faces[:, ::-1]
    n = m.vertex_normals.copy()
    n[:, 1] *= -1
    pts = ", ".join(f"({a:.5f}, {b:.5f}, {c:.5f})" for a, b, c in v)
    nrm = ", ".join(f"({a:.4f}, {b:.4f}, {c:.4f})" for a, b, c in n)
    idx = ", ".join(str(i) for i in f.reshape(-1))
    return f"""    def Mesh "{name}" (prepend apiSchemas = ["MaterialBindingAPI"])
    {{
        uniform token subdivisionScheme = "none"
        int[] faceVertexCounts = [{", ".join(["3"] * len(f))}]
        int[] faceVertexIndices = [{idx}]
        point3f[] points = [{pts}]
        normal3f[] normals = [{nrm}] (interpolation = "vertex")
        rel material:binding = </MiniHoot/Looks/{mat}>
    }}
"""


def the_sensors():
    """The Ping2s and the DVL as shapes, so the pictures show what is fitted."""
    out = []
    for name, (x, y), yaw in PINGS:
        turn = trimesh.transformations.rotation_matrix(math.radians(yaw), [0, 0, 1])
        body = trimesh.creation.box(extents=(71.0, 47.0, 41.0))
        face = trimesh.creation.cylinder(radius=17.0, height=4.0,
                                         transform=trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
        face.apply_translation((37.5, 0.0, 0.0))
        for m in (body, face):
            m.apply_transform(turn)
            m.apply_translation((x, y, PING_Z))
        out += [(f"Ping_{name}", body, "Sensor"), (f"PingFace_{name}", face, "SensorFace")]
    dvl = trimesh.creation.cylinder(radius=33.0, height=25.0, sections=48)
    dvl.apply_translation(DVL_AT)
    out.append(("Dvl", dvl, "Sensor"))
    return out


def write_usd(cg):
    looks = {
        "cover": ("Lid", 30000), "chassis": ("Chassis", 50000), "ref-thrusters": ("Thruster", 12000),
        "ref-enclosure": ("Metal", 8000), "ref-dome": ("Dome", 6000), "ref-camera": ("Camera", 3000), "ref-lights": ("Lens", 1500),
    }
    body = [USD_HEAD, '    def Scope "Looks"\n    {\n',
            material("Lid", S.COVER_COLOUR, 0.3, clearcoat=1.0),
            material("Chassis", S.CHASSIS_COLOUR, 0.5, clearcoat=0.3),
            material("Thruster", "#45484c", 0.45),
            material("Metal", "#4a4d52", 0.35, metal=0.85),
            material("Dome", "#dfe9ef", 0.02, opacity=0.12),
            material("Camera", "#0d0f11", 0.2),
            material("Lens", "#f4f1e6", 0.1, emissive="0.6, 0.58, 0.5"),
            # Inside the Looks scope with the rest: written after it closed,
            # they sat at /MiniHoot/Sensor and every sensor was drawn unbound.
            material("Sensor", "#2a2c30", 0.4, clearcoat=0.5),
            material("SensorFace", "#1f6fb2", 0.35), "    }\n"]
    for name, m, mat in the_sensors():
        body.append(usd_mesh(name, m, cg, mat))
    for part, (mat, faces) in looks.items():
        m = trimesh.load(OUT / f"{part}.stl")
        if len(m.faces) > faces:
            m = m.simplify_quadric_decimation(face_count=faces, aggression=2)
        body.append(usd_mesh(part.replace("ref-", "").replace("-", "_").title(), m, cg, mat))
    body.append("}\n")
    # Authored as text, shipped as crate: the same stage at a fifth of the size.
    from pxr import Usd
    text = OUT / "mini-hoot.usda"
    text.write_text("".join(body))
    Usd.Stage.Open(str(text)).Export(str(PKG / "mini-hoot.usd"))
    # And the physical materials beside the preview ones (looks.py).
    looks = importlib.util.spec_from_file_location("mini_looks", HERE / "looks.py")
    dressing = importlib.util.module_from_spec(looks)
    looks.loader.exec_module(dressing)
    hull = Usd.Stage.Open(str(PKG / "mini-hoot.usd"))
    dressing.dress(hull)
    hull.GetRootLayer().Save()
    (PKG / "mini-hoot.usda").unlink(missing_ok=True)


README = """# mini-hoot

iocean's first vehicle: a small, fully actuated ROV for a 1 m tank, in the
moulded Titan form. A Blue Robotics 3" tube is the dry hull and its dome the
nose; eight ApisQueen UG500 thrusters, four vertical in wing pods and four
horizontal toed in at the corners; a Raspberry Pi 5 with a Navigator running
ArduSub inside; 10 m of data-only tether to a DGX Spark that runs the
controllers.

Designed in the simulator first. Nothing here is measured: mass and buoyancy
are summed from the parts, and the hydrodynamic coefficients are the
BlueROV2's scaled to this size. dynamics.json says which number is which.

The drawing, the parts and the build: `hardware/mini/` (spec.md, params.py,
shape.py, package.py).
"""


def main() -> int:
    PKG.mkdir(parents=True, exist_ok=True)
    rows, dyn, cg = dynamics()
    (PKG / "dynamics.json").write_text(json.dumps(dyn, indent=1, ensure_ascii=False) + "\n")
    (PKG / "README.md").write_text(README)
    if "--no-hull" not in sys.argv:
        write_usd(cg)
    pic = OUT / "look-quarter.png"
    if pic.exists():
        from PIL import Image
        Image.open(pic).convert("RGB").save(PKG / "picture.jpg", quality=90)
        (PKG / "picture.json").write_text(json.dumps({"credit": "drawn: hardware/mini/shape.py", "kind": "render"}) + "\n")
    mass = dyn["massKg"]
    print(f"mass {mass:.3f} kg, displaced {dyn['displacedVolumeM3'] * 1e6:.0f} cm³, "
          f"net {(dyn['displacedVolumeM3'] * 1e6 * FRESH - mass * 1000):+.0f} g in fresh water")
    print(f"CB above CG {dyn['centreOfBuoyancyM'][2] * 1000:.1f} mm; inertia diag {[dyn['inertiaTensor'][i] for i in (0, 4, 8)]}")
    for r in rows:
        print(f"  {r[0]:58s} {r[1]:7.0f} g {r[2]:7.0f} cm³  {r[4]}")
    print(f"usd {(PKG / 'mini-hoot.usd').stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
