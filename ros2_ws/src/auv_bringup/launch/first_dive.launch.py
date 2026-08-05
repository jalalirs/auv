"""Headless DAVE launch for Project 001: First Dive."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


SUPPORTED_VEHICLES = {"bluerov2_heavy", "bluerov2_heavy_multibeam_sonar"}


def launch_setup(context):
    vehicle = LaunchConfiguration("vehicle").perform(context)
    world_name = LaunchConfiguration("world").perform(context)

    if vehicle not in SUPPORTED_VEHICLES:
        choices = ", ".join(sorted(SUPPORTED_VEHICLES))
        raise RuntimeError(f"Unsupported vehicle '{vehicle}'. Choose one of: {choices}")

    auv_simulation = Path(get_package_share_directory("auv_simulation"))
    world_file = auv_simulation / "worlds" / f"{world_name}.sdf"
    if not world_file.is_file():
        raise RuntimeError(f"DAVE world does not exist: {world_file}")

    ros_gz_sim = Path(get_package_share_directory("ros_gz_sim"))
    dave_robot_models = Path(get_package_share_directory("dave_robot_models"))
    auv_bringup = Path(get_package_share_directory("auv_bringup"))

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(ros_gz_sim / "launch" / "gz_sim.launch.py")
        ),
        launch_arguments={
            "gz_args": f"-r -s --headless-rendering -v 2 {world_file}",
            "on_exit_shutdown": "true",
        }.items(),
    )

    robot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(dave_robot_models / "launch" / "upload_robot.launch.py")
        ),
        launch_arguments={
            "gui": "false",
            "use_sim_time": "true",
            "namespace": vehicle,
            "x": LaunchConfiguration("x"),
            "y": LaunchConfiguration("y"),
            "z": LaunchConfiguration("z"),
            "yaw": LaunchConfiguration("yaw"),
            # DAVE currently uses deprecated underscore-style CLI flags in its
            # Jazzy static-transform launcher. Publish the transform below.
            "use_ned_frame": "false",
            "use_teleop": "false",
            "use_web_joystick": "false",
            "open_qgc": "false",
            "open_virtual_joystick": "false",
        }.items(),
    )

    # DAVE's camera uses the Gazebo topics .../camera and .../camera_info.
    # Remap only the ROS side to the conventional .../camera/image layout.
    model_root = f"/model/{vehicle}"
    camera_gz = f"{model_root}/camera"
    camera_info_gz = f"{model_root}/camera_info"
    camera_ros = f"{model_root}/camera/image"
    camera_info_ros = f"{model_root}/camera/camera_info"
    camera_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="first_dive_camera_bridge",
        arguments=[
            f"{camera_gz}@sensor_msgs/msg/Image[gz.msgs.Image",
            f"{camera_info_gz}@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo",
        ],
        remappings=[
            (camera_gz, camera_ros),
            (camera_info_gz, camera_info_ros),
        ],
        output="screen",
    )

    ned_transform = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="world_to_world_ned",
        arguments=[
            "--roll",
            "1.57079632679",
            "--yaw",
            "3.14159265359",
            "--frame-id",
            "world",
            "--child-frame-id",
            "world_ned",
        ],
        parameters=[{"use_sim_time": True}],
        output="screen",
    )

    foxglove = Node(
        package="foxglove_bridge",
        executable="foxglove_bridge",
        name="foxglove_bridge",
        parameters=[
            str(auv_bringup / "config" / "foxglove_bridge.yaml"),
            {"use_sim_time": True},
        ],
        output="screen",
    )

    return [gazebo, robot, camera_bridge, ned_transform, foxglove]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "vehicle",
                default_value="bluerov2_heavy_multibeam_sonar",
                description="DAVE vehicle model to spawn",
            ),
            DeclareLaunchArgument(
                "world",
                default_value="first_dive",
                description="AUV simulation world filename without .sdf",
            ),
            DeclareLaunchArgument("x", default_value="5.0"),
            DeclareLaunchArgument("y", default_value="2.0"),
            DeclareLaunchArgument("z", default_value="-14.0"),
            DeclareLaunchArgument("yaw", default_value="0.0"),
            OpaqueFunction(function=launch_setup),
        ]
    )
