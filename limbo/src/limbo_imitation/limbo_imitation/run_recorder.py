"""
한 바퀴 기록기 노드: 순찰 한 바퀴마다 bag·meta.json·metrics.csv를 한 폴더에 남긴다.

- 시작: /patrol/state가 patrolling이 되면(manual_start면 노드 시작 즉시)
- 끝: completed·failed가 되면(또는 노드 종료)
- bag은 ros2 bag record를 자식 프로세스로 띄우고 SIGINT로 닫는다.
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
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

END_STATES = (PatrolState.COMPLETED, PatrolState.FAILED)
DEFAULT_TOPICS = [
    '/scan', '/odom', '/tf', '/tf_static', '/patrol/state', '/person_detector/predictions',
    '/cmd_vel_teleop', '/cmd_vel_policy', '/cmd_vel_smoothed', '/cmd_vel_arbiter', '/cmd_vel',
    '/drive_mode', '/collision_monitor_state', '/joy', '/policy/status',
]


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
        self.robot_xy = None
        self._subscribe()
        if self.manual_start:
            self.start_run('manual_start')

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
        self.log = metrics.RunLog(start_time=self.now())
        self.get_logger().info(f'run {self.run_number} started ({reason}): {self.folder}')

    def start_bag(self, bag_path):
        """같은 세션(start_new_session=False)에서 띄운다.

        터미널 Ctrl+C가 같은 프로세스 그룹의 bag에도 직접 가서, 이 노드가 먼저 죽어도 bag이 닫힌다.
        """
        command = ['ros2', 'bag', 'record', '-o', bag_path, '--topics'] + self.topics
        return subprocess.Popen(command, start_new_session=False, preexec_fn=sigint_default)

    def stop_bag(self):
        """SIGINT로 닫고 기다린다. 안 닫히면 SIGTERM을 보내지 않고 경고만 남긴다.

        SIGTERM은 PM 승인 뒤에만 쓰기로 한 수단이다(TROUBLESHOOTING 2026-11-10).
        사람이 상황을 보고 판단하도록 PID를 남긴다.
        """
        if self.bag.poll() is not None:
            return
        self.bag.send_signal(signal.SIGINT)
        try:
            self.bag.wait(timeout=self.bag_stop_timeout)
        except subprocess.TimeoutExpired:
            self.get_logger().warning(
                f'ros2 bag record (pid {self.bag.pid}) did not exit within '
                f'{self.bag_stop_timeout} s after SIGINT; left running, bag may be unclosed')

    def stop_run(self, end_reason):
        self.stop_bag()
        self.log.end_time = self.now()
        row = metrics.metrics_row(metrics.compute_metrics(self.log, self.settings), self.settings)
        run_files.write_metrics_csv(os.path.join(self.folder, run_files.METRICS_FILE),
                                    row, metrics.ROW_COLUMNS)
        self.meta['end_time'] = datetime.now().isoformat(timespec='seconds')
        self.meta['end_reason'] = end_reason
        run_files.write_json(os.path.join(self.folder, run_files.META_FILE), self.meta)
        self.get_logger().info(f'run {self.run_number} ended ({end_reason}): '
                               f"passed={row['passed']} {row['fail_reasons']}")
        self.log = None
        self.bag = None


def main(args=None):
    rclpy.init(args=args)
    node = RunRecorder()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node.log is not None:
            node.stop_run('node shutdown')
        node.destroy_node()
        rclpy.try_shutdown()
