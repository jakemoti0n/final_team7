"""개발/시연 전용 가짜 수치 (PRD 5.1). 운영 모드에서는 만들어지지 않는다 (__init__.py 참고).

scenarios를 여러 개 주면 cycle_seconds마다 다음 시나리오로 넘어간다 (시연에서 나무 3상태를 보여 줄 때).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, tzinfo


class _ScenarioCycle:
    def __init__(self, scenarios: list[dict], cycle_seconds: float, clock=time.monotonic):
        if not scenarios:
            raise ValueError("mock scenarios가 비어 있습니다")
        self.scenarios = scenarios
        self.cycle_seconds = max(1.0, float(cycle_seconds))
        self._clock = clock
        self._t0 = clock()

    def current(self) -> dict:
        i = int((self._clock() - self._t0) // self.cycle_seconds) % len(self.scenarios)
        return self.scenarios[i]


class MockBinStatusAdapter:
    is_mock = True

    def __init__(self, scenarios: list[dict], cycle_seconds: float, tz: tzinfo, now_fn=None):
        self._cycle = _ScenarioCycle(scenarios, cycle_seconds)
        self._tz = tz
        self._now = now_fn or (lambda: datetime.now(tz))

    def describe(self) -> str:
        return "mock"

    def read(self) -> dict:
        sc = self._cycle.current()

        def entry(value):
            if value is None:
                return {"fill_percent": None, "measurement_method": "unknown", "quality": "unavailable"}
            return {"fill_percent": value, "measurement_method": sc.get("method", "volume_estimate"),
                    "quality": "ok"}

        return {
            "schema_version": 1,
            "observed_at": self._now().isoformat(timespec="seconds"),
            "source": "mock",
            "bins": {"general": entry(sc.get("general")), "recycling": entry(sc.get("recycling"))},
        }


class MockEcoMetricsAdapter:
    is_mock = True

    def __init__(self, scenarios: list[dict], cycle_seconds: float, tz: tzinfo, window_hours: float = 24,
                 now_fn=None):
        self._cycle = _ScenarioCycle(scenarios, cycle_seconds)
        self._tz = tz
        self._window = timedelta(hours=window_hours)
        self._now = now_fn or (lambda: datetime.now(tz))

    def describe(self) -> str:
        return "mock"

    def read(self) -> dict:
        sc = self._cycle.current()
        now = self._now()
        return {
            "schema_version": 1,
            "observed_at": now.isoformat(timespec="seconds"),
            "window_start": (now - self._window).isoformat(timespec="seconds"),
            "window_end": now.isoformat(timespec="seconds"),
            "source": "mock",
            "evaluation_method": sc.get("evaluation_method", "human_audit"),
            "verified_correct_count": sc.get("verified_correct_count"),
            "verified_total_count": sc.get("verified_total_count"),
            "quality": "ok",
        }
