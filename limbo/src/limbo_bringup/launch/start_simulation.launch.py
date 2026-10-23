import os
import tempfile

import yaml

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution, PythonExpression

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

    limbo_perception_dir = get_package_share_directory(
        'limbo_perception'
    )


    # ============================================================
    # File paths
    # ============================================================

    # robot:=legacy면 이전 모델(0.45 m 정사각형, 높이 약 0.7 m), 아니면 v14 (기본)
    is_legacy = ["'", LaunchConfiguration('robot'), "' == 'legacy'"]

    # role:=sim / robot / all(기본). 두 대로 나눠 돌릴 때 쓴다: PC는 Gazebo·센서 가공(sim), Jetson은 실물에서 돌릴 것만(robot).
    # 나누는 기준은 "실물에서 Jetson이 돌릴 것"이다. 포인트클라우드→/scan 가공은 실물에서 라이다 드라이버 쪽 일이라 sim에 둔다.
    role = LaunchConfiguration('role')
    on_sim = IfCondition(PythonExpression(["'", role, "' in ('all', 'sim')"]))
    on_robot = IfCondition(PythonExpression(["'", role, "' in ('all', 'robot')"]))

    urdf_file = PathJoinSubstitution([
        limbo_description_dir,
        'urdf',
        PythonExpression(["'legacy/limbo_legacy.urdf.xacro' if "] + is_legacy + [" else 'limbo.urdf.xacro'"]),
    ])

    self_filter_config = PathJoinSubstitution([
        limbo_navigation_dir,
        'config',
        PythonExpression(["'self_filter_legacy.yaml' if "] + is_legacy + [" else 'self_filter.yaml'"]),
    ])

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
        ),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'gui': LaunchConfiguration('gui'),
            'robot': LaunchConfiguration('robot'),
            'camera_z': LaunchConfiguration('camera_z'),
            'camera_pitch_deg': LaunchConfiguration('camera_pitch_deg'),
        }.items(),
        condition=on_sim,
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
                urdf_file,
                ' camera_z:=', LaunchConfiguration('camera_z'),
                ' camera_pitch_deg:=', LaunchConfiguration('camera_pitch_deg'),
            ]),
            'filter_config': self_filter_config,
            'in_pointcloud_topic': '/mid360/points',
            'out_pointcloud_topic': '/mid360/points_filtered',
            'lidar_sensor_type': '0',
            'zero_for_removed_points': 'false',
            'use_sim_time': 'true',
        }.items(),
        condition=on_sim,
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

    # 바퀴 odom(전진 속도) + IMU(회전 속도)를 합쳐 odom → base_footprint TF를 낸다
    ekf = Node(
        condition=on_robot,
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[os.path.join(limbo_navigation_dir, 'config', 'ekf.yaml')]
    )

    # 바퀴는 도는데 로봇이 안 움직이면(헛돎) Nav2 Goal을 취소해 위치 추정이 틀어지는 걸 막는다
    wheel_slip_monitor = Node(
        condition=on_robot,
        package='limbo_monitor',
        executable='wheel_slip_monitor',
        name='wheel_slip_monitor',
        output='screen',
        parameters=[
            os.path.join(
                get_package_share_directory('limbo_monitor'),
                'config', 'wheel_slip_monitor.yaml'),
            # 스캔 메시지끼리의 시각만 비교하므로 sim time이 필요 없다.
            # 켜면 Gazebo /clock(약 740Hz)을 Python에서 전부 받느라 CPU를 10배 쓴다 (50% → 5%)
            {'use_sim_time': False}
        ]
    )

    pointcloud_to_laserscan = Node(
        condition=on_sim,
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
            'map': PathJoinSubstitution(
                [limbo_navigation_dir, 'maps', [LaunchConfiguration('map'), '.yaml']]
            ),
        }.items(),
        condition=on_robot,
    )


    # 위치 추정을 바꿔 비교할 때: localization:=slam (slam_toolbox 위치 추정 모드, maps/<map>_posegraph 필요)
    #                             localization:=mapping (slam_toolbox 지도 작성 모드)
    # slam_toolbox가 /map과 map→odom TF를 내므로 map_server·AMCL은 띄우지 않는다
    def make_localization(context):
        mode = LaunchConfiguration('localization').perform(context)
        if mode == 'amcl':
            return [localization]
        slam_params = os.path.join(limbo_navigation_dir, 'config', 'slam_toolbox.yaml')
        map_name = LaunchConfiguration('map').perform(context)
        overrides = {'use_sim_time': True, 'mode': 'localization' if mode == 'slam' else 'mapping'}
        extra = []
        if mode == 'slam':
            overrides['map_file_name'] = os.path.join(limbo_navigation_dir, 'maps', map_name + '_posegraph')
            overrides['map_start_pose'] = [0.0, 0.0, 0.0]
        else:
            # 지도 작성 중에는 Nav2가 slam_toolbox의 작은 지도로는 멀리 못 가므로(목표가 지도 밖) 정적 지도를 /map으로 따로 띄우고,
            # slam_toolbox의 지도는 /slam_map으로 보낸다. TF map→odom은 slam_toolbox가 낸다(시작 자세가 지도 원점과 같아야 함)
            overrides['map_name'] = '/slam_map'
            extra = [
                Node(package='nav2_map_server', executable='map_server', name='map_server', output='screen',
                     parameters=[{'use_sim_time': True, 'yaml_filename': os.path.join(limbo_navigation_dir, 'maps', map_name + '.yaml')}]),
                Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_map', output='screen',
                     parameters=[{'use_sim_time': True, 'autostart': True, 'node_names': ['map_server']}]),
            ]
        slam = Node(
            package='slam_toolbox',
            executable='localization_slam_toolbox_node' if mode == 'slam' else 'async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_params, overrides],
        )
        manager = Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_localization',
            output='screen',
            # bond_timeout 0: slam_toolbox가 큰 포즈그래프(24 MB)를 읽거나 맞추는 동안 heartbeat 4 s를 놓치면
            # lifecycle manager가 노드를 내려 Nav2까지 무너짐 (2026-10-14). 감시만 끄고 lifecycle 전이는 그대로
            parameters=[{'use_sim_time': True, 'autostart': True, 'bond_timeout': 0.0, 'node_names': ['slam_toolbox']}],
        )
        return extra + [slam, manager]

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

    # nav2_params.yaml은 v14 기준이다. 이전 모델이면 로봇 외곽·팽창·장애물 높이만 예전 값으로 바꿔 넣는다
    def write_legacy_nav2_params():
        """nav2_params.yaml에서 로봇 크기에 달린 값만 이전 모델 값으로 바꿔 임시 파일로 쓴다."""
        with open(nav2_params_file) as f:
            params = yaml.safe_load(f)
        legacy_footprint = '[[0.225, 0.225], [0.225, -0.225], [-0.225, -0.225], [-0.225, 0.225]]'
        for costmap, inflation in (('local_costmap', 0.40), ('global_costmap', 0.35)):
            costmap_params = params[costmap][costmap]['ros__parameters']
            costmap_params['footprint'] = legacy_footprint
            costmap_params['footprint_padding'] = 0.02
            costmap_params['inflation_layer']['inflation_radius'] = inflation
            for layer in costmap_params.values():
                if isinstance(layer, dict):
                    for source in layer.values():
                        if isinstance(source, dict) and 'max_obstacle_height' in source:
                            source['max_obstacle_height'] = 0.80
        for source in params['collision_monitor']['ros__parameters'].values():
            if isinstance(source, dict) and 'max_height' in source:
                source['max_height'] = 0.80
        out = tempfile.NamedTemporaryFile('w', prefix='nav2_params_legacy_', suffix='.yaml', delete=False)
        yaml.safe_dump(params, out)
        out.close()
        return out.name

    def make_navigation(context):
        params_file = nav2_params_file
        if LaunchConfiguration('robot').perform(context) == 'legacy':
            params_file = write_legacy_nav2_params()
        # role:=robot(두 대로 나눌 때)만 Nav2를 한 프로세스(컨테이너)에 모은다. 코스트맵 두 개와 collision_monitor가
        # 포인트클라우드를 프로세스마다 따로 받으면 PC→Jetson이 약 910 Mbit/s, 한 프로세스면 한 벌만 와서 약 350 Mbit/s (2026-10-22 실측)
        composed = LaunchConfiguration('role').perform(context) == 'robot'
        container = []
        if composed:
            container = [Node(
                package='rclcpp_components',
                executable='component_container_isolated',
                name='nav2_container',
                output='screen',
                # params 파일을 컨테이너에도 준다. 안 주면 local_costmap 같은 하위 노드가 설정을 못 받아 기본 레이어로 뜨고 죽는다
                parameters=[params_file, {'use_sim_time': True}],
                remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')],
            )]
        return container + [IncludeLaunchDescription(
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
                'params_file': params_file,
                'use_composition': 'True' if composed else 'False',
                'container_name': 'nav2_container',
            }.items()
        )]

    navigation = OpaqueFunction(function=make_navigation, condition=on_robot)


    # ============================================================
    # 6. RViz2
    # ============================================================

    rviz = Node(
        condition=on_sim,
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        parameters=[
            {'use_sim_time': True}
        ]
    )

    def make_detector(context):
        parameters = [
            os.path.join(limbo_perception_dir, 'config', 'person_detector.yaml'),
            # 모든 시각을 카메라·TF 메시지에서 가져오므로 sim time이 필요 없다.
            # 켜면 Gazebo /clock(약 740Hz)을 Python에서 전부 받느라 CPU를 많이 쓴다
            {'use_sim_time': False}
        ]
        # person_model:=<경로>를 주면 yaml의 yolo.model 대신 그 모델로 시험한다 (비우면 yaml 그대로)
        model = LaunchConfiguration('person_model').perform(context)
        if model:
            parameters.append({'yolo.model': model})
        return [Node(
            package='limbo_perception',
            executable='person_detector',
            name='person_detector',
            output='screen',
            parameters=parameters
        )]

    detector = OpaqueFunction(function=make_detector, condition=on_robot)

    # ToF 근접 센서 → /tof/obstacle_ahead·/tof/nearest (관제·로그용). 코앞 안전 정지는 collision_monitor가 /tof/points로 한다
    tof = Node(
        condition=on_robot,
        package='limbo_perception',
        executable='tof_node',
        name='tof_node',
        output='screen',
        parameters=[os.path.join(limbo_perception_dir, 'config', 'tof.yaml')]
    )

    # 사람 기다리기 상태 기계 → /person_wait. BT 조건 IsWaitingForPerson이 이것만 본다 (PROJECT.md 2-7).
    # 시각은 카메라 예측 메시지에서 가져와 sim time(/clock 구독)이 필요 없다
    person_wait = Node(
        condition=on_robot,
        package='limbo_perception',
        executable='person_wait',
        name='person_wait',
        output='screen',
        parameters=[os.path.join(limbo_perception_dir, 'config', 'person_wait.yaml'),
                    {'use_sim_time': False}]
    )

    # 주행 평가 기록 (record:=true일 때만). Goal이 끝날 때마다 ~/limbo_results/에 CSV 한 줄
    nav_recorder = Node(
        package='limbo_evaluation',
        executable='nav_recorder',
        name='nav_recorder',
        output='screen',
        condition=IfCondition(PythonExpression(["'", LaunchConfiguration('record'), "' == 'true' and '", role, "' in ('all', 'robot')"])),
        parameters=[
            os.path.join(
                get_package_share_directory('limbo_evaluation'),
                'config', 'nav_recorder.yaml'),
            # 사람 시간표를 이 월드의 SDF에서 읽는다. 시각은 정답 위치 메시지에서 가져와 sim time이 필요 없다
            {'world': LaunchConfiguration('world'), 'use_sim_time': False}
        ]
    )


    # ============================================================
    # Start sequence
    #
    # 한꺼번에 시작하면 Gazebo / PointCloud / Nav2가 동시에
    # 초기화되면서 노트북 부하가 커질 수 있으므로 순차 실행
    # ============================================================

    return LaunchDescription([

        # 월드와 지도는 같은 건물끼리 짝지어 바꾼다 (예: world:=aischool_2f map:=aischool_2f_map)
        DeclareLaunchArgument('world', default_value='human_test_world'),
        DeclareLaunchArgument('map', default_value='human_test_map'),
        # 오래 주행 시험할 때나 컴퓨터가 버거울 때 gui:=false (Gazebo 3D 창만 끔, 동작은 같음)
        DeclareLaunchArgument('gui', default_value='true'),
        # 주행 평가를 CSV로 남기려면 record:=true (limbo_evaluation/nav_recorder)
        DeclareLaunchArgument('record', default_value='false'),
        # 사람 인식 모델을 바꿔 시험하려면 person_model:=<.pt 경로> (예: 기존 yolo11n.pt). 비우면 yaml의 모델
        DeclareLaunchArgument('person_model', default_value=''),
        # 로봇 모델: v14(기본, 쓰레기통 로봇 45x45x70) 또는 legacy(이전 모델, 비교용)
        DeclareLaunchArgument('robot', default_value='v14'),
        # 카메라 높이(m)와 아래로 기울인 각도(도). 기본은 URDF 값 (0.60 m, 0°, 2026-10-15). 비교 실험 때만 바꾼다
        DeclareLaunchArgument('camera_z', default_value='0.60'),
        DeclareLaunchArgument('camera_pitch_deg', default_value='0'),
        # 위치 추정: amcl(기본) / slam(slam_toolbox 위치 추정, maps/<map>_posegraph 필요) / mapping(slam_toolbox 지도 작성)
        DeclareLaunchArgument('localization', default_value='amcl'),
        # 두 대로 나눠 돌릴 때: PC에서 role:=sim (Gazebo·센서 가공·rviz), Jetson에서 role:=robot (EKF·AMCL·Nav2·인식).
        # 같은 ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY=0. robot 쪽은 PC의 /clock을 따른다. 기본 all은 지금처럼 한 대에서 전부
        DeclareLaunchArgument('role', default_value='all'),

        # 바로 Gazebo 실행
        gazebo,
        ekf,

        # Gazebo sensor / TF 준비 대기
        TimerAction(
            period=4.0,
            actions=[self_filter]
        ),

        # filtered PointCloud가 나온 뒤 실행
        TimerAction(
            period=6.0,
            actions=[pointcloud_to_laserscan, wheel_slip_monitor]
        ),

        # /scan 생성 후 위치 추정(AMCL 또는 slam_toolbox) 실행
        TimerAction(
            period=8.0,
            actions=[OpaqueFunction(function=make_localization, condition=on_robot)]
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

        detector,
        tof,
        person_wait,
        nav_recorder,
    ])