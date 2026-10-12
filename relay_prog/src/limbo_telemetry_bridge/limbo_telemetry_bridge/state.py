"""Bounded numeric state. No ROS message or data buffer is retained."""
from collections import deque
from datetime import datetime, timezone
import math
import threading
import time
import uuid

TOPICS = ('odom', 'lidar_raw', 'lidar_filtered', 'camera_raw')


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
        return dict(
            schema_version=1, robot_id=self.robot_id, bridge_session_id=self.session_id,
            sequence=sequence, sent_at=sent_at, source_clock=self.source_clock, topics=result,
            motion=dict(linear_speed_mps=None if motion is None else motion[0],
                        angular_velocity_radps=None if motion is None else motion[1],
                        last_received_at=None if motion is None else motion[2],
                        age_ms=None if motion is None else max(0.0, (now-motion[3])*1000)),
        )
