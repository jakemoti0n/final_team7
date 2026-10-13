"""Bounded numeric state. No ROS message or data buffer is retained."""
from collections import deque
from datetime import datetime, timezone
import math
import threading
import time
import uuid

TOPICS = ('odom', 'lidar_raw', 'lidar_filtered', 'camera_raw')
SCHEMA_VERSION = 2
PATROL_STATES = ('waiting_localization', 'patrolling', 'pausing', 'paused', 'completed', 'failed')
REASON_LIMIT = 200


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class State:
    def __init__(self, robot_id='LIMBO-01', source_clock='ros_sim',
                 monotonic=time.monotonic, utc=utc_now):
        self.robot_id, self.source_clock = robot_id, source_clock
        self.monotonic, self.utc = monotonic, utc
        self.started = monotonic()
        self.session_id = str(uuid.uuid4())
        self.lock = threading.Lock()
        self.sequence = 0
        self.motion = None
        self.topics = {key: dict(count=0, stamp=None, at=None, mono=None,
                                 buckets=deque(maxlen=51)) for key in TOPICS}
        # v2: 순찰 상태(/patrol/state)와 위치(/amcl_pose). 숫자·짧은 문자열만 보관한다
        self.patrol = dict(count=0, fields=None, at=None, mono=None, alive=True)
        self.pose = None

    def patrol_publisher(self, alive):
        """/patrol/state 발행자(순찰 노드)가 있는지. 없으면 마지막 상태 대신 "알 수 없음"으로 보낸다
        (순찰 노드가 꺼졌는데 화면이 "순찰 중"으로 남지 않게, 2026-10-13 실패 시험 문제 2)."""
        with self.lock:
            self.patrol['alive'] = bool(alive)

    def receive_patrol(self, state, waypoint_index, waypoint_count, waypoint_name,
                       has_resumable_task, reason):
        with self.lock:
            fields = None
            if (state in PATROL_STATES and type(waypoint_index) is int and waypoint_index >= 0
                    and type(waypoint_count) is int and waypoint_count >= 0
                    and isinstance(waypoint_name, str) and type(has_resumable_task) is bool
                    and isinstance(reason, str)):
                fields = dict(state=state, waypoint_index=waypoint_index, waypoint_count=waypoint_count,
                              waypoint_name=waypoint_name[:REASON_LIMIT],
                              has_resumable_task=has_resumable_task, reason=reason[:REASON_LIMIT])
            # 알 수 없는 상태도 수신 횟수는 센다 (명령 이후 상태 판정은 횟수로 하므로)
            self.patrol.update(count=self.patrol['count'] + 1, fields=fields,
                               at=self.utc(), mono=self.monotonic())

    def patrol_update_count(self):
        with self.lock:
            return self.patrol['count']

    def receive_pose(self, frame_id, x, y, yaw, position_std_m):
        with self.lock:
            now, at = self.monotonic(), self.utc()
            values = (x, y, yaw, position_std_m)
            if (isinstance(frame_id, str) and frame_id
                    and all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
                    and position_std_m >= 0):
                self.pose = (frame_id, float(x), float(y), float(yaw), float(position_std_m), at, now)
            else:
                self.pose = None

    def receive(self, key, sec, nanosec, velocity=None):
        # Only scalar arguments cross the ROS adapter boundary.
        with self.lock:
            now, at = self.monotonic(), self.utc()
            topic = self.topics[key]
            topic.update(count=topic['count'] + 1, stamp=(sec, nanosec), at=at, mono=now)
            bucket = math.floor(now * 10)
            history = topic['buckets']
            if history and history[-1][0] == bucket:
                history[-1] = (bucket, history[-1][1] + 1)
            else:
                history.append((bucket, 1))
            if key == 'odom':
                self.motion = None
                if velocity is not None and all(math.isfinite(v) for v in velocity):
                    x, y, angular = velocity
                    speed = math.hypot(x, y)
                    if math.isfinite(speed):
                        self.motion = (speed, angular, at, now)

    def snapshot(self):
        with self.lock:
            now, sent_at = self.monotonic(), self.utc()
            self.sequence += 1
            sequence = self.sequence
            # Copy only bounded numeric state; JSON and networking happen after unlock.
            topics = {k: {**v, 'buckets': tuple(v['buckets'])} for k, v in self.topics.items()}
            motion = self.motion
            patrol, pose = dict(self.patrol), self.pose
        result = {}
        bucket = math.floor(now * 10)
        for key, topic in topics.items():
            stamp = topic['stamp']
            result[key] = dict(
                header_stamp=None if stamp is None else dict(sec=stamp[0], nanosec=stamp[1]),
                last_received_at=topic['at'],
                age_ms=None if topic['mono'] is None else max(0.0, (now-topic['mono'])*1000),
                received_count=topic['count'],
                receive_hz=None if not topic['count'] or now-self.started < 5 else
                sum(n for b, n in topic['buckets'] if bucket-50 < b <= bucket)/5.0,
            )
        patrol_fields = (patrol['alive'] and patrol['fields']) or dict.fromkeys(
            ('state', 'waypoint_index', 'waypoint_count', 'waypoint_name', 'has_resumable_task', 'reason'))
        return dict(
            schema_version=SCHEMA_VERSION, robot_id=self.robot_id, bridge_session_id=self.session_id,
            sequence=sequence, sent_at=sent_at, source_clock=self.source_clock, topics=result,
            motion=dict(linear_speed_mps=None if motion is None else motion[0],
                        angular_velocity_radps=None if motion is None else motion[1],
                        last_received_at=None if motion is None else motion[2],
                        age_ms=None if motion is None else max(0.0, (now-motion[3])*1000)),
            patrol=dict(**patrol_fields, update_count=patrol['count'],
                        last_received_at=patrol['at'],
                        age_ms=None if patrol['mono'] is None else max(0.0, (now-patrol['mono'])*1000)),
            pose=dict(frame_id=None if pose is None else pose[0],
                      x=None if pose is None else pose[1],
                      y=None if pose is None else pose[2],
                      yaw=None if pose is None else pose[3],
                      position_std_m=None if pose is None else pose[4],
                      last_received_at=None if pose is None else pose[5],
                      age_ms=None if pose is None else max(0.0, (now-pose[6])*1000)),
        )
