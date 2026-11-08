#!/usr/bin/env python3
"""로봇 가까이(기본 2 m) 잡히는 것이 어느 센서에서 왔는지 base_footprint 기준으로 나열한다. 읽기 전용.

젯슨에서 센서 런치(와 Nav2가 떠 있으면 로컬 비용 지도까지)를 띄운 뒤:
  python3 tools/drive/near_obstacles.py [--radius 2.0]

출력
  /scan, /rgbd_camera/points, /mid360/points_filtered 각각: 반경 안 점 수, 가장 가까운 5점의 (앞, 옆, 높이), 0.7 m 안 점의 높이 범위
  /local_costmap/costmap: 막힌 칸(100)을 로봇 기준 좌표로, 가까운 순 10개

쓰임: 로컬 비용 지도에 로봇 발밑·정면에 막힌 칸이 있는데 눈에는 아무것도 없을 때 센서별로 가른다.
  2026-11-07 카메라 가짜 근거리 점(정면 0.5~1.25 m, 높이 0.3~1.0 m, 앞을 비워도 그대로) → filter_near_depth
  2026-11-08 라이다가 로봇 윗부분(중심 0.23~0.7 m, 높이 0.80~1.37 m)을 봄 → 몸체 필터 높이 0.79 m 위라 비용 지도에 찍힘
"""
import argparse
import math
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan, PointCloud2
from sensor_msgs_py import point_cloud2
import tf2_ros
from tf2_sensor_msgs.tf2_sensor_msgs import do_transform_cloud

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
CLOUDS = ('/rgbd_camera/points', '/mid360/points_filtered')


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class NearObstacles(Node):
    def __init__(self):
        super().__init__('near_obstacles')
        self.buf = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.buf, self)
        self.msgs = {}
        self.create_subscription(LaserScan, '/scan', lambda m: self.msgs.__setitem__('/scan', m), qos_profile_sensor_data)
        for topic in CLOUDS:
            self.create_subscription(PointCloud2, topic, lambda m, t=topic: self.msgs.__setitem__(t, m), qos_profile_sensor_data)
        self.create_subscription(OccupancyGrid, '/local_costmap/costmap', lambda m: self.msgs.__setitem__('local', m), LATCHED)

    def collect(self, seconds):
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            rclpy.spin_once(self, timeout_sec=0.05)

    def to_base(self, frame):
        return self.buf.lookup_transform('base_footprint', frame, rclpy.time.Time())


def scan_points(node, scan, radius):
    tr = node.to_base(scan.header.frame_id).transform
    yaw = yaw_of(tr.rotation)
    points = []
    for k, r in enumerate(scan.ranges):
        if scan.range_min < r < radius:
            a = yaw + scan.angle_min + k * scan.angle_increment
            points.append((tr.translation.x + r * math.cos(a), tr.translation.y + r * math.sin(a), tr.translation.z))
    return points


def cloud_points(node, cloud, radius):
    moved = do_transform_cloud(cloud, node.to_base(cloud.header.frame_id))
    return [(x, y, z) for x, y, z in point_cloud2.read_points(moved, field_names=('x', 'y', 'z'), skip_nans=True)
            if math.hypot(x, y) < radius]


def report_points(name, points):
    points.sort(key=lambda p: math.hypot(p[0], p[1]))
    print('%s: 반경 안 %d점' % (name, len(points)))
    for x, y, z in points[:5]:
        print('   앞 %+.2f 옆 %+.2f 높이 %.2f (거리 %.2f, 방위 %+.0f°)' % (x, y, z, math.hypot(x, y), math.degrees(math.atan2(y, x))))
    close = [p for p in points if math.hypot(p[0], p[1]) < 0.7]
    if close:
        print('   0.7 m 안 %d점: 높이 %.2f~%.2f m (몸체 필터 높이 위면 로봇 자신이다)' % (len(close), min(p[2] for p in close), max(p[2] for p in close)))


def report_costmap(node, grid, radius):
    tr = node.buf.lookup_transform(grid.header.frame_id, 'base_footprint', rclpy.time.Time()).transform
    rx, ry, yaw = tr.translation.x, tr.translation.y, yaw_of(tr.rotation)
    res, ox, oy, width = grid.info.resolution, grid.info.origin.position.x, grid.info.origin.position.y, grid.info.width
    cells = []
    for idx, value in enumerate(grid.data):
        if value >= 100:
            dx, dy = ox + (idx % width + 0.5) * res - rx, oy + (idx // width + 0.5) * res - ry
            fx, fy = dx * math.cos(yaw) + dy * math.sin(yaw), -dx * math.sin(yaw) + dy * math.cos(yaw)
            if math.hypot(fx, fy) < radius:
                cells.append((fx, fy))
    cells.sort(key=lambda c: math.hypot(*c))
    print('/local_costmap/costmap (%s 좌표): 막힌 칸 전체 %d, 반경 안 %d개' % (grid.header.frame_id, sum(1 for v in grid.data if v >= 100), len(cells)))
    for fx, fy in cells[:10]:
        print('   앞 %+.2f 옆 %+.2f (거리 %.2f, 방위 %+.0f°)' % (fx, fy, math.hypot(fx, fy), math.degrees(math.atan2(fy, fx))))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--radius', type=float, default=2.0)
    parser.add_argument('--wait', type=float, default=4.0, help='토픽을 모으는 시간(s)')
    args = parser.parse_args()
    rclpy.init()
    node = NearObstacles()
    node.collect(args.wait)
    for topic in ('/scan',) + CLOUDS:
        msg = node.msgs.get(topic)
        if msg is None:
            print('%s: 없음' % topic)
            continue
        try:
            points = scan_points(node, msg, args.radius) if topic == '/scan' else cloud_points(node, msg, args.radius)
            report_points(topic, points)
        except Exception as error:
            print('%s: TF 없음 (%s)' % (topic, str(error).splitlines()[0]))
    if 'local' in node.msgs:
        try:
            report_costmap(node, node.msgs['local'], args.radius)
        except Exception as error:
            print('/local_costmap/costmap: TF 없음 (%s)' % str(error).splitlines()[0])
    else:
        print('/local_costmap/costmap: 없음 (Nav2가 안 떠 있으면 정상)')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
