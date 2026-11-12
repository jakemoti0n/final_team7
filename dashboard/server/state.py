"""단일 프로세스 상태. 로봇마다 Store 하나이고, 모든 변경은 앱의 이벤트 루프에서만 일어난다."""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import re
import time
import uuid

from .models import Settings, Telemetry

NAMES = {"odom": "주행 정보", "lidar_raw": "LiDAR 원본",
         "lidar_filtered": "LiDAR 필터 결과", "camera_raw": "카메라 원본"}

# 관제 명령 단계 (docs/CONTROL_API_DRAFT.md §3). FINAL에 들어가면 결과가 바뀌지 않는다
FINAL = {"confirmed", "rejected", "service_unavailable", "no_response", "expired", "unconfirmed",
         "connection_lost"}
COMMAND_TEXT = {"pause": "정지", "resume": "재개", "start": "순찰 시작", "stop": "순찰 종료"}
ACTIVE_PATROL = ("waiting_localization", "patrolling", "pausing", "paused")
RESULT_TEXT = {  # (알림 중요도, 문구)
    "confirmed": ("info", "{c} 상태 확인됨"),
    "rejected": ("error", "{c} 요청 실패: {m}"),
    "service_unavailable": ("error", "{c} 요청 실패: 순찰 노드가 응답할 수 없음"),
    "no_response": ("warning", "{c} 여부 확인 불가: 로봇 응답 없음"),
    "expired": ("warning", "{c} 요청 실패: 로봇에 제때 전달되지 않아 실행 안 함"),
    "unconfirmed": ("warning", "{c} 여부 확인 불가: 응답 후 상태 확인 없음"),
    "connection_lost": ("warning", "{c} 여부 확인 불가: 처리 중 연결 끊김"),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, settings: Settings, monotonic=time.monotonic, utc=utc_now, robot_id=None):
        self.settings, self.monotonic, self.utc = settings, monotonic, utc
        self.robot_id = robot_id or settings.robot_id
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
        self.patrol_seen = None      # 마지막으로 알림을 판단한 (상태, 사유)
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

    # ---- Bridge가 띄운 순찰 노드 (텔레메트리 v3 launcher) ----

    def launcher(self):
        """연결된 Bridge가 보고한 순찰 노드 실행 상태. v1·v2 Bridge면 None (시작·종료 미지원)"""
        return (self.payload or {}).get("launcher")

    def patrol_running(self):
        """순찰 노드가 돌고 있다고 볼 근거가 있는가 (시작 거절·waypoint 편집 잠금).

        Bridge가 띄운 노드가 실행 중이거나 다른 곳에서 띄운 노드가 있으면 참.
        순찰 상태가 활성이어도 Bridge가 띄운 노드가 끝났다고 보고했으면(오래된 상태) 거짓."""
        launcher = self.launcher()
        patrol = (self.payload or {}).get("patrol") or {}
        if launcher and (launcher["state"] == "running" or launcher["other_patrol_running"]):
            return True
        return patrol.get("state") in ACTIVE_PATROL and not (launcher and launcher["state"] == "exited")

    def timeouts(self, command):
        """(응답 제한, 확인 제한). 시작·종료는 노드 기동·Nav2 목표 취소를 기다리므로 따로 둔다."""
        cfg = self.settings
        if command == "start":
            return cfg.command_start_response_timeout_s, cfg.command_start_confirm_timeout_s
        if command == "stop":
            return cfg.command_stop_response_timeout_s, cfg.command_stop_confirm_timeout_s
        return cfg.command_response_timeout_s, cfg.command_confirm_timeout_s

    def issue(self, command, route=None, issued_by=None):
        """화면의 명령 요청. (HTTP 상태, 본문). route는 start일 때 Bridge에 실어 보낼 waypoint 경로,
        issued_by는 요청한 사용자 아이디 (로그인 없이 연 로컬 개발이면 None)"""
        if self.command and self.command["stage"] not in FINAL:
            return 409, ("command_in_progress", "Another command is still in progress")
        if self.connection()[0] != "connected":
            return 409, ("bridge_not_connected", "Bridge is not connected")
        now = self.monotonic()
        self.command = dict(request_id=str(uuid.uuid4()), command=command, stage="queued", message="",
                            issued_at=self.utc(), updated_at=self.utc(), issued_mono=now,
                            delivered_mono=None, claimed_mono=None, accepted_mono=None, session=self.session,
                            count_at_call=None, route=route, accepted_launcher=None,
                            accepted_patrol_state=None, issued_by=issued_by)
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
        command = dict(request_id=c["request_id"], command=c["command"], ttl_ms=remaining * 1000)
        if c["command"] == "start":
            command["route"] = c["route"]
        return command

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
            launcher = self.launcher() or {}
            c.update(stage="accepted", accepted_mono=self.monotonic(), updated_at=self.utc(),
                     count_at_call=result.patrol_update_count_at_call,
                     # 수락 시점의 마지막 보고. 이보다 먼저 찍힌 텔레메트리가 늦게 와도 새 결과로 보지 않게
                     accepted_launcher=(launcher.get("state"), launcher.get("pid")),
                     accepted_patrol_state=((self.payload or {}).get("patrol") or {}).get("state"))
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
        launcher = p.get("launcher") or {}
        if c["command"] == "stop":
            # 노드 종료 보고, 또는 수락 때 있던 순찰 상태가 사라짐(/patrol/state 발행자 없음)
            if launcher.get("state") == "exited" or (
                    c["accepted_patrol_state"] is not None and patrol and patrol["update_count"]
                    and patrol["state"] is None):
                self.finish("confirmed")
            return
        if (c["command"] == "start" and launcher.get("state") == "exited"
                and c["accepted_launcher"] != ("exited", launcher.get("pid"))):
            # 새로 띄운 노드가 순찰 상태를 내기 전에 끝남. 수락 때 이미 끝나 있던 이전 실행(같은 pid)은 제외
            c["message"] = f"patrol_node exited (code {launcher.get('exit_code')}), log: {launcher.get('log') or '-'}"[:200]
            self.finish("rejected")
            return
        if not patrol or patrol["update_count"] <= c["count_at_call"]:
            return
        if c["command"] == "start" and patrol["state"] in ("waiting_localization", "patrolling"):
            self.finish("confirmed")
        elif c["command"] == "resume" and patrol["state"] == "patrolling":
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
        response_timeout, confirm_timeout = self.timeouts(c["command"])
        if c["stage"] in ("delivered", "accepted") and (
                self.session != c["session"] or self.connection(now)[0] == "disconnected"):
            self.finish("connection_lost")
        elif c["stage"] == "queued" and now - c["issued_mono"] >= cfg.command_ttl_s:
            self.finish("expired")
        elif c["stage"] == "delivered" and now - (c["claimed_mono"] or c["delivered_mono"]) >= response_timeout:
            self.finish("no_response")
        elif c["stage"] == "accepted" and now - c["accepted_mono"] >= confirm_timeout:
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
        view = {k: c[k] for k in ("request_id", "command", "stage", "message", "issued_at", "updated_at", "issued_by")}
        view["age_s"] = max(0., self.monotonic() - c["issued_mono"])  # 화면이 브라우저 시계와 비교하지 않게
        return view

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
                    self.close(key)  # 세션이 바뀐 것은 수신 복구가 아니다
            self.last_motion = self.last_motion_mono = None
            self.session_started = self.monotonic()
        self.session, self.sequence = session, sequence
        self.payload = payload.model_dump()
        self.received_mono, self.received_at = self.monotonic(), self.utc()
        if payload.motion.age_ms is not None:
            self.last_motion = self.payload["motion"].copy()
            self.last_motion_mono = self.received_mono
        self.check_confirmation()
        self.check_patrol()
        return {**reply, "accepted": True, "server_received_at": self.received_at}

    def check_patrol(self):
        """순찰 노드가 사유로 알리는 이동 실패를 알림으로 (docs/CONTROL_SCREEN.md A 4단계).

        순찰 카드 문구만 바뀌면 알림만 보는 사람은 로봇이 멈춘 걸 모른다.
        """
        patrol = (self.payload or {}).get("patrol") or {}
        state, reason = patrol.get("state"), patrol.get("reason") or ""
        if (state, reason) == self.patrol_seen:
            return
        self.patrol_seen = (state, reason)
        target = patrol.get("waypoint_name") or "—"
        retry = re.fullmatch(r"navigation failed, retry (\d+/\d+)", reason)
        if state == "patrolling" and retry:
            self.add("patrol:retry", "info", f"이동이 막혀 다시 시도합니다 ({retry[1]}, 다음 목표 {target})", "patrol")
        elif state == "paused" and reason == "navigation failed":
            self.problem("patrol:stopped", "warning",
                         f"순찰이 멈췄습니다: 이동 실패 (다음 목표 {target}). 확인 후 재개해 주세요")
        elif state == "failed":
            self.problem("patrol:failed", "error", f"순찰 실패: {reason or '사유 없음'}")
        elif state == "patrolling":
            self.close("patrol:stopped", "이동 실패로 멈췄던 순찰을 다시 진행합니다")
            self.close("patrol:failed", "순찰을 다시 시작했습니다")

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

    def pose_view(self):
        """다른 로봇 화면의 지도에 그릴 위치만. snapshot과 같은 기준으로 오래됨을 판정하되 알림·revision은 건드리지 않는다"""
        connection, elapsed = self.connection()
        pose = (self.payload or {}).get("pose")
        if not pose or pose["x"] is None or pose["y"] is None or pose["yaw"] is None:
            return None
        age = pose["age_ms"] / 1000 + elapsed if pose["age_ms"] is not None else None
        stale = connection in ("delayed", "disconnected") or age is None or age >= self.settings.topic_delay_s.odom
        return dict(x=pose["x"], y=pose["y"], yaw=pose["yaw"], age_s=age, stale=stale)

    def snapshot(self):
        now = self.monotonic()
        cfg = self.settings
        connection, elapsed = self.connection(now)
        self.tick(now)
        if connection in ("delayed", "disconnected"):
            self.problem("bridge", "error" if connection == "disconnected" else "warning",
                         "로봇 연결 끊김" if connection == "disconnected" else "로봇 상태 수신 지연")
        elif connection == "connected":
            self.close("bridge", "로봇 연결 복구")
            if not self.was_connected:
                self.add("connected", "info", "로봇 연결됨", "connection")
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
                    robot_id=self.robot_id, bridge=dict(status=connection, last_received_at=self.received_at,
                    age_s=elapsed if self.received_mono is not None else None,
                    session_id=self.session, sequence=self.sequence), topics=topics,
                    motion=dict(status=movement, rotating=rotating, current=motion if fresh else None,
                                age_s=motion_age, last_valid=retained),
                    alerts=deepcopy(list(self.alerts)), settings=cfg.model_dump(),
                    patrol=aged("patrol"), pose=pose, command=self.command_view(),
                    launcher=deepcopy(self.launcher()), patrol_running=self.patrol_running(),
                    map_available=self.map_available)
