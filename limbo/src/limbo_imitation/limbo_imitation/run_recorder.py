"""
한 바퀴 기록기 노드: 순찰 한 바퀴마다 bag·meta.json·metrics.csv를 한 폴더에 남긴다.

- 시작: /patrol/state가 patrolling이 되면(manual_start면 노드 시작 즉시)
- 끝: completed·failed가 되면(또는 노드 종료)
- bag은 ros2 bag record를 자식 프로세스로 띄우고 SIGINT로 닫는다. 닫는 단계는 run_files.finish_run.
- 지표는 bag을 다시 읽지 않고 기록 중 구독한 값으로 메모리에서 계산한다(metrics.py).
  바퀴가 끝나자마자 CSV가 나와 다음 바퀴 전에 결과를 볼 수 있게 하려는 것이다.
폴더 이름·파일 쓰기는 run_files, 지표는 metrics(둘 다 ROS 없음)가 한다.
"""

from datetime import datetime
import json
import math
import os
import signal
import subprocess

from geometry_msgs.msg import Twist
from limbo_imitation import metrics, run_files
from limbo_interfaces.msg import PatrolState, PersonPredictionArray
from nav2_msgs.msg import CollisionMonitorState
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

END_STATES = (PatrolState.COMPLETED, PatrolState.FAILED)
DEFAULT_TOPICS = [
    '/scan', '/odom', '/tf', '/tf_static', '/patrol/state', '/person_detector/predictions',
    '/cmd_vel_teleop', '/cmd_vel_policy', '/cmd_vel_smoothed', '/cmd_vel_arbiter', '/cmd_vel',
    '/drive_mode', '/collision_monitor_state', '/joy', '/policy/status',
]
# s. spin_once가 C에서 기다리는 동안은 파이썬 신호 처리기가 돌지 않아, 종료 신호를 이 주기 안에 알아챈다
SPIN_PERIOD = 0.1


def sigint_default():
    """자식(ros2 bag)의 SIGINT를 기본 동작으로 되돌린다.

    셸 스크립트에서 뒤로 띄운 프로세스는 SIGINT 무시 상태로 시작하고 자식이 그걸 물려받아,
    bag이 SIGINT로 안 닫히고 mcap이 깨진 일이 있다(TROUBLESHOOTING 2026-11-10).
    """
    signal.signal(signal.SIGINT, signal.SIG_DFL)


class RunRecorder(Node):

    def __init__(self):
        super().__init__('run_recorder')
        self._declare_parameters()
        self.log = None
        self.bag = None
        self.folder = None
        self.meta = None
        self.run_number = 0
        self.unclosed_bags = []
        self.robot_xy = None
        self._subscribe()
        if self.manual_start:
            self.start_run(metrics.START_MANUAL)

    def _declare_parameters(self):
        p = self.declare_parameter
        self.mode = p('mode', 'manual').value
        self.driver = p('driver', '').value
        self.note = p('note', '').value
        self.waypoints_file = p('waypoints_file', '').value
        self.map_yaml = p('map_yaml', '').value
        self.model_file = p('model_file', '').value
        self.manual_start = p('manual_start', False).value
        self.output_root = os.path.expanduser(p('output_root', '~/limbo_bags/imitation').value)
        self.topics = list(p('topics', DEFAULT_TOPICS).value)
        self.bag_stop_timeout = p('bag_stop_timeout', 10.0).value
        self.settings = {name: p(name, value).value
                         for name, value in metrics.DEFAULT_SETTINGS.items()}

    def _subscribe(self):
        p = self.declare_parameter
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        sensor = qos_profile_sensor_data
        self.create_subscription(PatrolState, p('patrol_state_topic', '/patrol/state').value,
                                 self.on_patrol_state, latched)
        self.create_subscription(LaserScan, p('scan_topic', '/scan').value, self.on_scan, sensor)
        self.create_subscription(Odometry, p('odom_topic', '/odom').value, self.on_odom, sensor)
        self.create_subscription(PersonPredictionArray,
                                 p('predictions_topic', '/person_detector/predictions').value,
                                 self.on_predictions, sensor)
        self.create_subscription(Twist, p('cmd_topic', '/cmd_vel_arbiter').value,
                                 self.on_cmd, sensor)
        self.create_subscription(Twist, p('cmd_out_topic', '/cmd_vel').value,
                                 self.on_cmd_out, sensor)
        self.create_subscription(String, p('drive_mode_topic', '/drive_mode').value,
                                 self.on_drive_mode, 10)
        monitor_topic = p('collision_monitor_state_topic', '/collision_monitor_state').value
        self.create_subscription(CollisionMonitorState, monitor_topic,
                                 self.on_monitor_state, sensor)

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_patrol_state(self, msg):
        if self.log is not None:
            self.log.patrol_states.append((self.now(), msg.state))
        if msg.state == PatrolState.PATROLLING and self.log is None:
            self.start_run('patrolling')
        elif msg.state in END_STATES and self.log is not None:
            self.stop_run(msg.state)

    def on_scan(self, msg):
        if self.log is not None:
            nearest = metrics.scan_min_range(msg.ranges, msg.range_min, msg.range_max)
            self.log.scan_min.append((self.now(), nearest))

    def on_odom(self, msg):
        position = msg.pose.pose.position
        self.robot_xy = (position.x, position.y)
        if self.log is not None:
            twist = msg.twist.twist
            self.log.odom.append((self.now(), position.x, position.y,
                                  twist.linear.x, twist.angular.z))

    def on_predictions(self, msg):
        """가장 가까운 사람 거리. 사람 위치(person_detector)와 로봇 위치(/odom) 모두 odom 좌표다."""
        if self.log is None or self.robot_xy is None:
            return
        rx, ry = self.robot_xy
        distances = [math.hypot(p.current_position.x - rx, p.current_position.y - ry)
                     for p in msg.predictions]
        self.log.person_dist.append((self.now(), min(distances, default=math.inf)))

    def on_cmd(self, msg):
        if self.log is not None:
            self.log.cmd.append((self.now(), msg.linear.x, msg.angular.z))

    def on_cmd_out(self, msg):
        if self.log is not None:
            self.log.cmd_out.append((self.now(), msg.linear.x, msg.angular.z))

    def on_drive_mode(self, msg):
        if self.log is None:
            return
        try:
            data = json.loads(msg.data)
            self.log.drive_modes.append((self.now(), data['source'], data['mode']))
        except (ValueError, KeyError, TypeError):
            self.get_logger().warning(f'unreadable /drive_mode: {msg.data}')

    def on_monitor_state(self, msg):
        if self.log is not None:
            self.log.monitor_states.append((self.now(), msg.action_type))

    def start_run(self, reason):
        self.unclosed_bags = [bag for bag in self.unclosed_bags if bag.poll() is None]
        self.run_number += 1
        start = datetime.now()
        self.folder = os.path.join(self.output_root, run_files.run_folder_name(
            start, self.run_number, self.mode))
        os.makedirs(self.folder, exist_ok=False)
        self.meta = run_files.build_meta(self.mode, self.driver, self.waypoints_file,
                                         self.map_yaml, self.model_file, self.note,
                                         start.isoformat(timespec='seconds'))
        self.meta['start_reason'] = reason
        run_files.write_json(os.path.join(self.folder, run_files.META_FILE), self.meta)
        self.bag = self.start_bag(os.path.join(self.folder, run_files.BAG_DIR))
        self.log = metrics.RunLog(start_time=self.now(), start_reason=reason)
        self.get_logger().info(f'run {self.run_number} started ({reason}): {self.folder}')

    def start_bag(self, bag_path):
        """같은 세션(start_new_session=False)에서 띄운다.

        터미널 Ctrl+C가 같은 프로세스 그룹의 bag에도 직접 가서, 이 노드가 먼저 죽어도 bag이 닫힌다.
        """
        command = ['ros2', 'bag', 'record', '-o', bag_path, '--topics'] + self.topics
        return subprocess.Popen(command, start_new_session=False, preexec_fn=sigint_default)

    def stop_run(self, end_reason):
        self.log.end_time = self.now()
        self.meta['end_time'] = datetime.now().isoformat(timespec='seconds')
        self.meta['end_reason'] = end_reason
        row, bag_closed = run_files.finish_run(self.folder, self.meta, self.log, self.settings,
                                               self.bag, self.bag_stop_timeout)
        self.get_logger().info(f'run {self.run_number} ended ({end_reason}): '
                               f"passed={row['passed']} {row['fail_reasons']}")
        if not bag_closed:
            # 다음 바퀴 시작 때 다시 거둔다(좀비로 남지 않게). 사람이 판단하도록 PID를 남긴다
            self.unclosed_bags.append(self.bag)
            self.get_logger().warning(
                f'ros2 bag record (pid {self.bag.pid}) did not exit within '
                f'{self.bag_stop_timeout} s after SIGINT; left running, bag may be unclosed')
        self.log = None
        self.bag = None


def raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt


def install_stop_signals():
    """SIGINT·SIGTERM을 KeyboardInterrupt로 받는다. rclpy 신호 처리기는 쓰지 않는다.

    rclpy 처리기는 신호를 받자마자 context를 닫아, 종료 단계의 로그가 rosout으로 못 가고
    ("publisher's context is invalid") 종료 중 온 두 번째 신호가 결과 쓰기를 끊을 수 있었다.
    SIGINT를 직접 거는 이유: 셸에서 뒤로 띄운 launch 아래면 SIGINT 무시 상태로 시작하고
    파이썬은 그때 KeyboardInterrupt 처리기를 걸지 않는다.
    """
    signal.signal(signal.SIGINT, raise_keyboard_interrupt)
    signal.signal(signal.SIGTERM, raise_keyboard_interrupt)


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    install_stop_signals()
    node = RunRecorder()
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    try:
        while rclpy.ok():
            executor.spin_once(timeout_sec=SPIN_PERIOD)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # 결과 쓰기 중 두 번째 Ctrl+C는 무시. SIGTERM(launch가 5 s 뒤 보냄)은 기본 동작으로 죽게 둔다
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        if node.log is not None:
            node.stop_run('node shutdown')
        executor.shutdown()
        node.destroy_node()
        rclpy.try_shutdown()
