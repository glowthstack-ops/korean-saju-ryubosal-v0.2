"""간지달력 service."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from saju_manse_core.calendar.ganji_calendar import build_month
from saju_shared_types.calendar_view import CalendarMonth

_KST = ZoneInfo("Asia/Seoul")


def month(year: int, month: int) -> CalendarMonth:
    if not 1 <= month <= 12:
        raise ValueError("month must be 1..12")
    return CalendarMonth(**build_month(year, month))


def today_month() -> CalendarMonth:
    # 달력은 KST 만세력 기준 → '오늘'도 KST로 고정(서버 리전 무관).
    t = datetime.now(_KST).date()
    return month(t.year, t.month)
