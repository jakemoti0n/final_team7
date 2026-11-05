"""데이터 공급원 인터페이스 (PRD 5.1).

UI는 adapter.read()가 돌려준 dict만 쓰고 파일·URL·토픽을 직접 보지 않는다.
새 공급원(ROS 2, MQTT 등)은 read()를 가진 클래스 하나와 __init__.py의 등록 한 줄로 추가한다.
"""

from __future__ import annotations

from typing import Protocol


class AdapterError(Exception):
    """이번 주기 읽기 실패. DataManager가 마지막 정상값을 유지한다."""


class BinStatusAdapter(Protocol):
    is_mock: bool

    def read(self) -> dict: ...

    def describe(self) -> str: ...


class EcoMetricsAdapter(Protocol):
    is_mock: bool

    def read(self) -> dict: ...

    def describe(self) -> str: ...


class UnavailableAdapter:
    """공급원이 없거나 허용되지 않을 때. 항상 '값 없음' 스냅샷을 준다."""

    is_mock = False

    def __init__(self, reason: str):
        self.reason = reason

    def read(self) -> dict:
        return {"schema_version": 1, "observed_at": None, "source": "unavailable", "quality": "unavailable"}

    def describe(self) -> str:
        return f"unavailable ({self.reason})"
