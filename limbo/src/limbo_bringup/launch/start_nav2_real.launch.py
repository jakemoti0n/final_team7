"""Real Nav2 core, with velocity outputs isolated by default. No motor driver."""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode, ParameterFile
from nav2_common.launch import RewrittenYaml


def _nodes(context):
    output = LaunchConfiguration('cmd_vel_out').perform(context)
    if not output.startswith('/') or output in ('/', '/cmd_vel_nav', '/cmd_vel_smoothed'):
        raise ValueError('cmd_vel_out must be an absolute final velocity topic')
    preview = output != '/cmd_vel'
    prefix = '/limbo/nav2_preview' if preview else ''
    nav, smoothed = prefix + '/cmd_vel_nav', prefix + '/cmd_vel_smoothed'
    if output in (nav, smoothed):
        raise ValueError('Output must not loop back into an intermediate velocity topic')
    path = LaunchConfiguration('params_file').perform(context)
    if not os.path.isfile(path):
        raise ValueError('Missing real Nav2 parameter file: ' + path)
    # composition:=true면 Nav2 노드 8개를 한 프로세스(component_container_isolated)에 싣는다.
    # 따로 띄우면 라이다 점군(18.6k점·10 Hz·5.6 MB/s, 2026-11-09 실측)을 로컬·글로벌 비용 지도·충돌 감시가 각자 DDS로 받아 풀어
    # 같은 데이터를 여러 벌 역직렬화한다. 한 프로세스면 프로세스 안에서 한 벌만 돈다. 시뮬 분리 시험(10-26)과 같은 방식.
    composed = LaunchConfiguration('composition').perform(context).lower() == 'true'
    # Route graphs and docking hardware are not part of this robot's navigation.
    specs = [
        ('nav2_controller', 'controller_server', 'nav2_controller::ControllerServer'),
        ('nav2_smoother', 'smoother_server', 'nav2_smoother::SmootherServer'),
        ('nav2_planner', 'planner_server', 'nav2_planner::PlannerServer'),
        ('nav2_behaviors', 'behavior_server', 'behavior_server::BehaviorServer'),
        ('nav2_bt_navigator', 'bt_navigator', 'nav2_bt_navigator::BtNavigator'),
        ('nav2_waypoint_follower', 'waypoint_follower', 'nav2_waypoint_follower::WaypointFollower'),
        ('nav2_velocity_smoother', 'velocity_smoother', 'nav2_velocity_smoother::VelocitySmoother'),
        ('nav2_collision_monitor', 'collision_monitor', 'nav2_collision_monitor::CollisionMonitor'),
    ]
    actions = []
    components = []
    for package, name, plugin in specs:
        overrides = {'use_sim_time': False}
        remappings = []
        if name in ('controller_server', 'behavior_server', 'velocity_smoother', 'collision_monitor'):
            overrides['enable_stamped_cmd_vel'] = False  # RoboClaw bridge consumes Twist.
        if name in ('controller_server', 'behavior_server', 'velocity_smoother'):
            remappings.append(('cmd_vel', nav))
        if name == 'velocity_smoother':
            remappings.append(('cmd_vel_smoothed', smoothed))
        if name == 'collision_monitor':
            overrides.update(cmd_vel_in_topic=smoothed, cmd_vel_out_topic=output)
        # Rewrite the node-specific entries: a second wildcard parameter file can
        # lose to node-specific YAML values on the installed ROS version.
        parameters = ParameterFile(RewrittenYaml(source_file=path, convert_types=True,
            param_rewrites={name+'.ros__parameters.'+k: str(v) for k,v in overrides.items()}),
            allow_substs=True)
        if composed:
            components.append(ComposableNode(package=package, plugin=plugin, name=name,
                                             parameters=[parameters], remappings=remappings))
        else:
            actions.append(Node(package=package, executable=name, name=name, output='screen',
                                parameters=[parameters], remappings=remappings,
                                sigterm_timeout='15', sigkill_timeout='5'))
    lifecycle = {'use_sim_time': False, 'autostart': True, 'node_names': [name for _, name, _ in specs]}
    if composed:
        components.append(ComposableNode(package='nav2_lifecycle_manager', plugin='nav2_lifecycle_manager::LifecycleManager',
                                         name='lifecycle_manager_navigation', parameters=[lifecycle]))
        # 컨테이너에도 설정 파일을 준다. 안 주면 local_costmap 같은 하위 노드가 설정을 못 받아 기본 레이어(STVL 없음)로 뜨고
        # MPPI 비용 심판이 비용 지도 모양 불일치로 세그폴트 난다(실물 2026-11-09, 시뮬 2026-10-25와 같은 함정).
        actions.append(ComposableNodeContainer(package='rclcpp_components', executable='component_container_isolated',
                                               name='nav2_container', namespace='', output='screen',
                                               parameters=[ParameterFile(path, allow_substs=True), {'use_sim_time': False}],
                                               composable_node_descriptions=components,
                                               sigterm_timeout='15', sigkill_timeout='5'))
    else:
        actions.append(Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                            name='lifecycle_manager_navigation', output='screen', parameters=[lifecycle]))
    return actions


def generate_launch_description():
    share = get_package_share_directory('limbo_navigation')
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=os.path.join(share, 'config', 'nav2_real.yaml')),
        DeclareLaunchArgument('cmd_vel_out', default_value='/limbo/nav2_preview/cmd_vel',
                              description='Default is a preview topic with no motor consumer.'),
        DeclareLaunchArgument('composition', default_value='false',
                              description='true: Nav2 노드 8개를 한 프로세스에 싣는다(점군 복사 1벌). CPU 측정 뒤 기본값 결정'),
        OpaqueFunction(function=_nodes),
    ])
