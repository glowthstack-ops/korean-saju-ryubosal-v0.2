"""Orchestrate BirthInput → time correction → solar terms → 원국 → ManseV2Result."""

from __future__ import annotations

import hashlib
from datetime import UTC

from saju_manse_analysis import analyze

from saju_manse_core.calendar.solar_terms import get_table
from saju_manse_core.pillars import four_pillars
from saju_manse_core.pillars.day_pillar import day_pillar
from saju_manse_core.pillars.hour_pillar import hour_pillar_for_branch
from saju_manse_core.time_correction import true_solar_time
from saju_manse_core.time_correction.input_normalizer import normalize
from saju_manse_core.time_correction.timezone_resolver import TZDATA_VERSION, resolve
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.constants import (
    ENGINE_VERSION,
    RULESET_VERSION,
    STEM_YINYANG,
)
from saju_shared_types.enums import Branch, Stem, YinYang
from saju_shared_types.manse_result import EngineMetadata, ManseV2Result
from saju_shared_types.time_correction import SolarTermBasis, TimeCorrectionResult

from ..location import resolve as resolve_location


def _chart_id(birth: BirthInput) -> str:
    canonical = "|".join(
        str(x)
        for x in (
            birth.calendar_type,
            birth.is_leap_month,
            birth.birth_date,
            birth.birth_time,
            birth.birth_time_unknown,
            birth.birth_place_name,
            birth.latitude,
            birth.longitude,
            birth.timezone,
            birth.gender,
            birth.time_options.model_dump(),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _daewoon_direction(birth: BirthInput, year_stem: Stem) -> str | None:
    """양남음녀 順行 / 음남양녀 逆行 (direction only; full 대운 is a later phase)."""
    if birth.daewoon_direction_basis == "manual":
        return birth.manual_daewoon_direction
    if birth.gender not in ("male", "female"):
        return None
    year_yang = STEM_YINYANG[year_stem] is YinYang.YANG
    male = birth.gender == "male"
    forward = (male and year_yang) or (not male and not year_yang)
    return "forward" if forward else "backward"


def calculate(birth: BirthInput) -> ManseV2Result:
    table = get_table()
    opts = birth.time_options

    loc = resolve_location(
        birth.birth_place_name, birth.latitude, birth.longitude, birth.timezone
    )
    norm = normalize(birth)
    tz = resolve(norm.naive_local_datetime, loc.iana_timezone)
    tc = true_solar_time.compute(norm.naive_local_datetime, loc.longitude, tz, opts)

    absolute_instant = tz.aware_datetime  # civil instant, tz-aware
    pillars, term_info = four_pillars.compute(
        absolute_instant=absolute_instant,
        final_local=tc.final_chart_datetime,
        time_known=norm.time_known,
        day_boundary_rule=opts.day_boundary_rule,
        ja_hour_rule=opts.ja_hour_rule,
        table=table,
        warnings=norm.warnings + tz.warnings + tc.warnings,
    )

    # Civil vs true-solar hour-pillar comparison (only meaningful with a time).
    std_hp: str | None = None
    ts_hp: str | None = None
    hour_changed = False
    if norm.time_known:
        civil_day_stem, _ = day_pillar(
            tc.civil_datetime, opts.day_boundary_rule, opts.ja_hour_rule
        )
        ts_day_stem, _ = day_pillar(
            tc.true_solar_datetime, opts.day_boundary_rule, opts.ja_hour_rule
        )
        cs, cb = hour_pillar_for_branch(civil_day_stem, Branch(tc.civil_hour_branch))
        ts_s, ts_b = hour_pillar_for_branch(ts_day_stem, Branch(tc.true_solar_hour_branch))
        std_hp = f"{cs}{cb}"
        ts_hp = f"{ts_s}{ts_b}"
        hour_changed = std_hp != ts_hp
        if hour_changed:
            pillars.warnings.append(
                f"true_solar_time_changes_hour: {std_hp}(일반시) → {ts_hp}(진태양시)"
            )

    time_correction = TimeCorrectionResult(
        input_datetime_local=norm.naive_local_datetime,
        calendar_type=birth.calendar_type,
        lunar_converted_solar_date=norm.lunar_converted_solar_date,
        is_leap_month=norm.is_leap_month,
        birth_place_name=loc.name,
        latitude=loc.latitude,
        longitude=loc.longitude,
        timezone=loc.iana_timezone,
        timezone_offset_minutes=tz.total_offset_minutes,
        daylight_saving_applied=tz.dst_applied and opts.apply_daylight_saving,
        local_time_status=tz.local_time_status,
        standard_meridian=tc.standard_meridian,
        longitude_correction_minutes=round(tc.longitude_correction_minutes, 4),
        equation_of_time_minutes=round(tc.equation_of_time_minutes, 4),
        true_solar_datetime=tc.true_solar_datetime,
        final_chart_datetime=tc.final_chart_datetime,
        standard_time_hour_pillar=std_hp,
        true_solar_time_hour_pillar=ts_hp,
        hour_pillar_changed_by_true_solar_time=hour_changed,
        date_changed_by_true_solar_time=tc.date_changed_by_true_solar_time,
        day_boundary_rule=opts.day_boundary_rule,
        ja_hour_rule=opts.ja_hour_rule,
        warnings=tc.warnings,
    )

    prev_term, next_term = term_info.prev_term, term_info.next_term
    solar_basis = SolarTermBasis(
        previous_term_name=prev_term[1],
        previous_term_datetime=prev_term[0],
        next_term_name=next_term[1],
        next_term_datetime=next_term[0],
        month_branch=str(term_info.month_branch),
        month_pillar_confirmed=pillars.month.ganji,
        birth_after_month_term=True,
        solar_terms_version=table.version,
    )

    year_stem = Stem(pillars.year.stem)
    input_summary = {
        "calendar_type": birth.calendar_type,
        "birth_date": birth.birth_date.isoformat(),
        "birth_time": birth.birth_time.isoformat() if birth.birth_time else None,
        "birth_time_unknown": not norm.time_known,
        "birth_place_name": loc.name,
        "gender": birth.gender,
        "daewoon_direction": _daewoon_direction(birth, year_stem),
    }

    metadata = EngineMetadata(
        engine_version=ENGINE_VERSION,
        ruleset_version=RULESET_VERSION,
        tzdata_version=TZDATA_VERSION,
        solar_terms_version=table.version,
    )

    force = analyze(pillars)

    return ManseV2Result(
        chart_id=_chart_id(birth),
        input_summary=input_summary,
        time_correction=time_correction,
        solar_term_basis=solar_basis,
        pillars=pillars,
        force_analysis=force,
        metadata=metadata,
        trace={
            "absolute_instant_utc": absolute_instant.astimezone(UTC).isoformat(),
            "final_chart_datetime": tc.final_chart_datetime.isoformat(),
            "standard_datetime": tc.standard_datetime.isoformat(),
        },
    )
