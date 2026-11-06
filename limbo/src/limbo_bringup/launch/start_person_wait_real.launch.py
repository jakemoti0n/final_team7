"""Real person_wait, without ToF. Mount TF can be owned by start_real.launch.py."""
import math
import os
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _actions(context):
    get = lambda key: LaunchConfiguration(key).perform(context)
    with open(get('mount_file'), encoding='utf-8') as stream:
        x = yaml.safe_load(stream)['bumper']['x']
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 < x < 1:
        raise ValueError('Invalid bumper.x')
    publish = get('publish_mount_tf').lower()
    if publish not in ('true', 'false'):
        raise ValueError('publish_mount_tf must be true/false')
    actions = []
    if publish == 'true':
        share = get_package_share_directory('limbo_bringup')
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'start_real_frames.launch.py')),
            launch_arguments={'mount_file': get('mount_file')}.items()))
    perception = get_package_share_directory('limbo_perception')
    real_params = os.path.join(perception, 'config', 'person_wait_real.yaml')
    if not os.path.isfile(real_params):
        raise ValueError('Missing installed real person_wait config: ' + real_params)
    actions.append(Node(package='limbo_perception', executable='person_wait', name='person_wait', output='screen',
                        parameters=[real_params,
                                    {'use_sim_time': False, 'bumper_x': float(x), 'tof_enabled': False}]))
    return actions


def generate_launch_description():
    share = get_package_share_directory('limbo_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('mount_file', default_value=os.path.join(share, 'config', 'real_robot_mount.yaml')),
        DeclareLaunchArgument('publish_mount_tf', default_value='true'),
        OpaqueFunction(function=_actions),
    ])
