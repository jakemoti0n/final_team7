from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = get_package_share_directory("limbo_navigation")

    default_params_file = os.path.join(
        pkg_share,
        "config",
        "amcl.yaml"
    )

    # 지금은 네 실제 map 저장 경로를 직접 기본값으로 사용
    default_map_file = os.path.expanduser(
        "~/limbo/limbo/src/limbo_navigation/maps/bookstore_map.yaml"
    )

    map_arg = DeclareLaunchArgument(
        "map",
        default_value=default_map_file,
        description="Full path to map yaml file"
    )

    params_arg = DeclareLaunchArgument(
        "params_file",
        default_value=default_params_file,
        description="Full path to amcl params file"
    )

    map_file = LaunchConfiguration("map")
    params_file = LaunchConfiguration("params_file")

    map_server = Node(
        package="nav2_map_server",
        executable="map_server",
        name="map_server",
        output="screen",
        parameters=[
            params_file,
            {"yaml_filename": map_file},
        ],
    )

    amcl = Node(
        package="nav2_amcl",
        executable="amcl",
        name="amcl",
        output="screen",
        parameters=[params_file],
    )

    lifecycle_manager = Node(
        package="nav2_lifecycle_manager",
        executable="lifecycle_manager",
        name="lifecycle_manager_localization",
        output="screen",
        parameters=[params_file],
    )

    return LaunchDescription([
        map_arg,
        params_arg,
        map_server,
        amcl,
        lifecycle_manager,
    ])