"""
로봇 몸(발판)과 Nav2 실물 설정에서 읽는 값. rclpy를 쓰지 않는다.

지표(metrics)·데이터셋(dataset)·기록 노드(run_recorder)가 같은 값을 쓰도록, 숫자를 여기 두지 않고
실물 Nav2 설정(nav2_real.yaml)·행동 트리에서 읽는다. 바뀌면 그쪽 한 곳만 고친다.
- 발판: local_costmap.footprint(실제 몸 크기, 여유 0. PROJECT.md 1절 "본체 0.50 × 0.59 m")
- 경유점 통과 반경: 실물 BT의 RemovePassedGoals radius(순찰 노드가 pass 경유점을 넘기는 기준)
- 도착 허용 오차: controller_server general_goal_checker.xy_goal_tolerance(stop 경유점 도착 기준)
"""

import math
import os
import xml.etree.ElementTree as ET

import numpy as np
import yaml

NAV2_PACKAGE = 'limbo_navigation'
NAV2_PARAMS = os.path.join('config', 'nav2_real.yaml')
PATROL_BT = os.path.join('behavior_trees',
                         'real_navigate_through_poses_w_replanning_and_recovery.xml')


def share_path(relative):
    from ament_index_python.packages import get_package_share_directory
    return os.path.join(get_package_share_directory(NAV2_PACKAGE), relative)


def nav2_params_path(path=''):
    return path or share_path(NAV2_PARAMS)


def patrol_bt_path(path=''):
    return path or share_path(PATROL_BT)


def footprint_text(nav2_params_file=''):
    """nav2_real.yaml의 local_costmap footprint 문자열(Nav2 형식 '[[x, y], …]')."""
    with open(nav2_params_path(nav2_params_file), encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data['local_costmap']['local_costmap']['ros__parameters']['footprint']


def parse_footprint(text):
    """'[[x, y], …]' → (N, 2) 배열. 꼭짓점이 셋 미만이면 오류."""
    points = np.asarray(yaml.safe_load(text), dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        raise ValueError(f'footprint must be a polygon: {text}')
    return points


def patrol_radii(nav2_params_file='', patrol_bt_file=''):
    """(pass 경유점 통과 반경, stop 경유점 도착 허용 오차) m."""
    root = ET.parse(patrol_bt_path(patrol_bt_file)).getroot()
    radii = {float(node.get('radius')) for node in root.iter('RemovePassedGoals')}
    if len(radii) != 1:
        raise ValueError(f'expected one RemovePassedGoals radius, found {sorted(radii)}')
    with open(nav2_params_path(nav2_params_file), encoding='utf-8') as f:
        controller = yaml.safe_load(f)['controller_server']['ros__parameters']
    checkers = controller['goal_checker_plugins']
    tolerances = {controller[name]['xy_goal_tolerance'] for name in checkers}
    if len(tolerances) != 1:
        raise ValueError(f'expected one xy_goal_tolerance, found {sorted(tolerances)}')
    return radii.pop(), float(tolerances.pop())


def points_in_base(ranges, angle_min, angle_increment, range_min, range_max, mount):
    """스캔 → base 좌표 점 (x, y). mount = base에서 본 스캔 프레임 (x, y, yaw). 무효 값은 뺀다."""
    ranges = np.asarray(ranges, dtype=float)
    angles = angle_min + angle_increment * np.arange(len(ranges))
    valid = np.isfinite(ranges) & (ranges >= range_min) & (ranges <= range_max)
    r, a = ranges[valid], angles[valid]
    mx, my, myaw = mount
    sx, sy = r * np.cos(a), r * np.sin(a)
    c, s = math.cos(myaw), math.sin(myaw)
    return mx + c * sx - s * sy, my + s * sx + c * sy


def inside_polygon(x, y, polygon):
    """점마다 다각형 안인지(짝홀 규칙)."""
    inside = np.zeros(np.shape(x), dtype=bool)
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        crosses = (y1 > y) != (y2 > y)
        with np.errstate(divide='ignore', invalid='ignore'):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (x < x_cross)
    return inside


def edge_distance(x, y, polygon):
    """점마다 다각형 가장자리까지 최단 거리."""
    best = np.full(np.shape(x), np.inf)
    n = len(polygon)
    for i in range(n):
        p, q = np.asarray(polygon[i]), np.asarray(polygon[(i + 1) % n])
        d = q - p
        t = np.clip(((x - p[0]) * d[0] + (y - p[1]) * d[1]) / (d @ d), 0.0, 1.0)
        best = np.minimum(best, np.hypot(x - (p[0] + t * d[0]), y - (p[1] + t * d[1])))
    return best


def nearest_outside_edge(ranges, angle_min, angle_increment, range_min, range_max, mount,
                         polygon):
    """발판 밖 점 중 가장자리에 가장 가까운 거리(m). 없으면 inf.

    발판 안쪽 점(자기 몸·장착물에 맞은 점, 정지 중 손님이 쓰레기를 넣는 손)은 몸과 겹친 것이라 장애물이 아니다.
    """
    x, y = points_in_base(ranges, angle_min, angle_increment, range_min, range_max, mount)
    outside = ~inside_polygon(x, y, polygon)
    if not outside.any():
        return math.inf
    return float(edge_distance(x[outside], y[outside], polygon).min())
