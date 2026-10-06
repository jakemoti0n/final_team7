"""Strict v1 wire models. Contract authority: relay_prog/docs/PRD.md §3."""
from datetime import datetime, timedelta
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


class Telemetry(StrictModel):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    robot_id: Annotated[str, Field(min_length=1)]
    bridge_session_id: Annotated[str, AfterValidator(uuid_string)]
    sequence: Annotated[int, Field(gt=0)]
    sent_at: UTC
    source_clock: Literal["ros_sim", "ros_system"]
    topics: Topics
    motion: Motion

    @model_validator(mode="after")
    def coherent(self):
        if self.topics.odom.received_count == 0 and self.motion.age_ms is not None:
            raise ValueError("motion requires odom reception")
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

    @model_validator(mode="after")
    def ordered(self):
        if self.bridge_disconnect_s <= self.bridge_delay_s:
            raise ValueError("disconnect threshold must exceed delay threshold")
        return self
