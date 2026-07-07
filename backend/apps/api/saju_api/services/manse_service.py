"""Orchestrate BirthInput → time correction → solar terms → 원국 → ManseV2Result."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.luck import (
    compute_luck_cycles,
    daily_luck_for_month,
    daily_luck_for_range,
    monthly_luck_for_year,
    yearly_luck_for_range,
)
from saju_manse_calibration import generate_calibration, score_calibration

import saju_manse_core.pillars.four_pillars as four_pillars
import saju_manse_core.time_correction.true_solar_time as true_solar_time
from saju_engines.context_reducer import event_ko
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.event_scoring import favorability_map_from_model
from saju_manse_core.calendar.solar_terms import get_table
from saju_manse_core.pillars.day_pillar import day_pillar
from saju_manse_core.pillars.hour_pillar import hour_pillar_for_branch
from saju_manse_core.time_correction.input_normalizer import normalize
from saju_manse_core.time_correction.timezone_resolver import TZDATA_VERSION, resolve
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import (
    CalibrationEventItem,
    CalibrationResult,
    DeficiencyPairCandidate,
    FeedbackAnswer,
    TraitProbeCandidate,
)
from saju_shared_types.constants import (
    ENGINE_VERSION,
    RULESET_VERSION,
    STEM_ELEMENT,
    STEM_YINYANG,
    group_elements,
)
from saju_shared_types.enums import Branch, Stem, YinYang
from saju_shared_types.event_taxonomy_v2 import EVENT_CATEGORY
from saju_shared_types.events import Confidence
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import EngineMetadata, ManseV2Result
from saju_shared_types.time_correction import SolarTermBasis, TimeCorrectionResult
from saju_shared_types.yongsin import YongsinCandidateModel

from ..location import resolve as resolve_location

# 용신 검증 이벤트 검출용 — 이벤트 사전 위치 + 단일 스코어러(지연 초기화).
_DICTS = Path(__file__).resolve().parents[4] / "dictionaries"
_event_scorer: EventEngineV2 | None = None
# EventCandidate.polarity → 검증 기대 극성 라벨.
_POLARITY_EXPECTED = {
    "positive": "positive",
    "negative_or_forced": "negative",
    "conditional": "mixed",
    "neutral": "neutral",
}
_EVENTS_PER_QUESTION = 4
# 검증 질문 표시용 라벨 보수화 — 일부 이벤트는 실제 사건 판정이 아니라 십성·관계 신호에서
# 파생된 proxy 라벨이라 사용자가 구체 사건으로 오인하지 않게 완화한다(노출 전용, 사전 불변).
_CALIB_LABEL_OVERRIDE = {
    "business_start": "독립·사업 기운",
}
# 약한 proxy 판별 — 기여 신호가 전부 십성 baseline(미발동 글자 기본 가감)뿐이면 검증 질문에
# 노출하지 않는다(관계·룰 등 실신호가 하나라도 있어야 노출). 내부 점수에는 그대로 반영된다.
_BASELINE_SIGNAL = "baseline_favorability"


def _scorer() -> EventEngineV2:
    """이벤트 스코어러 단일 인스턴스(사전 1회 로드)."""
    global _event_scorer
    if _event_scorer is None:
        _event_scorer = EventEngineV2(_DICTS)
    return _event_scorer


# 십성 그룹 → 구성 십성/한글 라벨(축 predicate·병합 라벨용 — CAL-P1-b).
_GROUP_TEN_GODS: dict[str, tuple[str, str]] = {
    "officer": ("정관", "편관"), "wealth": ("정재", "편재"),
    "output": ("식신", "상관"), "resource": ("정인", "편인"),
    "peer": ("비견", "겁재"),
}
_ELEMENT_EN: dict[str, str] = {
    "木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water",
}


@lru_cache(maxsize=1)
def _pair_question_entries() -> dict[tuple[str, str], dict]:
    """deficiency_pair_questions.json 로드 — (axis_type, axis_id) 인덱스(프로세스 캐시)."""
    data = json.loads(
        (_DICTS / "interpretations" / "deficiency_pair_questions.json").read_text(
            encoding="utf-8"
        )
    )
    return {(e["axis_type"], e["axis_id"]): e for e in data["entries"]}


def _disputed_elements(result: ManseV2Result) -> set[str]:
    """후보 모델 간 역할이 갈리는 오행 — 어느 모델에선 용·희, 다른 모델에선 기·구.

    CAL-P1 축 우선순위 1·2의 런타임 proxy(감수 플래그 축은 테스트 fixture 측 데이터라
    런타임 미접근 — 논쟁 축이 그 상위 개념을 덮는다).
    """
    ya = result.yongsin_analysis
    if ya is None:
        return set()
    fav: set[str] = set()
    unfav: set[str] = set()
    for m in ya.candidate_models:
        fav |= {x for x in (m.yongsin, m.heesin) if x}
        unfav |= {x for x in (m.gisin, m.gusin) if x}
    return fav & unfav


def _deficiency_pair_candidates(result: ManseV2Result) -> list[DeficiencyPairCandidate]:
    """CAL-P1-b axis predicate — 이원 질문 쌍 후보를 우선순위 순으로 만든다(결정론).

    predicate(기존 엔진 값 재사용, 새 임계값 없음):
    - element 축: 표면 부재(raw_visible == 0 — 지장간에 있어도 표면에 없으면 해당.
      이 사례의 '木 지장간 有·표면 無'를 잡는 핵심).
    - ten_god_group 축: 그룹 구성 십성이 모두 visible_absent.
    - 그룹 축의 대상 오행이 동시에 표면 부재면 하나로 병합(구체 문구인 그룹 축 채택,
      engine_basis에 양쪽 기재 — 설계 §6-1 예시와 동일).

    우선순위(§P1-b 확정): 논쟁 축(모델 간 역할 갈림 — 감수 플래그 축의 런타임 proxy)
    > 병합 축(결핍 신호 2중) > 결핍 강도(그룹 세력/분포 오름차순). intent 축은 온보딩
    캘리브레이션에 intent가 없어 미적용. 질문 문구는 사전(reviewed:false 초안)에서만.
    """
    fa = result.force_analysis
    pillars = result.pillars
    if fa is None or pillars is None:
        return []
    entries = _pair_question_entries()
    day_element = STEM_ELEMENT[Stem(pillars.day.stem)]
    group_element = {g: str(el) for g, el in group_elements(day_element).items()}
    visible_absent = set(fa.ten_gods.visible_absent)
    raw_visible = fa.five_elements.raw_visible
    absent_elements = {
        el for el in _ELEMENT_EN if raw_visible.get(el, 0.0) == 0.0
    }
    disputed = _disputed_elements(result)

    candidates: list[tuple[tuple, DeficiencyPairCandidate]] = []
    merged_elements: set[str] = set()
    for group, ten_gods in _GROUP_TEN_GODS.items():
        if not set(ten_gods) <= visible_absent:
            continue
        el = group_element[group]
        entry = entries[("ten_god_group", group)]
        basis = [entry["basis_label"]]
        suppress = [group]
        merged = el in absent_elements
        if merged:
            basis = [entries[("element", _ELEMENT_EN[el])]["basis_label"], *basis]
            suppress.append(_ELEMENT_EN[el])
            merged_elements.add(el)
        severity = fa.ten_gods.groups.get(group, 0.0)
        rank = (0 if el in disputed else 1, 0 if merged else 1, severity, group)
        candidates.append((rank, DeficiencyPairCandidate(
            axis_type="ten_god_group", axis_id=group, axis_element=el,
            engine_basis=basis,
            static_question_text=entry["static_question"],
            transit_question_text=entry["transit_question"],
            suppress_axis_keys=suppress,
        )))
    for el in absent_elements - merged_elements:
        en = _ELEMENT_EN[el]
        entry = entries[("element", en)]
        severity = fa.five_elements.distribution_total.get(el, 0.0)
        rank = (0 if el in disputed else 1, 1, severity, en)
        candidates.append((rank, DeficiencyPairCandidate(
            axis_type="element", axis_id=en, axis_element=el,
            engine_basis=[entry["basis_label"]],
            static_question_text=entry["static_question"],
            transit_question_text=entry["transit_question"],
            suppress_axis_keys=[en],
        )))
    candidates.sort(key=lambda x: x[0])
    return [c for _, c in candidates]


def _daewoon_element_years(result: ManseV2Result) -> dict[str, set[int]]:
    """오행 → 그 오행이 대운에서 활성인 연도 집합(B 앵커 boost용 — CAL-P1-b)."""
    out: dict[str, set[int]] = {}
    if result.luck_cycles is None:
        return out
    for d in result.luck_cycles.daewoon_table:
        years = range(d.approx_start_date.year, d.approx_end_date.year + 1)
        for el in d.raw_elements:
            out.setdefault(el, set()).update(years)
    return out


def _trait_probe_candidates(result: ManseV2Result) -> list[TraitProbeCandidate]:
    """명식 사실 → trait_probe 후보(결정론 predicate) — CAL-P0-b.

    성향 해석 '표현'의 적중도 검수 재료만 만들며 판정·점수와 무관하다(채점 비반영은
    scorer가 보장). 후보 순서 고정(재현성) — cap(기본 1)은 질문 생성기가 적용한다.
    """
    candidates: list[TraitProbeCandidate] = []
    sinsal_names: set[str] = set()
    extras = result.traditional_extras
    if extras is not None and extras.sinsal is not None:
        for names in extras.sinsal.summary.model_dump().values():
            if isinstance(names, list):
                sinsal_names.update(str(n) for n in names)
    if "현침" in sinsal_names:
        candidates.append(TraitProbeCandidate(
            target="communication_style",
            engine_basis=["현침"],
            question_text=(
                "사주에 말·글로 콕 집어 표현하는 정밀한 전달력 신호(현침)가 보여요. "
                "실제로도 생각을 말이나 글로 전하는 일이 편한 편인가요? 즉흥적인 대면 "
                "대화보다 글이나 정리된 설명이 편하다면 '상황에 따라 다르다'를 골라 주세요."
            ),
        ))
    fa = result.force_analysis
    if fa is not None and {"정관", "편관"} <= set(fa.ten_gods.visible_absent):
        candidates.append(TraitProbeCandidate(
            target="decision_style",
            engine_basis=["관성 표면 부재"],
            question_text=(
                "정해진 규칙이나 소속으로 자신을 묶기보다 흘러가는 대로 움직이는 편이라는 "
                "신호(관성이 겉으로 드러나지 않음)가 보여요. 실제 본인도 그런 편인가요?"
            ),
            # CAL-P1 §1-C — 같은 officer 축의 P1 pair가 생성되면 이 후보는 suppress.
            axis_key="officer",
        ))
    return candidates


def _event_items_provider(
    result: ManseV2Result, models: list[YongsinCandidateModel]
) -> Callable[[int], list[CalibrationEventItem]]:
    """연도 → 그 해의 검출 이벤트 목록(모델별 기대 극성 포함) 공급 클로저.

    그 해를 차트 용신으로 스코어링해 표시 이벤트(상위 N, 카테고리 보유분)를 고르고, 후보
    모델마다 fav_override로 재계산한 극성을 이벤트별 기대값으로 싣는다. 연도별로 지연
    계산·캐시한다(질문에 쓰이는 소수 연도만 스코어링).
    """
    scorer = _scorer()
    fav_by_model = {
        m.model_type: fav for m in models if (fav := favorability_map_from_model(m))
    }
    cache: dict[int, list[CalibrationEventItem]] = {}

    def provider(year: int) -> list[CalibrationEventItem]:
        if year in cache:
            return cache[year]
        # 차트 용신으로 그 해 표시 이벤트 선별(상위 N, 카테고리 보유분).
        base = sorted(scorer.score_legacy_years(result, [year]), key=lambda c: -c.score)
        # 모델별 그 해 재계산 극성: {model_type: {event_key: polarity}}.
        per_model = {
            mt: {str(c.event_key): str(c.polarity) for c in scorer.score_legacy_years(
                result, [year], fav_override=fav)}
            for mt, fav in fav_by_model.items()
        }
        items: list[CalibrationEventItem] = []
        seen: set[str] = set()
        for c in base:
            ek = str(c.event_key)
            category = EVENT_CATEGORY.get(c.event_key)
            if category is None or ek in seen:
                continue
            # 약한 proxy(십성 baseline 신호만)인 후보는 검증 질문에서 제외 — 사용자가 사건으로
            # 오인하지 않도록. 관계·룰 등 baseline 외 신호가 하나라도 있으면 노출한다.
            if c.confidence == Confidence.LOW:
                continue
            seen.add(ek)
            expected = {
                mt: _POLARITY_EXPECTED.get(pm.get(ek, "neutral"), "neutral")
                for mt, pm in per_model.items()
            }
            items.append(CalibrationEventItem(
                event_key=ek, category=category,
                label=_CALIB_LABEL_OVERRIDE.get(ek, event_ko(ek)),
                expected_by_model=expected,
            ))
            if len(items) >= _EVENTS_PER_QUESTION:
                break
        cache[year] = items
        return items

    return provider


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

    result = ManseV2Result(
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
        calibration=None,
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

    # 검증 질문은 result(루크·용신 포함)가 있어야 이벤트 엔진으로 연도별 이벤트를 검출하므로
    # result 구성 후 생성해 부착한다(이벤트형 질문 — 모델별 기대 극성).
    # CAL-P0: 교운기 연도(질문 후보 ranking 전용)와 trait_probe 후보(채점 비반영)를 주입.
    if birth.reference_date is not None and chart_analysis.yongsin.candidate_models:
        transition_years = (
            [d.approx_start_date.year for d in luck_cycles.daewoon_table]
            if luck_cycles is not None
            else None
        )
        result.calibration = generate_calibration(
            chart_analysis.yongsin,
            tc.civil_datetime.date().year,
            birth.reference_date.year,
            pillars=pillars,
            gender=birth.gender,
            event_provider=_event_items_provider(
                result, chart_analysis.yongsin.candidate_models
            ),
            transition_years=transition_years,
            trait_candidates=_trait_probe_candidates(result),
            # CAL-P1-b — 이원 질문 쌍 축 후보 + 대운 오행 활성 연도(B 앵커 boost).
            pair_candidates=_deficiency_pair_candidates(result),
            daewoon_element_years=_daewoon_element_years(result),
        )
    return result


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


def luck_years(birth: BirthInput, years: list[int]) -> list[LuckPillar]:
    """주어진 연도 목록의 세운 — 기본 yearly_luck 창(올해±5) 밖 연도를 온디맨드로 채운다.

    막연한 시점 질문의 '올해부터 10년' 연 단위 흐름에서 기본 창을 넘는 연도(예: 올해+6~+9)를
    조회하는 용도. 차트를 결정론적으로 재계산한다.
    """
    result = calculate(birth)
    pillars = result.pillars
    y = result.yongsin_analysis
    if pillars is None or y is None:
        raise ValueError("luck years unavailable: chart could not be computed")
    useful, unfavorable = _luck_role_sets(y)
    return yearly_luck_for_range(
        pillars, Stem(pillars.day.stem), useful, unfavorable, years
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


def daily_luck_window(result: ManseV2Result, start: date, end: date) -> list[LuckPillar]:
    """이미 계산된 차트의 일운을 임의 [start, end] 구간으로 생성한다(차트 재계산 없음).

    택일(E10)이 월 경계를 넘는 탐색 윈도우(예: '7월 4일 이후' → 7/4~8/3)의 일운 합성을
    만들 때 사용한다. 용희/기구 역할 집합은 차트의 용신 분석에서 추출한다(2026-06-16).
    """
    pillars = result.pillars
    y = result.yongsin_analysis
    if pillars is None or y is None:
        raise ValueError("daily luck window unavailable: chart could not be computed")
    useful, unfavorable = _luck_role_sets(y)
    return daily_luck_for_range(
        pillars, Stem(pillars.day.stem), useful, unfavorable, start, end,
    )
