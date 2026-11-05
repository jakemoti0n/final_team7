from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from PySide6.QtGui import QPainter

from ..context import AppContext


class Screen:
    """한 화면. build_view()가 표시할 값을 만들고 paint()가 그린다 (값 계산은 Qt 없이 시험 가능)."""

    screen_id = ""
    DEFAULTS: dict[str, Any] = {}

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.cfg: dict = copy.deepcopy(self.DEFAULTS)
        self.reload_config()

    def reload_config(self) -> None:
        self.cfg = self.ctx.screen_config(self.screen_id, self.DEFAULTS)

    def build_view(self, now: datetime) -> dict:
        raise NotImplementedError

    def paint(self, p: QPainter, now: datetime) -> None:
        raise NotImplementedError
