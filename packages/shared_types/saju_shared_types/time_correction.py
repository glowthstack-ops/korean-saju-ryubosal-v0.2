"""Time-correction and solar-term schemas (codex spec §4.2, §5.1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class TimeCorrectionResult(BaseModel):
    input_datetime_local: datetime
    calendar_type: Literal["solar", "lunar"]
    lunar_converted_solar_date: date | None = None
    is_leap_month: bool | None = None

    birth_place_name: str
    latitude: float
    longitude: float
    timezone: str
    timezone_offset_minutes: int
    daylight_saving_applied: bool
    local_time_status: Literal["valid", "ambiguous", "nonexistent"] = "valid"

    standard_meridian: float
    longitude_correction_minutes: float
    equation_of_time_minutes: float
    true_solar_datetime: datetime
    final_chart_datetime: datetime

    standard_time_hour_pillar: str | None = None
    true_solar_time_hour_pillar: str | None = None
    hour_pillar_changed_by_true_solar_time: bool = False
    date_changed_by_true_solar_time: bool = False

    day_boundary_rule: str
    ja_hour_rule: str
    warnings: list[str] = []


class SolarTermBasis(BaseModel):
    previous_term_name: str
    previous_term_datetime: datetime
    next_term_name: str
    next_term_datetime: datetime
    month_branch: str
    month_pillar_confirmed: str
    birth_after_month_term: bool = True
    solar_terms_version: str
