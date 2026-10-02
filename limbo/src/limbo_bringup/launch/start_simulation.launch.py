import os
import sys

from launch import LaunchDescription
from launch.actions import EmitEvent, ExecuteProcess, IncludeLaunchDescription, LogInfo, RegisterEventHandler, TimerAction
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command

from launch_ros.actions import Node

from ament_index_python.packages import get_package_share_directory


WAIT_FOR_SIM_READY = """
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from tf2_msgs.msg import TFMessage

node = None
try:
    rclpy.init()
    node = Node('limbo_wait_for_sim_ready')
    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
    state = {'clock': None, 'clock_running': False, 'odom_tf': False}

    def on_clock(msg):
        stamp = (msg.clock.sec, msg.clock.nanosec)
        if state['clock'] is not None and stamp != state['clock']:
            state['clock_running'] = True
        state['clock'] = stamp

    def on_tf(msg):
        for transform in msg.transforms:
            if (transform.header.frame_id.lstrip('/') == 'odom'
                    and transform.child_frame_id.lstrip('/') == 'base_footprint'):
                state['odom_tf'] = True

    node.create_subscription(Clock, '/clock', on_clock, qos)
    node.create_subscription(TFMessage, '/tf', on_tf, qos)
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
        if state['clock_running'] and state['odom_tf']:
            print('Gazebo clock and odom -> base_footprint TF are ready', flush=True)
            sys.exit(0)
    print('Timed out waiting for Gazebo clock and odom -> base_footprint TF. '
          'Check that Gazebo is running and the robot was spawned.', file=sys.stderr, flush=True)
    sys.exit(1)
finally:
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
"""

def generate_launch_description():

    # ============================================================
    # Package paths
    # ============================================================

    limbo_simulation_dir = get_package_share_directory(
        'limbo_simulation'
    )

    limbo_description_dir = get_package_share_directory(
        'limbo_description'
    )

    limbo_navigation_dir = get_package_share_directory(
        'limbo_navigation'
    )

    robot_self_filter_dir = get_package_share_directory(
        'robot_self_filter'
    )

    nav2_bringup_dir = get_package_share_directory(
        'nav2_bringup'
    )

    # ============================================================
    # File paths
    # ============================================================

    urdf_file = os.path.join(
        limbo_description_dir,
        'urdf',
        'limbo.urdf.xacro'
    )

    self_filter_config = os.path.join(
        limbo_navigation_dir,
        'config',
        'self_filter.yaml'
    )

    nav2_params_file = os.path.join(
        limbo_navigation_dir,
        'config',
        'nav2_params.yaml'
    )

    perception_python = os.environ.get(
        'LIMBO_PERCEPTION_PYTHON',
        os.path.join(os.path.expanduser('~'), 'limbo', 'venvs', 'limbo_yolo', 'bin', 'python')
    )
    if not os.path.isfile(perception_python):
        raise FileNotFoundError(
            f'YOLO Python not found: {perception_python}. '
            'Set LIMBO_PERCEPTION_PYTHON to the limbo_yolo environment Python.'
        )


    # ============================================================
    # 1. Gazebo
    # ============================================================

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                limbo_simulation_dir,
                'launch',
                'gazebo.launch.py'
            )
        )
    )


    # ============================================================
    # 2. Robot Self Filter
    #
    # /mid360/points
    #       ↓
    # robot_self_filter
    #       ↓
    # /mid360/points_filtered
    # ============================================================

    self_filter = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                robot_self_filter_dir,
                'launch',
                'self_filter.launch.py'
            )
        ),
        launch_arguments={
            'robot_description': Command([
                'xacro ',
                urdf_file
            ]),
            'filter_config': self_filter_config,
            'in_pointcloud_topic': '/mid360/points',
            'out_pointcloud_topic': '/mid360/points_filtered',
            'lidar_sensor_type': '0',
            'zero_for_removed_points': 'false',
            'use_sim_time': 'true',
        }.items()
    )


    # ============================================================
    # 3. PointCloud → LaserScan
    #
    # filtered PointCloud 사용
    #
    # /mid360/points_filtered
    #       ↓
    # pointcloud_to_laserscan
    #       ↓
    # /scan
    # ============================================================

    pointcloud_to_laserscan = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pointcloud_to_laserscan',

        remappings=[
            ('cloud_in', '/mid360/points_filtered'),
            ('scan', '/scan'),
        ],

        parameters=[{
            'use_sim_time': True,

            'target_frame': 'mid360_link',

            'min_height': -0.03,
            'max_height': 0.20,

            'angle_min': -3.14159265,
            'angle_max': 3.14159265,
            'angle_increment': 0.0174533,

            'scan_time': 0.1,

            'range_min': 0.10,
            'range_max': 20.0,
        }]
    )


    # ============================================================
    # 4. Localization
    #
    # map_server + AMCL
    # ============================================================

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                limbo_navigation_dir,
                'launch',
                'localization.launch.py'
            )
        ),
        launch_arguments={
            'use_sim_time': 'true',
        }.items()
    )


    # ============================================================
    # 5. Navigation2
    #
    # Planner
    # MPPI
    # Costmap
    # Velocity Smoother
    # Collision Monitor
    # BT Navigator
    # ============================================================

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                nav2_bringup_dir,
                'launch',
                'navigation_launch.py'
            )
        ),
        launch_arguments={
            'use_sim_time': 'true',
            'autostart': 'true',
            'params_file': nav2_params_file,
        }.items()
    )


    # ============================================================
    # 6. RViz2
    # ============================================================

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        parameters=[
            {'use_sim_time': True}
        ]
    )

    detector = Node(
        package='limbo_perception',
        executable='person_detector',
        name='person_detector',
        prefix=perception_python,
        output='screen',
        parameters=[
            {'use_sim_time': True}
        ]
    )


    # ============================================================
    # Start TF-dependent nodes only after Gazebo clock and odometry TF exist.
    # ============================================================

    wait_for_sim_ready = ExecuteProcess(
        cmd=[sys.executable, '-u', '-c', WAIT_FOR_SIM_READY],
        name='wait_for_sim_ready',
        output='screen',
    )

    def on_sim_ready(event, context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason='Gazebo clock or odom TF did not become ready'))]
        return [
            LogInfo(msg='Gazebo is ready; starting Limbo nodes'),
            self_filter,
            detector,
            TimerAction(period=2.0, actions=[pointcloud_to_laserscan]),
            TimerAction(period=4.0, actions=[localization]),
            TimerAction(period=7.0, actions=[navigation]),
            TimerAction(period=10.0, actions=[rviz]),
        ]

    return LaunchDescription([
        gazebo,
        wait_for_sim_ready,
        RegisterEventHandler(
            OnProcessExit(target_action=wait_for_sim_ready, on_exit=on_sim_ready)
        ),
    ])
