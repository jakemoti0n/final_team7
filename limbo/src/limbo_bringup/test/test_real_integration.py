"""Real configuration contracts; all launch actions are mocked, no devices open."""
import copy
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
import rclpy
import yaml
from launch import LaunchContext

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / 'limbo/src'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config(path):
    return yaml.safe_load((SRC / path).read_text())


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_real_profiles_do_not_wait_for_clock_or_tof():
    for name in ['limbo_navigation/config/nav2_real.yaml', 'limbo_navigation/config/amcl_real.yaml', 'limbo_navigation/config/slam_real.yaml',
                 'limbo_perception/config/person_wait_real.yaml']:
        data = config(name)
        for item in walk(data):
            if 'ros__parameters' in item:
                assert item['ros__parameters']['use_sim_time'] is False
        assert '/tof/' not in yaml.safe_dump(data)
        assert 'tof_link' not in yaml.safe_dump(data)
    nav = config('limbo_navigation/config/nav2_real.yaml')
    for name in ['local_costmap', 'global_costmap']:
        layer = nav[name][name]['ros__parameters']['stvl_layer']
        assert set(layer['observation_sources'].split()) == {'mid360_mark', 'mid360_clear', 'rgbd_mark', 'rgbd_clear'}
    monitor = nav['collision_monitor']['ros__parameters']
    assert monitor['observation_sources'] == monitor['FootprintApproach']['sources_names'] == ['mid360_cloud', 'rgbd_cloud']


def test_profile_builder_preserves_the_simulation_input():
    builder = load(ROOT / 'tools/drive/build_real_configs.py', 'builder_test')
    source = config('limbo_navigation/config/nav2_params.yaml')
    snapshot = copy.deepcopy(source)
    drive = config('limbo_hardware/config/drive.yaml')['roboclaw_drive']['ros__parameters']
    result = builder.nav2_profile(source, drive)
    assert source == snapshot
    assert result == config('limbo_navigation/config/nav2_real.yaml')


@pytest.mark.parametrize('enabled', [False, True])
def test_person_wait_tof_subscription_can_be_disabled_without_changing_sim_default(enabled):
    from limbo_perception.person_wait_node import PersonWaitNode
    args = ['--ros-args', '-p', 'use_sim_time:=false']
    if not enabled:
        args += ['-p', 'tof_enabled:=false']
    rclpy.init(args=args)
    node = None
    try:
        node = PersonWaitNode()
        topics = {sub.topic_name for sub in node.subscriptions}
        assert ('/tof/obstacle_ahead' in topics) is enabled
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def test_mount_has_one_camera_parent_and_user_measured_height():
    launch = load(SRC / 'limbo_bringup/launch/start_real_frames.launch.py', 'frames_test')
    context = LaunchContext()
    context.launch_configurations.update(camera='true', mount_file=str(SRC / 'limbo_bringup/config/real_robot_mount.yaml'))
    with patch.object(launch, 'Node', Mock()) as node:
        launch._nodes(context)
    calls = [x.kwargs for x in node.call_args_list]
    assert len(calls) == 2
    camera = next(x for x in calls if x['name'] == 'limbo_camera_mount_tf')
    args = camera['arguments']
    assert float(args[args.index('--x') + 1]) == .22
    assert float(args[args.index('--z') + 1]) == .68
    assert args[args.index('--frame-id') + 1] == 'base_footprint'
    assert args[args.index('--child-frame-id') + 1] == 'oak_device_frame'


@pytest.mark.parametrize('wait_enabled', [False, True])
def test_real_default_has_only_readonly_encoder_and_no_localization_or_navigation(wait_enabled):
    launch = load(SRC / 'limbo_bringup/launch/start_real.launch.py', 'real_test')
    context = LaunchContext()
    defaults={a.name: a for a in launch.generate_launch_description().entities if hasattr(a,'name')}
    assert ''.join(x.perform(context) for x in defaults['person_wait'].default_value)=='false'
    context.launch_configurations.update(camera='true', lidar='true', yolo='false', person_wait=str(wait_enabled).lower(),
                                         encoder_source='readonly', localization='none', map='',
                                         mount_file=str(SRC / 'limbo_bringup/config/real_robot_mount.yaml'))
    with patch.object(launch, 'Node', Mock()) as node, patch.object(launch, 'PythonLaunchDescriptionSource', lambda path: path), patch.object(launch, 'IncludeLaunchDescription', Mock()) as include:
        launch._actions(context)
    node.assert_not_called()  # no direct SLAM/map/AMCL process actions
    names = [x.args[0] for x in include.call_args_list]
    text = str(names)
    assert 'encoders_odometry.launch.py' in text
    assert 'teleop_drive' not in text and 'start_mapping' not in text and 'navigation' not in text
    waits = [x for x in include.call_args_list if 'start_person_wait_real' in str(x.args[0])]
    assert bool(waits) is wait_enabled
    if waits:
        assert dict(waits[0].kwargs['launch_arguments'])['publish_mount_tf'] == 'false'


def test_person_wait_disabled_without_removing_obstacle_handling():
    import xml.etree.ElementTree as ET
    nav=config('limbo_navigation/config/nav2_real.yaml')
    original=config('limbo_navigation/config/nav2_params.yaml')
    navigator=nav['bt_navigator']['ros__parameters']
    assert 'limbo_is_waiting_for_person_condition_bt_node' not in navigator.get('plugin_lib_names', [])
    assert navigator.get('plugin_lib_names') != []
    for key,planner in [('default_nav_to_pose_bt_xml','ComputePathToPose'),
                        ('default_nav_through_poses_bt_xml','ComputePathThroughPoses')]:
        name=Path(navigator[key]).name
        assert name.startswith('real_')
        tree=ET.parse(SRC/'limbo_navigation/behavior_trees'/name)
        assert not list(tree.iter('IsWaitingForPerson'))
        assert len(list(tree.iter('FollowPath')))==1
        assert len(list(tree.iter(planner)))==1
        assert list(tree.iter('WouldAControllerRecoveryHelp'))
        assert list(tree.iter('ClearEntireCostmap'))
        old=ET.parse(SRC/'limbo_navigation/behavior_trees'/Path(original['bt_navigator']['ros__parameters'][key]).name)
        assert list(old.iter('IsWaitingForPerson'))
    costmap=nav['local_costmap']['local_costmap']['ros__parameters']
    assert 'human_layer' in costmap['plugins']
    assert costmap['human_layer']==original['local_costmap']['local_costmap']['ros__parameters']['human_layer']
    assert nav['collision_monitor']['ros__parameters']['FootprintApproach']['enabled'] is True


def test_real_mapping_accepts_small_translation_and_rotation():
    p=config('limbo_navigation/config/slam_real.yaml')['slam_toolbox']['ros__parameters']
    assert p['minimum_travel_distance']==0.05
    assert p['minimum_travel_heading']==0.10
    assert p['check_min_dist_and_heading_precisely'] is True
    original=config('limbo_navigation/config/slam.yaml')['slam_toolbox']['ros__parameters']
    assert original['minimum_travel_distance']==0.5


def test_pointcloud_uses_depth_calibration_and_preserves_separate_rgb_info():
    launch = load(SRC / 'limbo_bringup/launch/start_rgbd_points.launch.py', 'points_test')
    with patch.object(launch, 'Node', Mock()) as node:
        launch.generate_launch_description()
    nodes = {call.kwargs['name']: call.kwargs for call in node.call_args_list}
    clean = nodes['real_near_depth_filter']
    xyz, voxel = nodes['real_depth_points'], nodes['real_rgbd_voxel']
    remaps = dict(xyz['remappings'])
    for enabled in (False, True):
        context = LaunchContext()
        context.launch_configurations['filter_near_depth'] = str(enabled).lower()
        assert clean['condition'].evaluate(context) == enabled
        expected = '/rgbd_camera/depth_for_points' if enabled else '/rgbd_camera/depth_image'
        assert remaps['image_rect'].perform(context) == expected
    assert dict(clean['remappings']) == {
        'depth_in': '/rgbd_camera/depth_image', 'depth_out': '/rgbd_camera/depth_for_points'}
    assert remaps['/rgbd_camera/camera_info'] == '/rgbd_camera/depth_camera_info'
    assert dict(voxel['remappings'])['output'] == '/rgbd_camera/points'


def test_installed_real_profiles_match_sources():
    from ament_index_python.packages import get_package_share_directory
    for package, name in [('limbo_navigation', 'nav2_real.yaml'), ('limbo_navigation', 'amcl_real.yaml'), ('limbo_navigation', 'slam_real.yaml'),
                          ('limbo_perception', 'person_wait_real.yaml')]:
        installed = Path(get_package_share_directory(package)) / 'config' / name
        assert installed.is_file()
        assert installed.read_bytes() == (SRC / package / 'config' / name).read_bytes()


def test_navigation_speed_limits_match_real_drive_bridge():
    p = config('limbo_navigation/config/nav2_real.yaml')
    drive = config('limbo_hardware/config/drive.yaml')['roboclaw_drive']['ros__parameters']
    assert p['controller_server']['ros__parameters']['FollowPath']['vx_max'] == drive['max_linear_m_s']
    assert p['controller_server']['ros__parameters']['FollowPath']['wz_max'] == drive['max_angular_rad_s']
    assert p['velocity_smoother']['ros__parameters']['max_velocity'] == [drive['max_linear_m_s'], 0., drive['max_angular_rad_s']]
