import os

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command

from launch_ros.actions import Node

from ament_index_python.packages import get_package_share_directory


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
        )
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


    # ============================================================
    # Start sequence
    #
    # 한꺼번에 시작하면 Gazebo / PointCloud / Nav2가 동시에
    # 초기화되면서 노트북 부하가 커질 수 있으므로 순차 실행
    # ============================================================

    return LaunchDescription([

        # 바로 Gazebo 실행
        gazebo,

        # Gazebo sensor / TF 준비 대기
        TimerAction(
            period=4.0,
            actions=[self_filter]
        ),

        # filtered PointCloud가 나온 뒤 실행
        TimerAction(
            period=6.0,
            actions=[pointcloud_to_laserscan]
        ),

        # /scan 생성 후 AMCL 실행
        TimerAction(
            period=8.0,
            actions=[localization]
        ),

        # localization 준비 후 Nav2 실행
        TimerAction(
            period=11.0,
            actions=[navigation]
        ),

        # 마지막으로 RViz
        TimerAction(
            period=14.0,
            actions=[rviz]
        ),
    ])