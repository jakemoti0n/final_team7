"""화면 A — 날짜·시각과 행사 일정 (PPT 3페이지)."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtGui import QPainter

from ..renderer.draw import color, rect
from ..schedule import Selected
from ..util import format_dt
from .base import Screen


class ClockScheduleScreen(Screen):
    screen_id = "clock_schedule"
    DEFAULTS = {
        "date": {"rect": [96, 60, 860, 200], "font": {"size": 140, "weight": "bold"}, "align": "left",
                 "color": "text", "format": "{year}-{month:02d}-{day:02d}"},
        "time": {"rect": [964, 60, 860, 200], "font": {"size": 140, "weight": "bold"}, "align": "right",
                 "color": "text", "format": "{ampm} {hour12}:{minute:02d}"},
        "divider": {"show": True, "rect": [96, 290, 1728, 6], "color": "accent"},
        "status_label": {"rect": [96, 330, 1728, 110], "font": {"size": 72, "weight": "bold"},
                         "align": "center", "color": "accent",
                         "ongoing_text": "content/text/schedule_ongoing_label.txt",
                         "upcoming_text": "content/text/schedule_upcoming_label.txt"},
        "event": {"rect": [96, 450, 1728, 570], "font": {"size": 140, "weight": "bold", "min_size": 56},
                  "align": "center", "color": "text",
                  "line_format": "{when}{start} – {title}{location_part}",
                  "location_format": " ({location})",
                  "time_format": "{ampm} {hour12}:{minute:02d}",
                  "when_today": "", "when_tomorrow": "내일 ",
                  "when_other": "{month}월 {day}일({weekday}) "},
        "empty": {"text": "content/text/schedule_empty.txt", "font": {"size": 110, "weight": "bold",
                                                                       "min_size": 56},
                  "color": "muted"},
    }

    def _event_line(self, sel: Selected, now: datetime) -> str:
        ev, c = sel.event, self.cfg["event"]
        start_day = ev.start.date()
        if sel.status == "ongoing" or start_day == now.date():
            when = c["when_today"]
        elif start_day == now.date() + timedelta(days=1):
            when = c["when_tomorrow"]
        else:
            when = format_dt(c["when_other"], ev.start)
        location_part = c["location_format"].format(location=ev.location) if ev.location else ""
        try:
            return c["line_format"].format(when=when, start=format_dt(c["time_format"], ev.start),
                                           title=ev.title, location_part=location_part,
                                           location=ev.location or "")
        except (KeyError, ValueError, IndexError):
            return f"{when}{format_dt(c['time_format'], ev.start)} – {ev.title}{location_part}"

    def build_view(self, now: datetime) -> dict:
        sv = self.ctx.data.schedule_view(now)
        view = {
            "date": format_dt(self.cfg["date"]["format"], now),
            "time": format_dt(self.cfg["time"]["format"], now),
            "label": "",
            "lines": [],
            "empty_text": "",
        }
        if sv.selected:
            lab = self.cfg["status_label"]
            key = "ongoing_text" if sv.selected[0].status == "ongoing" else "upcoming_text"
            view["label"] = self.ctx.content.text(lab[key], "")
            view["lines"] = [self._event_line(s, now) for s in sv.selected]
        else:
            view["empty_text"] = self.ctx.content.text(self.cfg["empty"]["text"], "예정된 행사가 없습니다.")
        return view

    def paint(self, p: QPainter, now: datetime) -> None:
        v = self.build_view(now)
        th, c, tx = self.ctx.theme, self.cfg, self.ctx.text
        for key in ("date", "time"):
            tx.draw(p, rect(c[key]["rect"]), v[key], c[key]["font"], color(th, c[key]["color"]),
                    c[key]["align"])
        if c["divider"].get("show", True):
            p.fillRect(rect(c["divider"]["rect"]), color(th, c["divider"]["color"], "accent"))
        if v["lines"]:
            lab = c["status_label"]
            tx.draw(p, rect(lab["rect"]), v["label"], lab["font"], color(th, lab["color"], "accent"),
                    lab["align"])
            ev = c["event"]
            tx.draw(p, rect(ev["rect"]), "\n".join(v["lines"]), ev["font"], color(th, ev["color"]),
                    ev["align"])
        else:
            em = c["empty"]
            tx.draw(p, rect(c["event"]["rect"]), v["empty_text"], em["font"], color(th, em["color"], "muted"),
                    c["event"]["align"])
