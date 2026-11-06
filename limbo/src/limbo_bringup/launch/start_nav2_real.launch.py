"""Real Nav2 core, with velocity outputs isolated by default. No motor driver."""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.descriptions import ParameterFile
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
    # Route graphs and docking hardware are not part of this robot's navigation.
    specs = [
        ('nav2_controller', 'controller_server'),
        ('nav2_smoother', 'smoother_server'),
        ('nav2_planner', 'planner_server'),
        ('nav2_behaviors', 'behavior_server'),
        ('nav2_bt_navigator', 'bt_navigator'),
        ('nav2_waypoint_follower', 'waypoint_follower'),
        ('nav2_velocity_smoother', 'velocity_smoother'),
        ('nav2_collision_monitor', 'collision_monitor'),
    ]
    actions = []
    for package, name in specs:
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
        actions.append(Node(package=package, executable=name, name=name, output='screen',
                            parameters=[parameters], remappings=remappings,
                            sigterm_timeout='15', sigkill_timeout='5'))
    actions.append(Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                        name='lifecycle_manager_navigation', output='screen',
                        parameters=[{'use_sim_time': False, 'autostart': True,
                                     'node_names': [name for _, name in specs]}]))
    return actions


def generate_launch_description():
    share = get_package_share_directory('limbo_navigation')
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=os.path.join(share, 'config', 'nav2_real.yaml')),
        DeclareLaunchArgument('cmd_vel_out', default_value='/limbo/nav2_preview/cmd_vel',
                              description='Default is a preview topic with no motor consumer.'),
        OpaqueFunction(function=_nodes),
    ])
