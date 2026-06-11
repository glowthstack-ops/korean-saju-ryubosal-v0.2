"""Orchestrate BirthInput → time correction → solar terms → 원국 → ManseV2Result."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.luck import (
    compute_luck_cycles,
    daily_luck_for_month,
    monthly_luck_for_year,
)
from saju_manse_calibration import generate_calibration, score_calibration

from saju_manse_core.calendar.solar_terms import get_table
from saju_manse_core.pillars import four_pillars
from saju_manse_core.pillars.day_pillar import day_pillar
from saju_manse_core.pillars.hour_pillar import hour_pillar_for_branch
from saju_manse_core.time_correction import true_solar_time
from saju_manse_core.time_correction.input_normalizer import normalize
from saju_manse_core.time_correction.timezone_resolver import TZDATA_VERSION, resolve
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import CalibrationResult, FeedbackAnswer
from saju_shared_types.constants import (
    ENGINE_VERSION,
    RULESET_VERSION,
    STEM_YINYANG,
)
from saju_shared_types.enums import Branch, Stem, YinYang
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import EngineMetadata, ManseV2Result
from saju_shared_types.time_correction import SolarTermBasis, TimeCorrectionResult

from ..location import resolve as resolve_location


def _chart_id(birth: BirthInput) -> str:
    """Stable identity for a chart + its calibration question set.

    Identity contract: same person (birth date/time/calendar/leap-month/gender/
    location) + same calculation options (time_options, 대운 방향 설정) + same
    reference YEAR → same chart_id.

    The reference date is hashed at YEAR granularity on purpose: the frontend
    sends ``reference_date = today`` on every visit, while the calibration
    question set depends only on the reference *year*
    (``generate_calibration(..., reference_date.year)``). Hashing the full date
    would silently invalidate client-side calibration answers keyed by chart_id
    the very next day. Full-date-dependent output (현재 나이 기준 세운/월운/일운
    anchoring) is NOT part of chart identity.
    """
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
            birth.daewoon_direction_basis,
            birth.manual_daewoon_direction,
            birth.reference_date.year if birth.reference_date is not None else None,
            birth.time_options.model_dump(),
            birth.chart_variant,
            birth.twin_shift,
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


def _term_basis_instant(birth: BirthInput, tc, tz) -> datetime:
    """절기 경계 비교 기준.

    진태양시 적용 시 원국의 일·시뿐 아니라 년·월 절기 경계와 대운수도 같은
    chart datetime 기준으로 맞춘다. ``final_chart_datetime``은 naive이므로 출생지
    timezone을 붙여 solar-term table의 UTC instant와 비교 가능한 aware datetime으로 만든다.
    """
    if birth.time_options.apply_true_solar_time:
        return tc.final_chart_datetime.replace(tzinfo=tz.aware_datetime.tzinfo)
    return tz.aware_datetime


def _luck_role_sets(y) -> tuple[set[str], set[str]]:
    """운 판정은 검증 전이라도 최종 역할 배정(용·희 / 기·구)을 우선 사용한다."""
    final = y.final or {}
    useful = {v for v in (final.get("yongsin"), final.get("heesin")) if v}
    unfavorable = {v for v in (final.get("gisin"), final.get("gusin")) if v}
    if not useful:
        useful = {c.element for c in y.useful_candidates}
    if not unfavorable:
        unfavorable = {c.element for c in y.unfavorable_candidates}
    return useful, unfavorable


def _hour_boundary_diagnostics(tc, time_known: bool) -> tuple[list[str], dict]:
    """Flag minute-sensitive hour/day-boundary cases without changing pillars."""
    if not time_known:
        return ["time_unknown: 시주·시지 기반 관계/신살은 확정할 수 없습니다."], {
            "time_unknown": True
        }
    dt = tc.final_chart_datetime
    minutes = dt.hour * 60 + dt.minute + dt.second / 60
    # Hour branches turn every odd hour: 23, 01, 03 ... 21. Include 23:00 of the
    # previous day as -60 minutes so births just after midnight are measured well.
    boundaries = [-60] + [60, 180, 300, 420, 540, 660, 780, 900, 1020, 1140, 1260, 1380]
    closest = min(boundaries, key=lambda b: abs(minutes - b))
    delta = round(minutes - closest, 2)
    abs_delta = abs(delta)
    warnings: list[str] = []
    if abs_delta <= 10:
        warnings.append(f"hour_boundary_sensitive: 시주 경계 {abs_delta:.1f}분 이내")
    day_delta = min(abs(minutes), abs(minutes - 24 * 60), abs(minutes - 23 * 60))
    if day_delta <= 10:
        warnings.append(f"day_boundary_sensitive: 일주/자시 경계 {day_delta:.1f}분 이내")
    return warnings, {
        "time_unknown": False,
        "minutes_from_nearest_hour_boundary": delta,
        "within_10_minutes": abs_delta <= 10,
    }


# In-process memoization of calculate(). calibrate_feedback / luck_months /
# luck_days each deterministically recompute the full pipeline (analysis +
# calibration generation + 100+ luck pillars) per request, and the calendar UI
# calls luck_days once per month navigation — caching makes those O(1) lookups.
#
# Key: the FULL canonical serialized BirthInput (model_dump_json), NOT the
# year-granular chart_id — calculate() output depends on the full
# reference_date (세운/월운 anchoring), so a coarser key would serve stale luck
# data. Bounded OrderedDict-LRU (maxsize 64) so memory stays flat under varied
# inputs; threading.Lock because FastAPI may run sync endpoints in a thread
# pool, and OrderedDict mutation is not thread-safe.
_CACHE_MAXSIZE = 64
_cache: OrderedDict[str, ManseV2Result] = OrderedDict()
_cache_lock = threading.Lock()


def calculate(birth: BirthInput) -> ManseV2Result:
    """Compute (or fetch from the in-process LRU cache) the full manse result.

    Deterministic for a given BirthInput; cached results are shared objects and
    must be treated as read-only by callers.
    """
    key = birth.model_dump_json()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached
    result = _calculate(birth)
    with _cache_lock:
        _cache[key] = result
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAXSIZE:
            _cache.popitem(last=False)
    return result


def _calculate(birth: BirthInput) -> ManseV2Result:
    """Run the full pipeline: time correction → 원국 → 분석 → 대운/보정 질문."""
    table = get_table()
    opts = birth.time_options

    loc = resolve_location(
        birth.birth_place_name, birth.latitude, birth.longitude, birth.timezone
    )
    norm = normalize(birth)
    calc_naive = norm.naive_local_datetime
    twin_adjusted = birth.chart_variant == "twin_adjusted" and birth.twin_shift != 0
    if twin_adjusted:
        calc_naive = calc_naive + timedelta(minutes=birth.twin_shift)
    tz = resolve(calc_naive, loc.iana_timezone)
    tc = true_solar_time.compute(calc_naive, loc.longitude, tz, opts)

    absolute_instant = tz.aware_datetime  # civil instant, tz-aware
    term_basis_instant = _term_basis_instant(birth, tc, tz)
    pillars, term_info = four_pillars.compute(
        absolute_instant=term_basis_instant,
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
    boundary_warnings, boundary_trace = _hour_boundary_diagnostics(tc, norm.time_known)
    time_correction.warnings.extend(boundary_warnings)

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
        "chart_variant": birth.chart_variant,
        "twin_shift": birth.twin_shift,
    }

    metadata = EngineMetadata(
        engine_version=ENGINE_VERSION,
        ruleset_version=RULESET_VERSION,
        tzdata_version=TZDATA_VERSION,
        solar_terms_version=table.version,
    )

    chart_analysis = analyze_chart(pillars)

    direction = _daewoon_direction(birth, year_stem)
    luck_cycles = None
    if direction is not None:
        useful_elements, unfavorable_elements = _luck_role_sets(chart_analysis.yongsin)
        luck_cycles = compute_luck_cycles(
            pillars=pillars,
            absolute_instant=term_basis_instant,
            birth_date=tc.civil_datetime.date(),
            direction=direction,
            useful_elements=useful_elements,
            unfavorable_elements=unfavorable_elements,
            table=table,
            reference_date=birth.reference_date,
            timezone=loc.iana_timezone,
        )

    calibration = None
    if birth.reference_date is not None and chart_analysis.yongsin.candidate_models:
        calibration = generate_calibration(
            chart_analysis.yongsin, tc.civil_datetime.date().year, birth.reference_date.year,
            pillars=pillars, gender=birth.gender,
        )

    return ManseV2Result(
        chart_id=_chart_id(birth),
        input_summary=input_summary,
        time_correction=time_correction,
        solar_term_basis=solar_basis,
        pillars=pillars,
        force_analysis=chart_analysis.force,
        structure_analysis=chart_analysis.structure,
        geokguk=chart_analysis.geokguk,
        yongsin_analysis=chart_analysis.yongsin,
        luck_cycles=luck_cycles,
        calibration=calibration,
        traditional_extras=chart_analysis.traditional,
        metadata=metadata,
        trace={
            "absolute_instant_utc": absolute_instant.astimezone(UTC).isoformat(),
            "solar_term_basis_instant_utc": term_basis_instant.astimezone(UTC).isoformat(),
            "final_chart_datetime": tc.final_chart_datetime.isoformat(),
            "standard_datetime": tc.standard_datetime.isoformat(),
            "twin_adjustment": {
                "applied": twin_adjusted,
                "shift_minutes": birth.twin_shift if twin_adjusted else 0,
                "calculation_datetime": calc_naive.isoformat(),
            },
            "boundary_diagnostics": boundary_trace,
        },
    )


def calibrate_feedback(birth: BirthInput, answers: list[FeedbackAnswer]) -> CalibrationResult:
    """Recompute the chart deterministically and score user feedback against the
    same validation questions (stateless calibration)."""
    result = calculate(birth)
    if result.calibration is None or result.yongsin_analysis is None:
        raise ValueError(
            "calibration unavailable: provide reference_date and a chart with candidate models"
        )
    return score_calibration(
        result.calibration.questions, answers, result.yongsin_analysis
    )


def luck_months(birth: BirthInput, year: int) -> list[LuckPillar]:
    """주어진 연도의 월운 12개(세운 선택 시 온디맨드 조회). 차트를 결정론적으로 재계산."""
    result = calculate(birth)
    pillars = result.pillars
    y = result.yongsin_analysis
    if pillars is None or y is None:
        raise ValueError("luck months unavailable: chart could not be computed")
    useful, unfavorable = _luck_role_sets(y)
    return monthly_luck_for_year(
        pillars,
        Stem(pillars.day.stem),
        useful,
        unfavorable,
        year,
        get_table(),
        timezone=result.time_correction.timezone if result.time_correction else "Asia/Seoul",
    )


def luck_days(birth: BirthInput, year: int, month: int) -> list[LuckPillar]:
    """주어진 연·월의 일운(날짜별) — 간지달력 오버레이용 온디맨드 조회(차트 재계산)."""
    result = calculate(birth)
    pillars = result.pillars
    y = result.yongsin_analysis
    if pillars is None or y is None:
        raise ValueError("luck days unavailable: chart could not be computed")
    useful, unfavorable = _luck_role_sets(y)
    return daily_luck_for_month(
        pillars,
        Stem(pillars.day.stem),
        useful,
        unfavorable,
        year,
        month,
    )
