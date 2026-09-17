"""BlueROV2, as the catalogue describes it. Generated; do not edit."""

from ..vehicle import Sensor, Thruster, Topic, Vehicle

DYNAMICS = {
    "massKg": 11.5,
    "displacedVolumeM3": 0.011054,
    "envelope": {
        "maxDepthM": 100.0,
        "maxSpeedMs": 1.5,
        "minAltitudeM": 0.3
    },
    "centreOfGravityM": [
        0,
        0,
        0
    ],
    "centreOfBuoyancyM": [
        0,
        0,
        0.02
    ],
    "inertiaTensor": [
        0.16,
        0,
        0,
        0,
        0.16,
        0,
        0,
        0,
        0.16
    ],
    "addedMass": {
        "note": "Diagonal of the 6x6 added-mass matrix, in surge, sway, heave, roll, pitch, yaw. Negative by the convention that they oppose acceleration.",
        "diagonal": [
            -5.5,
            -12.7,
            -14.57,
            -0.12,
            -0.12,
            -0.12
        ]
    },
    "linearDamping": {
        "note": "First-order drag. Dominates at the low speeds a survey ROV works at.",
        "diagonal": [
            -4.03,
            -6.22,
            -5.18,
            -0.07,
            -0.07,
            -0.07
        ]
    },
    "quadraticDamping": {
        "note": "Second-order drag, which dominates once it is moving. Heave is the largest because the frame presents its widest face to vertical motion.",
        "diagonal": [
            -18.18,
            -21.66,
            -36.99,
            -1.55,
            -1.55,
            -1.55
        ]
    },
    "thrusters": {
        "note": "The standard six-thruster vectored layout: four horizontal at 45 degrees giving surge, sway and yaw, and two vertical giving heave. Positions are metres from the centre of gravity; directions are unit vectors in the body frame. The verticals sit on the beam at mid-body, which is why the stock vehicle has no pitch authority and is passively stable in pitch: they were briefly modelled 12 cm forward, and every newton of depth-holding heave then pitched the hull and spent the attitude guard's budget, leaving too little horizontal thrust to hold station in a current.",
        "model": "BlueRobotics T200",
        "maxForwardN": 51.5,
        "maxReverseN": 40.0,
        "timeConstantS": 0.2,
        "units": [
            {
                "name": "front-right",
                "position": [
                    0.156,
                    0.111,
                    0.085
                ],
                "direction": [
                    0.707,
                    -0.707,
                    0
                ]
            },
            {
                "name": "front-left",
                "position": [
                    0.156,
                    -0.111,
                    0.085
                ],
                "direction": [
                    0.707,
                    0.707,
                    0
                ]
            },
            {
                "name": "rear-right",
                "position": [
                    -0.156,
                    0.111,
                    0.085
                ],
                "direction": [
                    -0.707,
                    -0.707,
                    0
                ]
            },
            {
                "name": "rear-left",
                "position": [
                    -0.156,
                    -0.111,
                    0.085
                ],
                "direction": [
                    -0.707,
                    0.707,
                    0
                ]
            },
            {
                "name": "vertical-right",
                "position": [
                    0,
                    0.218,
                    0
                ],
                "direction": [
                    0,
                    0,
                    1
                ]
            },
            {
                "name": "vertical-left",
                "position": [
                    0,
                    -0.218,
                    0
                ],
                "direction": [
                    0,
                    0,
                    1
                ]
            }
        ]
    },
    "tether": {
        "_": "The Fathom Slim tether Blue Robotics ships with it: 7.6 mm, and made very slightly buoyant in seawater on purpose \u2014 a tether that is not spends the dive dragging the vehicle down.",
        "diameterM": 0.0076,
        "lengthM": 100.0,
        "weightNPerM": -0.02,
        "dragNormal": 1.2
    },
    "sensors": [
        {
            "kind": "underwater_camera",
            "name": "forward",
            "position": [
                0.3,
                0,
                0.1
            ],
            "orientation": [
                0,
                0,
                0
            ],
            "focalLengthMm": 21,
            "widthPx": 1280,
            "heightPx": 720,
            "watts": 2.5,
            "wattsNote": "a machine-vision camera and its housing"
        },
        {
            "kind": "imaging_sonar",
            "name": "forward_looking",
            "position": [
                0.3,
                0,
                0.3
            ],
            "orientation": [
                0,
                0,
                0
            ],
            "rangeM": [
                0.5,
                10.0
            ],
            "horizontalFovDeg": 130,
            "verticalFovDeg": 20,
            "watts": 18.0,
            "wattsNote": "a Blueprint Oculus, which is most of what a small ROV's hotel load is when it is on"
        },
        {
            "kind": "dvl",
            "name": "bottom_track",
            "position": [
                0,
                0,
                -0.05
            ],
            "watts": 4.0,
            "wattsNote": "a Nortek DVL1000, averaged over its ping"
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
        },
        {
            "kind": "ctd",
            "name": "ctd",
            "position": [
                0.0,
                0.0,
                0.0
            ],
            "everyS": 1.0,
            "note": "Conductivity, temperature and depth. The instrument every oceanographic vehicle carries and the reason a glider section is worth flying.",
            "watts": 0.35,
            "wattsNote": "a pumped SBE 49, which is why gliders can carry one"
        }
    ],
    "topicContract": {
        "note": "What the vehicle publishes and what it will act on. A stack that asks for a sensor this vehicle does not carry is refused at admission rather than discovering it mid-dive.",
        "publishes": [
            {
                "topic": "/camera/image_raw",
                "type": "sensor_msgs/msg/Image"
            },
            {
                "topic": "/imu/data",
                "type": "sensor_msgs/msg/Imu"
            },
            {
                "topic": "/dvl/twist",
                "type": "geometry_msgs/msg/TwistWithCovarianceStamped"
            },
            {
                "topic": "/depth",
                "type": "sensor_msgs/msg/FluidPressure"
            },
            {
                "topic": "/tf",
                "type": "tf2_msgs/msg/TFMessage"
            },
            {
                "topic": "/sonar/scan",
                "type": "sensor_msgs/msg/LaserScan"
            },
            {
                "topic": "/ctd",
                "type": "sensor_msgs/msg/FluidPressure"
            }
        ],
        "subscribes": [
            {
                "topic": "/thruster_cmd",
                "type": "std_msgs/msg/Float64MultiArray",
                "note": "Six normalised commands in [-1, 1], in the order the thruster units are listed."
            },
            {
                "topic": "/cmd_vel",
                "type": "geometry_msgs/msg/Twist",
                "note": "A body-frame wrench for stacks that would rather not allocate thrust themselves."
            }
        ]
    },
    "power": {
        "note": "The stock BlueROV2 pack and the T200's published curve. A dive that spends energy has to spend somebody's real numbers: 14.8 V and 18 Ah is the battery Blue Robotics ships, 350 W is a T200 at full throttle on it, and the hotel load is the electronics, camera and lights the vehicle carries whether or not it is moving.",
        "capacityWh": 266.4,
        "nominalVoltage": 14.8,
        "hotelW": 6.0,
        "thrusterMaxW": 350.0,
        "powerExponent": 1.5,
        "reserveFraction": 0.1,
        "hotelNote": "The base electronics and nothing else: a Pixhawk, a Raspberry Pi and the tether interface. It was a single lumped figure that stood for the electronics, the sensors and the lights together \u2014 which meant unfitting a Doppler log or switching the lamps off changed the endurance by exactly nothing. Each instrument states its own draw now and they are added to this, so a dive that carries less lasts longer, which is the whole reason to be able to choose."
    },
    "lights": {
        "note": "Blue Robotics Lumen Subsea Lights, which is what a BlueROV2 carries. 1500 lumens each at 15 W, a 135 degree beam in water, mounted either side of the camera and aimed where it looks. Two is the stock fit; the Heavy takes four.",
        "fitted": [
            {
                "name": "port",
                "kind": "lumen",
                "position": [
                    0.22,
                    -0.16,
                    0.08
                ],
                "aim": [
                    1.0,
                    0.0,
                    -0.15
                ],
                "lumens": 1500.0,
                "watts": 15.0,
                "coneDeg": 135.0,
                "colourK": 6000
            },
            {
                "name": "starboard",
                "kind": "lumen",
                "position": [
                    0.22,
                    0.16,
                    0.08
                ],
                "aim": [
                    1.0,
                    0.0,
                    -0.15
                ],
                "lumens": 1500.0,
                "watts": 15.0,
                "coneDeg": 135.0,
                "colourK": 6000
            }
        ]
    },
    "modem": {
        "note": "An acoustic modem, because underwater there is no radio. These are a WHOI micro-modem class link at a few hundred metres: a couple of kilobits a second, two thirds of a second per kilometre each way, and packets that go missing when the range is long. It is what shapes autonomy more than anything else on this list \u2014 a vehicle that could ask the ship whenever it was unsure would be a different vehicle from the ones anybody builds.",
        "bitsPerSecond": 2400.0,
        "rangeM": 2000.0,
        "lossShare": 0.08
    },
    "computer": {
        "kind": "raspberry-pi-4",
        "watts": 5.0,
        "tops": 0.0,
        "ramGb": 4,
        "note": "What a stock BlueROV2 actually carries. It will run a PID loop and a state estimator and it will not run a network: a controller that needs tera-operations to think cannot be flown on this hull, and saying so before the dive is the point of declaring it."
    }
}

VEHICLE = Vehicle(
    slug='bluerov2',
    name='BlueROV2',
    mass_kg=11.5,
    net_buoyancy_n=-1.664,
    thrusters=(
        Thruster('front-right', (0.156, 0.111, 0.085), (0.707, -0.707, 0.0)),
        Thruster('front-left', (0.156, -0.111, 0.085), (0.707, 0.707, 0.0)),
        Thruster('rear-right', (-0.156, 0.111, 0.085), (-0.707, -0.707, 0.0)),
        Thruster('rear-left', (-0.156, -0.111, 0.085), (-0.707, 0.707, 0.0)),
        Thruster('vertical-right', (0.0, 0.218, 0.0), (0.0, 0.0, 1.0)),
        Thruster('vertical-left', (0.0, -0.218, 0.0), (0.0, 0.0, 1.0)),
    ),
    sensors=(
        Sensor('underwater_camera', 'forward'),
        Sensor('imaging_sonar', 'forward_looking'),
        Sensor('dvl', 'bottom_track'),
        Sensor('imu', 'body'),
        Sensor('barometer', 'depth'),
        Sensor('ctd', 'ctd'),
    ),
    publishes=(
        Topic('/camera/image_raw', 'sensor_msgs/msg/Image', ''),
        Topic('/imu/data', 'sensor_msgs/msg/Imu', ''),
        Topic('/dvl/twist', 'geometry_msgs/msg/TwistWithCovarianceStamped', ''),
        Topic('/depth', 'sensor_msgs/msg/FluidPressure', ''),
        Topic('/tf', 'tf2_msgs/msg/TFMessage', ''),
        Topic('/sonar/scan', 'sensor_msgs/msg/LaserScan', ''),
        Topic('/ctd', 'sensor_msgs/msg/FluidPressure', ''),
    ),
    subscribes=(
        Topic('/thruster_cmd', 'std_msgs/msg/Float64MultiArray', 'Six normalised commands in [-1, 1], in the order the thruster units are listed.'),
        Topic('/cmd_vel', 'geometry_msgs/msg/Twist', 'A body-frame wrench for stacks that would rather not allocate thrust themselves.'),
    ),
    capability=(145.642, 145.642, 103.0, 22.454, 0.0, 38.886),
    dynamics=DYNAMICS,
)
