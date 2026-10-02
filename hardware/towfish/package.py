"""The EdgeTech 2300 towfish as a catalogue vehicle: what KAUST tows.

    python3 hardware/towfish/package.py

From EdgeTech's 2300 datasheet (PN 0052421, read 2 October 2026): 205.9 × 81.7 ×
50.8 cm (76.3 with the rear fins); 449 kg in air, 272 kg in water; 3,000 m;
tri-frequency side-scan, 120/410/850 or 230/540/850 kHz, 500/300/200/150/75 m a
side, a 50-degree vertical beam tilted down 26; a 1–10 kHz sub-bottom profiler,
10–30 cm resolution, 20 m into coarse sand and 200 m into clay; heading, pitch,
roll, heave and depth sensors. No thrusters: it is flown by the ship.

Assumed, and said so in the package: its drag (a bluff body this size, from
its frontal and side areas), its added mass, and the tow cable (a 17 mm
armoured coax, 4.4 N/m in water, 150 kN breaking).
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
INTO = ROOT / "catalog/vehicles/edgetech-2300"
L, W, H = 2.059, 0.817, 0.508
AIR, WATER = 449.0, 272.0
RHO = 1025.0


def main() -> None:
    volume = (AIR - WATER) / RHO
    q = 0.5 * RHO
    surge = q * 0.8 * (W * H)          # nose on: a rounded bluff body, Cd 0.8
    sway = q * 1.2 * (L * H)           # side on
    heave = q * 1.2 * (L * W)          # face on
    doc = {
        "massKg": AIR, "displacedVolumeM3": round(volume, 4),
        "envelope": {"maxDepthM": 3000.0, "maxSpeedMs": 3.1, "minAltitudeM": 2.0,
                     "note": "Rated to 3,000 m (published). Towed at 2–6 kn; a fish is flown at 10–15% of its range above the bottom (EdgeTech's guidance)."},
        "hull": {"note": "EdgeTech 2300 combined side-scan and sub-bottom towfish.",
                 "dimensionsM": [L, W, H], "dimensionsFrom": "published: 205.9 × 81.7 × 50.8 cm (76.3 cm with the rear fins)",
                 "weathervanes": True,
                 "shape": "A flat aluminium sled with a tow bail and two tail fins that point it into the flow."},
        "provenance": {"note": "Size, weight in air and water, depth rating and the sonars' figures are EdgeTech's published datasheet. Drag, added mass and the tow cable are assumed."},
        "centreOfGravityM": [0, 0, 0], "centreOfBuoyancyM": [0, 0, 0.08],
        "inertiaTensor": [round(AIR / 12 * (W * W + H * H), 2), 0, 0, 0, round(AIR / 12 * (L * L + H * H), 2), 0, 0, 0,
                          round(AIR / 12 * (L * L + W * W), 2)],
        "addedMass": {"note": "Assumed: half the displaced mass along, the displaced mass across and down; rotational terms small.",
                      "diagonal": [round(-0.5 * RHO * volume, 1), round(-RHO * volume * 2, 1), round(-RHO * volume * 3, 1), -5.0, -20.0, -20.0]},
        "linearDamping": {"note": "Assumed: small; a towfish is all quadratic drag.", "diagonal": [-20.0, -40.0, -60.0, -10.0, -40.0, -40.0]},
        "quadraticDamping": {"note": "Assumed: ½ρ·Cd·area, Cd 0.8 nose on and 1.2 side and face on.",
                             "diagonal": [round(-surge, 1), round(-sway, 1), round(-heave, 1), -80.0, -400.0, -400.0]},
        "thrusters": {"note": "None. It is flown by the ship.", "maxForwardN": 0.0, "maxReverseN": 0.0, "units": []},
        "tether": {"_": "The tow cable: single armoured coax (published: digital telemetry over a single coaxial tow cable). Its size and strength are assumed.",
                   "diameterM": 0.0173, "lengthM": 0.0, "weightNPerM": 4.4, "massKgPerM": 0.95, "dragNormal": 1.2,
                   "attachM": [0.55, 0.0, 0.45], "breakingN": 150000.0, "axialStiffnessN": 4.0e6},
        "sensors": [
            {"kind": "side_scan", "name": "side_scan", "position": [0, 0, -0.2],
             "frequencieskHz": [120, 410, 850], "rangeMBykHz": {"120": 500, "230": 300, "410": 200, "540": 150, "850": 75},
             "acrossTrackResolutionMBykHz": {"120": 0.065, "230": 0.03, "410": 0.018, "540": 0.015, "850": 0.01},
             "horizontalBeamDegBykHz": {"120": 0.68, "230": 0.5, "410": 0.3, "540": 0.26, "850": 0.2},
             "verticalBeamDeg": 50.0, "depressionDeg": 26.0, "frequencykHz": 410, "binsPerSide": 512,
             "note": "EdgeTech 2300 side-scan, published figures; the ping is rendered by systems/sidescan.py."},
            {"kind": "sub_bottom", "name": "sub_bottom", "position": [0, 0, -0.25], "bandkHz": [1, 10],
             "resolutionM": [0.1, 0.3], "penetrationM": {"coarse sand": 20, "clay": 200},
             "note": "Four DW-106 transducers and a PVDF array (published). Not yet simulated: it needs what lies under the seabed."},
            {"kind": "imu", "name": "attitude", "position": [0, 0, 0]},
            {"kind": "barometer", "name": "depth", "position": [0, 0, 0]},
        ],
    }
    INTO.mkdir(parents=True, exist_ok=True)
    (INTO / "dynamics.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    (INTO / "README.md").write_text(
        "# EdgeTech 2300\n\nA combined side-scan and sub-bottom towfish, the one KAUST tows. In the catalogue from "
        "EdgeTech's datasheet; drag, added mass and the tow cable are assumed. No thrusters: a dive flies it by "
        "asking for a tow — `\"tow\": {\"speedKn\": 4, \"headingDeg\": 90, \"cableOutM\": 60, \"frequencykHz\": 850}`. "
        "Built by `hardware/towfish/package.py`.\n")
    print(f"edgetech-2300 -> {INTO}")


if __name__ == "__main__":
    main()
