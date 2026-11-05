"""설정(YAML) 읽기, 기본값 병합, 경로 검증."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("signage.config")

SCREEN_IDS = ("clock_schedule", "bin_status", "eco_feedback")

# app.yaml에 빠진 항목은 이 값으로 채운다. 수치는 PRD v0.2의 제안값.
APP_DEFAULTS: dict[str, Any] = {
    "app": {"locale": "ko-KR", "timezone": "Asia/Seoul", "mode": "production"},
    "display": {
        "fullscreen": True,
        "width": 1920,
        "height": 1080,
        "orientation": "landscape",
        "scale_mode": "keep_aspect_ratio",
        "hide_cursor": True,
        "window_size": [960, 540],
    },
    "rotation": [
        {"id": "clock_schedule", "duration_seconds": 12},
        {"id": "bin_status", "duration_seconds": 12},
        {"id": "eco_feedback", "duration_seconds": 12},
    ],
    "content": {"reload_interval_seconds": 3},
    "theme": {
        "background": "#FFFFFF",
        "text": "#000000",
        "accent": "#1EBE9B",
        "muted": "#7A8585",
        "letterbox": "#000000",
        "demo_badge": "#FB7365",
        "font_dir": "assets/fonts",
        "font_families": ["Pretendard", "Noto Sans CJK KR", "NanumGothic", "Noto Sans KR"],
    },
    "schedule": {
        "adapter": "excel",
        "file": "data/events.xlsx",
        "sheet": "Events",
        "reload_interval_seconds": 15,
        "max_visible_events": 1,
    },
    "bin_status": {
        "adapter": "json",
        "file": "data/bin_status.json",
        "url": None,
        "refresh_interval_seconds": 2,
        "max_data_age_seconds": 120,
    },
    "eco_feedback": {
        "adapter": "json",
        "file": "data/eco_metrics.json",
        "url": None,
        "refresh_interval_seconds": 5,
        "max_data_age_seconds": 600,
        "evaluation_window_hours": 24,
        "min_verified_samples": 20,
        "positive_threshold_percent": 80,
        "default_state": "initial",
    },
    "mock_data": {
        "allowed_only_in_demo_mode": True,
        "visible_demo_badge": True,
        "bin_status": {"scenarios": [{"general": 60, "recycling": 10}], "cycle_seconds": 36},
        "eco_metrics": {
            "scenarios": [{"verified_correct_count": 18, "verified_total_count": 20}],
            "cycle_seconds": 36,
        },
    },
    "logging": {"level": "INFO", "file": "logs/signage.log", "max_bytes": 1_000_000, "backup_count": 5},
}


class ConfigError(Exception):
    pass


def deep_merge(base: dict, override: dict) -> dict:
    """override가 base를 덮는다. dict끼리는 재귀 병합, 그 외(리스트 포함)는 통째로 교체."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def resolve_path(root: Path, rel: str | Path) -> Path:
    """프로젝트 루트 기준 경로. 루트 밖을 가리키면 거부한다 (PRD 6절)."""
    root = root.resolve()
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        raise ConfigError(f"프로젝트 밖 경로는 쓸 수 없습니다: {rel}")
    return path


def read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: 최상위가 key: value 형식이 아닙니다")
    return data


def load_app_config(path: Path) -> dict:
    cfg = deep_merge(APP_DEFAULTS, read_yaml(path))
    validate_app_config(cfg)
    return cfg


def validate_app_config(cfg: dict) -> None:
    mode = cfg["app"]["mode"]
    if mode not in ("production", "demo"):
        raise ConfigError(f"app.mode는 production 또는 demo여야 합니다: {mode!r}")
    rotation = cfg.get("rotation")
    if not isinstance(rotation, list) or not rotation:
        raise ConfigError("rotation이 비어 있습니다")
    for item in rotation:
        if not isinstance(item, dict) or item.get("id") not in SCREEN_IDS:
            raise ConfigError(f"rotation 항목이 잘못됐습니다: {item!r} (id는 {', '.join(SCREEN_IDS)})")
        dur = item.get("duration_seconds")
        if not isinstance(dur, (int, float)) or isinstance(dur, bool) or dur < 1:
            raise ConfigError(f"rotation {item['id']}: duration_seconds는 1 이상 숫자여야 합니다")
    eco = cfg["eco_feedback"]
    if eco.get("default_state") != "initial":
        # PRD: 평가 근거가 없을 때는 initial만 허용
        raise ConfigError("eco_feedback.default_state는 initial만 허용됩니다")


def load_screen_config(root: Path, screen_id: str, defaults: dict) -> dict:
    """config/screens/<id>.yaml을 화면 기본값 위에 덮는다. 파일이 없으면 기본값."""
    path = root / "config" / "screens" / f"{screen_id}.yaml"
    if not path.exists():
        return copy.deepcopy(defaults)
    return deep_merge(defaults, read_yaml(path))
