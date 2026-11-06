"""MID-360S preview by default; explicit mounted profile adds body box and TF.

Neither profile starts actuators, odometry, localization, or navigation.
The mounted profile requires a closed, fixed lid and one owner of the sensor TF.
"""

import math
from itertools import product
import json
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def mounted_parameters(config):
    """Axis-aligned body box and static TF must share the same geometry."""
    if config['parent_frame'] != 'base_footprint' or config['sensor_frame'] != 'mid360_link':
        raise ValueError('Mount frames must be base_footprint and mid360_link')
    vectors = [config[k] for k in ['sensor_translation_m', 'sensor_rpy_rad',
                                  'body_min_base_m', 'body_max_base_m']]
    for vector in vectors:
        if len(vector) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                   or not math.isfinite(v) for v in vector):
            raise ValueError('Mount geometry must contain finite three-vectors')
    translation, rpy, lower, upper = vectors
    # A quarter turn preserves an exact axis-aligned box in sensor coordinates.
    # Reject arbitrary rotations rather than enclosing the body in an oversized
    # box which could silently erase nearby real obstacles.
    quarter_turns = rpy[2] / (math.pi / 2)
    if rpy[0] != 0 or rpy[1] != 0 or not math.isclose(
            quarter_turns, round(quarter_turns), rel_tol=0, abs_tol=1e-9):
        raise ValueError('Body box requires zero roll/pitch and yaw in multiples of 90 degrees')
    cosine, sine = round(math.cos(rpy[2])), round(math.sin(rpy[2]))
    padding = config['body_padding_m']
    if isinstance(padding, bool) or not isinstance(padding, (int, float)) or not 0 <= padding <= 0.05:
        raise ValueError('Body padding must be between zero and 5cm')
    if any(a >= b for a, b in zip(lower, upper)) or not 0 < translation[2] < 3:
        raise ValueError('Invalid body bounds or sensor height')
    lo, hi = config['scan_min_height_sensor_m'], config['scan_max_height_sensor_m']
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in [lo, hi]) or lo >= hi:
        raise ValueError('Invalid scan height band')
    corners = []
    for corner in product(*[(lo - padding, hi + padding) for lo, hi in zip(lower, upper)]):
        x, y, z = [value - offset for value, offset in zip(corner, translation)]
        # Inverse of p_base = R_z(yaw) * p_sensor + translation.
        corners.append((cosine * x + sine * y, -sine * x + cosine * y, z))
    return {'body_filter_enabled': True,
            'body_min': [min(p[i] for p in corners) for i in range(3)],
            'body_max': [max(p[i] for p in corners) for i in range(3)]}


def launch_nodes(context):
    profile = LaunchConfiguration('profile').perform(context)
    if profile not in ['preview', 'mounted']:
        raise ValueError('profile must be preview or mounted')
    guard = {'use_sim_time': False, 'expected_frame': 'mid360_link'}
    cloud, scan, name = '/mid360/points_valid', '/mid360/scan_preview', 'mid360_scan_preview'
    low, high = -0.03, 0.20
    transforms = []
    if profile == 'mounted':
        config = json.loads(Path(LaunchConfiguration('mount_config_path').perform(context)).read_text())
        guard.update(mounted_parameters(config))
        low, high = config['scan_min_height_sensor_m'], config['scan_max_height_sensor_m']
        cloud, scan, name = '/mid360/points_filtered', '/scan', 'mid360_scan'
        xyz = config['sensor_translation_m']
        transforms.append(Node(
            package='tf2_ros', executable='static_transform_publisher',
            name='limbo_mid360_mount_tf', output='screen',
            parameters=[{'use_sim_time': False}],
            arguments=['--x', str(xyz[0]), '--y', str(xyz[1]), '--z', str(xyz[2]),
                       '--roll', str(config['sensor_rpy_rad'][0]),
                       '--pitch', str(config['sensor_rpy_rad'][1]),
                       '--yaw', str(config['sensor_rpy_rad'][2]),
                       '--frame-id', config['parent_frame'], '--child-frame-id', config['sensor_frame']],
        ))
    return [
        Node(
            package='livox_ros_driver2', executable='livox_ros_driver2_node',
            name='limbo_mid360_driver', output='screen',
            parameters=[{
                'use_sim_time': False,
                'xfer_format': 0, 'multi_topic': 0, 'data_src': 0,
                'publish_freq': 10.0, 'output_data_type': 0,
                'frame_id': 'mid360_link',
                'user_config_path': LaunchConfiguration('user_config_path'),
            }],
            remappings=[('/livox/lidar', '/mid360/points'),
                        ('/livox/imu', '/mid360/imu_raw')],
        ),
        Node(
            package='limbo_bringup', executable='lidar_cloud_guard.py',
            name='lidar_cloud_guard', output='screen',
            parameters=[guard],
        ),
        Node(
            package='pointcloud_to_laserscan', executable='pointcloud_to_laserscan_node',
            name=name, output='screen',
            parameters=[{
                'use_sim_time': False,
                'target_frame': 'mid360_link',
                'transform_tolerance': 0.05,
                'queue_size': 1,
                'min_height': low, 'max_height': high,
                'angle_min': -math.pi, 'angle_max': math.pi,
                # Existing Limbo increment also keeps +pi inside the last bin
                # under the converter's float32 angle/index calculation.
                'angle_increment': 0.0174533,
                'scan_time': 0.1,
                'range_min': 0.10, 'range_max': 20.0,
                'use_inf': True,
            }],
            remappings=[('cloud_in', cloud), ('scan', scan)],
        ),
    ] + transforms


def generate_launch_description():
    share = FindPackageShare('limbo_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('profile', default_value='preview',
                              description='preview or mounted; mounted owns base_footprint to mid360_link TF'),
        DeclareLaunchArgument('user_config_path', default_value=PathJoinSubstitution([
            share, 'config', 'MID360s_limbo.json'])),
        DeclareLaunchArgument('mount_config_path', default_value=PathJoinSubstitution([
            share, 'config', 'MID360s_mount.json'])),
        OpaqueFunction(function=launch_nodes),
    ])
