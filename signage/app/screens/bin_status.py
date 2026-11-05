"""화면 B — 일반/재활용 수거함 적재율 (PPT 4~5페이지).

값이 있으면 퍼센트 + 아래부터 채워지는 막대, 없으면 '정보 없음' + 점선 빈 칸. 0%로 대신하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen

from ..bin_resolver import BIN_IDS
from ..renderer.draw import color, draw_badge, rect, sub_rect
from .base import Screen


class BinStatusScreen(Screen):
    screen_id = "bin_status"
    DEFAULTS = {
        "boxes": {
            "general": {"rect": [160, 120, 760, 840], "label_text": "content/text/bin_general_label.txt",
                        "label_default": "일반"},
            "recycling": {"rect": [1000, 120, 760, 840], "label_text": "content/text/bin_recycle_label.txt",
                          "label_default": "재활용"},
        },
        "box": {"corner_radius": 56, "border_width": 8, "border_color": "text", "fill_color": "accent",
                "unavailable_border_color": "muted"},
        "label": {"rect_rel": [0.05, 0.22, 0.9, 0.2], "font": {"size": 120, "weight": "bold", "min_size": 60},
                  "color": "text"},
        "percent": {"rect_rel": [0.05, 0.44, 0.9, 0.26], "font": {"size": 170, "weight": "bold", "min_size": 80},
                    "color": "text", "decimals": 0},
        "unavailable": {"text": "content/text/bin_unavailable.txt", "default": "정보 없음",
                        "font": {"size": 96, "weight": "bold", "min_size": 48}, "color": "muted"},
        "mock_badge": {"text": "MOCK", "rect_rel": [0.66, 0.04, 0.3, 0.07]},
    }

    def build_view(self, now: datetime) -> dict:
        bv = self.ctx.data.bin_view(now)
        unavailable = self.ctx.content.text(self.cfg["unavailable"]["text"], self.cfg["unavailable"]["default"])
        decimals = int(self.cfg["percent"].get("decimals", 0))
        bins = {}
        for bin_id in BIN_IDS:
            box = self.cfg["boxes"][bin_id]
            r = bv.readings[bin_id]
            bins[bin_id] = {
                "label": self.ctx.content.text(box["label_text"], box.get("label_default", bin_id)),
                "available": r.available,
                "text": f"{r.percent:.{decimals}f}%" if r.available else unavailable,
                "fill": r.percent / 100.0 if r.available else None,
            }
        return {"bins": bins, "mock": bv.is_mock}

    def paint(self, p: QPainter, now: datetime) -> None:
        v = self.build_view(now)
        th, c = self.ctx.theme, self.cfg
        for bin_id, b in v["bins"].items():
            outer = rect(c["boxes"][bin_id]["rect"])
            self._paint_box(p, outer, b)
            if v["mock"]:
                draw_badge(p, self.ctx.fonts, sub_rect(outer, c["mock_badge"]["rect_rel"]),
                           c["mock_badge"]["text"], color(th, "demo_badge"), color(th, "background"))

    def _paint_box(self, p: QPainter, outer: QRectF, b: dict) -> None:
        th, c = self.ctx.theme, self.cfg
        radius = float(c["box"]["corner_radius"])
        bw = float(c["box"]["border_width"])
        inner = outer.adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2)
        path = QPainterPath()
        path.addRoundedRect(inner, radius, radius)

        if b["fill"] is not None and b["fill"] > 0:
            h = inner.height() * min(1.0, b["fill"])
            p.save()
            p.setClipPath(path)
            p.fillRect(QRectF(inner.left(), inner.bottom() - h, inner.width(), h),
                       color(th, c["box"]["fill_color"], "accent"))
            p.restore()

        p.save()
        if b["available"]:
            pen = QPen(color(th, c["box"]["border_color"]), bw)
        else:
            pen = QPen(color(th, c["box"]["unavailable_border_color"], "muted"), bw, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.restore()

        lab, pc, un = c["label"], c["percent"], c["unavailable"]
        self.ctx.text.draw(p, sub_rect(outer, lab["rect_rel"]), b["label"], lab["font"], color(th, lab["color"]))
        if b["available"]:
            self.ctx.text.draw(p, sub_rect(outer, pc["rect_rel"]), b["text"], pc["font"], color(th, pc["color"]))
        else:
            self.ctx.text.draw(p, sub_rect(outer, pc["rect_rel"]), b["text"], un["font"],
                               color(th, un["color"], "muted"))
