#!/usr/bin/env python3
"""제자리 회전 시험: /cmd_vel로 일정 각속도 회전 명령을 내고 바퀴 odom yaw 누적이 목표 각도에 닿으면 멈춘다. straight_run.py의 회전판.

사용법 (젯슨, 주행 노드가 떠 있어야 함. AMCL까지 떠 있으면 라이다 기준 비교가 같이 나온다):
  python3 tools/drive/spin_run.py [--turns 2.0] [--speed 0.5] [--right]
- 명령은 키보드 도구와 같은 10 Hz(주행 노드의 명령 끊김 정지 0.5 s 안).
- odom yaw는 /odom의 yaw를 틱마다 감싸서 누적한다(한 바퀴 넘게 돌아도 셈).
- AMCL yaw(/amcl_pose)도 같은 방식으로 누적해 비교한다. AMCL은 라이다로 지도 벽에 맞추므로 회전각의 독립 기준이 된다.
  odom 회전각은 바퀴 간격(wheel_odometry.yaml의 wheel_separation)에 반비례한다: odom이 k배 크면 간격을 k배 늘린다.
- Ctrl+C 또는 어떤 오류든 0 명령을 보내고 끝난다.

결과: odom 누적 각도(°), 걸린 시간, 평균 각속도, AMCL 누적 각도(°)와 odom 대비 비율, 제자리에서 벗어난 거리(odom, m).
"""
import argparse
import math
import signal
import sys
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

COMMAND_HZ = 10.0
MAX_SPEED = 0.8   # 주행 노드 max_angular_rad_s (drive.yaml)
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


class Accumulator:
    """yaw를 틱마다 감싸서 누적한다. 첫 값이 기준."""

    def __init__(self):
        self.last = None
        self.total = 0.0
        self.count = 0

    def add(self, yaw):
        if self.last is not None:
            self.total += wrap(yaw - self.last)
        self.last = yaw
        self.count += 1


class SpinRun(Node):
    def __init__(self, target_rad, speed, timeout_s):
        super().__init__('spin_run')
        self.target_rad, self.speed, self.timeout_s = target_rad, speed, timeout_s
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Odometry, '/odom', self.on_odom, 20)
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self.on_amcl, LATCHED)
        self.odom = Accumulator()
        self.amcl = Accumulator()
        self.start_xy = None
        self.latest_xy = None
        self.began = None
        self.done = None
        self.timer = self.create_timer(1.0 / COMMAND_HZ, self.tick)

    def on_odom(self, msg):
        p = msg.pose.pose.position
        self.latest_xy = (p.x, p.y)
        if self.began is not None:
            self.odom.add(yaw_of(msg.pose.pose.orientation))
        elif self.odom.last is None:
            self.odom.last = yaw_of(msg.pose.pose.orientation)

    def on_amcl(self, msg):
        if self.began is not None:
            self.amcl.add(yaw_of(msg.pose.pose.orientation))
        else:
            self.amcl.last = yaw_of(msg.pose.pose.orientation)

    def tick(self):
        if self.latest_xy is None or self.odom.last is None:
            return
        if self.began is None:
            self.began = time.monotonic()
            self.start_xy = self.latest_xy
            self.get_logger().info('출발: 목표 %.0f°, %.2f rad/s (%s)' % (
                math.degrees(abs(self.target_rad)), abs(self.speed), '좌회전' if self.speed > 0 else '우회전'))
        if abs(self.odom.total) >= abs(self.target_rad):
            self.finish('목표 각도 도달')
            return
        if time.monotonic() - self.began > self.timeout_s:
            self.finish('시간 초과')
            return
        msg = Twist()
        msg.angular.z = self.speed
        self.pub.publish(msg)

    def finish(self, why):
        if self.done is not None:
            return
        for _ in range(3):
            self.pub.publish(Twist())
        seconds = time.monotonic() - (self.began or time.monotonic())
        odom_deg = math.degrees(self.odom.total)
        drift = math.hypot(self.latest_xy[0] - self.start_xy[0], self.latest_xy[1] - self.start_xy[1]) if self.start_xy else 0.0
        self.done = {'why': why, 'odom_deg': round(odom_deg, 1), 'seconds': round(seconds, 1),
                     'mean_rad_s': round(self.odom.total / seconds, 3) if seconds else 0.0,
                     'drift_m': round(drift, 3)}
        if self.amcl.count >= 2:
            amcl_deg = math.degrees(self.amcl.total)
            self.done['amcl_deg'] = round(amcl_deg, 1)
            self.done['odom_over_amcl'] = round(odom_deg / amcl_deg, 4) if amcl_deg else None
            self.done['separation_hint'] = '간격 0.53 × %.4f' % (odom_deg / amcl_deg) if amcl_deg else None
        else:
            self.done['amcl_deg'] = None
        self.get_logger().info('끝: %s' % self.done)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--turns', type=float, default=2.0, help='바퀴 수(기본 2 = 720°)')
    parser.add_argument('--speed', type=float, default=0.5, help='각속도 rad/s (상한 %.1f)' % MAX_SPEED)
    parser.add_argument('--right', action='store_true', help='우회전(기본 좌회전)')
    parser.add_argument('--timeout', type=float, default=None, help='기본은 각도/속도의 2배')
    args = parser.parse_args()
    if not 0 < args.speed <= MAX_SPEED or not 0 < args.turns <= 10:
        sys.exit('속도는 0..%.1f rad/s, 바퀴 수는 0..10' % MAX_SPEED)
    target = args.turns * 2 * math.pi
    speed = -args.speed if args.right else args.speed
    timeout_s = args.timeout or 2 * target / args.speed
    rclpy.init()
    node = SpinRun(target, speed, timeout_s)
    signal.signal(signal.SIGINT, lambda *_: node.finish('중단(Ctrl+C)'))
    try:
        while rclpy.ok() and node.done is None:
            rclpy.spin_once(node, timeout_sec=0.1)
        # 멈춘 뒤 AMCL이 마지막 자세를 반영할 시간을 준다
        settle = time.monotonic()
        while time.monotonic() - settle < 1.5:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        for _ in range(3):
            node.pub.publish(Twist())
            time.sleep(0.05)
        node.destroy_node()
        rclpy.shutdown()
    if node.done:
        # 정지 뒤 감속 구간까지 포함한 최종 각도로 다시 계산(odom·AMCL 모두 멈춘 자세 기준)
        odom_deg = math.degrees(node.odom.total)
        node.done['odom_deg'] = round(odom_deg, 1)
        if node.amcl.count >= 2:
            amcl_deg = math.degrees(node.amcl.total)
            node.done['amcl_deg'] = round(amcl_deg, 1)
            node.done['odom_over_amcl'] = round(odom_deg / amcl_deg, 4) if amcl_deg else None
            node.done['separation_hint'] = '간격 0.53 × %.4f' % (odom_deg / amcl_deg) if amcl_deg else None
        print('\n'.join('%s: %s' % item for item in node.done.items()))


if __name__ == '__main__':
    main()
