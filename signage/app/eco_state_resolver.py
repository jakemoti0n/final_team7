"""검증된 분리수거 건수 → 성공률 → 나무 상태 (PRD 5.4, 5.5).

평가 근거가 하나라도 부족하면 판정하지 않고 initial을 유지한다. 적재율 등 다른 값으로 추정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any

from .util import is_count, parse_timestamp

STATES = ("initial", "positive", "negative")
EVALUATION_METHODS = ("verified_route_log", "human_audit", "sensor_verified")
FUTURE_TOLERANCE_SECONDS = 30
WINDOW_TOLERANCE_SECONDS = 60


@dataclass(frozen=True)
class EcoPolicy:
    max_data_age_seconds: float = 600
    evaluation_window_hours: float = 24
    min_verified_samples: int = 20
    positive_threshold_percent: float = 80

    @classmethod
    def from_config(cls, section: dict) -> "EcoPolicy":
        return cls(
            max_data_age_seconds=float(section["max_data_age_seconds"]),
            evaluation_window_hours=float(section["evaluation_window_hours"]),
            min_verified_samples=int(section["min_verified_samples"]),
            positive_threshold_percent=float(section["positive_threshold_percent"]),
        )


@dataclass(frozen=True)
class EcoResult:
    state: str  # initial | positive | negative
    evaluated: bool  # False면 '평가 준비 중' 안내 대상
    rate_percent: float | None
    sample_count: int | None
    reason: str


def _not_evaluated(reason: str, samples: int | None = None) -> EcoResult:
    return EcoResult("initial", False, None, samples, reason)


def resolve_eco(metrics: Any, now: datetime, policy: EcoPolicy, tz: tzinfo) -> EcoResult:
    if not isinstance(metrics, dict):
        return _not_evaluated("데이터 없음")
    if metrics.get("schema_version") != 1:
        return _not_evaluated(f"schema_version 불일치 ({metrics.get('schema_version')!r})")
    if metrics.get("quality") != "ok":
        return _not_evaluated(f"quality={metrics.get('quality')!r}")
    method = metrics.get("evaluation_method")
    if method not in EVALUATION_METHODS:
        return _not_evaluated(f"evaluation_method={method!r} (검증 근거 없음)")

    observed_at = parse_timestamp(metrics.get("observed_at"), tz)
    if observed_at is None:
        return _not_evaluated("observed_at 없음/형식 오류")
    age = (now - observed_at).total_seconds()
    if age > policy.max_data_age_seconds:
        return _not_evaluated(f"집계 만료 (관측 후 {policy.max_data_age_seconds:.0f}초 초과)")
    if age < -FUTURE_TOLERANCE_SECONDS:
        return _not_evaluated("observed_at이 미래 시각")

    # 분자·분모가 같은 평가 창에서 나왔다는 근거
    w_start = parse_timestamp(metrics.get("window_start"), tz)
    w_end = parse_timestamp(metrics.get("window_end"), tz)
    if w_start is None or w_end is None:
        return _not_evaluated("window_start/window_end 없음")
    span = (w_end - w_start).total_seconds()
    if span <= 0:
        return _not_evaluated("평가 창이 잘못됨 (window_end <= window_start)")
    if span > policy.evaluation_window_hours * 3600 + WINDOW_TOLERANCE_SECONDS:
        return _not_evaluated(f"평가 창 {span / 3600:.1f}시간 > 설정 {policy.evaluation_window_hours}시간")

    correct = metrics.get("verified_correct_count")
    total = metrics.get("verified_total_count")
    if not is_count(correct) or not is_count(total):
        return _not_evaluated("검증 건수 없음/정수 아님")
    if correct > total:
        return _not_evaluated(f"verified_correct_count({correct}) > verified_total_count({total})")
    if total == 0:
        return _not_evaluated("판정 불가 (검증 건수 0)", 0)
    if total < policy.min_verified_samples:
        return _not_evaluated(f"표본 부족 ({total}/{policy.min_verified_samples}건)", total)

    rate = 100.0 * correct / total
    state = "positive" if rate >= policy.positive_threshold_percent else "negative"
    return EcoResult(state, True, rate, total, f"성공률 {rate:.1f}% ({correct}/{total}, {method})")
