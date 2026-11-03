"""Read-only encoder input and raw wheel odometry; no TF, EKF or motor nodes."""
import math
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _nodes(context):
    encoder_file = LaunchConfiguration('encoder_params_file').perform(context)
    odom_file = LaunchConfiguration('odom_params_file').perform(context)
    with open(encoder_file, encoding='utf-8') as stream:
        config = yaml.safe_load(stream)
    encoder_parameters = config['roboclaw_encoder']['ros__parameters']
    with open(odom_file, encoding='utf-8') as stream:
        odom_parameters = yaml.safe_load(stream)['wheel_odometry']['ros__parameters']
    for name in ('left_wheel_radius', 'right_wheel_radius', 'wheel_separation'):
        value = odom_parameters[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be explicitly positive in the odometry parameter file')
    shared_cpr = {}
    for name in ('left_counts_per_revolution', 'right_counts_per_revolution'):
        value = encoder_parameters[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be explicitly positive in the encoder parameter file')
        shared_cpr[name] = float(value)
    return [
        Node(package='limbo_hardware', executable='roboclaw_encoder',
             name='roboclaw_encoder', output='screen', parameters=[encoder_file]),
        Node(package='limbo_hardware', executable='wheel_odometry',
             name='wheel_odometry', output='screen', parameters=[odom_file, shared_cpr]),
    ]


def generate_launch_description():
    share = get_package_share_directory('limbo_hardware')
    return LaunchDescription([
        DeclareLaunchArgument('encoder_params_file', default_value=os.path.join(
            share, 'config', 'encoders_readonly.yaml')),
        DeclareLaunchArgument('odom_params_file', default_value=os.path.join(
            share, 'config', 'wheel_odometry.yaml')),
        OpaqueFunction(function=_nodes),
    ])
