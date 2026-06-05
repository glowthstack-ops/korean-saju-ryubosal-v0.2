"""간지달력 service."""

from __future__ import annotations

from datetime import date

from saju_manse_core.calendar.ganji_calendar import build_month
from saju_shared_types.calendar_view import CalendarMonth


def month(year: int, month: int) -> CalendarMonth:
    if not 1 <= month <= 12:
        raise ValueError("month must be 1..12")
    return CalendarMonth(**build_month(year, month))


def today_month() -> CalendarMonth:
    t = date.today()
    return month(t.year, t.month)
