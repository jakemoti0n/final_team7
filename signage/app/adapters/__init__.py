"""설정의 adapter 이름 → 공급원 객체. 새 공급원은 여기 등록한다."""

from __future__ import annotations

import logging
from datetime import tzinfo
from pathlib import Path

from ..config import resolve_path
from .base import AdapterError, UnavailableAdapter
from .bin_json import JsonBinStatusAdapter
from .eco_json import JsonEcoMetricsAdapter
from .http_json import HttpJsonAdapter
from .mock import MockBinStatusAdapter, MockEcoMetricsAdapter
from .schedule_excel import ExcelScheduleAdapter

__all__ = ["AdapterError", "build_bin_adapter", "build_eco_adapter", "build_schedule_adapter"]

log = logging.getLogger("signage.adapters")

# 후속 개발 예정 (PRD 10절 3단계). 선택되면 '정보 없음'으로 동작하고 로그를 남긴다.
NOT_IMPLEMENTED = ("ros2", "mqtt")


def _mock_allowed(cfg: dict) -> bool:
    return cfg["app"]["mode"] == "demo" or not cfg["mock_data"]["allowed_only_in_demo_mode"]


def _build(kind: str, cfg: dict, root: Path, tz: tzinfo, json_cls, mock_factory):
    section = cfg[kind]
    name = section.get("adapter")
    try:
        if name == "mock":
            if not _mock_allowed(cfg):
                log.error("%s: 운영 모드에서는 mock을 쓸 수 없습니다 → 정보 없음으로 표시", kind)
                return UnavailableAdapter("mock은 demo 모드 전용")
            return mock_factory()
        if name == "json":
            return json_cls(resolve_path(root, section["file"]))
        if name == "http":
            return HttpJsonAdapter(section.get("url"))
        if name in NOT_IMPLEMENTED:
            log.error("%s: adapter '%s'는 아직 구현되지 않았습니다 → 정보 없음으로 표시", kind, name)
            return UnavailableAdapter(f"{name} 미구현")
        log.error("%s: 알 수 없는 adapter '%s' → 정보 없음으로 표시", kind, name)
        return UnavailableAdapter(f"알 수 없는 adapter {name!r}")
    except Exception as e:
        log.error("%s: adapter 생성 실패 (%s) → 정보 없음으로 표시", kind, e)
        return UnavailableAdapter(str(e))


def build_bin_adapter(cfg: dict, root: Path, tz: tzinfo, now_fn=None):
    mock = cfg["mock_data"]["bin_status"]
    return _build("bin_status", cfg, root, tz, JsonBinStatusAdapter,
                  lambda: MockBinStatusAdapter(mock["scenarios"], mock["cycle_seconds"], tz, now_fn))


def build_eco_adapter(cfg: dict, root: Path, tz: tzinfo, now_fn=None):
    mock = cfg["mock_data"]["eco_metrics"]
    window = cfg["eco_feedback"]["evaluation_window_hours"]
    return _build("eco_feedback", cfg, root, tz, JsonEcoMetricsAdapter,
                  lambda: MockEcoMetricsAdapter(mock["scenarios"], mock["cycle_seconds"], tz, window, now_fn))


def build_schedule_adapter(cfg: dict, root: Path, tz: tzinfo):
    section = cfg["schedule"]
    if section.get("adapter") != "excel":
        log.error("schedule: adapter는 현재 excel만 지원합니다 (%r)", section.get("adapter"))
    return ExcelScheduleAdapter(resolve_path(root, section["file"]), section["sheet"], tz)
