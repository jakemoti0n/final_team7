"""1920×1080 설계 좌표에서 쓰는 그리기 도구: 색, 사각형, 크기 맞춤 텍스트, 배지, 이미지."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QPainterPath

from ..content_loader import FontBook

_ALIGN_H = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight}


def color(theme: dict, ref: str | None, fallback: str = "text") -> QColor:
    """'accent' 같은 theme 이름 또는 '#RRGGBB'."""
    value = theme.get(ref or fallback, ref) if ref else theme.get(fallback, "#000000")
    c = QColor(str(value))
    return c if c.isValid() else QColor(theme.get(fallback, "#000000"))


def rect(values, default=(0, 0, 100, 100)) -> QRectF:
    try:
        x, y, w, h = (float(v) for v in values)
    except (TypeError, ValueError):
        x, y, w, h = default
    return QRectF(x, y, max(1.0, w), max(1.0, h))


def sub_rect(outer: QRectF, rel) -> QRectF:
    """outer 안의 비율 좌표 [x, y, w, h] (0~1)."""
    try:
        x, y, w, h = (float(v) for v in rel)
    except (TypeError, ValueError):
        return QRectF(outer)
    return QRectF(outer.x() + x * outer.width(), outer.y() + y * outer.height(),
                  w * outer.width(), h * outer.height())


class TextFitter:
    """긴 문구는 줄바꿈하고, 그래도 넘치면 min_size까지 글자를 줄인다 (잘림 방지, PRD 8절).

    spec.wrap: "wrap_first"(기본, 줄바꿈 먼저) | "shrink_first"(TXT의 줄바꿈을 지키고 글자를 먼저 줄임)
    """

    def __init__(self, fonts: FontBook):
        self.fonts = fonts
        self._cache: dict[tuple, int] = {}

    def draw(self, p: QPainter, r: QRectF, text: str, spec: dict, col: QColor,
             align: str = "center", valign: str = "center") -> None:
        if not text:
            return
        flags = _ALIGN_H.get(align, Qt.AlignmentFlag.AlignHCenter) | {
            "top": Qt.AlignmentFlag.AlignTop, "bottom": Qt.AlignmentFlag.AlignBottom,
        }.get(valign, Qt.AlignmentFlag.AlignVCenter)
        wrap = Qt.TextFlag.TextWordWrap
        size, fits = (0, False)
        if spec.get("wrap") == "shrink_first":
            # 작성자가 넣은 줄바꿈을 지키도록 줄바꿈 없이 먼저 줄여 보고, 안 되면 줄바꿈
            size, fits = self._fit_size(r, text, spec, int(flags), Qt.TextFlag(0))
            if fits:
                wrap = Qt.TextFlag(0)
        if not fits:
            size, fits = self._fit_size(r, text, spec, int(flags), wrap)
        p.setFont(self.fonts.font(spec, size))
        p.setPen(col)
        # 최소 크기에서도 넘치면(띄어쓰기 없는 긴 낱말) 글자 단위로 줄바꿈
        extra = wrap if fits else Qt.TextFlag.TextWrapAnywhere
        p.drawText(r, int(flags) | int(extra), text)

    def _fit_size(self, r: QRectF, text: str, spec: dict, flags: int, wrap) -> tuple[int, bool]:
        size = int(spec.get("size", 48))
        min_size = int(spec.get("min_size", size))
        key = (text, round(r.width()), round(r.height()), size, min_size, int(wrap), str(spec.get("weight")),
               spec.get("family"), self.fonts.family)
        if key in self._cache:
            return self._cache[key]
        min_size = min(min_size, size)
        chosen = (min_size, False)
        s = size
        while True:
            fm = QFontMetricsF(self.fonts.font(spec, s))
            br = fm.boundingRect(r, flags | int(wrap), text)
            if br.height() <= r.height() + 0.5 and br.width() <= r.width() + 0.5:
                chosen = (s, True)
                break
            if s <= min_size:
                break
            s = max(min_size, s - max(2, s // 20))
        if len(self._cache) > 256:
            self._cache.clear()
        self._cache[key] = chosen
        return chosen


def draw_badge(p: QPainter, fonts: FontBook, r: QRectF, text: str, bg: QColor, fg: QColor) -> None:
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    radius = r.height() / 2
    p.drawRoundedRect(r, radius, radius)
    p.setPen(fg)
    p.setFont(fonts.font({"size": int(r.height() * 0.55), "weight": "bold"}))
    p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), text)
    p.restore()


class ImagePainter:
    """이미지를 비율 유지로 영역에 맞춰 그린다. 실제 화면 픽셀 크기로 한 번 줄여 캐시 (Pi 부하 감소)."""

    def __init__(self):
        self._cache: dict[tuple, QImage] = {}

    def draw(self, p: QPainter, r: QRectF, img: QImage, corner_radius: float = 0) -> None:
        if img is None or img.isNull():
            return
        scaled_size = img.size().scaled(r.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF(0, 0, scaled_size.width(), scaled_size.height())
        target.moveCenter(r.center())
        t = p.worldTransform()
        dev_w = max(1, round(target.width() * abs(t.m11())))
        dev_h = max(1, round(target.height() * abs(t.m22())))
        key = (img.cacheKey(), dev_w, dev_h)
        scaled = self._cache.get(key)
        if scaled is None:
            if len(self._cache) > 12:
                self._cache.clear()
            scaled = img.scaled(dev_w, dev_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            self._cache[key] = scaled
        p.save()
        if corner_radius > 0:
            path = QPainterPath()
            path.addRoundedRect(target, corner_radius, corner_radius)
            p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        p.drawImage(target, scaled)
        p.restore()
