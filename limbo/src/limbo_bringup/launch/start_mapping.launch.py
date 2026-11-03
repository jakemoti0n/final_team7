"""실물 지도 작성: 키보드 주행(/cmd_vel 브리지 + 바퀴 odom TF) + MID-360S(/scan + 라이다 TF) + slam_toolbox(지도 작성).

- 주행: limbo_hardware/teleop_drive.launch.py (키보드는 tools/drive/teleop_keyboard.sh로 따로)
- 라이다: start_mid360.launch.py profile:=mounted (몸체 상자 필터, base_footprint→mid360_link 0.837 m)
- SLAM: limbo_navigation/config/slam.yaml(시뮬 지도 작성과 같은 설정) 위에 실물 시계만 덮어씀. /map과 map→odom TF를 낸다
- bag:=true면 ~/limbo_bags/mapping_<label>/ 에 scan·odom·tf·cmd_vel·엔코더를 녹화 (나중에 다시 지도를 만들 수 있게)
지도 저장은 tools/drive/save_map.sh <이름>.
"""
import os
import time

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _actions(context):
    get = lambda key: LaunchConfiguration(key).perform(context)
    bringup = get_package_share_directory('limbo_bringup')
    hardware = get_package_share_directory('limbo_hardware')
    navigation = get_package_share_directory('limbo_navigation')
    actions = [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(hardware, 'launch', 'teleop_drive.launch.py')),
            launch_arguments={'max_duty_raw': get('max_duty_raw'), 'publish_tf': 'true'}.items()),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(bringup, 'launch', 'start_mid360.launch.py')),
            launch_arguments={'profile': 'mounted'}.items()),
        Node(package='slam_toolbox', executable='async_slam_toolbox_node', name='slam_toolbox', output='screen',
             parameters=[os.path.join(navigation, 'config', 'slam.yaml'), {'use_sim_time': False, 'mode': 'mapping'}]),
    ]
    if get('bag').lower() == 'true':
        label = get('label') or time.strftime('%m%d_%H%M%S')
        folder = os.path.expanduser('~/limbo_bags/mapping_' + label)
        actions.append(ExecuteProcess(
            cmd=['ros2', 'bag', 'record', '-o', folder, '/scan', '/odom', '/tf', '/tf_static', '/cmd_vel',
                 '/wheel/encoder_counts', '/diagnostics', '/map'],
            output='screen'))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('max_duty_raw', default_value='', description='출력 상한 raw. 비우면 drive.yaml 값'),
        DeclareLaunchArgument('bag', default_value='true'),
        DeclareLaunchArgument('label', default_value=''),
        OpaqueFunction(function=_actions),
    ])
