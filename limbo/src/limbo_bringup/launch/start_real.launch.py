"""Real sensor/TF integration. Never starts motor output or autonomous navigation.

encoder_source=readonly owns the RoboClaw port and odom TF. For future attended
teleop use external instead, with exactly one separate drive/odom owner.
localization=none does not invent a map->odom transform. Explicit person waiting
is disabled by default; YOLO obstacle predictions remain available.
"""
import os
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, GroupAction, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetParameter


def _actions(context):
    get = lambda key: LaunchConfiguration(key).perform(context)
    def flag(key):
        value = get(key).lower()
        if value not in ('true', 'false'):
            raise ValueError(key + ' must be true/false')
        return value == 'true'
    camera, lidar, yolo, wait = [flag(k) for k in ('camera', 'lidar', 'yolo', 'person_wait')]
    if yolo and not camera:
        raise ValueError('yolo=true requires camera=true in this integrated launch')
    source, localization = get('encoder_source'), get('localization')
    if source not in ('readonly', 'external') or localization not in ('none', 'mapping', 'amcl'):
        raise ValueError('Invalid encoder_source or localization')
    if localization != 'none' and not lidar:
        raise ValueError('Localization requires lidar=true')
    bringup = get_package_share_directory('limbo_bringup')
    hardware = get_package_share_directory('limbo_hardware')
    navigation = get_package_share_directory('limbo_navigation')
    perception = get_package_share_directory('limbo_perception')
    def include(share, name, **args):
        return IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(share, 'launch', name)),
                                        launch_arguments=args.items())
    actions = [SetParameter(name='use_sim_time', value=False),
               include(bringup, 'start_real_frames.launch.py', camera=str(camera).lower(), mount_file=get('mount_file'))]
    if source == 'readonly':
        actions.append(include(hardware, 'encoders_odometry.launch.py', publish_tf='true'))
    if lidar:
        actions.append(include(bringup, 'start_mid360.launch.py', profile='mounted'))
    if camera:
        actions += [
            include(bringup, 'start_oak_camera.launch.py'),
            include(bringup, 'start_rgbd_points.launch.py',
                    filter_near_depth=LaunchConfiguration('filter_near_depth')),
        ]
    if yolo:
        python = Path(get('yolo_python'))
        if not python.is_file() or not os.access(python, os.X_OK):
            raise ValueError('Missing executable YOLO venv: ' + str(python))
        actions.append(ExecuteProcess(
            cmd=[str(python), '-m', 'limbo_perception.person_detector', '--ros-args',
                 '--params-file', os.path.join(perception, 'config', 'person_detector.yaml'),
                 '--params-file', os.path.join(perception, 'config', 'person_detector_oak_ros.yaml'),
                 '-p', 'use_sim_time:=false', '-p', 'tf_timeout:=0.1'],
            name='real_person_detector', output='screen', additional_env={'YOLO_AUTOINSTALL': 'false'},
            sigterm_timeout='10', sigkill_timeout='5'))
    if wait:
        actions.append(include(bringup, 'start_person_wait_real.launch.py',
                               publish_mount_tf='false', mount_file=get('mount_file')))
    if localization == 'mapping':
        actions += [Node(package='slam_toolbox', executable='async_slam_toolbox_node', name='slam_toolbox',
                         output='screen', parameters=[os.path.join(navigation, 'config', 'slam_real.yaml'),
                                                     {'use_sim_time': False, 'mode': 'mapping'}]),
                    Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_slam',
                         parameters=[{'use_sim_time': False, 'autostart': True, 'bond_timeout': 0.,
                                      'node_names': ['slam_toolbox']}])]
    elif localization == 'amcl':
        map_file = get('map')
        if not map_file or not Path(map_file).is_file():
            raise ValueError('localization=amcl requires an explicit existing real map YAML')
        actions.append(include(navigation, 'localization.launch.py', map=map_file,
                               params_file=os.path.join(navigation, 'config', 'amcl_real.yaml')))
    return [GroupAction(actions=actions)]


def generate_launch_description():
    share = get_package_share_directory('limbo_bringup')
    defaults = {'camera': 'true', 'lidar': 'true', 'yolo': 'true', 'person_wait': 'false',
                'filter_near_depth': 'false',
                'encoder_source': 'readonly', 'localization': 'none', 'map': '',
                'yolo_python': str(Path.home() / 'limbo/venvs/limbo_yolo/bin/python'),
                'mount_file': os.path.join(share, 'config', 'real_robot_mount.yaml')}
    return LaunchDescription([*[DeclareLaunchArgument(k, default_value=v) for k, v in defaults.items()],
                              OpaqueFunction(function=_actions)])
