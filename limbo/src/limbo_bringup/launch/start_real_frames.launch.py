"""Single owner of real base alias and camera mounting TF; no simulated URDF."""
import math
import os
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _nodes(context):
    get = lambda key: LaunchConfiguration(key).perform(context)
    enabled = get('camera').lower()
    if enabled not in ('true', 'false'):
        raise ValueError('camera must be true/false')
    transforms = [('limbo_base_alias_tf', 'base_footprint', 'base_link', [0., 0., 0.], 0.)]
    if enabled == 'true':
        with open(get('mount_file'), encoding='utf-8') as stream:
            mount = yaml.safe_load(stream)['camera']
        if mount['parent_frame'] != 'base_footprint' or mount['child_frame'] != 'oak_device_frame':
            raise ValueError('Camera mount must connect base_footprint to oak_device_frame')
        for key in ('x', 'y', 'z', 'pitch_deg'):
            value = mount[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Invalid camera.' + key)
        if not 0 < mount['z'] < 2:
            raise ValueError('Invalid camera height')
        transforms.append(('limbo_camera_mount_tf', mount['parent_frame'], mount['child_frame'],
                           [mount['x'], mount['y'], mount['z']], math.radians(mount['pitch_deg'])))
    return [Node(package='tf2_ros', executable='static_transform_publisher', name=name, output='screen',
                 parameters=[{'use_sim_time': False}],
                 arguments=['--x', str(xyz[0]), '--y', str(xyz[1]), '--z', str(xyz[2]),
                            '--roll', '0', '--pitch', str(pitch), '--yaw', '0',
                            '--frame-id', parent, '--child-frame-id', child])
            for name, parent, child, xyz, pitch in transforms]


def generate_launch_description():
    share = get_package_share_directory('limbo_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('mount_file', default_value=os.path.join(share, 'config', 'real_robot_mount.yaml')),
        DeclareLaunchArgument('camera', default_value='true'),
        OpaqueFunction(function=_nodes),
    ])
