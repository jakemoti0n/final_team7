#!/usr/bin/env python3
"""위치 추정이 틀렸을 때 실제 자세 찾기: 가정한 위치 주변·모든 방향에서 라이다 스캔 끝점이 정적 지도 벽에 맞는 비율을 전수 비교한다. 읽기 전용.

젯슨에서 센서 런치(/scan, /map)가 떠 있을 때:
  python3 tools/drive/pose_search.py X Y [--radius 0.6] [--step 0.3] [--deg-step 5]

출력: 일치율 상위 후보 (x, y, 로봇 방향°). 11-09: 로봇이 (1.0, 0.3)에서 "+x"라고 넣었더니 일치 27 %, 탐색 결과 +175°(−x)가 80 %로 맞았다.
결과로 /initialpose를 넣고 nav_preflight.py의 위치 추정 항목(≥ 70 %)으로 확인한다.
앞뒤가 비슷한 복도에서는 180° 뒤집힌 후보도 60 %대로 나오니 1위와 2위 차이가 작으면 로봇 정면에 뭐가 있는지 눈으로 함께 본다.
"""
import argparse
import math
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
LIDAR_YAW = math.radians(90)   # mid360 장착 yaw (MID360s_mount.json sensor_rpy_rad[2]); /scan 0°가 로봇 왼쪽
MAX_RANGE = 8.0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('x', type=float)
    parser.add_argument('y', type=float)
    parser.add_argument('--radius', type=float, default=0.6, help='위치 탐색 반경(m)')
    parser.add_argument('--step', type=float, default=0.3, help='위치 격자(m)')
    parser.add_argument('--deg-step', type=int, default=5, help='방향 간격(°)')
    parser.add_argument('--top', type=int, default=6)
    args = parser.parse_args()
    rclpy.init()
    node = Node('pose_search')
    got = {}
    node.create_subscription(LaserScan, '/scan', lambda m: got.__setitem__('scan', m), qos_profile_sensor_data)
    node.create_subscription(OccupancyGrid, '/map', lambda m: got.__setitem__('map', m), LATCHED)
    start = time.monotonic()
    while time.monotonic() - start < 8 and not ('scan' in got and 'map' in got):
        rclpy.spin_once(node, timeout_sec=0.1)
    if not ('scan' in got and 'map' in got):
        raise SystemExit('/scan 또는 /map 없음')
    scan, grid = got['scan'], got['map']
    res, ox, oy = grid.info.resolution, grid.info.origin.position.x, grid.info.origin.position.y
    width, height, data = grid.info.width, grid.info.height, grid.data

    def wall(x, y):
        i, j = int((x - ox) / res), int((y - oy) / res)
        return any(0 <= i + a < width and 0 <= j + b < height and data[(j + b) * width + i + a] >= 65
                   for a in (-1, 0, 1) for b in (-1, 0, 1))

    rays = [(scan.angle_min + k * scan.angle_increment, r) for k, r in enumerate(scan.ranges)
            if scan.range_min < r < min(scan.range_max, MAX_RANGE)][::2]
    offsets = [k * args.step for k in range(-int(args.radius / args.step), int(args.radius / args.step) + 1)]
    results = []
    for dx in offsets:
        for dy in offsets:
            for deg in range(-180, 180, args.deg_step):
                yaw = math.radians(deg) + LIDAR_YAW
                hits = sum(wall(args.x + dx + r * math.cos(yaw + a), args.y + dy + r * math.sin(yaw + a)) for a, r in rays)
                results.append((hits / len(rays), args.x + dx, args.y + dy, deg))
    results.sort(reverse=True)
    print('스캔 %d점, 후보 %d개 중 상위:' % (len(rays), len(results)))
    for fit, x, y, deg in results[:args.top]:
        print('  일치 %3.0f %%  (%.1f, %.1f) 로봇 방향 %+d°' % (fit * 100, x, y, deg))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
