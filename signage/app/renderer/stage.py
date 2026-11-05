"""전체 화면 위젯: 1920×1080 설계 좌표를 비율 유지로 실제 창에 맞추고, 화면을 순환시킨다."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QPainter
from PySide6.QtWidgets import QWidget

from ..context import AppContext
from ..screens.base import Screen
from ..util import ChangeLogger
from .draw import color, draw_badge

log = logging.getLogger("signage.stage")


class Stage(QWidget):
    def __init__(self, ctx: AppContext, screens: dict[str, Screen], pinned: str | None = None):
        super().__init__()
        self.ctx = ctx
        self.screens = screens
        self.pinned = pinned  # --screen: 한 화면 고정 (미리보기용)
        self.design_w = int(ctx.cfg["display"]["width"])
        self.design_h = int(ctx.cfg["display"]["height"])
        self.index = 0
        self.paused = False
        self._errors = ChangeLogger(log)
        self.setWindowTitle("Automaton 하단 디스플레이")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        if ctx.cfg["display"].get("hide_cursor", True):
            self.setCursor(Qt.CursorShape.BlankCursor)

        # 초 경계에 맞춰 다시 그린다 (분이 바뀌는 순간 시계가 정확히 바뀌도록)
        self._tick = QTimer(self)
        self._tick.setSingleShot(True)
        self._tick.timeout.connect(self._on_tick)
        self._rotate = QTimer(self)
        self._rotate.setSingleShot(True)
        self._rotate.timeout.connect(self.next_screen)
        self._reload = QTimer(self)
        self._reload.timeout.connect(self._on_reload)
        self._reload.start(int(float(ctx.cfg["content"]["reload_interval_seconds"]) * 1000))

        self._schedule_tick()
        self._start_rotation_timer()
        log.info("화면 순환: %s", " → ".join(f"{i['id']}({i['duration_seconds']}s)" for i in self.rotation))

    # ------------------------------------------------------------ 순환

    @property
    def rotation(self) -> list[dict]:
        if self.pinned:
            return [{"id": self.pinned, "duration_seconds": 3600}]
        return [r for r in self.ctx.cfg["rotation"] if r["id"] in self.screens] or \
            [{"id": next(iter(self.screens)), "duration_seconds": 12}]

    def current_screen(self) -> Screen:
        rot = self.rotation
        self.index %= len(rot)
        return self.screens[rot[self.index]["id"]]

    def _start_rotation_timer(self) -> None:
        rot = self.rotation
        self.index %= len(rot)
        if not self.paused:
            self._rotate.start(int(float(rot[self.index]["duration_seconds"]) * 1000))

    def next_screen(self, step: int = 1) -> None:
        self.index = (self.index + step) % len(self.rotation)
        self._start_rotation_timer()
        self.update()

    def _schedule_tick(self) -> None:
        ms_to_next_second = 1000 - int(time.time() * 1000) % 1000
        self._tick.start(ms_to_next_second + 5)

    def _on_tick(self) -> None:
        self.update()
        self._schedule_tick()

    def _on_reload(self) -> None:
        try:
            self.ctx.content.refresh()
            app_changed, screen_ids = self.ctx.config_changed()
            if app_changed and self.ctx.reload_app_config():
                self._reload.setInterval(int(float(self.ctx.cfg["content"]["reload_interval_seconds"]) * 1000))
                screen_ids = set(self.screens)  # 테마가 바뀌었을 수 있으니 전부
            for sid in screen_ids:
                if sid in self.screens:
                    self.screens[sid].reload_config()
                    log.info("화면 설정 반영: %s", sid)
        except Exception:
            log.exception("콘텐츠/설정 재로딩 중 오류 (표시는 계속)")

    # ------------------------------------------------------------ 그리기

    def render_scene(self, p: QPainter, screen: Screen, now: datetime) -> None:
        """설계 좌표(1920×1080)에 화면 하나를 그린다. 화면 오류는 여기서 막고 배경만 남긴다."""
        th = self.ctx.theme
        full = QRectF(0, 0, self.design_w, self.design_h)
        p.save()
        p.setClipRect(full)
        p.fillRect(full, color(th, "background"))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        try:
            p.save()
            screen.paint(p, now)
            p.restore()
            self._errors.log(screen.screen_id, logging.INFO, None)
        except Exception as e:
            p.restore()
            p.fillRect(full, color(th, "background"))
            if self._errors.log(screen.screen_id, logging.ERROR, f"화면 {screen.screen_id} 그리기 실패: {e!r}"):
                log.exception("상세")
        if self.ctx.demo and self.ctx.cfg["mock_data"].get("visible_demo_badge", True):
            draw_badge(p, self.ctx.fonts, QRectF(self.design_w * 0.95 - 200, self.design_h * 0.95 - 56, 200, 56), "DEMO",
                       color(th, "demo_badge"), color(th, "background"))
        p.restore()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), color(self.ctx.theme, "letterbox"))
        scale = min(self.width() / self.design_w, self.height() / self.design_h)
        p.translate((self.width() - self.design_w * scale) / 2, (self.height() - self.design_h * scale) / 2)
        p.scale(scale, scale)
        self.render_scene(p, self.current_screen(), self.ctx.clock.now())
        p.end()

    # ------------------------------------------------------------ 키 (점검용)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        k = e.key()
        if k in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_Space):
            self.next_screen(1)
        elif k == Qt.Key.Key_Left:
            self.next_screen(-1)
        elif k == Qt.Key.Key_P:
            self.paused = not self.paused
            log.info("순환 %s", "일시정지" if self.paused else "재개")
            if self.paused:
                self._rotate.stop()
            else:
                self._start_rotation_timer()
        elif k == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        else:
            super().keyPressEvent(e)
