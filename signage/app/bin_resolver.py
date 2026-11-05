"""수거함 적재율 스냅샷 검증 (PRD 5.3). 표시 가능한 값만 통과시키고, 나머지는 '정보 없음'."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from typing import Any

from .util import is_real_number, parse_timestamp

BIN_IDS = ("general", "recycling")
MEASUREMENT_METHODS = ("volume_estimate", "weight_estimate", "manual_measured")
FUTURE_TOLERANCE_SECONDS = 30  # 생산자·표시기 시계 차이 허용


@dataclass(frozen=True)
class BinReading:
    bin_id: str
    available: bool
    percent: float | None  # available일 때만 0~100
    method: str | None
    reason: str  # 정보 없음의 이유 (로그용). 정상이면 "ok"


@dataclass(frozen=True)
class BinView:
    readings: dict[str, BinReading]
    source: str
    observed_at: datetime | None
    is_mock: bool = False
    notes: list[str] = field(default_factory=list)


def _unavailable(bin_id: str, reason: str) -> BinReading:
    return BinReading(bin_id, False, None, None, reason)


def resolve_bins(snapshot: Any, now: datetime, max_age_seconds: float, tz: tzinfo,
                 is_mock: bool = False) -> BinView:
    """두 수거함을 따로 검증한다. 한쪽 오류가 다른 쪽 표시를 막지 않는다.

    퍼센트를 표시하는 조건: schema_version 1, observed_at 유효·TTL 이내, 해당 bin의 quality=ok,
    measurement_method가 알려진 측정 방식, fill_percent가 0~100 숫자.
    """
    if not isinstance(snapshot, dict):
        return BinView({b: _unavailable(b, "데이터 없음") for b in BIN_IDS}, "unavailable", None, is_mock)

    source = str(snapshot.get("source") or "unknown")
    common_reason = None
    observed_at = parse_timestamp(snapshot.get("observed_at"), tz)
    if snapshot.get("schema_version") != 1:
        common_reason = f"schema_version 불일치 ({snapshot.get('schema_version')!r})"
    elif observed_at is None:
        common_reason = "observed_at 없음/형식 오류"
    else:
        age = (now - observed_at).total_seconds()
        if age > max_age_seconds:
            common_reason = f"데이터 만료 (관측 후 {max_age_seconds:.0f}초 초과)"
        elif age < -FUTURE_TOLERANCE_SECONDS:
            common_reason = "observed_at이 미래 시각"

    bins = snapshot.get("bins") if isinstance(snapshot.get("bins"), dict) else {}
    readings: dict[str, BinReading] = {}
    for bin_id in BIN_IDS:
        if common_reason:
            readings[bin_id] = _unavailable(bin_id, common_reason)
            continue
        entry = bins.get(bin_id)
        if not isinstance(entry, dict):
            readings[bin_id] = _unavailable(bin_id, "항목 없음")
            continue
        quality = entry.get("quality")
        method = entry.get("measurement_method")
        value = entry.get("fill_percent")
        if quality != "ok":
            readings[bin_id] = _unavailable(bin_id, f"quality={quality!r}")
        elif method not in MEASUREMENT_METHODS:
            readings[bin_id] = _unavailable(bin_id, f"measurement_method={method!r} (측정 근거 불명)")
        elif not is_real_number(value):
            readings[bin_id] = _unavailable(bin_id, f"fill_percent 값 없음/숫자 아님 ({value!r})")
        elif not 0 <= value <= 100:
            readings[bin_id] = _unavailable(bin_id, f"fill_percent 범위 밖 ({value})")
        else:
            readings[bin_id] = BinReading(bin_id, True, float(value), method, "ok")
    return BinView(readings, source, observed_at, is_mock)
