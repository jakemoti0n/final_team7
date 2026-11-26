"""분리수거 성공률 (로봇 하단 디스플레이 장면 ⑤ 나무 3상태). 근거: signage/docs/PRD_로봇_하단_디스플레이_v0.3.md 「분리수거 성공률 계약」

Raspberry Pi(로봇 ROS 2 네트워크 밖)가 POST /api/v1/eco로 묶음을 보내고, 서버가 판정해 visitor/state의 eco로 판정만 내보낸다.

{
  "schema_version": 1,
  "observed_at": "2026-11-25T14:00:00+09:00",   # 센 시각 (Pi 시계)
  "window_start": "2026-11-25T09:00:00+09:00",  # 수거함을 마지막으로 비운 시각 (비운 뒤 누적)
  "window_end": "2026-11-25T14:00:00+09:00",    # 마지막으로 센 시각
  "source": "rpi-sorter",
  "evaluation_method": "ai_bin_inspection",      # 수거함에 들어간 뒤 AI가 확인 (넣기 전 예측만으로 센 건수는 안 됨)
  "verified_correct_count": 18,                  # 그중 맞는 칸(일반/재활용)에 있던 건수
  "verified_total_count": 20,                    # 확인한 건수
  "quality": "ok"
}

형식이 틀리면 거부하고 마지막 정상 값을 그대로 둔다. 형식은 맞지만 조건을 못 넘으면(품질·방법·표본 부족) initial.
오래됨은 Pi의 observed_at이 아니라 서버가 받은 시각으로 판단한다(Pi는 시간 동기화가 보장되지 않음).
"""
from datetime import datetime
import logging
import re

SCHEMA_VERSION = 1
FIELDS = {"schema_version", "observed_at", "window_start", "window_end", "source", "evaluation_method",
          "verified_correct_count", "verified_total_count", "quality"}
# 맞고 틀림을 실제로 확인한 방법만 센다. ai_bin_inspection은 PRD v0.3.2에서 더함 (화면에 「AI 확인」)
METHODS = ("ai_bin_inspection", "verified_route_log", "human_audit", "sensor_verified")
MAX_TEXT = 64
MAX_COUNT = 10_000_000
# 시간대까지 적은 ISO 8601 (Pi 시계와 서버 시계를 비교할 수 있게)
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})")


class EcoError(ValueError):
    pass


def _time(value, name):
    if not isinstance(value, str) or not ISO.fullmatch(value):
        raise EcoError(f"{name} must be ISO 8601 with a time zone, like 2026-11-25T14:00:00+09:00")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EcoError(f"{name} is not a real date and time") from exc


def _text(value, name):
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_TEXT or not value.isprintable():
        raise EcoError(f"{name} must be 1–{MAX_TEXT} printable characters")
    return value


def _count(value, name):
    # 품질이 나빠 셀 수 없을 때는 null을 보낼 수 있다 (v0.2 계약). 그때는 판정하지 않는다
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COUNT:
        raise EcoError(f"{name} must be a whole number 0–{MAX_COUNT} or null")
    return value


def validate(payload):
    """Pi가 보낸 묶음을 검사해 정리된 사본을 돌려준다. 형식이 틀리면 EcoError (→ 422)"""
    if not isinstance(payload, dict):
        raise EcoError("Body must be a JSON object")
    if set(payload) != FIELDS:
        missing, extra = sorted(FIELDS - set(payload)), sorted(set(payload) - FIELDS)
        raise EcoError("Fields do not match the contract" + (f"; missing: {', '.join(missing)}" if missing else "")
                       + (f"; unknown: {', '.join(extra)}" if extra else ""))
    if payload["schema_version"] != SCHEMA_VERSION or isinstance(payload["schema_version"], bool):
        raise EcoError(f"schema_version must be {SCHEMA_VERSION}")
    observed = _time(payload["observed_at"], "observed_at")
    start = _time(payload["window_start"], "window_start")
    end = _time(payload["window_end"], "window_end")
    if not start <= end <= observed:
        raise EcoError("Times must be in order: window_start ≤ window_end ≤ observed_at")
    correct = _count(payload["verified_correct_count"], "verified_correct_count")
    total = _count(payload["verified_total_count"], "verified_total_count")
    if (correct is None) != (total is None):
        raise EcoError("verified_correct_count and verified_total_count must both be numbers or both null")
    if correct is not None and correct > total:
        raise EcoError("verified_correct_count cannot exceed verified_total_count")
    return dict(observed_at=observed, source=_text(payload["source"], "source"),
                method=_text(payload["evaluation_method"], "evaluation_method"),
                quality=_text(payload["quality"], "quality"), correct=correct, total=total)


def judge(record, positive_percent, min_samples):
    """판정만 (화면에 보여도 되는 것). initial이면 숫자를 내지 않는다(모르는 값을 0 %로 보이지 않게)"""
    if (record is None or record["quality"] != "ok" or record["method"] not in METHODS
            or record["total"] is None or record["total"] < min_samples):
        return dict(state="initial")
    rate = 100 * record["correct"] / record["total"]
    return dict(state="positive" if rate >= positive_percent else "negative",
                rate_percent=int(rate), correct=record["correct"], total=record["total"], method=record["method"])


class EcoState:
    """마지막 정상 묶음과 서버가 그것을 받은 시각(monotonic)"""

    def __init__(self, settings, monotonic, utc):
        self.settings, self.monotonic, self.utc = settings, monotonic, utc
        self._record = None
        self._received = None
        self._skewed = False    # Pi 시계가 어긋났다고 이미 알렸는가 (60초마다 보내도 로그가 쌓이지 않게)

    def accept(self, payload):
        """검사·저장하고 지금 판정을 돌려준다. 형식이 틀리면 EcoError, 마지막 정상 값은 그대로"""
        record = validate(payload)
        self._record, self._received = record, self.monotonic()
        self._check_clock(record["observed_at"])
        return self.view()

    def view(self):
        s = self.settings
        if self._received is None or self.monotonic() - self._received > s.eco_max_age_s:
            return dict(state="initial")
        return judge(self._record, s.eco_positive_percent, s.eco_min_samples)

    def _check_clock(self, observed):
        try:
            server = datetime.fromisoformat(self.utc().replace("Z", "+00:00"))
        except ValueError:
            return
        skew = abs((observed - server).total_seconds())
        if skew > self.settings.eco_clock_skew_warn_s:
            if not self._skewed:
                logging.warning("eco: sender clock differs from the server by %d s (observed_at %s); "
                                "judging by the time the server received it. Fix the Raspberry Pi clock",
                                skew, observed.isoformat())
            self._skewed = True
        else:
            self._skewed = False
