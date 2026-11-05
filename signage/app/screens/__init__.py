from __future__ import annotations

from ..context import AppContext
from .base import Screen
from .bin_status import BinStatusScreen
from .clock_schedule import ClockScheduleScreen
from .eco_feedback import EcoFeedbackScreen

SCREEN_CLASSES = (ClockScheduleScreen, BinStatusScreen, EcoFeedbackScreen)


def build_screens(ctx: AppContext) -> dict[str, Screen]:
    return {cls.screen_id: cls(ctx) for cls in SCREEN_CLASSES}
