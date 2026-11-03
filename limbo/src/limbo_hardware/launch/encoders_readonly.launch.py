"""Start encoder input only."""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default = os.path.join(get_package_share_directory('limbo_hardware'),
                           'config', 'encoders_readonly.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=default),
        Node(package='limbo_hardware', executable='roboclaw_encoder',
             name='roboclaw_encoder', output='screen',
             parameters=[LaunchConfiguration('params_file')]),
    ])
