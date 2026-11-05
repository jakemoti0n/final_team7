"""행사 일정: Excel 행 해석(검증)과 표시할 일정 선택. Qt·openpyxl에 의존하지 않는 순수 로직."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, Iterable, Sequence

HEADERS = ("event_id", "date", "start_time", "end_time", "title", "location", "enabled", "notes")
REQUIRED_HEADERS = ("event_id", "date", "start_time", "title", "enabled")

_DATE_RE = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_EXCEL_EPOCH = datetime(1899, 12, 30)  # Excel(1900 체계) 일련번호 0


class ScheduleFileError(Exception):
    """파일 전체를 쓸 수 없는 오류. 마지막 정상 스냅샷을 유지해야 한다."""


@dataclass(frozen=True)
class Event:
    event_id: str
    start: datetime
    end: datetime | None
    title: str
    location: str | None
    row: int


@dataclass
class ParseResult:
    events: list[Event] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # 행 단위 오류: "행 5: date 형식 오류 ..."


@dataclass(frozen=True)
class Selected:
    event: Event
    status: str  # "ongoing" | "upcoming"


# ---------------------------------------------------------------- 셀 값 해석

class _CellError(ValueError):
    pass


def parse_date_cell(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # 일반 서식 셀에 들어간 Excel 날짜 일련번호
        if 1 <= value < 2958466:
            return (_EXCEL_EPOCH + timedelta(days=int(value))).date()
        raise _CellError(f"date 숫자 범위 오류 ({value})")
    if isinstance(value, str):
        m = _DATE_RE.match(value.strip())
        if m:
            try:
                return date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                pass
    raise _CellError(f"date 형식 오류 ({value!r}, YYYY-MM-DD)")


def parse_time_cell(value: Any) -> time:
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0, tzinfo=None)
    if isinstance(value, timedelta):
        secs = int(round(value.total_seconds()))
        if 0 <= secs < 86400:
            return time(secs // 3600, secs % 3600 // 60, secs % 60)
        raise _CellError(f"시간 범위 오류 ({value})")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # 하루의 비율로 저장된 Excel 시간 (0.5 = 12:00)
        if 0 <= value < 1:
            secs = int(round(value * 86400)) % 86400
            return time(secs // 3600, secs % 3600 // 60, secs % 60)
        raise _CellError(f"시간 숫자 범위 오류 ({value})")
    if isinstance(value, str):
        m = _TIME_RE.match(value.strip())
        if m:
            h, mi, s = int(m[1]), int(m[2]), int(m[3] or 0)
            if h < 24 and mi < 60 and s < 60:
                return time(h, mi, s)
    raise _CellError(f"시간 형식 오류 ({value!r}, 24시간제 HH:MM)")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


# ---------------------------------------------------------------- 시트 해석

def header_index(header_row: Sequence[Any] | None) -> dict[str, int]:
    if not header_row:
        raise ScheduleFileError("헤더 행이 없습니다")
    names = [_text(v).lower() for v in header_row]
    index = {name: i for i, name in enumerate(names) if name in HEADERS}
    missing = [h for h in REQUIRED_HEADERS if h not in index]
    if missing:
        raise ScheduleFileError(f"헤더 누락: {', '.join(missing)} (1행 헤더 이름을 바꾸지 마세요)")
    return index


def parse_rows(header_row: Sequence[Any] | None, rows: Iterable[Sequence[Any]], tz: tzinfo,
               first_row_number: int = 2, max_rows: int = 5000) -> ParseResult:
    """enabled=Y 행만 검증해 Event로 만든다. 잘못된 행은 행 번호와 이유를 errors에 남기고 뺀다."""
    idx = header_index(header_row)
    result = ParseResult()
    candidates: list[Event] = []

    def cell(row: Sequence[Any], name: str) -> Any:
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    for offset, row in enumerate(rows):
        if offset >= max_rows:
            result.errors.append(f"{max_rows}행 이후는 읽지 않았습니다")
            break
        rownum = first_row_number + offset
        row = tuple(row or ())
        if all(v is None or _text(v) == "" for v in row):
            continue
        enabled = _text(cell(row, "enabled")).upper()
        if enabled in ("N", ""):
            continue  # 비활성(또는 미입력 = 기본 N)
        if enabled != "Y":
            result.errors.append(f"행 {rownum}: enabled는 Y 또는 N ({cell(row, 'enabled')!r})")
            continue
        try:
            event_id = _text(cell(row, "event_id"))
            if not event_id:
                raise _CellError("event_id 비어 있음")
            title = _text(cell(row, "title"))
            if not title:
                raise _CellError("title 비어 있음")
            day = parse_date_cell(cell(row, "date"))
            start_t = parse_time_cell(cell(row, "start_time"))
            start = datetime.combine(day, start_t, tzinfo=tz)
            end = None
            raw_end = cell(row, "end_time")
            if raw_end is not None and _text(raw_end) != "":
                end = datetime.combine(day, parse_time_cell(raw_end), tzinfo=tz)
                if end <= start:
                    raise _CellError("end_time이 start_time보다 늦어야 합니다 (자정 넘김 미지원)")
            location = _text(cell(row, "location")) or None
        except _CellError as e:
            result.errors.append(f"행 {rownum}: {e}")
            continue
        candidates.append(Event(event_id, start, end, title, location, rownum))

    # 활성 일정의 event_id 중복은 잘못된 입력: 해당 ID의 행을 모두 뺀다
    counts: dict[str, int] = {}
    for ev in candidates:
        counts[ev.event_id] = counts.get(ev.event_id, 0) + 1
    for ev in candidates:
        if counts[ev.event_id] > 1:
            result.errors.append(f"행 {ev.row}: event_id 중복 ({ev.event_id})")
        else:
            result.events.append(ev)
    return result


# ---------------------------------------------------------------- 표시 일정 선택

def _sort_key(ev: Event) -> tuple[datetime, str]:
    return (ev.start, ev.event_id)


def select_events(events: Iterable[Event], now: datetime, max_count: int = 1) -> list[Selected]:
    """진행 중 행사 우선, 그다음 가장 가까운 다음 일정. 지난 행사는 제외.

    - 진행 중: end_time이 있고 start <= now < end
    - 다음 일정: start > now (end_time이 없는 행사는 시작시각이 지나면 제외)
    - 정렬: 시작시각 오름차순, 같으면 event_id 오름차순
    """
    events = list(events)
    ongoing = sorted((e for e in events if e.end is not None and e.start <= now < e.end), key=_sort_key)
    upcoming = sorted((e for e in events if e.start > now), key=_sort_key)
    picked = [Selected(e, "ongoing") for e in ongoing] + [Selected(e, "upcoming") for e in upcoming]
    return picked[: max(1, int(max_count))]
