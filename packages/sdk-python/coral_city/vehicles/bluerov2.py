"""BlueROV2, as the catalogue describes it. Generated; do not edit."""

from ..vehicle import Sensor, Thruster, Topic, Vehicle

DYNAMICS = {
    "massKg": 11.5,
    "displacedVolumeM3": 0.011054,
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
        "note": "The standard six-thruster vectored layout: four horizontal at 45 degrees giving surge, sway and yaw, and two vertical giving heave. Positions are metres from the centre of gravity; directions are unit vectors in the body frame.",
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
                    0.12,
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
                    0.12,
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
            "heightPx": 720
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
            "verticalFovDeg": 20
        },
        {
            "kind": "dvl",
            "name": "bottom_track",
            "position": [
                0,
                0,
                -0.05
            ]
        },
        {
            "kind": "imu",
            "name": "body",
            "position": [
                0,
                0,
                0
            ]
        },
        {
            "kind": "barometer",
            "name": "depth",
            "position": [
                0,
                0,
                0
            ]
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
                "topic": "/sonar/image",
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
        Thruster('vertical-right', (0.12, 0.218, 0.0), (0.0, 0.0, 1.0)),
        Thruster('vertical-left', (0.12, -0.218, 0.0), (0.0, 0.0, 1.0)),
    ),
    sensors=(
        Sensor('underwater_camera', 'forward'),
        Sensor('imaging_sonar', 'forward_looking'),
        Sensor('dvl', 'bottom_track'),
        Sensor('imu', 'body'),
        Sensor('barometer', 'depth'),
    ),
    publishes=(
        Topic('/camera/image_raw', 'sensor_msgs/msg/Image', ''),
        Topic('/sonar/image', 'sensor_msgs/msg/Image', ''),
        Topic('/imu/data', 'sensor_msgs/msg/Imu', ''),
        Topic('/dvl/twist', 'geometry_msgs/msg/TwistWithCovarianceStamped', ''),
        Topic('/depth', 'sensor_msgs/msg/FluidPressure', ''),
        Topic('/tf', 'tf2_msgs/msg/TFMessage', ''),
    ),
    subscribes=(
        Topic('/thruster_cmd', 'std_msgs/msg/Float64MultiArray', 'Six normalised commands in [-1, 1], in the order the thruster units are listed.'),
        Topic('/cmd_vel', 'geometry_msgs/msg/Twist', 'A body-frame wrench for stacks that would rather not allocate thrust themselves.'),
    ),
    capability=(145.642, 145.642, 103.0, 22.454, 0.0, 38.886),
    dynamics=DYNAMICS,
)
