"""Normalize raw birth input into a solar date + naive local datetime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from saju_shared_types.birth_input import BirthInput

from ..calendar.lunar_solar_converter import lunar_to_solar


@dataclass
class NormalizedInput:
    solar_date: date
    naive_local_datetime: datetime
    time_known: bool
    lunar_converted_solar_date: date | None
    is_leap_month: bool | None
    warnings: list[str] = field(default_factory=list)


def normalize(birth: BirthInput) -> NormalizedInput:
    warnings: list[str] = []
    lunar_solar: date | None = None

    if birth.calendar_type == "lunar":
        lunar_solar = lunar_to_solar(birth.birth_date, bool(birth.is_leap_month))
        solar_date = lunar_solar
    else:
        solar_date = birth.birth_date

    time_known = birth.birth_time is not None and not birth.birth_time_unknown
    # Unknown time anchors at noon for date-stable calculations; the hour pillar
    # is suppressed downstream and a warning is attached.
    local_time = birth.birth_time if time_known else time(12, 0)
    if not time_known:
        warnings.append("time_unknown: hour pillar suppressed; noon used for date stability")

    naive = datetime.combine(solar_date, local_time or time(12, 0))
    return NormalizedInput(
        solar_date=solar_date,
        naive_local_datetime=naive,
        time_known=time_known,
        lunar_converted_solar_date=lunar_solar,
        is_leap_month=birth.is_leap_month if birth.calendar_type == "lunar" else None,
        warnings=warnings,
    )
