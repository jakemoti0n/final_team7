"""
한 바퀴 기록기 노드: 순찰 한 바퀴마다 bag·meta.json·metrics.csv를 한 폴더에 남긴다.

- 시작: 패드 기록 버튼(record_button)을 누르면, 또는 /patrol/state가 patrolling이 되면
  (manual_start면 노드 시작 즉시)
- 끝: 기록 버튼을 다시 누르면, 또는 completed·failed가 되면(또는 노드 종료)
  런치를 한 번 띄워 두고 버튼으로 여러 바퀴를 기록한다. 바퀴 번호는 노드가 사는 동안 올라간다.
- bag은 ros2 bag record를 자식 프로세스로 띄우고 SIGINT로 닫는다. 닫는 단계는 run_files.finish_run.
- 다음 바퀴용 bag을 일시 정지 상태(--start-paused)로 미리 띄워 둔다(런치가 뜰 때, 바퀴가 끝날 때마다).
  새 bag 프로세스가 토픽을 찾아 붙는 데 실물에서 1.3~6.4 s가 걸려 바퀴 첫머리가 비었다(2026-11-26).
  일시 정지 중에도 구독은 붙고, 받은 메시지는 버린다. 시작하면 정지만 푼다(~/resume 서비스).
  대기 bag은 임시 폴더(.standby_<PID>_<순번>)에 쓰고, 바퀴가 끝나 bag을 거둔 뒤 시작 시각 이름의 바퀴 폴더로
  옮긴다. rosbag2가 닫을 때 처음 받은 경로에 metadata.yaml을 쓰므로 녹화 중에는 옮기지 않는다.
- 지표는 bag을 다시 읽지 않고 기록 중 구독한 값으로 메모리에서 계산한다(metrics.py).
  바퀴가 끝나자마자 CSV가 나와 다음 바퀴 전에 결과를 볼 수 있게 하려는 것이다.
폴더 이름·파일 쓰기는 run_files, 지표는 metrics(둘 다 ROS 없음)가 한다.
"""

from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
import shutil
import signal
import subprocess

from geometry_msgs.msg import Twist
from limbo_imitation import metrics, record_button, run_files
from limbo_interfaces.msg import PatrolState, PersonPredictionArray
from nav2_msgs.msg import CollisionMonitorState
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from rosbag2_interfaces.srv import Resume
from sensor_msgs.msg import Joy, LaserScan
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

END_STATES = (PatrolState.COMPLETED, PatrolState.FAILED)
DEFAULT_TOPICS = [
    '/scan', '/odom', '/tf', '/tf_static', '/patrol/state', '/person_detector/predictions',
    '/cmd_vel_teleop', '/cmd_vel_policy', '/cmd_vel_smoothed', '/cmd_vel_arbiter', '/cmd_vel',
    '/drive_mode', '/collision_monitor_state', '/joy', '/policy/status',
]
# s. spin_once가 C에서 기다리는 동안은 파이썬 신호 처리기가 돌지 않아, 종료 신호를 이 주기 안에 알아챈다
SPIN_PERIOD = 0.1
# /tf_static 구독 깊이: tf2_ros 정적 TF 수신(StaticListenerQoS)과 같은 값. 정적 TF 발행자가 여럿이라
# 구독하는 순간 한꺼번에 오는 메시지를 놓치지 않게
TF_STATIC_DEPTH = 100


@dataclass
class StandbyBag:
    """일시 정지 상태로 미리 띄운 bag 하나."""

    process: subprocess.Popen
    folder: str        # 임시 폴더(.standby_…). 안에 bag/
    node_name: str     # rosbag2 노드 이름. 구독 확인·~/resume 서비스에 쓴다
    resume: object     # ~/resume 서비스 클라이언트


@dataclass
class OpenBag:
    """기록을 끝냈지만 아직 안 닫힌 bag. 닫히면 임시 폴더를 바퀴 폴더로 옮긴다."""

    process: subprocess.Popen
    folder: str
    final_folder: str


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
        self.final_folder = None
        self.meta = None
        self.run_number = 0
        self.unclosed_bags = []
        self.robot_xy = None
        self.tf_static = {}
        self.standby = None
        self.standby_seq = 0
        self.pending_resume = None
        self.resume_timer = None
        self.button = record_button.RecordButton(self.record_button)
        self._subscribe()
        self.remove_stale_standby()
        self.standby = self.prepare_standby()
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
        self.record_button = p('record_button', 7).value
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
        # 깊이 10: drive_arbiter가 /joy를 구독하는 것과 같게
        self.create_subscription(Joy, p('record_button_topic', '/joy').value, self.on_joy, 10)
        static = QoSProfile(depth=TF_STATIC_DEPTH, reliability=ReliabilityPolicy.RELIABLE,
                            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(TFMessage, '/tf_static', self.on_tf_static, static)

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_patrol_state(self, msg):
        if self.log is not None:
            self.log.patrol_states.append((self.now(), msg.state))
        if msg.state == PatrolState.PATROLLING and self.log is None:
            self.start_run('patrolling')
        elif msg.state in END_STATES and self.log is not None:
            self.stop_run(msg.state)

    def on_joy(self, msg):
        if not self.button.pressed_now(msg.buttons):
            return
        if record_button.toggle_action(self.log is not None) == record_button.START:
            self.start_run(metrics.START_BUTTON)
        else:
            self.stop_run(metrics.START_BUTTON)

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

    def on_tf_static(self, msg):
        for t in msg.transforms:
            tr, q = t.transform.translation, t.transform.rotation
            self.tf_static[t.child_frame_id] = {
                'parent': t.header.frame_id, 'child': t.child_frame_id,
                'x': tr.x, 'y': tr.y, 'z': tr.z, 'qx': q.x, 'qy': q.y, 'qz': q.z, 'qw': q.w}

    # ------------------------------------------------------------ 대기 bag

    def remove_stale_standby(self):
        """이전 노드가 강제 종료로 남긴 대기 폴더 정리. 빈 대기 bag만 지우고, 기록이 든 폴더는 알린다."""
        for path, has_meta in run_files.stale_standby_folders(self.output_root, pid_alive):
            if has_meta:
                self.get_logger().warning(f'{path}: 옮기지 못한 바퀴 기록(meta.json 있음). 그대로 둔다')
            else:
                shutil.rmtree(path)

    def prepare_standby(self):
        """다음 바퀴용 bag을 일시 정지 상태로 띄운다.

        같은 세션(start_new_session=False)에서 띄운다. 터미널 Ctrl+C가 같은 프로세스 그룹의 bag에도
        직접 가서, 이 노드가 먼저 죽어도 bag이 닫힌다.
        """
        self.standby_seq += 1
        folder_name, node_name = run_files.standby_name(os.getpid(), self.standby_seq)
        folder = os.path.join(self.output_root, folder_name)
        os.makedirs(folder, exist_ok=False)
        command = ['ros2', 'bag', 'record', '--start-paused', '--disable-keyboard-controls',
                   '--node-name', node_name, '-o', os.path.join(folder, run_files.BAG_DIR),
                   '--topics'] + self.topics
        client = self.create_client(Resume, f'/{node_name}/resume')
        return StandbyBag(self.spawn_bag(command), folder, node_name, client)

    def spawn_bag(self, command):
        return subprocess.Popen(command, start_new_session=False, preexec_fn=sigint_default)

    def standby_problems(self, standby):
        """대기 bag이 아직 덜 된 점(사람이 읽을 말 목록). 비면 준비 끝."""
        problems = []
        if not standby.resume.service_is_ready():
            problems.append('재개 서비스 아직 없음')

        def subscribed(topic):
            return any(info.node_name == standby.node_name
                       for info in self.get_subscriptions_info_by_topic(topic))
        missing = run_files.unsubscribed_topics(self.topics, self.count_publishers, subscribed)
        if missing:
            problems.append('연결 중인 토픽 ' + ', '.join(missing))
        return problems

    def resume_bag(self, standby):
        """정지를 푼다. 서비스가 아직 없으면 생길 때까지 SPIN_PERIOD마다 다시 본다."""
        if standby.resume.service_is_ready():
            standby.resume.call_async(Resume.Request())
            return
        self.pending_resume = standby
        if self.resume_timer is None:
            self.resume_timer = self.create_timer(SPIN_PERIOD, self.on_resume_timer)

    def on_resume_timer(self):
        standby = self.pending_resume
        if standby is None or standby.process.poll() is not None:
            self.pending_resume = None
        elif standby.resume.service_is_ready():
            standby.resume.call_async(Resume.Request())
            self.pending_resume = None
        if self.pending_resume is None:
            self.destroy_timer(self.resume_timer)
            self.resume_timer = None

    def close_standby(self):
        """쓰지 않은 대기 bag을 SIGINT로 닫고 임시 폴더를 지운다(노드 종료 때)."""
        standby, self.standby = self.standby, None
        if standby is None:
            return
        run_files.signal_bag(standby.process)
        if run_files.wait_bag(standby.process, self.bag_stop_timeout):
            shutil.rmtree(standby.folder, ignore_errors=True)
        else:
            self.get_logger().warning(
                f'standby ros2 bag record (pid {standby.process.pid}) did not exit within '
                f'{self.bag_stop_timeout} s after SIGINT; {standby.folder} left')

    def settle_unclosed(self):
        """늦게 닫힌 bag을 거두고 바퀴 폴더로 옮긴다."""
        still_open = []
        for bag in self.unclosed_bags:
            if bag.process.poll() is None:
                still_open.append(bag)
            else:
                os.rename(bag.folder, bag.final_folder)
        self.unclosed_bags = still_open

    # ------------------------------------------------------------ 바퀴

    def start_run(self, reason):
        self.settle_unclosed()
        standby, self.standby = self.standby, None
        if standby is None or standby.process.poll() is not None:
            # 대기 bag이 없거나 죽어 있으면 지금 새로 띄운다(첫머리가 빌 수 있다)
            if standby is not None:
                shutil.rmtree(standby.folder, ignore_errors=True)
            standby = self.prepare_standby()
        problems = self.standby_problems(standby)
        self.resume_bag(standby)
        self.run_number += 1
        start = datetime.now()
        self.folder = standby.folder
        self.final_folder = os.path.join(self.output_root, run_files.run_folder_name(
            start, self.run_number, self.mode))
        self.meta = run_files.build_meta(self.mode, self.driver, self.waypoints_file,
                                         self.map_yaml, self.model_file, self.note,
                                         start.isoformat(timespec='seconds'))
        self.meta['start_reason'] = reason
        run_files.write_json(os.path.join(self.folder, run_files.META_FILE), self.meta)
        run_files.write_json(os.path.join(self.folder, run_files.TF_STATIC_FILE),
                             sorted(self.tf_static.values(), key=lambda t: t['child']))
        self.bag = standby.process
        self.log = metrics.RunLog(start_time=self.now(), start_reason=reason)
        self.get_logger().info(run_files.start_line(self.run_number, reason, start))
        self.get_logger().info(
            f'{run_files.LINE_PREFIX} 폴더 {os.path.basename(self.final_folder)}')
        if problems:
            # 기록은 바로 시작한다(운전자를 세우지 않는다). 덜 붙은 토픽은 첫머리가 빌 수 있다
            self.get_logger().warning(
                f'{run_files.LINE_PREFIX} 기록 준비가 덜 된 채 시작: ' + '; '.join(problems))

    def stop_run(self, end_reason, prepare_next=True):
        self.log.end_time = self.now()
        self.meta['end_time'] = datetime.now().isoformat(timespec='seconds')
        self.meta['end_reason'] = end_reason
        row, bag_closed = run_files.finish_run(self.folder, self.meta, self.log, self.settings,
                                               self.bag, self.bag_stop_timeout)
        # 거리는 /odom이 두 개 이상 왔을 때만 안다(없으면 0 m가 아니라 모르는 값)
        distance = row['distance'] if len(self.log.odom) >= 2 else None
        if bag_closed:
            os.rename(self.folder, self.final_folder)
        else:
            # 닫히면(다음 바퀴 시작 때 확인) 바퀴 폴더로 옮긴다. 사람이 판단하도록 PID를 남긴다
            self.unclosed_bags.append(OpenBag(self.bag, self.folder, self.final_folder))
            self.get_logger().warning(
                f'ros2 bag record (pid {self.bag.pid}) did not exit within '
                f'{self.bag_stop_timeout} s after SIGINT; left running in {self.folder}, '
                f'bag may be unclosed')
        self.get_logger().info(run_files.end_line(self.run_number, end_reason, row['duration'],
                                                  distance, bag_closed))
        self.log = None
        self.bag = None
        if prepare_next:
            # 이전 bag을 거둔 뒤에 띄운다. 대기 bag과 기록 중 bag이 함께 뜨는 때가 없게
            # (record_laps_checks.py의 RECORDER_CHILD_PROCESSES = 1)
            self.standby = self.prepare_standby()
        if end_reason == metrics.START_BUTTON:
            # 버튼으로 끝낸 경우만. 런치 종료·순찰 끝에는 ≡ 안내가 맞지 않는다
            self.get_logger().info(run_files.IDLE_LINE)


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
            node.stop_run('node shutdown', prepare_next=False)
        node.close_standby()
        node.settle_unclosed()
        for bag in node.unclosed_bags:
            node.get_logger().warning(
                f'{bag.folder}: bag not closed, not moved to {bag.final_folder}')
        executor.shutdown()
        node.destroy_node()
        rclpy.try_shutdown()
