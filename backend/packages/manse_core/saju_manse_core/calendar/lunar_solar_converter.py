"""Lunar/leap-month → solar conversion via ``korean_lunar_calendar`` (KASI data)."""

from __future__ import annotations

from datetime import date

from korean_lunar_calendar import KoreanLunarCalendar


def solar_to_lunar(solar: date) -> tuple[str, bool]:
    """Return (lunar ISO date 'YYYY-MM-DD', is_leap_month) for a solar date."""
    cal = KoreanLunarCalendar()
    if not cal.setSolarDate(solar.year, solar.month, solar.day):
        raise ValueError(f"solar date out of range: {solar.isoformat()}")
    iso = f"{cal.lunarYear:04d}-{cal.lunarMonth:02d}-{cal.lunarDay:02d}"
    return iso, bool(cal.isIntercalation)


def lunar_to_solar(lunar: date, is_leap_month: bool) -> date:
    """Convert a Korean lunar date to the proleptic Gregorian (solar) date."""
    cal = KoreanLunarCalendar()
    ok = cal.setLunarDate(lunar.year, lunar.month, lunar.day, is_leap_month)
    if not ok:
        raise ValueError(
            f"invalid lunar date {lunar.isoformat()} (leap={is_leap_month})"
        )
    return date.fromisoformat(cal.SolarIsoFormat())
