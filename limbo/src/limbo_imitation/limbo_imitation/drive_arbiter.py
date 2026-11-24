"""
주행 중재기 노드: teleop·정책·MPPI 세 속도 명령 중 하나를 골라 collision_monitor 입력으로 낸다.

판단은 arbiter_logic(ROS 없음)이 한다. 이 노드는 구독한 최신 값을 arbiter_logic.Inputs에 담아
publish_rate마다 arbiter_logic.step을 부르고 결과를 낸다.
- 출력: cmd_vel_out_topic(기본 /cmd_vel_arbiter) → collision_monitor → /cmd_vel → 바퀴
- /drive_mode: 출처가 바뀔 때마다, 그리고 바뀌지 않아도 1 Hz로 JSON을 낸다.
  기록기가 바퀴 중간에 켜져도 지금 누가 운전하는지 알 수 있게 하려는 것이다.
"""

import json

from geometry_msgs.msg import Twist
from limbo_imitation import arbiter_logic
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import String

DRIVE_MODE_REPEAT_SEC = 1.0


class DriveArbiter(Node):

    def __init__(self):
        super().__init__('drive_arbiter')
        p = self.declare_parameter
        mode = p('mode', 'nav').value
        if mode not in arbiter_logic.MODES:
            raise ValueError(f'mode must be one of {arbiter_logic.MODES}, got {mode}')
        self.deadman_button = p('deadman_button', 4).value
        self.settings = arbiter_logic.Settings(
            command_timeout=p('command_timeout', 0.5).value,
            stuck_speed=p('stuck_speed', 0.05).value,
            stuck_timeout=p('stuck_timeout', 3.0).value,
            require_deadman=p('require_deadman', True).value)
        self.inputs = arbiter_logic.Inputs(mode=mode)
        self.state = arbiter_logic.State()
        self.last_mode_publish = None
        self.last_reason = None
        self._subscribe(p)
        cmd_topic = p('cmd_vel_out_topic', '/cmd_vel_arbiter').value
        self.cmd_pub = self.create_publisher(Twist, cmd_topic, 10)
        mode_topic = p('drive_mode_topic', '/drive_mode').value
        self.mode_pub = self.create_publisher(String, mode_topic, 10)
        self.create_timer(1.0 / p('publish_rate', 20.0).value, self.on_tick)
        self.get_logger().info(f'drive_arbiter mode={mode} deadman_button={self.deadman_button}')

    def _subscribe(self, p):
        self.create_subscription(Twist, p('teleop_topic', '/cmd_vel_teleop').value,
                                 self.on_teleop, 10)
        self.create_subscription(Twist, p('policy_topic', '/cmd_vel_policy').value,
                                 self.on_policy, 10)
        self.create_subscription(Twist, p('nav_topic', '/cmd_vel_smoothed').value, self.on_nav, 10)
        self.create_subscription(Joy, p('joy_topic', '/joy').value, self.on_joy, 10)
        self.create_subscription(String, p('policy_status_topic', '/policy/status').value,
                                 self.on_status, 10)
        self.create_subscription(Odometry, p('odom_topic', '/odom').value, self.on_odom, 10)

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_teleop(self, msg):
        self.inputs.teleop = (msg.linear.x, msg.angular.z)
        self.inputs.teleop_time = self.now()

    def on_policy(self, msg):
        self.inputs.policy = (msg.linear.x, msg.angular.z)
        self.inputs.policy_time = self.now()

    def on_nav(self, msg):
        self.inputs.nav = (msg.linear.x, msg.angular.z)
        self.inputs.nav_time = self.now()

    def on_joy(self, msg):
        buttons = msg.buttons
        self.inputs.deadman = (self.deadman_button < len(buttons)
                               and buttons[self.deadman_button] == 1)
        self.inputs.joy_time = self.now()

    def on_status(self, msg):
        ok, reason = arbiter_logic.parse_policy_status(msg.data)
        self.inputs.status_ok, self.inputs.status_reason = ok, reason
        self.inputs.status_time = self.now()

    def on_odom(self, msg):
        self.inputs.odom_speed = msg.twist.twist.linear.x
        self.inputs.odom_time = self.now()

    def on_tick(self):
        self.inputs.now = self.now()
        previous_source = self.state.source
        (v, w), source, reason = arbiter_logic.step(self.state, self.inputs, self.settings)
        twist = Twist()
        twist.linear.x, twist.angular.z = v, w
        self.cmd_pub.publish(twist)
        changed = source != previous_source or reason != self.last_reason
        due = (self.last_mode_publish is None
               or self.inputs.now - self.last_mode_publish >= DRIVE_MODE_REPEAT_SEC)
        if changed or due:
            self.publish_mode(source, reason)
        if changed:
            self.get_logger().info(f'source {previous_source} -> {source} ({reason})')

    def publish_mode(self, source, reason):
        payload = {'source': source, 'mode': self.inputs.mode, 'reason': reason,
                   'stamp': self.inputs.now}
        self.mode_pub.publish(String(data=json.dumps(payload)))
        self.last_mode_publish = self.inputs.now
        self.last_reason = reason


def main(args=None):
    rclpy.init(args=args)
    node = DriveArbiter()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
