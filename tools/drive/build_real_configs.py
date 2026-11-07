#!/usr/bin/env python3
"""Derive real-only profiles while preserving the Gazebo configuration."""
from copy import deepcopy
from pathlib import Path
import yaml
import xml.etree.ElementTree as ET


REAL_BT_NAMES = {
    'default_nav_to_pose_bt_xml': 'navigate_to_pose_w_replanning_and_recovery.xml',
    'default_nav_through_poses_bt_xml': 'navigate_through_poses_w_replanning_and_recovery.xml',
}


def without_person_wait(text):
    """Remove only the explicit person-wait branches from a real-only BT copy."""
    root = ET.fromstring(text)
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == 'RecoveryNode' and child.get('name') in ('ComputePathOrWait', 'FollowPathOrWait'):
                assert len(child) == 2 and child[0].tag == 'RecoveryNode'
                position = list(parent).index(child)
                parent.remove(child)
                parent.insert(position, child[0])
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == 'Inverter' and len(child) == 1 and child[0].tag == 'IsWaitingForPerson':
                parent.remove(child)
            elif child.tag == 'Sequence' and child.get('name') == 'WaitInsteadOfRecoveryWhenPerson':
                parent.remove(child)
    if list(root.iter('IsWaitingForPerson')):
        raise ValueError('Unexpected person-wait branch remains in real behavior tree')
    ET.indent(root, space='  ')
    return '<!-- Generated real-only tree: explicit person waiting disabled; obstacle handling retained. -->\n'+ET.tostring(root,encoding='unicode')+'\n'


def real_time(tree):
    if isinstance(tree, dict):
        for key, value in tree.items():
            if key == 'ros__parameters':
                value['use_sim_time'] = False
            real_time(value)
    elif isinstance(tree, list):
        for value in tree:
            real_time(value)
    return tree


def nav2_profile(source, drive, geometry):
    data = real_time(deepcopy(source))
    navigator = data['bt_navigator']['ros__parameters']
    for key, name in REAL_BT_NAMES.items():
        navigator[key] = '$(find-pkg-share limbo_navigation)/behavior_trees/real_' + name
    plugins = [name for name in navigator.get('plugin_lib_names', [])
               if name != 'limbo_is_waiting_for_person_condition_bt_node']
    if plugins:
        navigator['plugin_lib_names'] = plugins
    else:
        # Empty YAML sequences have no ROS parameter type; use Nav2's typed default.
        navigator.pop('plugin_lib_names', None)
    data.pop('loopback_simulator', None)
    for key in ('local_costmap', 'global_costmap'):
        layer = data[key][key]['ros__parameters']['stvl_layer']
        layer['observation_sources'] = ' '.join(x for x in layer['observation_sources'].split() if not x.startswith('tof'))
        for name in list(layer):
            if name.startswith('tof'):
                del layer[name]
    collision = data['collision_monitor']['ros__parameters']
    collision['observation_sources'] = [x for x in collision['observation_sources'] if not x.startswith('tof')]
    for key in list(collision):
        if key.startswith('tof'):
            del collision[key]
        elif isinstance(collision[key], dict) and 'sources_names' in collision[key]:
            collision[key]['sources_names'] = [x for x in collision[key]['sources_names'] if not x.startswith('tof')]
    # Keep future navigation requests within the existing real bridge limits.
    linear, angular = drive['max_linear_m_s'], drive['max_angular_rad_s']
    controller = data['controller_server']['ros__parameters']['FollowPath']
    controller['vx_max'] = min(controller['vx_max'], linear)
    controller['wz_max'] = min(controller['wz_max'], angular)
    # Reduce brief inner-wheel reversals during real straight starts.
    controller['wz_std'] = 0.2
    smoother = data['velocity_smoother']['ros__parameters']
    smoother['max_velocity'] = [min(smoother['max_velocity'][0], linear), 0., min(smoother['max_velocity'][2], angular)]
    smoother['min_velocity'] = [max(smoother['min_velocity'][0], -linear), 0., max(smoother['min_velocity'][2], -angular)]
    behavior = data['behavior_server']['ros__parameters']
    behavior['max_rotational_vel'] = min(behavior['max_rotational_vel'], angular)
    # 가속 한계는 주행 노드가 실제로 거는 값(drive.yaml target_slew_rad_s2, 바퀴 rad/s²)에서 도출해 MPPI·속도 평활기에 똑같이 넣는다.
    # 층마다 다르면 MPPI가 명령 실현 시점을 잘못 예측해 지그재그가 난다(2026-11-07: 바퀴 0.15 m/s²·0.56 rad/s² 대 MPPI 가정 1.0·4.0).
    # 전진 가속 = 바퀴 각가속 × 반지름, 회전 가속 = 두 바퀴가 반대로 가속할 때 = 2 × 전진 가속 / 바퀴 간격
    linear_accel = round(drive['target_slew_rad_s2'] * geometry['wheel_radius'], 3)
    angular_accel = round(2 * linear_accel / geometry['wheel_separation'], 3)
    controller['ax_max'], controller['ax_min'], controller['az_max'] = linear_accel, -linear_accel, angular_accel
    smoother['max_accel'] = [linear_accel, 0., angular_accel]
    smoother['max_decel'] = [-linear_accel, 0., -angular_accel]
    return data


def wheel_geometry(source):
    """바퀴 반지름(좌우 평균)과 간격. wheel_odometry.yaml 한 곳에서 읽는다."""
    odom = yaml.safe_load((source / 'limbo_hardware/config/wheel_odometry.yaml').read_text())['wheel_odometry']['ros__parameters']
    return {'wheel_radius': (odom['left_wheel_radius'] + odom['right_wheel_radius']) / 2, 'wheel_separation': odom['wheel_separation']}


def generate(root):
    source = root / 'limbo/src'
    navigation = source / 'limbo_navigation/config'
    perception = source / 'limbo_perception/config'
    drive = yaml.safe_load((source / 'limbo_hardware/config/drive.yaml').read_text())['roboclaw_drive']['ros__parameters']
    nav = nav2_profile(yaml.safe_load((navigation / 'nav2_params.yaml').read_text()), drive, wheel_geometry(source))
    trees = navigation.parent / 'behavior_trees'
    for name in REAL_BT_NAMES.values():
        (trees / ('real_' + name)).write_text(without_person_wait((trees / ('limbo_' + name)).read_text()), encoding='utf-8')
    amcl = real_time(yaml.safe_load((navigation / 'amcl.yaml').read_text()))
    # A real robot's pose is unknown until explicitly supplied.
    amcl['amcl']['ros__parameters']['set_initial_pose'] = False
    amcl['amcl']['ros__parameters'].pop('initial_pose', None)
    # Avoid node-specific empty path overriding localization launch's supplied map.
    amcl['map_server']['ros__parameters'].pop('yaml_filename', None)
    slam = real_time(yaml.safe_load((navigation / 'slam.yaml').read_text()))
    # At low manual speed, 0.5 m skips too much of the room. Include rotation
    # explicitly so turning in place can add scans as well as translation.
    slam['slam_toolbox']['ros__parameters'].update(minimum_travel_distance=0.05,
        minimum_travel_heading=0.10,check_min_dist_and_heading_precisely=True,
        minimum_time_interval=0.5,map_update_interval=2.0)
    wait = real_time(yaml.safe_load((perception / 'person_wait.yaml').read_text()))
    p = wait['person_wait']['ros__parameters']
    p.update(tof_enabled=False, bumper_frame='', odom_topic='/odom', base_frame='base_footprint')
    p.pop('tof_topic', None)
    outputs = {navigation / 'nav2_real.yaml': nav, navigation / 'amcl_real.yaml': amcl,
               navigation / 'slam_real.yaml': slam,
               perception / 'person_wait_real.yaml': wait}
    for path, data in outputs.items():
        path.write_text('# Generated by tools/drive/build_real_configs.py. Real-only; Gazebo files remain unchanged.\n'
                        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
    return outputs


if __name__ == '__main__':
    generate(Path(__file__).resolve().parents[2])
