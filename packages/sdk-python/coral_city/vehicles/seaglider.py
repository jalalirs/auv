"""seaglider, as the catalogue describes it. Generated; do not edit."""

from ..vehicle import Sensor, Topic, Vehicle

DYNAMICS = {
    "massKg": 52.0,
    "displacedVolumeM3": 0.05073,
    "envelope": {
        "maxDepthM": 1000.0,
        "maxSpeedMs": 0.45,
        "minAltitudeM": 10.0
    },
    "centreOfGravityM": [
        0,
        0,
        0
    ],
    "centreOfBuoyancyM": [
        0,
        0,
        0.011
    ],
    "inertiaTensor": [
        1.2,
        0,
        0,
        0,
        8.0,
        0,
        0,
        0,
        8.0
    ],
    "addedMass": {
        "note": "A slender hull with wings: little added mass along its length, a great deal across it. Nothing like the near-isotropic box an ROV is.",
        "diagonal": [
            -2.0,
            -40.0,
            -40.0,
            -0.3,
            -4.0,
            -4.0
        ]
    },
    "linearDamping": {
        "note": "Low along the hull, which is the whole design: a glider is a body built to go forward for almost nothing. The wings carry the rest and are not here \u2014 they are in the lift and drag model, which is where a wing belongs.",
        "diagonal": [
            -1.2,
            -18.0,
            -18.0,
            -0.5,
            -3.0,
            -3.0
        ]
    },
    "quadraticDamping": {
        "note": "Second-order drag. Small in surge for the same reason.",
        "diagonal": [
            -3.0,
            -60.0,
            -60.0,
            -1.0,
            -8.0,
            -8.0
        ]
    },
    "hull": {
        "note": "A thousand-metre hull, where volume stops being a constant. Squeezed at nearly the same rate as seawater on purpose: a hull softer than the water it is in grows heavier as it descends and runs away, and one stiffer stops descending. Thermal expansion is the aluminium.",
        "compressibilityPerDbar": 4.1e-06,
        "thermalExpansionPerC": 6.9e-05,
        "referenceTemperatureC": 20.0,
        "attitudeGuard": 0.0
    },
    "commandedIn": "buoyancy",
    "actuators": {
        "note": "No propeller anywhere on it. A pump moves about 800 cc in total and the working range is the middle of that; a battery on a screw thread slides to set pitch, and rolls to turn. The rates are why a dive cycle is hours.",
        "vbdCcRange": [
            -400.0,
            400.0
        ],
        "vbdRateCcPerS": 3.0,
        "massShiftM": 0.035,
        "massRollM": 0.02,
        "massRateMPerS": 0.004,
        "massShiftKg": 9.0
    },
    "wings": {
        "note": "Eriksen's parameterisation, taken from the Seaglider paper rather than invented. The reference length is the hull, not the wing: that is how the model is written.",
        "referenceLengthM": 1.8,
        "liftPerRadian": 3.836,
        "dragBase": 0.00988,
        "inducedDrag": 5.487,
        "stallDeg": 45.0
    },
    "thrusters": {
        "note": "None. This is the point of the vehicle.",
        "model": "none",
        "maxForwardN": 0.0,
        "maxReverseN": 0.0,
        "timeConstantS": 0.2,
        "units": []
    },
    "sensors": [
        {
            "kind": "ctd",
            "name": "flight",
            "position": [
                0,
                0,
                0
            ],
            "watts": 0.35,
            "wattsNote": "a pumped SBE 49, which is why gliders can carry one"
        },
        {
            "kind": "imu",
            "name": "body",
            "position": [
                0,
                0,
                0
            ],
            "watts": 0.5,
            "wattsNote": "a MEMS unit; a fibre-optic gyro is ten times this"
        },
        {
            "kind": "barometer",
            "name": "depth",
            "position": [
                0,
                0,
                0
            ],
            "watts": 0.1,
            "wattsNote": "a pressure sensor, which costs nothing"
        }
    ],
    "topicContract": {
        "note": "A glider is not commanded in thrust and does not pretend to be.",
        "publishes": [
            {
                "topic": "/ctd",
                "type": "sensor_msgs/msg/FluidPressure"
            },
            {
                "topic": "/imu/data",
                "type": "sensor_msgs/msg/Imu"
            },
            {
                "topic": "/depth",
                "type": "sensor_msgs/msg/FluidPressure"
            }
        ],
        "subscribes": [
            {
                "topic": "/buoyancy_cmd",
                "type": "std_msgs/msg/Float64MultiArray",
                "note": "Displacement in cubic centimetres, then the pitch and roll mass positions in metres."
            }
        ]
    },
    "power": {
        "note": "Primary lithium, and almost nothing drawn: a glider spends energy on the pump and on talking, and nothing at all on going forward. Ten months is what that buys.",
        "capacityWh": 10000.0,
        "nominalVoltage": 24.0,
        "hotelW": 0.25,
        "thrusterMaxW": 12.0,
        "powerExponent": 1.0,
        "reserveFraction": 0.1,
        "hotelNote": "The base electronics and nothing else: a low-power board asleep between casts, which is the whole reason a glider lasts months. It was a single lumped figure that stood for the electronics, the sensors and the lights together \u2014 which meant unfitting a Doppler log or switching the lamps off changed the endurance by exactly nothing. Each instrument states its own draw now and they are added to this, so a dive that carries less lasts longer, which is the whole reason to be able to choose."
    },
    "modem": {
        "note": "None. A glider talks by satellite when it surfaces and not at all when it is down, which is why its decisions are made in hours.",
        "bitsPerSecond": 0.0,
        "rangeM": 0.0,
        "lossShare": 1.0
    },
    "computer": {
        "kind": "low-power-board",
        "watts": 0.15,
        "tops": 0.0,
        "ramGb": 0,
        "note": "Asleep between casts. A glider's whole endurance argument is that it thinks slowly and rarely, and a hundred milliwatts over six months is more energy than any single dive spends."
    }
}

VEHICLE = Vehicle(
    slug='seaglider',
    name='seaglider',
    mass_kg=52.0,
    net_buoyancy_n=-0.017,
    thrusters=(
    ),
    sensors=(
        Sensor('ctd', 'flight'),
        Sensor('imu', 'body'),
        Sensor('barometer', 'depth'),
    ),
    publishes=(
        Topic('/ctd', 'sensor_msgs/msg/FluidPressure', ''),
        Topic('/imu/data', 'sensor_msgs/msg/Imu', ''),
        Topic('/depth', 'sensor_msgs/msg/FluidPressure', ''),
    ),
    subscribes=(
        Topic('/buoyancy_cmd', 'std_msgs/msg/Float64MultiArray', 'Displacement in cubic centimetres, then the pitch and roll mass positions in metres.'),
    ),
    capability=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    dynamics=DYNAMICS,
)
