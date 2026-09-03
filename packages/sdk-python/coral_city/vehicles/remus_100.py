"""REMUS 100, as the catalogue describes it. Generated; do not edit."""

from ..vehicle import Sensor, Thruster, Topic, Vehicle

DYNAMICS = {
    "massKg": 30.48,
    "displacedVolumeM3": 0.0304,
    "centreOfGravityM": [
        0,
        0,
        -0.0196
    ],
    "centreOfBuoyancyM": [
        0,
        0,
        0
    ],
    "inertiaTensor": [
        0.177,
        0,
        0,
        0,
        3.45,
        0,
        0,
        0,
        3.45
    ],
    "addedMass": {
        "note": "Diagonal of the added-mass matrix from Prestero (2001): a slender body, so sway and heave carry far more entrained water than surge.",
        "diagonal": [
            -0.93,
            -35.5,
            -35.5,
            -0.0704,
            -4.88,
            -4.88
        ]
    },
    "linearDamping": {
        "note": "Prestero models the drag as quadratic; the linear terms are small and are carried so that the model settles rather than oscillating at very low speed.",
        "diagonal": [
            -0.5,
            -1.0,
            -1.0,
            -0.01,
            -0.5,
            -0.5
        ]
    },
    "quadraticDamping": {
        "note": "Cross-flow and axial drag coefficients from Prestero (2001).",
        "diagonal": [
            -1.62,
            -1310.0,
            -1310.0,
            -0.13,
            -188.0,
            -188.0
        ]
    },
    "thrusters": {
        "note": "A torpedo: one propeller on the axis and four fins. Only the propeller is a thruster in the sense this platform allocates; the fins steer by deflection at speed, which the allocator does not model yet. Until it does, this vehicle can go forward and cannot turn.",
        "model": "REMUS 100 propeller",
        "maxForwardN": 15.0,
        "maxReverseN": 5.0,
        "timeConstantS": 0.3,
        "units": [
            {
                "name": "propeller",
                "position": [
                    -0.67,
                    0,
                    0
                ],
                "direction": [
                    1,
                    0,
                    0
                ]
            }
        ]
    },
    "sensors": [
        {
            "kind": "dvl",
            "name": "bottom_track",
            "position": [
                0.2,
                0,
                -0.08
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
        },
        {
            "kind": "imaging_sonar",
            "name": "side_scan",
            "position": [
                0,
                0,
                -0.05
            ],
            "orientation": [
                0,
                0,
                0
            ],
            "rangeM": [
                2.0,
                50.0
            ],
            "horizontalFovDeg": 1,
            "verticalFovDeg": 50
        }
    ],
    "topicContract": {
        "publishes": [
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
                "note": "One normalised command in [-1, 1] for the propeller."
            }
        ]
    }
}

VEHICLE = Vehicle(
    slug='remus-100',
    name='REMUS 100',
    mass_kg=30.48,
    net_buoyancy_n=6.669,
    thrusters=(
        Thruster('propeller', (-0.67, 0.0, 0.0), (1.0, 0.0, 0.0)),
    ),
    sensors=(
        Sensor('dvl', 'bottom_track'),
        Sensor('imu', 'body'),
        Sensor('barometer', 'depth'),
        Sensor('imaging_sonar', 'side_scan'),
    ),
    publishes=(
        Topic('/imu/data', 'sensor_msgs/msg/Imu', ''),
        Topic('/dvl/twist', 'geometry_msgs/msg/TwistWithCovarianceStamped', ''),
        Topic('/depth', 'sensor_msgs/msg/FluidPressure', ''),
        Topic('/tf', 'tf2_msgs/msg/TFMessage', ''),
    ),
    subscribes=(
        Topic('/thruster_cmd', 'std_msgs/msg/Float64MultiArray', 'One normalised command in [-1, 1] for the propeller.'),
    ),
    capability=(15.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    dynamics=DYNAMICS,
)
