"""
바퀴는 도는데 로봇이 실제로는 안 움직이는 상황(헛돎)을 감지해 주행을 멈추는 노드.

바퀴 odom만 믿으면 헛도는 동안 위치가 계속 앞으로 쌓여 AMCL이 위치를 놓친다.
일정 시간마다 바퀴 이동량과 LiDAR 스캔으로 본 이동량을 비교하고,
헛돎이 확정되면 /wheel_slip을 True로 내고 Nav2 Goal을 취소해 바퀴를 세운다.
"""

import math

from action_msgs.srv import CancelGoal
from limbo_monitor import scan_motion, slip
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool

SLIP_TOPIC = '/wheel_slip'
PUBLISH_QUEUE = 10
# 빈 goal_id로 취소 요청하면 그 액션 서버의 모든 Goal이 취소된다
CANCEL_SERVICE_SUFFIX = '/_action/cancel_goal'


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class WheelSlipMonitor(Node):

    def __init__(self):
        super().__init__('wheel_slip_monitor')
        self._declare_parameters()

        self.detector = slip.SlipDetector(self.slip_config)
        self.latest_odom = None
        self.reference = None   # (stamp_sec, scan points, odom x, y, yaw)
        self.slipping = False

        self.slip_pub = self.create_publisher(Bool, SLIP_TOPIC, PUBLISH_QUEUE)
        self.cancel_clients = [
            self.create_client(CancelGoal, action + CANCEL_SERVICE_SUFFIX)
            for action in self.cancel_actions]

        # 바퀴만으로 계산한 odom이어야 헛돎이 드러난다 (EKF 출력이 아니라 diff-drive /odom)
        self.create_subscription(
            Odometry, self.wheel_odom_topic, self.odom_callback, PUBLISH_QUEUE)
        self.create_subscription(
            LaserScan, self.scan_topic, self.scan_callback, qos_profile_sensor_data)

        self.get_logger().info('Wheel slip monitor started')

    def _declare_parameters(self):
        # 코드 기본값은 yaml 없이도 노드가 뜨게 하는 보험이다. 튜닝은 yaml에서 한다.
        p = self.declare_parameter

        self.scan_topic = p('scan_topic', '/scan').value
        self.wheel_odom_topic = p('wheel_odom_topic', '/odom').value
        self.cancel_actions = p(
            'cancel_actions',
            ['/navigate_to_pose', '/navigate_through_poses', '/follow_waypoints']).value
        self.cancel_navigation = p('cancel_navigation_on_slip', True).value

        self.check_period = p('check_period', 0.5).value
        self.scan_range_min = p('scan_range_min', 0.1).value
        self.scan_range_max = p('scan_range_max', 10.0).value

        i = scan_motion.IcpConfig()
        self.icp_config = scan_motion.IcpConfig(
            max_iterations=p('icp.max_iterations', i.max_iterations).value,
            max_correspondence=p('icp.max_correspondence', i.max_correspondence).value,
            min_points=p('icp.min_points', i.min_points).value,
        )

        s = slip.SlipConfig()
        self.slip_config = slip.SlipConfig(
            min_wheel_distance=p('slip.min_wheel_distance', s.min_wheel_distance).value,
            max_scan_ratio=p('slip.max_scan_ratio', s.max_scan_ratio).value,
            min_forward_constraint=p(
                'slip.min_forward_constraint', s.min_forward_constraint).value,
            max_wheel_rotation=p('slip.max_wheel_rotation', s.max_wheel_rotation).value,
            consecutive_windows=p('slip.consecutive_windows', s.consecutive_windows).value,
        )

    def odom_callback(self, msg):
        pose = msg.pose.pose
        self.latest_odom = (pose.position.x, pose.position.y, yaw_of(pose.orientation))

    def scan_callback(self, msg):
        if self.latest_odom is None:
            return

        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        points = scan_motion.scan_to_points(
            msg.ranges, msg.angle_min, msg.angle_increment,
            self.scan_range_min, self.scan_range_max)

        if self.reference is None:
            self.reference = (stamp, points, *self.latest_odom)
            return
        if stamp - self.reference[0] < self.check_period:
            return

        state = self._judge(points)
        self.reference = (stamp, points, *self.latest_odom)
        self._publish(state)

    def _judge(self, points):
        _, ref_points, ref_x, ref_y, ref_yaw = self.reference
        x, y, yaw = self.latest_odom
        wheel_distance = math.hypot(x - ref_x, y - ref_y)
        wheel_rotation = math.remainder(yaw - ref_yaw, 2 * math.pi)
        motion = scan_motion.estimate_motion(ref_points, points, self.icp_config)
        state = self.detector.update(wheel_distance, wheel_rotation, motion)

        if state in (slip.SUSPECT, slip.SLIP):
            self.get_logger().warn(
                f'{state}: wheel {wheel_distance:.2f} m, '
                f'scan {math.hypot(motion.dx, motion.dy):.2f} m')
        return state

    def _publish(self, state):
        now_slipping = state == slip.SLIP
        # UNKNOWN 구간에서는 이전 판단을 유지한다
        if state in (slip.OK, slip.SLIP):
            if now_slipping and not self.slipping:
                self.get_logger().error(
                    'Wheel slip detected: wheels turn but the robot is not moving')
                if self.cancel_navigation:
                    self._cancel_navigation()
            self.slipping = now_slipping

        msg = Bool()
        msg.data = self.slipping
        self.slip_pub.publish(msg)

    def _cancel_navigation(self):
        for client in self.cancel_clients:
            if client.service_is_ready():
                client.call_async(CancelGoal.Request())


def main(args=None):
    rclpy.init(args=args)
    node = WheelSlipMonitor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
