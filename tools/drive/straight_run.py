#!/usr/bin/env python3
"""자동 직진 시험: /cmd_vel로 일정 속도 직진 명령을 내고 바퀴 odom 거리가 목표에 닿으면 멈춘다. Nav2 없이 "똑바로 가는가"만 본다.

사용법 (젯슨, 주행 노드가 떠 있어야 함): python3 tools/drive/straight_run.py [--distance 6.0] [--speed 0.1]
- 명령은 키보드 도구와 같은 10 Hz로 보낸다(주행 노드의 명령 끊김 정지 0.5 s 안).
- 거리는 /odom(wheel_odometry)의 위치로 재고, 방향은 /odom의 yaw로 본다. 좌우 바퀴 이동량은 /wheel_counts가 아니라 주행 노드
  기록(control.jsonl)에 있으므로 끝나면 drive_report.py로 본다.
- Ctrl+C 또는 어떤 오류든 0 명령을 보내고 끝난다.

결과: 간 거리, 걸린 시간, 평균 속도, 시작 대비 odom 방향 변화(°), 옆으로 샌 거리(odom 기준, m).
"""
import argparse
import math
import signal
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node

COMMAND_HZ = 10.0


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class StraightRun(Node):
    def __init__(self, distance, speed, timeout_s):
        super().__init__('straight_run')
        self.distance, self.speed, self.timeout_s = distance, speed, timeout_s
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Odometry, '/odom', self.on_odom, 20)
        self.start = None       # (x, y, yaw, time)
        self.latest = None
        self.began = None
        self.timer = self.create_timer(1.0 / COMMAND_HZ, self.tick)
        self.done = None

    def on_odom(self, msg):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.latest = (p.x, p.y, yaw_of(q), time.monotonic())

    def tick(self):
        if self.latest is None:
            return
        if self.start is None:
            self.start = self.latest
            self.began = time.monotonic()
            self.get_logger().info('출발: 목표 %.2f m, %.2f m/s' % (self.distance, self.speed))
        x0, y0, yaw0, _ = self.start
        x, y, yaw, _ = self.latest
        gone = math.hypot(x - x0, y - y0)
        if gone >= self.distance:
            self.finish('목표 거리 도달')
            return
        if time.monotonic() - self.began > self.timeout_s:
            self.finish('시간 초과')
            return
        msg = Twist()
        msg.linear.x = self.speed
        self.pub.publish(msg)

    def finish(self, why):
        if self.done is not None:
            return
        for _ in range(3):
            self.pub.publish(Twist())
        x0, y0, yaw0, _ = self.start
        x, y, yaw, _ = self.latest
        seconds = time.monotonic() - self.began
        gone = math.hypot(x - x0, y - y0)
        heading = math.degrees(math.atan2(math.sin(yaw - yaw0), math.cos(yaw - yaw0)))
        # 출발 방향 기준 옆으로 샌 거리(왼쪽 +)
        lateral = -(x - x0) * math.sin(yaw0) + (y - y0) * math.cos(yaw0)
        self.done = {'why': why, 'distance_m': round(gone, 3), 'seconds': round(seconds, 1),
                     'mean_speed_m_s': round(gone / seconds, 3) if seconds else 0.0,
                     'heading_change_deg': round(heading, 1), 'lateral_m': round(lateral, 3)}
        self.get_logger().info('끝: %s' % self.done)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--distance', type=float, default=6.0)
    parser.add_argument('--speed', type=float, default=0.1, help='키보드 기본값과 같은 0.1 m/s')
    parser.add_argument('--timeout', type=float, default=None, help='기본은 거리/속도의 2배')
    args = parser.parse_args()
    if not 0 < args.speed <= 0.25 or not 0 < args.distance <= 20:
        sys.exit('속도는 0..0.25 m/s(주행 노드 상한), 거리는 0..20 m')
    timeout_s = args.timeout or 2 * args.distance / args.speed
    rclpy.init()
    node = StraightRun(args.distance, args.speed, timeout_s)
    signal.signal(signal.SIGINT, lambda *_: node.finish('중단(Ctrl+C)'))
    try:
        while rclpy.ok() and node.done is None:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        for _ in range(3):
            node.pub.publish(Twist())
            time.sleep(0.05)
        node.destroy_node()
        rclpy.shutdown()
    if node.done:
        print('\n'.join('%s: %s' % item for item in node.done.items()))


if __name__ == '__main__':
    main()
