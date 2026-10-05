"""Boxfish Luna as a catalogue vehicle: a reference for the reef survey the buyers want.

    hardware/.venv/bin/python hardware/luna/package.py

Writes catalog/vehicles/boxfish-luna: dynamics.json (what the simulator flies),
README.md, and the drawn hull (boxfish-luna.usd, from shape.py). Then run
packages/sdk-python/tools/generate_vehicles.py --package catalog/vehicles/boxfish-luna.

What Boxfish publish, and is taken as stated (boxfishrobotics.com, Luna page,
read 2 October 2026): 730 × 435 × 351 mm; 25 kg; eight 3D-vectored thrusters,
six degrees of freedom; 300, 500 or 1,000 m; a 4K full-frame main camera and an
optional stereo pair for fish surveys; 20,000 lumens of light; a 600 Wh
battery, up to ten hours; USBL and DVL; an Oculus imaging sonar; miniCTD, pH,
turbidity, chlorophyll and a hydrophone; an optional fibre tether, 2.7 or
4.3 mm, neutrally buoyant in fresh water.

What their photographs show, and is read off them (shape.py): the hull — a
yellow cylinder in a black frame — and where the thrusters and lamps are. The
thrusters are one at each corner of the two end plates.

What they do not, and is assumed here and said so in the package: which way
each thruster points and how hard it pushes (a T200's figures); every
hydrodynamic coefficient (the
BlueROV2's, scaled by displaced volume for added mass and by frontal area for
drag); the lenses; the colours. These are the numbers a tow test or Boxfish's
own figures replace.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("luna_shape", pathlib.Path(__file__).parent / "shape.py")
shape = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shape)
INTO = ROOT / "catalog/vehicles/boxfish-luna"
BASE = ROOT / "catalog/vehicles/bluerov2/dynamics.json"

L, W, H = 0.730, 0.435, 0.351
MASS = 25.0
RHO = 1025.0
# Trimmed a little light, as a working AUV is so that it surfaces if it dies:
# a tenth of a per cent of its weight.
VOLUME = MASS * 1.001 / RHO

# The BlueROV2's frame, which the coefficients are scaled from.
BR2 = (0.457, 0.338, 0.254)


def scaled(base: dict) -> dict:
    v = VOLUME / base["displacedVolumeM3"]
    across = {"surge": (W * H) / (BR2[1] * BR2[2]), "sway": (L * H) / (BR2[0] * BR2[2]),
              "heave": (L * W) / (BR2[0] * BR2[1])}
    turn = 4.0          # rotational terms: area times lever squared, roughly; assumed
    am = base["addedMass"]["diagonal"]
    lin = base["linearDamping"]["diagonal"]
    quad = base["quadraticDamping"]["diagonal"]
    k = [across["surge"], across["sway"], across["heave"], turn, turn, turn]
    return {"addedMass": [round(a * (v if i < 3 else turn), 3) for i, a in enumerate(am)],
            "linearDamping": [round(a * k[i], 3) for i, a in enumerate(lin)],
            "quadraticDamping": [round(a * k[i], 3) for i, a in enumerate(quad)]}


def sensors() -> list[dict]:
    return [
        {"kind": "underwater_camera", "name": "forward", "position": [0.30, 0.0, -0.005], "orientation": [0, 0, 0],
         "focalLengthMm": 20, "sensorWidthMm": 36.0, "widthPx": 3840, "heightPx": 2160, "watts": 6.0,
         "note": "The 4K full-frame main camera, 50 MP stills. The lens is assumed: 20 mm on full frame."},
        {"kind": "underwater_camera", "name": "stereo", "position": [0.34, 0.0, -0.08], "orientation": [0, 25, 0],
         "focalLengthMm": 8, "widthPx": 1920, "heightPx": 1200, "baselineM": 0.12, "watts": 4.0,
         "note": "The optional stereo pair for fish surveys: measuring a fish needs two eyes. Baseline and lenses assumed."},
        {"kind": "imaging_sonar", "name": "forward_looking", "position": [0.35, 0.0, 0.12], "orientation": [0, 0, 0],
         "rangeM": [0.1, 120.0], "horizontalFovDeg": 130, "verticalFovDeg": 20, "watts": 18.0,
         "note": "An Oculus M750d, the one Boxfish offer."},
        {"kind": "dvl", "name": "bottom_track", "position": [0.0, 0.0, -0.17], "watts": 4.0,
         "note": "A DVL, as Boxfish offer; a Water Linked A50's figures are used."},
        {"kind": "imu", "name": "body", "position": [0, 0, 0], "watts": 0.5},
        {"kind": "barometer", "name": "depth", "position": [0, 0, 0], "watts": 0.1},
        {"kind": "ctd", "name": "ctd", "position": [0.0, 0.0, 0.0], "everyS": 1.0, "watts": 0.35,
         "note": "Boxfish's miniCTD."},
        {"kind": "water_quality", "name": "water", "position": [0.0, 0.1, 0.0], "everyS": 1.0,
         "measures": ["turbidity", "chlorophyll", "pH"], "watts": 1.0,
         "note": "Turbidity, chlorophyll and pH. Turbidity is read from the dive's sediment: what the vehicle's "
                 "own wash raised is what it measures."},
        {"kind": "hydrophone", "name": "hydrophone", "position": [-0.3, 0.0, 0.0], "watts": 0.5},
    ]


def quadratic(scaled_diagonal: list) -> dict:
    """The quadratic drag: surge, sway and heave from the hull drawn by
    shape.py, the rotations scaled from the BlueROV2 (hardware/hull_coefficients.py
    says why)."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    import hull_coefficients

    got = hull_coefficients.towed_for("boxfish-luna") or hull_coefficients.drag_for(INTO / "boxfish-luna.usd")
    if got is None:
        return {"note": "Assumed: the BlueROV2's, scaled by frontal area per axis.", "diagonal": scaled_diagonal}
    drag, note = got
    return {"note": note, "diagonal": [round(-abs(d), 3) for d in drag] + list(scaled_diagonal[3:])}


def main() -> None:
    INTO.mkdir(parents=True, exist_ok=True)
    (INTO / "boxfish-luna.usda").unlink(missing_ok=True)      # the plain box it replaces
    shape.build().save(INTO / "boxfish-luna.usd")
    base = json.loads(BASE.read_text())
    coefficients = scaled(base)
    Ixx = MASS / 12 * (W * W + H * H)
    Iyy = MASS / 12 * (L * L + H * H)
    Izz = MASS / 12 * (L * L + W * W)
    doc = {
        "massKg": MASS,
        "displacedVolumeM3": round(VOLUME, 6),
        "envelope": {"maxDepthM": 300.0, "maxSpeedMs": 1.0, "minAltitudeM": 0.3,
                     "note": "300 m is the base rating (500 and 1,000 m are options). Top speed is not published; a metre a second is assumed."},
        "hull": {"note": "Boxfish Luna, a hovering reef AUV that can also fly on a fibre tether.",
                 "dimensionsM": [L, W, H], "dimensionsFrom": "published: 730 × 435 × 351 mm",
                 "shape": "A yellow cylindrical pressure hull lying fore and aft in a black frame of two end plates, an acrylic dome on its nose over the main camera, yellow-and-carbon tubes along the top and carbon skids under it, a ducted thruster at each corner of each end plate, a lamp either side of the dome. Drawn from Boxfish's photographs (hardware/luna/shape.py)."},
        "provenance": {"note": "Size, mass, thruster count, sensors, battery and depth ratings are Boxfish's published figures. Thruster positions and figures, every hydrodynamic coefficient, the lenses and the colours are assumed (see hardware/luna/package.py), and are what a tow test replaces."},
        "centreOfGravityM": [0, 0, 0],
        "centreOfBuoyancyM": [0, 0, 0.03],
        "inertiaTensor": [round(Ixx, 4), 0, 0, 0, round(Iyy, 4), 0, 0, 0, round(Izz, 4)],
        "addedMass": {"note": "Assumed: the BlueROV2's, scaled by displaced volume (rotational terms by four).",
                      "diagonal": coefficients["addedMass"]},
        "linearDamping": {"note": "Assumed: the BlueROV2's, scaled by frontal area per axis.",
                          "diagonal": coefficients["linearDamping"]},
        "quadraticDamping": quadratic(coefficients["quadraticDamping"]),
        "thrusters": {"note": "Eight 3D-vectored thrusters (published), one at each corner of the two end plates (photographed). Which way each points is not published or visible: toed out 45 degrees and tilted 30 degrees towards the middle (assumed; tilted out along the corner it would have a tenth of the roll authority). A T200's 51.5 N forward and 40 N reverse (assumed).",
                      "model": "assumed T200-class", "maxForwardN": 51.5, "maxReverseN": 40.0, "timeConstantS": 0.2,
                      "maxRpm": 3600, "rpmFrom": "assumed: a Blue Robotics T200's 3,600 rpm at 16 V",
                      "propellerDiameterM": 0.076, "propellerFrom": "assumed: a T200's 76 mm propeller",
                      "units": shape.thrusters()},
        "tether": {"_": "The optional fibre tether, 4.3 mm, neutrally buoyant in fresh water and so a little light in the sea. Untethered unless the dive pays some out: Luna is an AUV that can be an ROV.",
                   "diameterM": 0.0043, "lengthM": 0.0, "weightNPerM": -0.004, "dragNormal": 1.2,
                   "attachM": [-0.3, 0.0, 0.17], "leadOutM": 0.05, "breakingN": 800.0,
                   "breakingFrom": "assumed: a fibre tether's strength member"},
        "sensors": sensors(),
        "topicContract": base.get("topicContract"),
        "power": {"note": "600 Wh lithium polymer, published; up to ten hours. The voltage and hotel load are assumed.",
                  "capacityWh": 600.0, "nominalVoltage": 14.8, "hotelW": 25.0, "thrusterMaxW": 350.0,
                  "powerExponent": 1.5, "reserveFraction": 0.15},
        "lights": {"note": "20,000 lumens, high CRI, dimmable (published), as two lamps either side of the dome (photographed).",
                   "fitted": [{"name": name, "kind": "lumen", "lumens": 10000.0, "watts": 100.0, "coneDeg": 120.0,
                               "colourK": 5600, "position": at, "aim": [1.0, 0.0, -0.1]} for name, at in shape.lamps()],
                   "lampsFrom": "published: 20,000 lumens; their power, beam and colour temperature assumed"},
        "computer": base.get("computer"),
    }
    INTO.mkdir(parents=True, exist_ok=True)
    (INTO / "dynamics.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    (INTO / "README.md").write_text(
        "# Boxfish Luna\n\nA hovering reef AUV that can also be flown on a fibre tether: built for the repeat visual "
        "survey of reef and fish that reef programmes ask for. In the catalogue as a reference vehicle, from Boxfish's "
        "published figures. What they do not publish — thruster layout and figures, hydrodynamic coefficients, lenses, "
        "colours — is assumed, and `dynamics.json` says which. Built by `hardware/luna/package.py`.\n")
    print(f"boxfish-luna -> {INTO}")


if __name__ == "__main__":
    main()
