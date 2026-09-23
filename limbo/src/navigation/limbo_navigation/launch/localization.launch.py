"""map_server + AMCL + lifecycle manager.

인자:
  map           맵 이름(config 없이, 예: bookstore_map) 또는 yaml 전체 경로
  localization  config/localization/<name>.yaml   (기본 amcl)
  use_sim_time
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_setup(context, *args, **kwargs):
    pkg_share = get_package_share_directory('limbo_navigation')

    map_arg = LaunchConfiguration('map').perform(context)
    if os.sep in map_arg or map_arg.endswith('.yaml'):
        map_file = os.path.expanduser(map_arg)
    else:
        map_file = os.path.join(pkg_share, 'maps', map_arg + '.yaml')

    params_file = os.path.join(
        pkg_share, 'config', 'localization',
        LaunchConfiguration('localization').perform(context) + '.yaml')

    use_sim_time = {'use_sim_time': LaunchConfiguration('use_sim_time')}

    return [
        Node(
            package='nav2_map_server', executable='map_server', name='map_server', output='screen',
            parameters=[params_file, {'yaml_filename': map_file}, use_sim_time],
        ),
        Node(
            package='nav2_amcl', executable='amcl', name='amcl', output='screen',
            parameters=[params_file, use_sim_time],
        ),
        Node(
            package='nav2_lifecycle_manager', executable='lifecycle_manager',
            name='lifecycle_manager_localization', output='screen',
            parameters=[params_file, use_sim_time],
        ),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('map', default_value='human_test_map', # bookstore_map
                              description='maps/<name>.yaml 의 이름 또는 yaml 전체 경로'),
        DeclareLaunchArgument('localization', default_value='amcl',
                              description='config/localization/<name>.yaml'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        OpaqueFunction(function=_launch_setup),
    ])
