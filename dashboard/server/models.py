"""Strict wire models: 텔레메트리 v1·v2, 관제 명령. Contract: relay_prog/docs/PRD.md §3, docs/CONTROL_API_DRAFT.md."""
from datetime import datetime, timedelta
import math
from typing import Annotated, Literal
from uuid import UUID
import re

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator


def utc_string(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value):
        raise ValueError("expected UTC ISO 8601")
    if datetime.fromisoformat(value).utcoffset() != timedelta(0):
        raise ValueError("expected UTC")
    return value


def uuid_string(value: str) -> str:
    return str(UUID(value))


UTC = Annotated[str, AfterValidator(utc_string)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Stamp(StrictModel):
    sec: int
    nanosec: Annotated[int, Field(ge=0, lt=1_000_000_000)]


class Topic(StrictModel):
    header_stamp: Stamp | None
    last_received_at: UTC | None
    age_ms: Nonnegative | None
    received_count: Count
    receive_hz: Nonnegative | None

    @model_validator(mode="after")
    def coherent(self):
        metadata = (self.header_stamp, self.last_received_at, self.age_ms)
        if self.received_count == 0:
            if any(x is not None for x in (*metadata, self.receive_hz)):
                raise ValueError("unreceived topic must have null metadata")
        elif any(x is None for x in metadata):
            raise ValueError("received topic requires stamp, UTC and age")
        return self


class Topics(StrictModel):
    odom: Topic
    lidar_raw: Topic
    lidar_filtered: Topic
    camera_raw: Topic


class Motion(StrictModel):
    linear_speed_mps: Nonnegative | None
    angular_velocity_radps: Finite | None
    last_received_at: UTC | None
    age_ms: Nonnegative | None

    @model_validator(mode="after")
    def coherent(self):
        fields = tuple(self.model_dump().values())
        if any(x is None for x in fields) and not all(x is None for x in fields):
            raise ValueError("motion must be entirely populated or entirely null")
        return self


PatrolStateName = Literal["waiting_localization", "patrolling", "pausing", "paused", "completed", "failed"]
ShortText = Annotated[str, Field(max_length=200)]


class Patrol(StrictModel):
    """v2: 순찰 노드 상태(/patrol/state). update_count는 Bridge 세션에서 받은 횟수"""
    state: PatrolStateName | None
    waypoint_index: Count | None
    waypoint_count: Count | None
    waypoint_name: ShortText | None
    has_resumable_task: bool | None
    reason: ShortText | None
    update_count: Count
    last_received_at: UTC | None
    age_ms: Nonnegative | None

    @model_validator(mode="after")
    def coherent(self):
        content = (self.state, self.waypoint_index, self.waypoint_count, self.waypoint_name,
                   self.has_resumable_task, self.reason)
        if self.update_count == 0:
            if any(x is not None for x in (*content, self.last_received_at, self.age_ms)):
                raise ValueError("unreceived patrol must be null")
        else:
            if self.last_received_at is None or self.age_ms is None:
                raise ValueError("received patrol requires UTC and age")
            if any(x is None for x in content) and not all(x is None for x in content):
                raise ValueError("patrol state must be entirely populated or entirely null")
        return self


class Pose(StrictModel):
    """v2: 로봇 위치(/amcl_pose, 지도 좌표)"""
    frame_id: Annotated[str, Field(min_length=1)] | None
    x: Finite | None
    y: Finite | None
    yaw: Annotated[float, Field(ge=-math.pi - 1e-9, le=math.pi + 1e-9, allow_inf_nan=False)] | None
    position_std_m: Nonnegative | None
    last_received_at: UTC | None
    age_ms: Nonnegative | None

    @model_validator(mode="after")
    def coherent(self):
        fields = tuple(self.model_dump().values())
        if any(x is None for x in fields) and not all(x is None for x in fields):
            raise ValueError("pose must be entirely populated or entirely null")
        return self


FollowStateName = Literal["idle", "following", "holding", "stopped"]


class Follow(StrictModel):
    """v2 선택 필드: 따라가기 상태(/follow/state, PROJECT.md 2-9 3단계). 규칙은 Patrol과 같다"""
    state: FollowStateName | None
    active: bool | None
    enrolled: bool | None
    visible: bool | None
    target_id: int | None
    distance_m: Nonnegative | None
    reason: ShortText | None
    elapsed_s: Nonnegative | None
    lost_s: Nonnegative | None
    update_count: Count
    last_received_at: UTC | None
    age_ms: Nonnegative | None

    @model_validator(mode="after")
    def coherent(self):
        content = (self.state, self.active, self.enrolled, self.visible, self.target_id, self.distance_m,
                   self.reason, self.elapsed_s, self.lost_s)
        if self.update_count == 0:
            if any(x is not None for x in (*content, self.last_received_at, self.age_ms)):
                raise ValueError("unreceived follow must be null")
        elif self.last_received_at is None or self.age_ms is None:
            raise ValueError("received follow needs timestamps")
        elif any(x is None for x in content) and not all(x is None for x in content):
            raise ValueError("follow content must be entirely populated or entirely null")
        return self


class Telemetry(StrictModel):
    schema_version: Annotated[int, Field(ge=1, le=2)]
    robot_id: Annotated[str, Field(min_length=1)]
    bridge_session_id: Annotated[str, AfterValidator(uuid_string)]
    sequence: Annotated[int, Field(gt=0)]
    sent_at: UTC
    source_clock: Literal["ros_sim", "ros_system"]
    topics: Topics
    motion: Motion
    patrol: Patrol | None = None   # v2에만 있음
    pose: Pose | None = None       # v2에만 있음
    follow: Follow | None = None   # v2 선택 필드 (따라가기 3단계). 없으면 "따라가기 상태 없음"

    @model_validator(mode="after")
    def coherent(self):
        v2 = {"patrol", "pose"} & self.model_fields_set
        if self.schema_version == 2 and (len(v2) != 2 or self.patrol is None or self.pose is None):
            raise ValueError("v2 requires patrol and pose")
        if self.schema_version == 1 and (v2 or "follow" in self.model_fields_set):
            raise ValueError("v1 must not include patrol, pose or follow")
        if self.motion.age_ms is not None:
            odom = self.topics.odom
            if odom.received_count == 0:
                raise ValueError("motion requires odom reception")
            if (self.motion.last_received_at != odom.last_received_at
                    or self.motion.age_ms != odom.age_ms):
                raise ValueError("motion must refer to latest odom")
        return self


CommandName = Literal["pause", "resume", "follow_start", "follow_stop", "follow_enroll"]


class CommandRequest(StrictModel):
    """화면 → 서버 POST /api/v1/commands"""
    command: CommandName


class CommandClaim(StrictModel):
    """Bridge → 서버 POST /api/v1/commands/{request_id}/claim: 서비스를 부르기 직전 "아직 유효한가" """
    robot_id: Annotated[str, Field(min_length=1)]
    bridge_session_id: Annotated[str, AfterValidator(uuid_string)]


class CommandResult(StrictModel):
    """Bridge → 서버 POST /api/v1/commands/{request_id}/result"""
    robot_id: Annotated[str, Field(min_length=1)]
    bridge_session_id: Annotated[str, AfterValidator(uuid_string)]
    request_id: Annotated[str, AfterValidator(uuid_string)]
    outcome: Literal["accepted", "rejected", "no_response", "service_unavailable", "expired"]
    message: ShortText
    service_latency_ms: Nonnegative | None
    patrol_update_count_at_call: Count
    follow_update_count_at_call: Count

    @model_validator(mode="after")
    def coherent(self):
        answered = self.outcome in ("accepted", "rejected")
        if answered != (self.service_latency_ms is not None):
            raise ValueError("latency only for answered calls")
        return self


class Thresholds(StrictModel):
    odom: Annotated[float, Field(gt=0)] = 3.0
    lidar_raw: Annotated[float, Field(gt=0)] = 3.0
    lidar_filtered: Annotated[float, Field(gt=0)] = 3.0
    camera_raw: Annotated[float, Field(gt=0)] = 3.0


class Settings(StrictModel):
    robot_id: str = "LIMBO-01"
    bridge_delay_s: Annotated[float, Field(gt=0)] = 3.0
    bridge_disconnect_s: Annotated[float, Field(gt=0)] = 10.0
    topic_delay_s: Thresholds = Field(default_factory=Thresholds)
    browser_delay_s: Annotated[float, Field(gt=1)] = 3.0
    linear_threshold_mps: Annotated[float, Field(gt=0)] = 0.05
    angular_threshold_radps: Annotated[float, Field(gt=0)] = 0.05
    alert_limit: Annotated[int, Field(gt=0, le=100)] = 100
    # 관제 명령 (Dashboard PRD §5.3 데모 기본값과 같음)
    command_ttl_s: Annotated[float, Field(gt=0)] = 5.0
    command_response_timeout_s: Annotated[float, Field(gt=0)] = 5.0
    command_confirm_timeout_s: Annotated[float, Field(gt=0)] = 5.0
    # 지도·waypoint 파일 (저장소 루트 기준 상대경로 또는 절대경로). 없으면 지도 API가 404
    map_yaml: str | None = None
    waypoints_yaml: str | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.bridge_disconnect_s <= self.bridge_delay_s:
            raise ValueError("disconnect threshold must exceed delay threshold")
        return self
