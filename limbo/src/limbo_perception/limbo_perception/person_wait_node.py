"""
사람 기다리기 노드: 사람 트랙 → /person_wait (설계 2-7, tof_node의 래치 둘을 대체).

판단은 person_wait.PersonWait(ROS 없는 상태 기계) 하나가 한다. 이 노드는 입력을 맞춰 넣고 결과를 낸다.
- 사람 트랙: /person_detector/predictions(odom 기준) → 범퍼 앞 기준 위치·로봇 축 속도
  (geometry.tracks_ahead_of_bumper)
- 준비: /map 수신 + map→base_link TF가 ready_hold_sec 동안 끊김 없이 조회됨 + 트랙 메시지가 한 번 이상 옴
- ToF: /tof/obstacle_ahead. 트랙이 끊긴 코앞 손님을 이어 기다릴 때만 쓴다(ToF만으로 기다리기를 시작하지 않음)
- 비켜서기(R6): /pull_over/available·/pull_over/done (R6가 붙기 전에는 아무도 안 내므로 늘 거짓)
라이다 점은 넣지 않는다. 사람인지 모르는 장애물 신호라 Nav2(costmap·collision_monitor) 몫이다.
BT 조건 IsWaitingForPerson이 /person_wait의 wait만 본다.
"""

import math
import time

from builtin_interfaces.msg import Time as TimeMsg
from limbo_interfaces.msg import PersonPredictionArray, PersonWait as PersonWaitMsg
from limbo_perception import geometry, person_wait
from nav_msgs.msg import OccupancyGrid
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformException, TransformListener

TICK_SEC = 0.1   # 10 Hz. 사람 걸음(1 m/s)으로 0.1 m, release_sec 0.5 s보다 충분히 잘다


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


def stamp_of(t):
    sec = int(math.floor(t))
    return TimeMsg(sec=sec, nanosec=int((t - sec) * 1e9))


class PersonWaitNode(Node):

    def __init__(self):
        super().__init__('person_wait')
        p = self.declare_parameter
        self.machine = person_wait.PersonWait(person_wait.WaitConfig(
            robot_half_width=p('robot_half_width', 0.30).value,
            person_radius=p('person_radius', 0.25).value,
            zone_length=p('zone_length', 1.5).value,
            zone_exit_margin=p('zone_exit_margin', 0.2).value,
            approach_range=p('approach_range', 3.0).value,
            cpa_radius=p('cpa_radius', 0.6).value,
            min_speed=p('min_speed', 0.2).value,
            moving_speed=p('moving_speed', 0.3).value,
            moving_hold_sec=p('moving_hold_sec', 1.0).value,
            release_sec=p('release_sec', 0.5).value,
            service_sec=p('service_sec', 15.0).value,
            alarm_period_sec=p('alarm_period_sec', 30.0).value,
            recent_track_sec=p('recent_track_sec', 3.0).value,
            track_lost_range=p('track_lost_range', 1.0).value))
        self.base_frame = p('base_frame', 'base_link').value
        self.map_frame = p('map_frame', 'map').value
        self.bumper_frame = p('bumper_frame', 'tof_link').value
        self.bumper_x = p('bumper_x', 0.25).value
        self.bumper_from_tf = False
        self.ready_hold_sec = p('ready_hold_sec', 2.0).value
        self.tracks_timeout_sec = p('tracks_timeout_sec', 0.5).value
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.map_received = False
        self.tf_ok_since = None       # map→base_link가 끊김 없이 조회되기 시작한 벽시계
        self.tracks = []
        self.tracks_wall = None       # 마지막 트랙 메시지를 받은 벽시계
        self.clock = None             # (메시지 시각, 받은 벽시계): 상태 기계 시각의 기준
        self.last_t = None
        self.tof = (False, None)       # (/tof/obstacle_ahead, 받은 벽시계)
        self.pull_over_available = False
        self.pull_over_done = False
        self.logged = 0
        self.pub = self.create_publisher(PersonWaitMsg, '/person_wait', 10)
        self._subscribe(p)
        self.create_timer(TICK_SEC, self.on_tick)

    def _subscribe(self, p):
        self.create_subscription(
            OccupancyGrid, p('map_topic', '/map').value, self.on_map,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                       reliability=ReliabilityPolicy.RELIABLE))
        self.create_subscription(
            PersonPredictionArray, p('predictions_topic', '/person_detector/predictions').value,
            self.on_predictions, 10)
        self.create_subscription(
            Bool, p('tof_topic', '/tof/obstacle_ahead').value, self.on_tof, 10)
        self.create_subscription(Bool, '/pull_over/available', self.on_pull_over_available, 10)
        self.create_subscription(Bool, '/pull_over/done', self.on_pull_over_done, 10)

    def on_map(self, msg):
        if not self.map_received:
            self.get_logger().info(f'map {msg.info.width}x{msg.info.height} received')
        self.map_received = True

    def on_tof(self, msg):
        self.tof = (msg.data, time.monotonic())

    def on_pull_over_available(self, msg):
        self.pull_over_available = msg.data

    def on_pull_over_done(self, msg):
        self.pull_over_done = msg.data

    def on_predictions(self, msg):
        # 예측은 카메라 사진 시각의 odom 기준. 로봇 자세는 최신 TF로 충분하다(틱 0.1 s 안의 회전은 작다)
        try:
            pose = self.tf_buffer.lookup_transform(msg.header.frame_id, self.base_frame, Time())
        except TransformException:
            return
        people = [(q.current_position.x, q.current_position.y, q.velocity.x, q.velocity.y)
                  for q in msg.predictions]
        offset = pose.transform.translation
        self.tracks = geometry.tracks_ahead_of_bumper(
            people, offset.x, offset.y, yaw_of(pose.transform.rotation), self.bumper_x)
        wall = time.monotonic()
        self.tracks_wall = wall
        self.clock = (seconds(msg.header.stamp), wall)

    def now(self, wall):
        """
        상태 기계 시각 = 마지막 트랙 메시지 시각 + 그 뒤 지난 벽시계. 뒤로 가지 않게 한다.

        모든 시각을 카메라 메시지에서 가져와 /clock 구독(use_sim_time)이 필요 없다(person_detector와 같은 이유).
        """
        stamp, received = self.clock
        t = stamp + (wall - received)
        self.last_t = t if self.last_t is None else max(self.last_t, t)
        return self.last_t

    def is_ready(self, wall):
        try:
            self.tf_buffer.lookup_transform(self.map_frame, self.base_frame, Time())
            if self.tf_ok_since is None:
                self.tf_ok_since = wall
        except TransformException:
            self.tf_ok_since = None
        return (self.map_received and self.clock is not None and self.tf_ok_since is not None and
                wall - self.tf_ok_since >= self.ready_hold_sec)

    def resolve_bumper(self):
        """범퍼(ToF 링크) x를 TF에서 한 번 읽는다. 없으면 파라미터 bumper_x."""
        if self.bumper_from_tf or not self.bumper_frame:
            return
        try:
            t = self.tf_buffer.lookup_transform(self.base_frame, self.bumper_frame, Time())
        except TransformException:
            return
        self.bumper_x, self.bumper_from_tf = t.transform.translation.x, True
        self.get_logger().info(
            f'zone starts at bumper x {self.bumper_x:.3f} m ({self.bumper_frame})')

    def on_tick(self):
        self.resolve_bumper()
        wall = time.monotonic()
        if self.clock is None:
            return   # 트랙 공급자(카메라)가 아직 없음: 시각 기준도 없다
        ready = self.is_ready(wall)
        fresh = self.tracks_wall is not None and wall - self.tracks_wall <= self.tracks_timeout_sec
        tracks = self.tracks if fresh else []
        t = self.now(wall)
        tof_blocked, tof_wall = self.tof
        tof_fresh = tof_wall is not None and wall - tof_wall <= self.tracks_timeout_sec
        tof_blocked = tof_blocked and tof_fresh
        status = self.machine.on_tick(
            t, tracks, ready, self.pull_over_available, self.pull_over_done, tof_blocked)
        self.log_changes(status, tracks)
        self.publish(t, status)

    def log_changes(self, status, tracks):
        """전이마다 INFO 한 줄, 경보 틱마다 WARN 한 줄. "왜 멈췄나/갔나"가 이 줄로 설명되게 한다."""
        for change in self.machine.transitions[self.logged:]:
            self.get_logger().info(
                f'{change.to_state} ← {change.from_state}: {change.reason}, '
                f'tracks {len(tracks)} (zone {status.tracks_in_zone}){nearest_text(tracks)}')
        self.logged = len(self.machine.transitions)
        if status.alarm:
            self.get_logger().warn(
                f'{status.state} alarm: {status.reason}, tracks {status.tracks_in_zone}, '
                f'stationary {status.stationary_sec:.1f} s, waiting {status.elapsed_sec:.1f} s'
                f'{nearest_text(tracks)}')

    def publish(self, t, status):
        msg = PersonWaitMsg()
        msg.header.stamp = stamp_of(t)
        msg.header.frame_id = self.base_frame
        msg.state, msg.wait, msg.reason = status.state, status.wait, status.reason
        msg.tracks_in_zone = status.tracks_in_zone
        msg.elapsed_sec = float(status.elapsed_sec)
        msg.stationary_sec = float(status.stationary_sec)
        msg.alarm, msg.abort_pull_over = status.alarm, status.abort_pull_over
        self.pub.publish(msg)


def nearest_text(tracks):
    """가장 가까운 트랙의 범퍼 앞 위치·속도 (로그용)."""
    if not tracks:
        return ''
    x, y, vx, vy = min(tracks, key=lambda track: math.hypot(track[0], track[1]))
    return f', nearest x {x:.2f} y {y:.2f} v ({vx:.2f}, {vy:.2f})'


def main(args=None):
    rclpy.init(args=args)
    node = PersonWaitNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
