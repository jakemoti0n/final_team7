from launch import LaunchDescription
from launch.actions import (
    IncludeLaunchDescription,
    TimerAction,
    AppendEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.substitutions import Command
from ament_index_python.packages import (
    get_package_share_directory,
    get_package_prefix,
)
import os

def generate_launch_description():

    description_pkg = get_package_share_directory(
        "limbo_description"
    )

    simulation_pkg = get_package_share_directory(
        "limbo_simulation"
    )

    bookstore_models = os.path.join(
    simulation_pkg,
    "models"
    )

    bookstore_resource_path = AppendEnvironmentVariable(
        "GZ_SIM_RESOURCE_PATH",
        bookstore_models
    )

    xacro_file = os.path.join(
        description_pkg,
        "urdf",
        "limbo.urdf.xacro"
    )

    bridge_config = os.path.join(
        simulation_pkg,
        "config",
        "bridge.yaml"
    )

    # Gazebo가 package://limbo_description/... mesh를
    # 찾을 수 있도록 ROS install share 경로 등록
    gz_resource_path = os.path.join(
        get_package_prefix("limbo_description"),
        "share"
    )

    set_gz_resource_path = AppendEnvironmentVariable(
        "GZ_SIM_RESOURCE_PATH",
        gz_resource_path
    )

    robot_description = ParameterValue(
        Command(["xacro ", xacro_file]),
        value_type=str,
    )

    world_file = os.path.join(
    simulation_pkg,
    "worlds",
    "bookstore_world.sdf"
)

    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("ros_gz_sim"),
                "launch",
                "gz_sim.launch.py",
            )
        ),
        launch_arguments={"gz_args": world_file}.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[
            {
                "robot_description": robot_description,
                "use_sim_time": True,
            }
        ],
        output="screen",
    )

    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        parameters=[
            {
                "config_file": bridge_config,
                "use_sim_time": True,
            }
        ],
        output="screen",
    )

    spawn_robot = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="ros_gz_sim",
                executable="create",
                arguments=[
                    "-topic", "robot_description",
                    "-name", "limbo",
                    "-allow_renaming", "true",
                    "-z", "0.02",
                ],
                output="screen",
            )
        ],
    )

    return LaunchDescription([
        set_gz_resource_path,
        bookstore_resource_path,
        gz_sim,
        robot_state_publisher,
        bridge,
        spawn_robot,
    ])  
