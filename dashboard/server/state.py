"""Single-process state; all mutations run on the application's event loop."""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import time
import uuid

from .models import Settings, Telemetry

NAMES = {"odom": "주행 정보", "lidar_raw": "LiDAR 원본",
         "lidar_filtered": "LiDAR 필터 결과", "camera_raw": "카메라 원본"}

# 관제 명령 단계 (docs/CONTROL_API_DRAFT.md §3). FINAL에 들어가면 결과가 바뀌지 않는다
FINAL = {"confirmed", "rejected", "service_unavailable", "no_response", "expired", "unconfirmed",
         "connection_lost"}
COMMAND_TEXT = {"pause": "정지", "resume": "재개"}
RESULT_TEXT = {  # (알림 중요도, 문구)
    "confirmed": ("info", "{c} 상태 확인됨"),
    "rejected": ("error", "{c} 요청 실패: {m}"),
    "service_unavailable": ("error", "{c} 요청 실패: 순찰 노드가 응답할 수 없음"),
    "no_response": ("warning", "{c} 여부 확인 불가: 로봇 응답 없음"),
    "expired": ("warning", "{c} 여부 확인 불가: 요청이 로봇에 전달되지 않음"),
    "unconfirmed": ("warning", "{c} 여부 확인 불가: 응답 후 상태 확인 없음"),
    "connection_lost": ("warning", "{c} 여부 확인 불가: 처리 중 연결 끊김"),
}


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
        self.command = None          # 마지막 명령 하나 (다음 명령 전까지 유지)
        self.map_available = False   # 앱이 지도 파일을 읽으면 True

    # ---- 연결 판정 (snapshot과 명령 접수에서 같이 씀) ----

    def connection(self, now=None):
        now = self.monotonic() if now is None else now
        elapsed = max(0., now - (self.received_mono if self.received_mono is not None else self.started))
        cfg = self.settings
        if elapsed >= cfg.bridge_disconnect_s:
            return "disconnected", elapsed
        if self.payload is None:
            return "checking", elapsed
        if elapsed >= cfg.bridge_delay_s:
            return "delayed", elapsed
        return "connected", elapsed

    # ---- 관제 명령 ----

    def issue(self, command):
        """화면의 명령 요청. (HTTP 상태, 본문)"""
        if self.command and self.command["stage"] not in FINAL:
            return 409, ("command_in_progress", "Another command is still in progress")
        if self.connection()[0] != "connected":
            return 409, ("bridge_not_connected", "Bridge is not connected")
        now = self.monotonic()
        self.command = dict(request_id=str(uuid.uuid4()), command=command, stage="queued", message="",
                            issued_at=self.utc(), updated_at=self.utc(), issued_mono=now,
                            delivered_mono=None, claimed_mono=None, accepted_mono=None, session=self.session,
                            count_at_call=None)
        return 202, self.command_view()

    def take_command(self, session):
        """Bridge의 commands/next. 현재 세션에만, 한 번만 내준다."""
        self.tick()
        c = self.command
        if not c or c["stage"] != "queued" or session != self.session or session != c["session"]:
            return None
        now = self.monotonic()
        remaining = c["issued_mono"] + self.settings.command_ttl_s - now
        if remaining <= 0:
            self.finish("expired")
            return None
        c.update(stage="delivered", delivered_mono=now, updated_at=self.utc())
        return dict(request_id=c["request_id"], command=c["command"], ttl_ms=remaining * 1000)

    def claim(self, request_id, session):
        """Bridge가 서비스를 부르기 직전에 묻는다. 아직 전달됨 단계이고 응답 제한 안이면 허락.
        허락하면 응답 제한을 이 시각부터 다시 센다 (늦게 읽은 명령이 '응답 없음' 뒤에 실행되지 않게)."""
        self.tick()
        c = self.command
        if (not c or c["request_id"] != request_id or c["stage"] != "delivered"
                or c["claimed_mono"] is not None or session != c["session"]):
            return False
        c["claimed_mono"] = self.monotonic()
        return True

    def apply_result(self, result):
        """Bridge의 결과 보고. 끝난 명령·모르는 명령의 늦은 보고는 결과를 바꾸지 않는다."""
        self.tick()
        c = self.command
        if (not c or c["request_id"] != result.request_id or c["stage"] != "delivered"
                or result.bridge_session_id != c["session"]):
            return {"accepted": False, "reason": "command_closed"}
        c["message"] = result.message
        if result.outcome == "accepted":
            c.update(stage="accepted", accepted_mono=self.monotonic(), updated_at=self.utc(),
                     count_at_call=result.patrol_update_count_at_call)
            self.check_confirmation()
        else:
            self.finish(result.outcome)
        return {"accepted": True}

    def check_confirmation(self):
        """명령 이후 상태인지는 Bridge가 센 순찰 상태 수신 횟수로 본다 (시각 비교 안 함)."""
        c, p = self.command, self.payload
        if not c or c["stage"] != "accepted" or not p or p["bridge_session_id"] != c["session"]:
            return
        patrol = p.get("patrol")
        if not patrol or patrol["update_count"] <= c["count_at_call"]:
            return
        if c["command"] == "resume" and patrol["state"] == "patrolling":
            self.finish("confirmed")
        elif c["command"] == "pause" and patrol["state"] == "paused":
            motion, cfg = p["motion"], self.settings
            if (motion["age_ms"] is not None and motion["age_ms"] / 1000 < cfg.topic_delay_s.odom
                    and motion["linear_speed_mps"] < cfg.linear_threshold_mps
                    and abs(motion["angular_velocity_radps"]) < cfg.angular_threshold_radps):
                self.finish("confirmed")

    def tick(self, now=None):
        """시간 초과·연결 끊김으로 명령을 마감한다."""
        c = self.command
        if not c or c["stage"] in FINAL:
            return
        now = self.monotonic() if now is None else now
        cfg = self.settings
        if c["stage"] in ("delivered", "accepted") and (
                self.session != c["session"] or self.connection(now)[0] == "disconnected"):
            self.finish("connection_lost")
        elif c["stage"] == "queued" and now - c["issued_mono"] >= cfg.command_ttl_s:
            self.finish("expired")
        elif c["stage"] == "delivered" and now - (c["claimed_mono"] or c["delivered_mono"]) >= cfg.command_response_timeout_s:
            self.finish("no_response")
        elif c["stage"] == "accepted" and now - c["accepted_mono"] >= cfg.command_confirm_timeout_s:
            self.finish("unconfirmed")

    def finish(self, stage):
        c = self.command
        c.update(stage=stage, updated_at=self.utc())
        severity, text = RESULT_TEXT[stage]
        self.add(f"command:{c['request_id']}", severity,
                 text.format(c=COMMAND_TEXT[c["command"]], m=c["message"] or "사유 없음"), "control")

    def command_view(self):
        c = self.command
        if not c:
            return None
        return {k: c[k] for k in ("request_id", "command", "stage", "message", "issued_at", "updated_at")}

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
        self.check_confirmation()
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
        cfg = self.settings
        connection, elapsed = self.connection(now)
        self.tick(now)
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
        def aged(key):
            # v2 patrol·pose에 서버 경과 시간을 더한다 (v1이면 None)
            value = self.payload.get(key) if self.payload else None
            if value is None:
                return None
            age = value["age_ms"] / 1000 + elapsed if value["age_ms"] is not None else None
            return {**value, "age_s": age}
        pose = aged("pose")
        if pose is not None:
            pose["stale"] = uncertain or pose["age_s"] is None or pose["age_s"] >= cfg.topic_delay_s.odom
        self.revision += 1
        return dict(server_run_id=self.run_id, revision=self.revision, server_utc=self.utc(),
                    robot_id=cfg.robot_id, bridge=dict(status=connection, last_received_at=self.received_at,
                    age_s=elapsed if self.received_mono is not None else None,
                    session_id=self.session, sequence=self.sequence), topics=topics,
                    motion=dict(status=movement, rotating=rotating, current=motion if fresh else None,
                                age_s=motion_age, last_valid=retained),
                    alerts=deepcopy(list(self.alerts)), settings=cfg.model_dump(),
                    patrol=aged("patrol"), pose=pose, command=self.command_view(),
                    map_available=self.map_available)
