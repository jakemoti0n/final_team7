"""조종 관문. 키보드·게임패드·(나중에) 폰이 /drive/cmd로 보낸 속도를 하나로 받아 로봇에 낸다.

왜 따로 두나: 입력이 무엇이든 로봇으로 가는 속도 명령은 이 노드 하나만 낸다. 그래서
  - 데드맨: 입력이 deadman_sec 안에 안 오면 0을 낸다 (패드 버튼을 떼거나 폰·키보드 창이 끊겨도 선다)
  - 상한: 전진·후진·회전 속도를 자른다. 가속도 제한으로 스틱을 확 밀어도 미끄러지지 않는다
  - 켜기/끄기: /drive/enable, /drive/disable (std_srvs/Trigger), /drive/enabled (std_msgs/Bool, 늦게 붙어도 받음)
  - 순찰과 겹치지 않게: /patrol/state가 patrolling·pausing이면 켜기를 거절하고, 켜진 채 순찰이 시작되면 스스로 끈다
출력 토픽은 파라미터 cmd_topic. 지도 작성(Nav2 없음)은 /cmd_vel, 주행 스택에 붙일 땐 /cmd_vel_nav(속도 평활기·충돌 감시 뒤).
"""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from geometry_msgs.msg import Twist
from std_msgs.msg import Bool
from std_srvs.srv import Trigger

try:
    from limbo_interfaces.msg import PatrolState
    BUSY_STATES = (PatrolState.PATROLLING, PatrolState.PAUSING)
except ImportError:          # 순찰 패키지 없이도(지도 작성만) 돈다
    PatrolState = None
    BUSY_STATES = ('patrolling', 'pausing')


def clamp(value, low, high):
    return max(low, min(high, value))


def approach(current, target, max_step):
    """current를 target 쪽으로 최대 max_step만큼만 옮긴다 (가속도 제한)."""
    return current + clamp(target - current, -max_step, max_step)


class DriveGate(Node):

    def __init__(self):
        super().__init__('drive_gate')
        self.cmd_topic = self.declare_parameter('cmd_topic', '/cmd_vel').value
        self.max_forward = self.declare_parameter('max_forward_mps', 0.3).value
        self.max_reverse = self.declare_parameter('max_reverse_mps', 0.15).value
        self.max_angular = self.declare_parameter('max_angular_radps', 0.8).value
        self.max_accel = self.declare_parameter('max_accel_mps2', 0.5).value
        self.max_angular_accel = self.declare_parameter('max_angular_accel_radps2', 2.0).value
        self.deadman_sec = self.declare_parameter('deadman_sec', 0.5).value
        self.rate_hz = self.declare_parameter('rate_hz', 20.0).value
        self.enabled = self.declare_parameter('enabled_on_start', True).value

        self.target = Twist()          # 마지막 입력(상한으로 자른 것)
        self.output = Twist()          # 실제로 낸 값(가속도 제한 뒤)
        self.last_input_time = None
        self.patrol_state = ''

        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.cmd_pub = self.create_publisher(Twist, self.cmd_topic, 10)
        self.enabled_pub = self.create_publisher(Bool, '/drive/enabled', latched)
        self.create_subscription(Twist, '/drive/cmd', self.on_cmd, 10)
        if PatrolState is not None:
            self.create_subscription(PatrolState, '/patrol/state', self.on_patrol_state, latched)
        self.create_service(Trigger, '/drive/enable', self.on_enable)
        self.create_service(Trigger, '/drive/disable', self.on_disable)
        self.create_timer(1.0 / self.rate_hz, self.tick)
        self.publish_enabled()
        self.get_logger().info(
            f'drive gate → {self.cmd_topic}: forward {self.max_forward} m/s, reverse {self.max_reverse}, '
            f'turn {self.max_angular} rad/s, deadman {self.deadman_sec} s, '
            f'{"enabled" if self.enabled else "disabled"}')

    # ---- 켜기·끄기
    def on_enable(self, request, response):
        if self.patrol_state in BUSY_STATES:
            response.success, response.message = False, f'patrol in progress ({self.patrol_state})'
        elif self.enabled:
            response.success, response.message = False, 'already enabled'
        else:
            self.set_enabled(True, 'enabled by request')
            response.success, response.message = True, 'drive enabled'
        return response

    def on_disable(self, request, response):
        if not self.enabled:
            response.success, response.message = False, 'already disabled'
        else:
            self.set_enabled(False, 'disabled by request')
            response.success, response.message = True, 'drive disabled'
        return response

    def set_enabled(self, enabled, reason):
        self.enabled = enabled
        self.target = Twist()
        self.output = Twist()
        self.last_input_time = None
        if not enabled:
            self.cmd_pub.publish(Twist())     # 끌 때 0을 한 번 내서 바로 선다
        self.publish_enabled()
        self.get_logger().info(f'drive {"on" if enabled else "off"}: {reason}')

    def publish_enabled(self):
        self.enabled_pub.publish(Bool(data=self.enabled))

    # ---- 입력
    def on_cmd(self, msg):
        if not self.enabled:
            return
        lin = msg.linear.x if math.isfinite(msg.linear.x) else 0.0
        ang = msg.angular.z if math.isfinite(msg.angular.z) else 0.0
        self.target.linear.x = clamp(lin, -self.max_reverse, self.max_forward)
        self.target.angular.z = clamp(ang, -self.max_angular, self.max_angular)
        self.last_input_time = self.get_clock().now()

    def on_patrol_state(self, msg):
        self.patrol_state = msg.state
        if self.enabled and msg.state in BUSY_STATES:
            self.set_enabled(False, f'patrol started ({msg.state})')

    # ---- 출력 (rate_hz마다)
    def tick(self):
        if not self.enabled:
            return
        fresh = (self.last_input_time is not None and
                 (self.get_clock().now() - self.last_input_time).nanoseconds * 1e-9 < self.deadman_sec)
        target = self.target if fresh else Twist()
        dt = 1.0 / self.rate_hz
        self.output.linear.x = approach(self.output.linear.x, target.linear.x, self.max_accel * dt)
        self.output.angular.z = approach(self.output.angular.z, target.angular.z, self.max_angular_accel * dt)
        self.cmd_pub.publish(self.output)


def main(args=None):
    rclpy.init(args=args)
    node = DriveGate()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):   # Ctrl+C·launch 종료 때 조용히 끝낸다
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
