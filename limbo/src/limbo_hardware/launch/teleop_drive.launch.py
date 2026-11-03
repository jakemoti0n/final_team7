"""실물 주행 명령: /cmd_vel 브리지(roboclaw_drive) + 바퀴 odom(/odom, TF odom→base_footprint).

키보드는 터미널이 있어야 하므로 따로 띄운다: tools/drive/teleop_keyboard.sh
인자: max_duty_raw(출력 상한 raw, 기본은 drive.yaml), max_linear_m_s, max_angular_rad_s, record_dir, publish_tf
"""
import math
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _positive(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name}은 설정 파일에 양수로 있어야 함')
    return float(value)


def _nodes(context):
    get = lambda key: LaunchConfiguration(key).perform(context)
    with open(get('encoder_params_file'), encoding='utf-8') as f:
        enc = yaml.safe_load(f)['roboclaw_encoder']['ros__parameters']
    with open(get('odom_params_file'), encoding='utf-8') as f:
        odom = yaml.safe_load(f)['wheel_odometry']['ros__parameters']
    geometry = {k: _positive(k, odom[k]) for k in ('left_wheel_radius', 'right_wheel_radius', 'wheel_separation')}
    cpr = {k: _positive(k, enc[k]) for k in ('left_counts_per_revolution', 'right_counts_per_revolution')}
    overrides = dict(geometry, **cpr, use_sim_time=False, record_dir=get('record_dir'))
    if get('max_duty_raw'):
        overrides['max_duty_raw'] = int(get('max_duty_raw'))
    for key in ('max_linear_m_s', 'max_angular_rad_s'):
        if get(key):
            overrides[key] = float(get(key))
    publish_tf = get('publish_tf').lower()
    if publish_tf not in ('true', 'false'):
        raise ValueError('publish_tf는 true/false')
    return [
        Node(package='limbo_hardware', executable='roboclaw_drive', name='roboclaw_drive', output='screen',
             parameters=[get('drive_params_file'), overrides]),
        Node(package='limbo_hardware', executable='wheel_odometry', name='wheel_odometry', output='screen',
             parameters=[get('odom_params_file'), dict(cpr, publish_tf=publish_tf == 'true')]),
    ]


def generate_launch_description():
    share = get_package_share_directory('limbo_hardware')
    defaults = {
        'drive_params_file': os.path.join(share, 'config', 'drive.yaml'),
        'encoder_params_file': os.path.join(share, 'config', 'encoders_readonly.yaml'),
        'odom_params_file': os.path.join(share, 'config', 'wheel_odometry.yaml'),
        'max_duty_raw': '', 'max_linear_m_s': '', 'max_angular_rad_s': '', 'record_dir': '',
        'publish_tf': 'true',
    }
    return LaunchDescription([*[DeclareLaunchArgument(k, default_value=v) for k, v in defaults.items()],
                              OpaqueFunction(function=_nodes)])
