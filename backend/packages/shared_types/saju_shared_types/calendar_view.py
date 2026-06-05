"""간지달력 (page-view 서비스) schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CalendarDay(BaseModel):
    date: date
    weekday: int  # 0=Mon … 6=Sun
    day_ganji: str  # 한자 (예: 庚申)
    day_ganji_ko: str  # 한글 (예: 경신)
    month_ganji: str
    month_ganji_ko: str
    year_ganji: str
    year_ganji_ko: str
    solar_term: str | None = None  # 그날에 절기가 들면 절기명
    lunar_date: str  # 음력 'YYYY-MM-DD'
    is_leap_month: bool = False  # 음력 윤달 여부
    naeum: str | None = None  # 일주 납음
    year_zodiac: str  # 띠 (년지 기준)


class SolarTermMark(BaseModel):
    date: date
    name: str


class CalendarMonth(BaseModel):
    year: int
    month: int
    days: list[CalendarDay] = Field(default_factory=list)
    solar_terms: list[SolarTermMark] = Field(default_factory=list)
