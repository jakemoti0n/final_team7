"""실물에서 사람 앞 기다리기(2-7): 카메라 장착 TF + person_wait 노드. 키보드 주행 중 사람 앞에서 서는지 보는 시험용.

전제(이미 떠 있어야 함): 카메라+검출기(tools/oak/run_ros_input.sh, run_ros_yolo.sh), 주행 브리지(/odom·TF odom→base_footprint),
SLAM 또는 AMCL(map 프레임·/map). person_wait는 map→base TF가 2 s 이어져야 준비(NOT_READY → DRIVING)되고, /person_wait.wait가
참이면 roboclaw_drive가 출력을 0으로 둔다. 시뮬과 다른 점: ToF 없음(코앞 손님 이어 기다리기 없음), odom은 EKF 대신 /odom.
"""
import math
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _actions(context):
    with open(LaunchConfiguration('mount_file').perform(context), encoding='utf-8') as f:
        mount = yaml.safe_load(f)
    cam, bumper = mount['camera'], mount['bumper']
    for key in ('x', 'y', 'z', 'pitch_deg'):
        if not isinstance(cam[key], (int, float)) or not math.isfinite(cam[key]):
            raise ValueError(f'camera.{key}는 유한한 수여야 함')
    if not 0 < cam['z'] < 2 or not 0 < bumper['x'] < 1:
        raise ValueError('카메라 높이·범퍼 거리가 로봇 크기 밖')
    perception = get_package_share_directory('limbo_perception')
    return [
        Node(package='tf2_ros', executable='static_transform_publisher', name='limbo_camera_mount_tf', output='screen',
             parameters=[{'use_sim_time': False}],
             arguments=['--x', str(cam['x']), '--y', str(cam['y']), '--z', str(cam['z']),
                        '--roll', '0', '--pitch', str(math.radians(cam['pitch_deg'])), '--yaw', '0',
                        '--frame-id', cam['parent_frame'], '--child-frame-id', cam['child_frame']]),
        Node(package='limbo_perception', executable='person_wait', name='person_wait', output='screen',
             parameters=[os.path.join(perception, 'config', 'person_wait.yaml'),
                         {'use_sim_time': False, 'base_frame': 'base_footprint', 'bumper_frame': '',
                          'bumper_x': float(bumper['x']), 'odom_topic': '/odom'}]),
    ]


def generate_launch_description():
    bringup = get_package_share_directory('limbo_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('mount_file', default_value=os.path.join(bringup, 'config', 'real_robot_mount.yaml')),
        OpaqueFunction(function=_actions),
    ])
