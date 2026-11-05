"""여러 모듈이 같이 쓰는 작은 도구: 시각 해석, 숫자 판정, 원자적 JSON 쓰기, 시각 표기."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any

WEEKDAYS_KO = "월화수목금토일"


# ---------------------------------------------------------------- 값 판정

def is_real_number(value: Any) -> bool:
    """bool이 아닌 유한한 int/float인지. (JSON의 true/false가 1/0으로 새는 것을 막는다)"""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def is_count(value: Any) -> bool:
    """0 이상의 정수(bool 제외). 2.0처럼 정수값인 float도 받지 않는다."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_timestamp(value: Any, tz: tzinfo) -> datetime | None:
    """ISO 8601 문자열을 시간대가 있는 datetime으로. 'Z' 허용, 시간대가 없으면 앱 시간대로 본다.

    해석할 수 없으면 None.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


# ---------------------------------------------------------------- 표기

def format_fields(dt: datetime) -> dict[str, Any]:
    """YAML의 날짜/시각 형식 문자열("{year}-{month:02d}" 등)에 넣을 값."""
    hour12 = dt.hour % 12 or 12
    return {
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "hour12": hour12,
        "minute": dt.minute,
        "second": dt.second,
        "ampm": "오전" if dt.hour < 12 else "오후",
        "weekday": WEEKDAYS_KO[dt.weekday()],
    }


def format_dt(fmt: str, dt: datetime, **extra: Any) -> str:
    """형식 문자열이 틀려도 화면이 죽지 않게, 실패하면 ISO 표기로 대신한다."""
    try:
        return fmt.format(**format_fields(dt), **extra)
    except (KeyError, ValueError, IndexError):
        logging.getLogger("signage").warning("형식 문자열 오류: %r", fmt)
        return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- 파일

def file_signature(path: Path) -> tuple[int, int] | None:
    """변경 감지용 (수정시각 ns, 크기). 파일이 없거나 못 읽으면 None."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def atomic_write_json(path: str | os.PathLike, data: Any) -> None:
    """같은 디렉터리의 임시 파일에 다 쓴 뒤 os.replace로 바꿔 끼운다.

    읽는 쪽은 언제 읽어도 옛 파일 전체 또는 새 파일 전체만 보게 된다. 데이터 생산자(센서/평가 프로그램)도
    이 함수를 그대로 복사해 쓰면 된다.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class ChangeLogger:
    """같은 키의 메시지가 바뀔 때만 로그를 남긴다 (매 주기 같은 오류로 로그가 넘치는 것을 막음)."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger
        self._last: dict[str, str | None] = {}

    def log(self, key: str, level: int, message: str | None) -> bool:
        if self._last.get(key, "<unset>") == message:
            return False
        self._last[key] = message
        if message is not None:
            self._logger.log(level, "%s", message)
        return True
