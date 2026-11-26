"""
모방 학습 기록 런치(실물): 조이스틱 → teleop_twist_joy → drive_arbiter → /cmd_vel_arbiter, 그리고 바퀴 기록기.

센서·위치 추정·Nav2·바퀴 드라이버는 띄우지 않는다. Nav2는 collision_monitor 입력을 중재기 출력으로 바꿔 따로 띄운다:
  tools/drive/run_nav2_real.sh cmd_vel_out:=/cmd_vel cmd_vel_in:=/cmd_vel_arbiter
인자: mode(manual|policy_assist|policy|nav, 기본 manual), driver(운전자 이름), note(메모),
      joy_dev(조이스틱 장치 번호), manual_start(/patrol/state 없이 바로 기록),
      record_button(바퀴 기록 시작/끝 패드 버튼 번호, 기본 7 = Xbox Start. 런치는 한 번 띄워 두고 바퀴마다 누른다),
      require_deadman(false = 키보드 운전: tools/drive/teleop_keyboard.sh /cmd_vel_teleop),
      model_path(정책 .pt, mode가 policy·policy_assist일 때만 policy_node를 띄움),
      waypoints(경유점 yaml 전체 경로. patrol_node와 같은 파일을 넘긴다. 기록기 meta.json에도 남음).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = get_package_share_directory('limbo_imitation')
    params = os.path.join(share, 'config', 'imitation.yaml')
    joy_params = os.path.join(share, 'config', 'joy_xbox.yaml')
    default_waypoints = os.path.join(get_package_share_directory('limbo_patrol'), 'config',
                                     'real_loop_waypoints.yaml')
    mode = LaunchConfiguration('mode')
    waypoints = ParameterValue(LaunchConfiguration('waypoints'), value_type=str)
    model_path = ParameterValue(LaunchConfiguration('model_path'), value_type=str)
    policy_mode = PythonExpression(["'", mode, "' in ('policy', 'policy_assist')"])
    return LaunchDescription([
        DeclareLaunchArgument('mode', default_value='manual'),
        DeclareLaunchArgument('driver', default_value=''),
        DeclareLaunchArgument('note', default_value=''),
        DeclareLaunchArgument('joy_dev', default_value='0',
                              description='joy_node device_id (/dev/input/js<번호>)'),
        DeclareLaunchArgument('manual_start', default_value='false'),
        DeclareLaunchArgument('record_button', default_value='7',
                              description='바퀴 기록 시작/끝 토글 버튼(sensor_msgs/Joy.buttons 번호)'),
        DeclareLaunchArgument('require_deadman', default_value='true'),
        DeclareLaunchArgument('model_path', default_value=''),
        DeclareLaunchArgument('waypoints', default_value=default_waypoints),
        Node(package='joy', executable='joy_node', name='joy_node', output='screen',
             parameters=[{'device_id': ParameterValue(LaunchConfiguration('joy_dev'),
                                                      value_type=int)}]),
        Node(package='teleop_twist_joy', executable='teleop_node', name='teleop_twist_joy_node',
             output='screen', parameters=[joy_params],
             remappings=[('cmd_vel', '/cmd_vel_teleop')]),
        Node(package='limbo_imitation', executable='drive_arbiter', name='drive_arbiter',
             output='screen',
             parameters=[params, {
                 'mode': mode,
                 'require_deadman': ParameterValue(LaunchConfiguration('require_deadman'),
                                                   value_type=bool)}]),
        Node(package='limbo_imitation', executable='run_recorder', name='run_recorder',
             output='screen',
             parameters=[params, {
                 'mode': mode,
                 # str로 고정: 이름이나 메모가 숫자처럼 생기면 정수로 읽혀 선언된 문자열 파라미터와 충돌한다
                 'driver': ParameterValue(LaunchConfiguration('driver'), value_type=str),
                 'note': ParameterValue(LaunchConfiguration('note'), value_type=str),
                 'manual_start': ParameterValue(LaunchConfiguration('manual_start'),
                                                value_type=bool),
                 'record_button': ParameterValue(LaunchConfiguration('record_button'),
                                                 value_type=int),
                 'waypoints_file': waypoints,
                 'model_file': model_path}]),
        Node(package='limbo_imitation', executable='policy_node', name='policy_node',
             output='screen', condition=IfCondition(policy_mode),
             parameters=[params, {'model_path': model_path, 'waypoints_file': waypoints}]),
    ])
