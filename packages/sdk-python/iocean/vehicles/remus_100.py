"""REMUS 100, as the catalogue describes it. Generated; do not edit."""

from ..vehicle import Sensor, Thruster, Topic, Vehicle

DYNAMICS = {'massKg': 30.48,
 'displacedVolumeM3': 0.0304,
 'centreOfGravityM': [0, 0, -0.0196],
 'centreOfBuoyancyM': [0, 0, 0],
 'inertiaTensor': [0.177, 0, 0, 0, 3.45, 0, 0, 0, 3.45],
 'addedMass': {'note': 'Diagonal of the added-mass matrix from Prestero (2001): a slender body, so sway and '
                       'heave carry far more entrained water than surge.',
               'diagonal': [-0.93, -35.5, -35.5, -0.0704, -4.88, -4.88]},
 'linearDamping': {'note': 'Prestero models the drag as quadratic; the linear terms are small and are '
                           'carried so that the model settles rather than oscillating at very low speed.',
                   'diagonal': [-0.5, -1.0, -1.0, -0.01, -0.5, -0.5]},
 'quadraticDamping': {'note': 'Cross-flow and axial drag coefficients from Prestero (2001).',
                      'diagonal': [-1.62, -1310.0, -1310.0, -0.13, -188.0, -188.0]},
 'thrusters': {'note': 'A torpedo: one propeller on the axis, and four fins that steer it (see `fins`). The '
                       'propeller is the only thruster; the fins are actuators the fins controller moves.',
               'model': 'REMUS 100 propeller',
               'maxForwardN': 15.0,
               'maxReverseN': 5.0,
               'timeConstantS': 0.3,
               'units': [{'name': 'propeller', 'position': [-0.67, 0, 0], 'direction': [1, 0, 0]}]},
 'sensors': [{'kind': 'dvl',
              'name': 'bottom_track',
              'position': [0.2, 0, -0.08],
              'watts': 4.0,
              'wattsNote': 'a Nortek DVL1000, averaged over its ping'},
             {'kind': 'imu',
              'name': 'body',
              'position': [0, 0, 0],
              'watts': 0.5,
              'wattsNote': 'a MEMS unit; a fibre-optic gyro is ten times this'},
             {'kind': 'barometer',
              'name': 'depth',
              'position': [0, 0, 0],
              'watts': 0.1,
              'wattsNote': 'a pressure sensor, which costs nothing'},
             {'kind': 'imaging_sonar',
              'name': 'side_scan',
              'position': [0, 0, -0.05],
              'orientation': [0, 0, 0],
              'rangeM': [2.0, 50.0],
              'horizontalFovDeg': 1,
              'verticalFovDeg': 50,
              'watts': 18.0,
              'wattsNote': "a Blueprint Oculus, which is most of what a small ROV's hotel load is when it is "
                           'on'},
             {'kind': 'ctd',
              'name': 'ctd',
              'position': [0.0, 0.0, 0.0],
              'everyS': 1.0,
              'note': 'Conductivity, temperature and depth. The instrument every oceanographic vehicle '
                      'carries and the reason a glider section is worth flying.',
              'watts': 0.35,
              'wattsNote': 'a pumped SBE 49, which is why gliders can carry one'},
             {'kind': 'multibeam',
              'name': 'downward_swath',
              'beams': 256,
              'halfSwathDeg': 60.0,
              'rangeM': [0.5, 120.0],
              'pingsPerSecond': 10.0,
              'depthNoiseM': 0.02,
              'acrossNoiseM': 0.05,
              'position': [0.5, 0.0, -0.08],
              'note': 'a downward swath, for survey. The forward sonar is for avoiding things; this is for '
                      'charting the bottom — and charting the bottom is what this vehicle is for.',
              'watts': 28.0,
              'topic': '/multibeam/soundings'}],
 'topicContract': {'publishes': [{'topic': '/imu/data', 'type': 'sensor_msgs/msg/Imu'},
                                 {'topic': '/dvl/twist',
                                  'type': 'geometry_msgs/msg/TwistWithCovarianceStamped'},
                                 {'topic': '/dvl/range',
                                  'type': 'sensor_msgs/msg/Range',
                                  'note': 'The range to the seabed, from the same Doppler log as the twist. '
                                          'Infinity, or outside [min_range, max_range], is no bottom lock — '
                                          'which is a thing that happens and a controller holding an '
                                          'altitude has to handle. Reef work is altitude work.'},
                                 {'topic': '/depth', 'type': 'sensor_msgs/msg/FluidPressure'},
                                 {'topic': '/tf', 'type': 'tf2_msgs/msg/TFMessage'},
                                 {'topic': '/ctd', 'type': 'sensor_msgs/msg/FluidPressure'}],
                   'subscribes': [{'topic': '/thruster_cmd',
                                   'type': 'std_msgs/msg/Float64MultiArray',
                                   'note': 'One normalised command in [-1, 1] for the propeller.'}]},
 'modem': {'note': 'The same micro-modem class link as the BlueROV2.',
           'bitsPerSecond': 2400.0,
           'rangeM': 2000.0,
           'lossShare': 0.08},
 'power': {'hotelW': 9.0,
           'hotelNote': 'The base electronics and nothing else: the vehicle computer and its housekeeping. '
                        'It was a single lumped figure that stood for the electronics, the sensors and the '
                        'lights together — which meant unfitting a Doppler log or switching the lamps off '
                        'changed the endurance by exactly nothing. Each instrument states its own draw now '
                        'and they are added to this, so a dive that carries less lasts longer, which is the '
                        'whole reason to be able to choose.'},
 'computer': {'kind': 'vehicle-computer',
              'watts': 12.0,
              'tops': 0.0,
              'ramGb': 8,
              'note': "A survey AUV's own computer: navigation, logging, and the payload."},
 'commandedIn': 'fins',
 'fins': {'note': 'Two rudders and two stern planes, Prestero (2001). The lift is per pair, per u|u| and per '
                  'radian of deflection; it acts at the fins, so the turning moment is its arm about the '
                  'centre.',
          'liftPerU2Rad': 9.64,
          'positionM': [-0.638, 0.0, 0.0],
          'mostDeg': 13.6,
          'rateDegPerS': 30.0,
          'rateFrom': 'assumed: Prestero gives the limit, not the rate',
          'from': 'Prestero (2001), as the same three reproductions print it: Y_uudr 9.64 kg/(m·rad), N_uudr '
                  "-6.15 kg/rad, so the fins act 0.638 m behind the centre, which is the thesis's own x_fin; "
                  "the 13.6° limit is also the thesis's (read in a search excerpt)"},
 'bodyLift': {'note': 'Body lift and Munk moment as the hull slips, and the added-mass cross terms as it '
                      'turns, Prestero (2001). In his z-down frame; the same numbers hold in this z-up one.',
              'Yuv': -28.6,
              'Nuv': -24.0,
              'Yur': 5.22,
              'Nur': -2.0,
              'Zuw': -28.6,
              'Muw': 24.0,
              'Zuq': -5.22,
              'Muq': -2.0,
              'from': 'Prestero (2001). The thesis could not be opened on any mirror (4 October 2026); these '
                      'are as three independent reproductions of its tables print them, and agree: '
                      "Psarhadi's AUV_model.py, Vandervaeren's Coef_Remus.h (moos-ivp-marineswarm) and "
                      "Ariza's REMUS.m. Shi et al. (2019) differ in Y_ur, N_uv and N_ur, and look "
                      'miscopied.'},
 'envelope': {'maxDepthM': 100.0,
              'maxSpeedMs': 2.6,
              'cruiseMs': 1.5,
              'note': 'REMUS 100: rated to 100 m, 2.6 m/s at most, cruising at about 1.5 (Hydroid).'}}

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
        Sensor('ctd', 'ctd'),
        Sensor('multibeam', 'downward_swath'),
    ),
    publishes=(
        Topic('/imu/data', 'sensor_msgs/msg/Imu', ''),
        Topic('/dvl/twist', 'geometry_msgs/msg/TwistWithCovarianceStamped', ''),
        Topic('/dvl/range', 'sensor_msgs/msg/Range', 'The range to the seabed, from the same Doppler log as the twist. Infinity, or outside [min_range, max_range], is no bottom lock — which is a thing that happens and a controller holding an altitude has to handle. Reef work is altitude work.'),
        Topic('/depth', 'sensor_msgs/msg/FluidPressure', ''),
        Topic('/tf', 'tf2_msgs/msg/TFMessage', ''),
        Topic('/ctd', 'sensor_msgs/msg/FluidPressure', ''),
    ),
    subscribes=(
        Topic('/thruster_cmd', 'std_msgs/msg/Float64MultiArray', 'One normalised command in [-1, 1] for the propeller.'),
    ),
    capability=(15.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    dynamics=DYNAMICS,
)
