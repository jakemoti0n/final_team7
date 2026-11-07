#!/usr/bin/env python3
"""자율주행 출발 전 점검: 층별로 "정상인가"를 숫자로 확인하고, 하나라도 실패하면 종료 코드 1 (목표를 보내지 말 것).

젯슨에서 주행 노드·센서+AMCL·Nav2를 띄우고 초기 위치를 넣은 뒤, 로봇 앞 2 m를 비우고:
  python3 tools/drive/nav_preflight.py [--goal X Y]

점검 항목 (2026-11-07에 자율주행 실패 원인이 전부 이 층들에서 나왔다)
  1 바퀴 odom      /odom 주기 ≥ 15 Hz (주행 노드가 살아 있고 TF odom→base가 나온다)
  2 위치 추정      map→base_footprint TF가 있고, 라이다 스캔 점이 정적 지도 벽에 맞는 비율 ≥ 70 % (11-07: 맞을 때 80~90 %, 틀렸을 때 29~41 %)
  3 카메라 입력    base_footprint 기준 정면 2 m·높이 0.3 m 아래에 카메라 점이 없다 (가짜 근거리 점이면 1 m 앞에 가상 벽이 생긴다)
  4 로컬 비용 지도 로봇 정면 0.3~1.5 m 중심선 최대 비용 < 50 (팀원 11-06 로그의 "첫 0.75 m 비용 92"가 가상 벽이었다)
  5 정적 지도      --goal을 주면 로봇에서 목표 쪽으로 2 m까지 글로벌 비용 지도 중심선 최대 비용 < 50 (−x 복도는 지도에 없었다)
  6 Nav2           bt_navigator·controller_server 노드가 보인다
"""
import argparse
import math
import sys
import time

import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan, PointCloud2
from sensor_msgs_py import point_cloud2
import tf2_ros
from tf2_sensor_msgs.tf2_sensor_msgs import do_transform_cloud

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
SCAN_FIT_MIN = 0.70
COST_MAX = 50
ODOM_HZ_MIN = 15.0


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class Preflight(Node):
    def __init__(self):
        super().__init__('nav_preflight')
        self.buf = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.buf, self)
        self.msgs = {}
        self.odom_stamps = []
        self.create_subscription(Odometry, '/odom', lambda m: self.odom_stamps.append(time.monotonic()), 20)
        self.create_subscription(LaserScan, '/scan', lambda m: self.msgs.__setitem__('scan', m), qos_profile_sensor_data)
        self.create_subscription(PointCloud2, '/rgbd_camera/points', lambda m: self.msgs.__setitem__('rgbd', m), qos_profile_sensor_data)
        self.create_subscription(OccupancyGrid, '/map', lambda m: self.msgs.__setitem__('map', m), LATCHED)
        self.create_subscription(OccupancyGrid, '/local_costmap/costmap', lambda m: self.msgs.__setitem__('local', m), LATCHED)
        self.create_subscription(OccupancyGrid, '/global_costmap/costmap', lambda m: self.msgs.__setitem__('global', m), LATCHED)

    def collect(self, seconds):
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            rclpy.spin_once(self, timeout_sec=0.05)

    def pose(self):
        tr = self.buf.lookup_transform('map', 'base_footprint', rclpy.time.Time()).transform
        return tr.translation.x, tr.translation.y, yaw_of(tr.rotation)


def cost_at(grid, x, y):
    i = int((x - grid.info.origin.position.x) / grid.info.resolution)
    j = int((y - grid.info.origin.position.y) / grid.info.resolution)
    if 0 <= i < grid.info.width and 0 <= j < grid.info.height:
        return grid.data[j * grid.info.width + i]
    return None


def line_max_cost(grid, x0, y0, heading, start_m, end_m):
    costs = [cost_at(grid, x0 + d * math.cos(heading), y0 + d * math.sin(heading))
             for d in [start_m + k * 0.1 for k in range(int((end_m - start_m) / 0.1) + 1)]]
    known = [c for c in costs if c is not None and c >= 0]
    return max(known) if known else None


def scan_fit(node, scan, grid):
    """스캔 끝점이 정적 지도의 벽(±1칸)에 놓이는 비율."""
    tr = node.buf.lookup_transform('map', scan.header.frame_id, rclpy.time.Time()).transform
    yaw = yaw_of(tr.rotation)
    res, ox, oy = grid.info.resolution, grid.info.origin.position.x, grid.info.origin.position.y
    W, H = grid.info.width, grid.info.height

    def wall(x, y):
        i, j = int((x - ox) / res), int((y - oy) / res)
        return any(0 <= i + di < W and 0 <= j + dj < H and grid.data[(j + dj) * W + i + di] >= 65
                   for di in (-1, 0, 1) for dj in (-1, 0, 1))
    hits = total = 0
    for k, r in enumerate(scan.ranges):
        if scan.range_min < r < min(scan.range_max, 8.0):
            a = yaw + scan.angle_min + k * scan.angle_increment
            total += 1
            hits += wall(tr.translation.x + r * math.cos(a), tr.translation.y + r * math.sin(a))
    return hits / total if total else 0.0, total


def low_camera_points(node, cloud):
    tr = node.buf.lookup_transform('base_footprint', cloud.header.frame_id, rclpy.time.Time())
    moved = do_transform_cloud(cloud, tr)
    return sum(1 for x, y, z in point_cloud2.read_points(moved, field_names=('x', 'y', 'z'), skip_nans=True)
               if 0.2 < x < 2.0 and abs(y) < 1.0 and z < 0.3)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--goal', type=float, nargs=2, metavar=('X', 'Y'), help='정적 지도에서 목표 쪽 2 m 비용 검사')
    parser.add_argument('--wait', type=float, default=6.0, help='토픽을 모으는 시간(s)')
    args = parser.parse_args()
    rclpy.init()
    node = Preflight()
    node.collect(args.wait)
    results = []   # (이름, 통과, 설명)

    hz = len(node.odom_stamps) / args.wait
    results.append(('바퀴 odom', hz >= ODOM_HZ_MIN, '/odom %.1f Hz (기준 ≥ %.0f)' % (hz, ODOM_HZ_MIN)))

    pose = None
    try:
        pose = node.pose()
        if 'scan' in node.msgs and 'map' in node.msgs:
            fit, n = scan_fit(node, node.msgs['scan'], node.msgs['map'])
            results.append(('위치 추정', fit >= SCAN_FIT_MIN, '자세 (%.2f, %.2f) %.0f°, 스캔 %d점 중 지도 벽에 맞음 %.0f %% (기준 ≥ %.0f)' % (
                pose[0], pose[1], math.degrees(pose[2]), n, fit * 100, SCAN_FIT_MIN * 100)))
        else:
            results.append(('위치 추정', False, '/scan 또는 /map 없음'))
    except Exception as error:
        results.append(('위치 추정', False, 'map→base_footprint TF 없음 (초기 위치를 넣었는가): %s' % str(error).splitlines()[0]))

    if 'rgbd' in node.msgs:
        try:
            low = low_camera_points(node, node.msgs['rgbd'])
            results.append(('카메라 입력', low == 0, '정면 2 m·높이 0.3 m 아래 점 %d개 (기준 0. 앞을 비우고도 있으면 가짜 근거리 점 → filter_near_depth)' % low))
        except Exception as error:
            results.append(('카메라 입력', False, '카메라 TF 없음: %s' % str(error).splitlines()[0]))
    else:
        results.append(('카메라 입력', False, '/rgbd_camera/points 없음 (충돌 감시가 모든 명령을 막는다)'))

    if pose and 'local' in node.msgs:
        c = line_max_cost(node.msgs['local'], pose[0], pose[1], pose[2], 0.3, 1.5)
        results.append(('로컬 비용 지도', c is not None and c < COST_MAX, '로봇 정면 0.3~1.5 m 최대 비용 %s (기준 < %d)' % (c, COST_MAX)))
    else:
        results.append(('로컬 비용 지도', False, '/local_costmap/costmap 없음 또는 자세 없음'))

    if args.goal:
        if pose and 'global' in node.msgs:
            heading = math.atan2(args.goal[1] - pose[1], args.goal[0] - pose[0])
            c = line_max_cost(node.msgs['global'], pose[0], pose[1], heading, 0.5, 2.0)
            results.append(('정적 지도', c is not None and c < COST_MAX, '목표 (%.2f, %.2f) 쪽 0.5~2 m 최대 비용 %s (기준 < %d)' % (*args.goal, c, COST_MAX)))
        else:
            results.append(('정적 지도', False, '/global_costmap/costmap 없음 또는 자세 없음'))

    names = {n for n, _ in node.get_node_names_and_namespaces()}
    missing = [n for n in ('bt_navigator', 'controller_server', 'planner_server', 'collision_monitor') if n not in names]
    results.append(('Nav2', not missing, '없는 노드: %s' % missing if missing else '노드 전부 보임'))

    width = max(len(n) for n, _, _ in results)
    for name, ok, text in results:
        print('%s  %-*s  %s' % ('통과' if ok else '실패', width, name, text))
    print('\n결과: %s' % ('전부 통과 — 목표를 보내도 된다' if all(ok for _, ok, _ in results) else '실패 항목이 있다 — 그 층부터 고친다. 목표를 보내지 말 것'))
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)


if __name__ == '__main__':
    main()
