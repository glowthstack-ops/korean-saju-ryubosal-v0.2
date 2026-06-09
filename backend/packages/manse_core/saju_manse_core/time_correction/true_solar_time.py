"""Compute true solar time (진태양시) from a normalized local datetime.

Processing order (codex §4.1): standard time → remove DST → longitude correction
→ equation of time → true solar time. Longitude correction and equation of time
are kept as separate fields and never merged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from saju_shared_types.birth_input import TimeCalculationOptions

from .equation_of_time import equation_of_time_minutes
from .longitude_correction import longitude_correction_minutes, standard_meridian
from .time_boundary import hour_branch
from .timezone_resolver import TimezoneResolution


@dataclass
class TimeCorrection:
    civil_datetime: datetime  # local clock time (naive), DST included
    standard_datetime: datetime  # DST removed
    true_solar_datetime: datetime
    final_chart_datetime: datetime  # the datetime used to build the pillars

    standard_meridian: float
    longitude_correction_minutes: float
    equation_of_time_minutes: float

    civil_hour_branch: str
    true_solar_hour_branch: str
    date_changed_by_true_solar_time: bool
    warnings: list[str] = field(default_factory=list)


def compute(
    naive_local: datetime,
    longitude: float,
    tz: TimezoneResolution,
    options: TimeCalculationOptions,
) -> TimeCorrection:
    warnings: list[str] = []

    civil = naive_local

    # 1) Strip DST to reach standard local time (if present and enabled).
    standard = civil
    if tz.dst_applied and options.apply_daylight_saving:
        standard = civil - timedelta(minutes=tz.dst_offset_minutes)

    meridian = standard_meridian(tz.standard_offset_minutes)

    # 2) Longitude correction (standard → local mean solar time).
    lon_corr = (
        longitude_correction_minutes(longitude, tz.standard_offset_minutes)
        if options.apply_longitude_correction
        else 0.0
    )
    mean_solar = standard + timedelta(minutes=lon_corr)

    # 3) Equation of time (mean → apparent/true solar time).
    # 균시차는 출생시각의 고정 천문값이므로 항상 산출해 보고하고, 진태양시 적용만 옵션으로 끈다
    # (미사용 시 보고값은 원값 유지, 진태양시에는 0으로 반영).
    eot = equation_of_time_minutes(mean_solar)
    eot_applied = eot if options.apply_equation_of_time else 0.0
    true_solar = mean_solar + timedelta(minutes=eot_applied)

    final = true_solar if options.apply_true_solar_time else civil

    civil_branch = hour_branch(civil)
    true_branch = hour_branch(true_solar)
    date_changed = true_solar.date() != civil.date()
    if date_changed:
        warnings.append("true_solar_time_changes_date")

    return TimeCorrection(
        civil_datetime=civil,
        standard_datetime=standard,
        true_solar_datetime=true_solar,
        final_chart_datetime=final,
        standard_meridian=meridian,
        longitude_correction_minutes=lon_corr,
        equation_of_time_minutes=eot,
        civil_hour_branch=str(civil_branch),
        true_solar_hour_branch=str(true_branch),
        date_changed_by_true_solar_time=date_changed,
        warnings=warnings,
    )
