"""공급원 폴링, 마지막 정상값 보존, 표시 시점 검증 (PRD 5절 Data Manager).

각 공급원은 자기 주기로 백그라운드 스레드에서 읽는다. 느린 HTTP나 큰 Excel이 화면 갱신을 막지 않고,
예외는 스레드 안에서 잡혀 로그만 남는다. 화면은 *_view(now)로 '지금 시각 기준으로 검증된' 값만 받는다.
보존한 마지막 값도 TTL은 매번 다시 따지므로, 오래된 값이 현재값처럼 보이지 않는다.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, Callable

from .adapters import AdapterError, build_bin_adapter, build_eco_adapter, build_schedule_adapter
from .bin_resolver import BinView, resolve_bins
from .eco_state_resolver import EcoPolicy, EcoResult, resolve_eco
from .schedule import Event, ScheduleFileError, Selected, select_events
from .util import ChangeLogger

log = logging.getLogger("signage.data")


class Clock:
    """앱 전체가 쓰는 현재 시각. --at으로 시작 시각을 바꿔 시험할 수 있다 (시간은 그대로 흐름)."""

    def __init__(self, tz: tzinfo, start_at: datetime | None = None):
        self.tz = tz
        self._offset = timedelta(0)
        if start_at is not None:
            if start_at.tzinfo is None:
                start_at = start_at.replace(tzinfo=tz)
            self._offset = start_at - datetime.now(tz)

    def now(self) -> datetime:
        return (datetime.now(self.tz) + self._offset).astimezone(self.tz)


class _Poller(threading.Thread):
    def __init__(self, name: str, interval: float, fn: Callable[[], None]):
        super().__init__(name=f"poll-{name}", daemon=True)
        self.interval = max(0.5, float(interval))
        self.fn = fn
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.fn()
            except Exception:  # 마지막 방어선: 스레드가 죽어 갱신이 멈추는 일이 없게
                log.exception("%s: 예기치 못한 오류", self.name)
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()


@dataclass
class _Slot:
    """한 공급원의 마지막 정상값."""
    value: Any = None
    received_at: datetime | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass(frozen=True)
class ScheduleView:
    selected: list[Selected]
    has_snapshot: bool  # 한 번이라도 Excel을 정상으로 읽었는지
    error: str | None


class DataManager:
    def __init__(self, cfg: dict, root: Path, clock: Clock):
        self.cfg = cfg
        self.clock = clock
        tz = clock.tz
        self.tz = tz
        self.schedule_adapter = build_schedule_adapter(cfg, root, tz)
        self.bin_adapter = build_bin_adapter(cfg, root, tz, clock.now)
        self.eco_adapter = build_eco_adapter(cfg, root, tz, clock.now)
        self.eco_policy = EcoPolicy.from_config(cfg["eco_feedback"])
        self.bin_max_age = float(cfg["bin_status"]["max_data_age_seconds"])
        self.max_visible_events = int(cfg["schedule"]["max_visible_events"])
        self._schedule = _Slot(value=[])
        self._schedule_ok = False
        self._bins = _Slot()
        self._eco = _Slot()
        self._pollers: list[_Poller] = []
        self._changes = ChangeLogger(log)
        log.info("데이터 공급원: 일정=%s, 적재율=%s, 환경평가=%s", self.schedule_adapter.describe(),
                 self.bin_adapter.describe(), self.eco_adapter.describe())

    # ------------------------------------------------------------ 폴링

    def start(self) -> None:
        self._pollers = [
            _Poller("schedule", self.cfg["schedule"]["reload_interval_seconds"], self.poll_schedule),
            _Poller("bins", self.cfg["bin_status"]["refresh_interval_seconds"], self.poll_bins),
            _Poller("eco", self.cfg["eco_feedback"]["refresh_interval_seconds"], self.poll_eco),
        ]
        for p in self._pollers:
            p.start()

    def stop(self) -> None:
        for p in self._pollers:
            p.stop()

    def poll_all_once(self) -> None:
        self.poll_schedule()
        self.poll_bins()
        self.poll_eco()

    def poll_schedule(self) -> None:
        try:
            result, fresh = self.schedule_adapter.read()
        except ScheduleFileError as e:
            with self._schedule.lock:
                self._schedule.error = str(e)
            kept = "마지막 정상 일정 유지" if self._schedule_ok else "표시할 일정 없음"
            self._changes.log("schedule.error", logging.WARNING, f"일정 읽기 실패: {e} → {kept}")
            return
        with self._schedule.lock:
            self._schedule.value = result.events
            self._schedule.received_at = self.clock.now()
            self._schedule.error = None
            self._schedule_ok = True
        self._changes.log("schedule.error", logging.INFO, None)
        if fresh:
            log.info("일정 읽음: 활성 일정 %d건, 제외된 행 %d건", len(result.events), len(result.errors))
            for err in result.errors:
                log.warning("일정 행 제외: %s", err)

    def _poll_snapshot(self, slot: _Slot, adapter, key: str) -> None:
        try:
            value = adapter.read()
        except AdapterError as e:
            with slot.lock:
                slot.error = str(e)
            self._changes.log(f"{key}.error", logging.WARNING, f"{key} 읽기 실패: {e} (마지막 값은 유효기간까지만 사용)")
            return
        with slot.lock:
            slot.value = value
            slot.received_at = self.clock.now()
            slot.error = None
        self._changes.log(f"{key}.error", logging.INFO, None)

    def poll_bins(self) -> None:
        self._poll_snapshot(self._bins, self.bin_adapter, "bin_status")

    def poll_eco(self) -> None:
        self._poll_snapshot(self._eco, self.eco_adapter, "eco_metrics")

    # ------------------------------------------------------------ 화면용 값

    def schedule_view(self, now: datetime | None = None) -> ScheduleView:
        now = now or self.clock.now()
        with self._schedule.lock:
            events: list[Event] = list(self._schedule.value or [])
            error = self._schedule.error
        selected = select_events(events, now, self.max_visible_events)
        desc = ", ".join(f"{s.status}:{s.event.event_id}" for s in selected) or "없음"
        self._changes.log("schedule.selected", logging.INFO, f"표시 일정: {desc}")
        return ScheduleView(selected, self._schedule_ok, error)

    def bin_view(self, now: datetime | None = None) -> BinView:
        now = now or self.clock.now()
        with self._bins.lock:
            snapshot = self._bins.value
        view = resolve_bins(snapshot, now, self.bin_max_age, self.tz, self.bin_adapter.is_mock)
        for bin_id, r in view.readings.items():
            state = "표시" if r.available else f"정보 없음 ({r.reason})"
            self._changes.log(f"bin.{bin_id}", logging.INFO,
                              f"적재율 {bin_id}: {state} [source={view.source}]")
        return view

    def eco_result(self, now: datetime | None = None) -> EcoResult:
        now = now or self.clock.now()
        with self._eco.lock:
            metrics = self._eco.value
        result = resolve_eco(metrics, now, self.eco_policy, self.tz)
        self._changes.log("eco.state", logging.INFO,
                          f"환경 피드백 상태: {result.state} ({result.reason})")
        return result
