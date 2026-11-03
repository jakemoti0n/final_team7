"""Preview Twist wheel targets only. No serial port or motor node is started."""
import math
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def load_shared_parameters(encoder_file, odom_file):
    with open(encoder_file, encoding='utf-8') as stream:
        encoders = yaml.safe_load(stream)['roboclaw_encoder']['ros__parameters']
    with open(odom_file, encoding='utf-8') as stream:
        geometry = yaml.safe_load(stream)['wheel_odometry']['ros__parameters']
    shared = {}
    for source, keys in ((encoders, ('left_counts_per_revolution', 'right_counts_per_revolution')),
                         (geometry, ('left_wheel_radius', 'right_wheel_radius', 'wheel_separation'))):
        for key in keys:
            value = source[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} must be finite and positive')
            shared[key] = float(value)
    return shared


def _nodes(context):
    parameters = load_shared_parameters(
        LaunchConfiguration('encoder_params_file').perform(context),
        LaunchConfiguration('odom_params_file').perform(context))
    parameters.update(use_sim_time=False,
                      command_topic=LaunchConfiguration('command_topic').perform(context),
                      feedback_topic=LaunchConfiguration('feedback_topic').perform(context))
    return [Node(package='limbo_hardware', executable='drive_preview',
                 name='drive_preview', output='screen', parameters=[parameters])]


def generate_launch_description():
    share = get_package_share_directory('limbo_hardware')
    return LaunchDescription([
        DeclareLaunchArgument('encoder_params_file', default_value=os.path.join(share, 'config', 'encoders_readonly.yaml')),
        DeclareLaunchArgument('odom_params_file', default_value=os.path.join(share, 'config', 'wheel_odometry.yaml')),
        DeclareLaunchArgument('command_topic', default_value='/limbo/drive_preview/cmd_vel'),
        DeclareLaunchArgument('feedback_topic', default_value='/wheel/joint_states'),
        OpaqueFunction(function=_nodes),
    ])
