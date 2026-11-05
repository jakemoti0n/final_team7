"""화면 C — 환경 피드백(Eco Feedback): 나무 3상태 (PPT 6~8페이지, 원본 제목 'Green Washing').

문구와 이미지는 상태별 '묶음'으로 바뀐다: 두 파일을 모두 정상으로 읽었을 때만 새 묶음으로 교체하고,
아니면 마지막 정상 묶음(없으면 기본 문구 + 그림 자리)을 쓴다.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPen

from ..eco_state_resolver import STATES
from ..renderer.draw import color, draw_badge, rect, sub_rect
from .base import Screen

DEFAULT_TEXTS = {
    "initial": "여러분의 재활용이 이 나무를\n자라게 해요.",
    "negative": "분리수거가 잘 안되고 있어요.\n더욱 노력해 주세요.",
    "positive": "분리수거가 잘 되고 있어요.\n자연이 고마워 해요.",
}


class EcoFeedbackScreen(Screen):
    screen_id = "eco_feedback"
    DEFAULTS = {
        "message": {"rect": [96, 200, 800, 520], "font": {"size": 84, "weight": "bold", "min_size": 44,
                                                          "wrap": "shrink_first"},
                    "align": "center", "color": "text"},
        "pending": {"show": True, "rect": [96, 780, 800, 110], "text": "content/text/eco_pending.txt",
                    "default": "평가 준비 중", "font": {"size": 52, "min_size": 28}, "color": "muted"},
        "image": {"rect": [944, 100, 880, 880], "corner_radius": 36},
        "states": {
            "initial": {"text": "content/text/eco_initial.txt", "image": "assets/images/tree_initial.png"},
            "positive": {"text": "content/text/eco_positive.txt", "image": "assets/images/tree_positive.png"},
            "negative": {"text": "content/text/eco_negative.txt", "image": "assets/images/tree_negative.png"},
        },
        "mock_badge": {"text": "MOCK", "rect_rel": [0.74, 0.03, 0.23, 0.07]},
    }

    def __init__(self, ctx):
        self._bundles: dict[str, tuple[str, QImage | None]] = {}
        super().__init__(ctx)

    def _bundle(self, state: str) -> tuple[str, QImage | None]:
        files = self.cfg["states"].get(state, {})
        text_rel, image_rel = files.get("text"), files.get("image")
        text = self.ctx.content.text(text_rel, "")
        image = self.ctx.content.image(image_rel)
        if self.ctx.content.is_ok(text_rel) and self.ctx.content.is_ok(image_rel):
            self._bundles[state] = (text, image)
        return self._bundles.get(state, (DEFAULT_TEXTS[state], None))

    def build_view(self, now: datetime) -> dict:
        result = self.ctx.data.eco_result(now)
        state = result.state if result.state in STATES else "initial"
        text, image = self._bundle(state)
        pending = ""
        if not result.evaluated and self.cfg["pending"].get("show", True):
            pending = self.ctx.content.text(self.cfg["pending"]["text"], self.cfg["pending"]["default"])
        return {"state": state, "text": text, "image": image, "pending": pending,
                "mock": self.ctx.data.eco_adapter.is_mock}

    def paint(self, p: QPainter, now: datetime) -> None:
        v = self.build_view(now)
        th, c = self.ctx.theme, self.cfg
        m = c["message"]
        self.ctx.text.draw(p, rect(m["rect"]), v["text"], m["font"], color(th, m["color"]), m["align"])
        if v["pending"]:
            pc = c["pending"]
            self.ctx.text.draw(p, rect(pc["rect"]), v["pending"], pc["font"], color(th, pc["color"], "muted"))
        img_rect = rect(c["image"]["rect"])
        if v["image"] is not None:
            self.ctx.images.draw(p, img_rect, v["image"], float(c["image"].get("corner_radius", 0)))
        else:
            # 그림 파일을 한 번도 못 읽었을 때: 빈 자리만 표시
            p.save()
            p.setPen(QPen(color(th, "muted"), 6, Qt.PenStyle.DashLine))
            radius = float(c["image"].get("corner_radius", 0))
            p.drawRoundedRect(img_rect.adjusted(3, 3, -3, -3), radius, radius)
            p.restore()
        if v["mock"]:
            draw_badge(p, self.ctx.fonts, sub_rect(img_rect, c["mock_badge"]["rect_rel"]), c["mock_badge"]["text"],
                       color(th, "demo_badge"), color(th, "background"))
