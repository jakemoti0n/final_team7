"""PRD 4절 Excel 스키마, 3절 화면 A 선택 규칙, 9절 시나리오 1~3."""

import os
from datetime import date, datetime, time as dtime

import openpyxl
import pytest

from app.adapters.schedule_excel import ExcelScheduleAdapter
from app.config import APP_DEFAULTS, deep_merge
from app.data_manager import Clock, DataManager
from app.schedule import (HEADERS, Event, ScheduleFileError, parse_date_cell, parse_rows, parse_time_cell,
                          select_events)
from conftest import TEMPLATE_XLSX, TZ, kst


def ev(eid, start, end=None, title="t"):
    return Event(eid, start, end, title, None, 2)


# ---------------------------------------------------------------- 셀 해석

@pytest.mark.parametrize("value,expected", [
    ("2026-11-07", date(2026, 11, 7)),
    ("2026.11.7", date(2026, 11, 7)),
    (datetime(2026, 11, 7, 0, 0), date(2026, 11, 7)),
    (date(2026, 11, 7), date(2026, 11, 7)),
    (46333, date(2026, 11, 7)),  # Excel 일련번호
])
def test_parse_date_cell_accepts_text_and_excel_types(value, expected):
    assert parse_date_cell(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("14:00", dtime(14, 0)),
    ("9:05", dtime(9, 5)),
    (dtime(14, 0), dtime(14, 0)),
    (datetime(1899, 12, 30, 14, 0), dtime(14, 0)),
    (0.5, dtime(12, 0)),
])
def test_parse_time_cell_accepts_text_and_excel_types(value, expected):
    assert parse_time_cell(value) == expected


@pytest.mark.parametrize("bad", ["2026-13-01", "11/07", "", None, True])
def test_parse_date_cell_rejects(bad):
    with pytest.raises(ValueError):
        parse_date_cell(bad)


@pytest.mark.parametrize("bad", ["25:00", "14:60", "오후 2시", 1.5])
def test_parse_time_cell_rejects(bad):
    with pytest.raises(ValueError):
        parse_time_cell(bad)


# ---------------------------------------------------------------- 행 해석

def rows(*data):
    return list(HEADERS), [list(r) for r in data]


def test_parse_rows_only_enabled_y_and_bad_row_isolated():
    header, data = rows(
        ["e1", "2026-11-07", "14:00", "15:00", "국악 공연", "주행사장 > 열린야외 무대", "Y", "memo"],
        ["e2", "2026-11-07", "16:00", None, "비활성", None, "N", None],
        ["e3", "2026-99-07", "16:00", None, "날짜 오류", None, "Y", None],  # 이 행만 빠져야 함
        ["e4", "2026-11-07", "17:00", "", "장소 없음", "", "y", None],
        [None] * 8,
        ["e5", "2026-11-07", "18:00", None, "엉뚱한 enabled", None, "yes", None],
    )
    res = parse_rows(header, data, TZ)
    assert [e.event_id for e in res.events] == ["e1", "e4"]
    assert res.events[0].start == kst(2026, 11, 7, 14, 0)
    assert res.events[0].location == "주행사장 > 열린야외 무대"
    assert res.events[1].location is None and res.events[1].end is None
    assert len(res.errors) == 2
    assert res.errors[0].startswith("행 4:")  # 헤더가 1행이므로 e3는 4행


def test_parse_rows_duplicate_enabled_ids_are_invalid():
    header, data = rows(
        ["dup", "2026-11-07", "14:00", None, "a", None, "Y", None],
        ["dup", "2026-11-08", "14:00", None, "b", None, "Y", None],
        ["dup", "2026-11-09", "14:00", None, "c", None, "N", None],  # 비활성 중복은 상관없음
        ["ok", "2026-11-09", "14:00", None, "d", None, "Y", None],
    )
    res = parse_rows(header, data, TZ)
    assert [e.event_id for e in res.events] == ["ok"]
    assert sum("중복" in e for e in res.errors) == 2


def test_parse_rows_end_before_start_invalid():
    header, data = rows(["e", "2026-11-07", "15:00", "14:00", "x", None, "Y", None])
    res = parse_rows(header, data, TZ)
    assert res.events == [] and len(res.errors) == 1


def test_missing_required_header_is_file_error():
    with pytest.raises(ScheduleFileError):
        parse_rows(["event_id", "date", "title", "enabled"], [], TZ)


# ---------------------------------------------------------------- 선택

def test_select_prefers_ongoing_then_next_upcoming():
    events = [
        ev("past", kst(2026, 11, 7, 9), kst(2026, 11, 7, 10)),
        ev("now", kst(2026, 11, 7, 13), kst(2026, 11, 7, 15)),
        ev("next", kst(2026, 11, 7, 16)),
    ]
    sel = select_events(events, kst(2026, 11, 7, 14))
    assert [(s.event.event_id, s.status) for s in sel] == [("now", "ongoing")]
    sel = select_events(events, kst(2026, 11, 7, 15))  # 끝나는 순간은 진행 중 아님
    assert [(s.event.event_id, s.status) for s in sel] == [("next", "upcoming")]


def test_select_excludes_no_end_events_after_start_and_past():
    events = [ev("noend", kst(2026, 11, 7, 13)), ev("tomorrow", kst(2026, 11, 8, 10))]
    sel = select_events(events, kst(2026, 11, 7, 13, 0, 1))
    assert [s.event.event_id for s in sel] == ["tomorrow"]


def test_select_tie_break_by_event_id_and_max_count():
    events = [ev("b", kst(2026, 11, 7, 16)), ev("a", kst(2026, 11, 7, 16)), ev("c", kst(2026, 11, 7, 17))]
    assert [s.event.event_id for s in select_events(events, kst(2026, 11, 7, 12))] == ["a"]
    assert [s.event.event_id for s in select_events(events, kst(2026, 11, 7, 12), 3)] == ["a", "b", "c"]


def test_select_empty_when_nothing_ahead():  # 시나리오 3
    assert select_events([ev("x", kst(2026, 11, 1, 10))], kst(2026, 11, 7, 12)) == []


# ---------------------------------------------------------------- 실제 xlsx

def write_xlsx(path, data_rows, sheet="Events"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(list(HEADERS))
    for r in data_rows:
        ws.append(list(r))
    wb.save(path)


def bump_mtime(path):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


def test_template_example_row_is_not_shown():  # 예시 행은 enabled=N
    res, fresh = ExcelScheduleAdapter(TEMPLATE_XLSX, "Events", TZ).read()
    assert fresh and res.events == [] and res.errors == []


def test_excel_cells_typed_as_excel_dates_and_times(tmp_path):
    p = tmp_path / "events.xlsx"
    write_xlsx(p, [["e1", datetime(2026, 11, 7), dtime(14, 0), dtime(15, 0), "공연", None, "Y", None]])
    res, _ = ExcelScheduleAdapter(p, "Events", TZ).read()
    assert res.events[0].start == kst(2026, 11, 7, 14) and res.events[0].end == kst(2026, 11, 7, 15)


def test_excel_edit_is_picked_up_on_next_read(tmp_path):  # 시나리오 1
    p = tmp_path / "events.xlsx"
    write_xlsx(p, [["e1", "2026-11-07", "14:00", None, "국악 공연", "열린야외 무대", "Y", None]])
    a = ExcelScheduleAdapter(p, "Events", TZ)
    assert a.read()[0].events[0].title == "국악 공연"
    assert a.read()[1] is False  # 안 바뀌었으면 다시 파싱하지 않음
    write_xlsx(p, [["e1", "2026-11-07", "14:00", None, "사물놀이", "메인 무대", "Y", None]])
    bump_mtime(p)
    res, fresh = a.read()
    assert fresh and res.events[0].title == "사물놀이" and res.events[0].location == "메인 무대"


def test_wrong_sheet_name_is_file_error(tmp_path):
    p = tmp_path / "events.xlsx"
    write_xlsx(p, [], sheet="Sheet1")
    with pytest.raises(ScheduleFileError):
        ExcelScheduleAdapter(p, "Events", TZ).read()


def test_corrupt_file_keeps_last_good_snapshot(tmp_path):  # 시나리오 2
    (tmp_path / "data").mkdir()
    p = tmp_path / "data/events.xlsx"
    write_xlsx(p, [["e1", "2026-11-07", "14:00", None, "국악 공연", None, "Y", None]])
    cfg = deep_merge(APP_DEFAULTS, {})
    dm = DataManager(cfg, tmp_path, Clock(TZ))
    dm.poll_schedule()
    now = kst(2026, 11, 7, 12)
    assert dm.schedule_view(now).selected[0].event.title == "국악 공연"

    p.write_bytes(b"this is not a zip file")
    bump_mtime(p)
    dm.poll_schedule()
    view = dm.schedule_view(now)
    assert view.error and view.selected[0].event.title == "국악 공연"

    p.unlink()
    dm.poll_schedule()
    assert dm.schedule_view(now).selected[0].event.title == "국악 공연"
