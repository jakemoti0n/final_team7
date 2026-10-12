"""Single-process state; all mutations run on the application's event loop."""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import time
import uuid

from .models import Settings, Telemetry

NAMES = {"odom": "주행 정보", "lidar_raw": "LiDAR 원본",
         "lidar_filtered": "LiDAR 필터 결과", "camera_raw": "카메라 원본"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, settings: Settings, monotonic=time.monotonic, utc=utc_now):
        self.settings, self.monotonic, self.utc = settings, monotonic, utc
        self.run_id = str(uuid.uuid4())
        self.started = monotonic()
        self.session_started = self.started
        self.received_mono = self.received_at = self.payload = None
        self.session = None
        self.sequence = 0
        self.retired = deque(maxlen=100)
        self.last_motion = None
        self.last_motion_mono = None
        self.alerts = deque(maxlen=settings.alert_limit)
        self.active = {}
        self.revision = 0
        self.was_connected = False

    def accept(self, payload: Telemetry):
        session, sequence = payload.bridge_session_id, payload.sequence
        reply = dict(accepted=False, bridge_session_id=session, sequence=sequence)
        if session in self.retired:
            return {**reply, "reason": "retired_session"}
        if session == self.session and sequence <= self.sequence:
            return {**reply, "reason": "duplicate_or_out_of_order"}
        if session != self.session:
            if self.session:
                self.retired.append(self.session)
            for key in list(self.active):
                if key.startswith("topic:"):
                    self.close(key)  # Session replacement is not reception recovery.
            self.last_motion = self.last_motion_mono = None
            self.session_started = self.monotonic()
        self.session, self.sequence = session, sequence
        self.payload = payload.model_dump()
        self.received_mono, self.received_at = self.monotonic(), self.utc()
        if payload.motion.age_ms is not None:
            self.last_motion = self.payload["motion"].copy()
            self.last_motion_mono = self.received_mono
        return {**reply, "accepted": True, "server_received_at": self.received_at}

    def add(self, key, severity, message, kind, active=False):
        alert = dict(id=str(uuid.uuid4()), key=key, at=self.utc(), severity=severity,
                     message=message, kind=kind, active=active)
        self.alerts.appendleft(alert)
        if active:
            self.active[key] = alert

    def problem(self, key, severity, message):
        if key in self.active:
            self.active[key].update(severity=severity, message=message)
        else:
            self.add(key, severity, message, "problem", True)

    def close(self, key, recovery=None):
        previous = self.active.pop(key, None)
        if previous:
            previous["active"] = False
            if recovery:
                self.add(key, "info", recovery, "recovery")

    def snapshot(self):
        now = self.monotonic()
        elapsed = max(0., now - (self.received_mono if self.received_mono is not None else self.started))
        cfg = self.settings
        if elapsed >= cfg.bridge_disconnect_s:
            connection = "disconnected"
        elif self.payload is None:
            connection = "checking"
        elif elapsed >= cfg.bridge_delay_s:
            connection = "delayed"
        else:
            connection = "connected"
        if connection in ("delayed", "disconnected"):
            self.problem("bridge", "error" if connection == "disconnected" else "warning",
                         "상태 전달 프로그램 연결 끊김" if connection == "disconnected" else "상태 전달 정보 수신 지연")
        elif connection == "connected":
            self.close("bridge", "상태 전달 프로그램 연결 복구")
            if not self.was_connected:
                self.add("connected", "info", "상태 전달 프로그램 연결됨", "connection")
                self.was_connected = True
        uncertain = connection in ("delayed", "disconnected")
        topics = {}
        for key, name in NAMES.items():
            raw = self.payload["topics"][key] if self.payload else None
            seen = bool(raw and raw["received_count"])
            age = max(0., raw["age_ms"] / 1000 + elapsed) if seen else None
            threshold = getattr(cfg.topic_delay_s, key)
            status = "unknown" if uncertain else "never_received" if not seen else "delayed" if age >= threshold else "receiving"
            topics[key] = dict(status=status, last_received_at=raw["last_received_at"] if seen else None,
                               age_s=age, received_count=raw["received_count"] if raw else 0,
                               receive_hz=raw["receive_hz"] if status == "receiving" else None,
                               last_receive_hz=raw["receive_hz"] if raw else None)
            if connection == "connected":
                problem_key = f"topic:{key}"
                if status == "delayed" or (not seen and now - self.session_started >= threshold):
                    self.problem(problem_key, "warning", f"{name} {'수신 지연' if seen else '미수신'}")
                elif status == "receiving":
                    self.close(problem_key, f"{name} 수신 재개")
        motion = self.payload["motion"] if self.payload else None
        motion_age = motion["age_ms"] / 1000 + elapsed if motion and motion["age_ms"] is not None else None
        fresh = not uncertain and motion_age is not None and motion_age < cfg.topic_delay_s.odom
        rotating = False
        if fresh:
            linear, angular = motion["linear_speed_mps"], abs(motion["angular_velocity_radps"])
            moving = linear >= cfg.linear_threshold_mps or angular >= cfg.angular_threshold_radps
            rotating = linear < cfg.linear_threshold_mps and angular >= cfg.angular_threshold_radps
            movement = "moving" if moving else "stopped"
        else:
            movement = "unknown" if uncertain or self.last_motion or (self.payload and self.payload["topics"]["odom"]["received_count"]) else "unconfirmed"
        retained = None
        if self.last_motion:
            retained = {**self.last_motion, "age_s": self.last_motion["age_ms"] / 1000 + max(0., now-self.last_motion_mono)}
        self.revision += 1
        return dict(server_run_id=self.run_id, revision=self.revision, server_utc=self.utc(),
                    robot_id=cfg.robot_id, bridge=dict(status=connection, last_received_at=self.received_at,
                    age_s=elapsed if self.received_mono is not None else None,
                    session_id=self.session, sequence=self.sequence), topics=topics,
                    motion=dict(status=movement, rotating=rotating, current=motion if fresh else None,
                                age_s=motion_age, last_valid=retained),
                    alerts=deepcopy(list(self.alerts)), settings=cfg.model_dump())
