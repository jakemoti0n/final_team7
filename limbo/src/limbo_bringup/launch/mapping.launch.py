"""지도 작성 스택 (tools/make_map.sh가 띄운다).

주행 스택(start_simulation.launch.py)에서 위치 추정(AMCL·map_server)과 Nav2를 빼고 slam_toolbox 지도 작성 모드를 넣은 것.
로봇은 사람이 몬다: 키보드(teleop_twist_keyboard)·게임패드(joy + teleop_twist_joy)·나중에 폰이 /drive/cmd로 보내고,
drive_gate가 데드맨·속도 상한을 걸어 /cmd_vel을 낸다.

인자:
  world        시뮬 월드 (기본 human_test_world)
  gui          Gazebo 화면 (true)
  rviz         지도가 쌓이는 RViz (true)
  joy          게임패드 입력 (true. 장치가 없으면 joy 노드만 경고하고 나머지는 그대로)
  map_name     상태 글자에 보일 지도 이름
  resume_from  이어서 작성할 포즈그래프 경로(확장자 없이). 비면 새로 시작
  autosave_stamp_file  자동 저장 시각 파일(스크립트가 씀). 상태 글자용
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory('limbo_bringup')
    navigation_dir = get_package_share_directory('limbo_navigation')
    simulation_dir = get_package_share_directory('limbo_simulation')

    args = [
        DeclareLaunchArgument('world', default_value='human_test_world'),
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('joy', default_value='true'),
        DeclareLaunchArgument('map_name', default_value='new_map'),
        DeclareLaunchArgument('resume_from', default_value=''),
        DeclareLaunchArgument('autosave_stamp_file', default_value=''),
    ]

    # 1. Gazebo + 로봇 (주행 스택과 같은 launch)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(simulation_dir, 'launch', 'gazebo.launch.py')),
        launch_arguments={'world': LaunchConfiguration('world'), 'gui': LaunchConfiguration('gui')}.items(),
    )

    # 2. 바퀴 odom + IMU → odom → base_footprint TF (주행 스택과 같은 설정)
    ekf = Node(package='robot_localization', executable='ekf_node', name='ekf_filter_node', output='screen',
               parameters=[os.path.join(navigation_dir, 'config', 'ekf.yaml')])

    # 3. 3D 점구름 → /scan (주행 스택과 같은 값)
    scan = Node(package='pointcloud_to_laserscan', executable='pointcloud_to_laserscan_node',
                name='pointcloud_to_laserscan', remappings=[('cloud_in', '/mid360/points_filtered'), ('scan', '/scan')],
                parameters=[{'use_sim_time': True, 'target_frame': 'mid360_link', 'min_height': -0.03, 'max_height': 0.20,
                             'angle_min': -3.14159265, 'angle_max': 3.14159265, 'angle_increment': 0.0174533,
                             'scan_time': 0.1, 'range_min': 0.10, 'range_max': 20.0}])
    # /mid360/points_filtered는 self_filter가 낸다 (로봇 몸체 점 제거). 주행 스택과 같은 설정
    urdf_file = os.path.join(get_package_share_directory('limbo_description'), 'urdf', 'limbo.urdf.xacro')
    self_filter = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(get_package_share_directory('robot_self_filter'), 'launch', 'self_filter.launch.py')),
        launch_arguments={
            'robot_description': Command(['xacro ', urdf_file]),
            'filter_config': os.path.join(navigation_dir, 'config', 'self_filter.yaml'),
            'in_pointcloud_topic': '/mid360/points',
            'out_pointcloud_topic': '/mid360/points_filtered',
            'lidar_sensor_type': '0',
            'zero_for_removed_points': 'false',
            'use_sim_time': 'true',
        }.items(),
    )

    # 4. slam_toolbox 지도 작성 모드: /map과 map→odom TF를 낸다. 지도 갱신 1.5 s(기본 5 s는 보기에 느림)
    def make_slam(context):
        overrides = {'use_sim_time': True, 'mode': 'mapping', 'map_update_interval': 1.5}
        resume_from = LaunchConfiguration('resume_from').perform(context)
        if resume_from:
            # 저장된 포즈그래프를 읽고 그 위에 스캔을 계속 붙인다. 시작 자세는 저장 당시 마지막 자세(dock)
            overrides['map_file_name'] = resume_from
            overrides['map_start_at_dock'] = True
        slam = Node(package='slam_toolbox', executable='async_slam_toolbox_node', name='slam_toolbox', output='screen',
                    parameters=[os.path.join(navigation_dir, 'config', 'slam_toolbox.yaml'), overrides])
        # bond_timeout 0: 큰 포즈그래프를 읽는 동안 heartbeat를 놓쳐도 내리지 않는다 (start_simulation과 같음)
        manager = Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_slam',
                       output='screen', parameters=[{'use_sim_time': True, 'autostart': True, 'bond_timeout': 0.0,
                                                     'node_names': ['slam_toolbox']}])
        return [slam, manager]

    # 5. 조종: 입력들 → /drive/cmd → drive_gate → /cmd_vel (Nav2가 없으니 바로 로봇으로)
    gate = Node(package='limbo_drive', executable='drive_gate', name='drive_gate', output='screen',
                parameters=[{'use_sim_time': True, 'cmd_topic': '/cmd_vel', 'enabled_on_start': True}])
    joy = Node(package='joy', executable='joy_node', name='joy_node', output='screen',
               condition=IfCondition(LaunchConfiguration('joy')),
               parameters=[{'autorepeat_rate': 20.0, 'deadzone': 0.1}])
    # 게임패드 → /drive/cmd. xbox 설정: 왼쪽 스틱, LB(데드맨) 누른 채로만. 속도 배율은 drive_gate 상한 안
    teleop_joy = Node(package='teleop_twist_joy', executable='teleop_node', name='teleop_twist_joy', output='screen',
                      condition=IfCondition(LaunchConfiguration('joy')),
                      parameters=[os.path.join(get_package_share_directory('teleop_twist_joy'), 'config', 'xbox.config.yaml'),
                                  {'scale_linear.x': 0.3, 'scale_angular.yaw': 0.8}],
                      remappings=[('cmd_vel', '/drive/cmd')])

    # 6. 보기: RViz + 상태 글자
    rviz = Node(package='rviz2', executable='rviz2', name='rviz2', output='screen',
                condition=IfCondition(LaunchConfiguration('rviz')),
                arguments=['-d', os.path.join(bringup_dir, 'rviz', 'mapping.rviz')],
                parameters=[{'use_sim_time': True}])
    status = Node(package='limbo_drive', executable='map_status', name='map_status', output='screen',
                  parameters=[{'use_sim_time': True, 'map_name': LaunchConfiguration('map_name'),
                               'autosave_stamp_file': LaunchConfiguration('autosave_stamp_file')}])

    return LaunchDescription(args + [
        gazebo,
        ekf,
        TimerAction(period=4.0, actions=[self_filter]),
        TimerAction(period=6.0, actions=[scan]),
        TimerAction(period=8.0, actions=[OpaqueFunction(function=make_slam)]),
        TimerAction(period=8.0, actions=[gate, joy, teleop_joy, status]),
        TimerAction(period=12.0, actions=[rviz]),
    ])
