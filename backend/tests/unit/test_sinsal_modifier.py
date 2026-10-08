"""신살 보정 derive 엔진 단위 테스트 (SINSAL_MODIFIER_SPEC Phase A).

원천 SinsalItem 불변·event_score 불변 전제하에, 위치·도메인 정렬·생애단계(대운 우선)·
재활성화·강도밴드 산출을 검증한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import sinsal_modifier_config as cfg
from saju_engines.sinsal_modifier import (
    derive_natal_sinsal_modifiers,
    select_llm_sinsal_modifiers,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.sinsal import SinsalModifier


def _mod(name, position, polarity, domain_match, activation, weight) -> SinsalModifier:
    return SinsalModifier(
        name=name, polarity=polarity, position=position, domain_match=domain_match,
        activation_status=activation, internal_weight=weight,
    )


@pytest.fixture(scope="module")
def chart():
    """1980-11-22 07:30 서울 남성, 기준일 2026-06-25."""
    birth = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="07:30",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 25),
    )
    return calculate(birth)


def test_strength_band_boundaries() -> None:
    assert cfg.strength_band(0.0) == "약함"
    assert cfg.strength_band(0.24) == "약함"
    assert cfg.strength_band(0.25) == "보조"
    assert cfg.strength_band(0.54) == "보조"
    assert cfg.strength_band(0.55) == "강함"
    assert cfg.strength_band(0.79) == "강함"
    assert cfg.strength_band(0.80) == "매우 강함"
    assert cfg.strength_band(1.10) == "매우 강함"


def test_returns_modifiers_with_safe_defaults(chart) -> None:
    mods = derive_natal_sinsal_modifiers(chart, "career", reference_date=date(2026, 6, 25))
    assert isinstance(mods, list)
    # 신살이 산출되면 각 항목의 필수 필드가 채워진다.
    for m in mods:
        assert m.position in ("year", "month", "day", "hour")
        assert m.polarity in ("positive", "caution", "neutral")
        assert m.source == "natal"
        assert m.llm_strength in ("약함", "보조", "강함", "매우 강함")
        assert m.life_stage in ("childhood", "youth", "middle", "late")
        assert m.scope  # 위치별 scope 비어있지 않음
        assert m.effect_tags  # 효과 태그 1개 이상


def test_no_sinsal_or_empty_is_harmless() -> None:
    # traditional_extras 없는 더미는 calculate 로는 만들기 어렵우니, 빈 입력 방어만 직접 확인.
    class _Dummy:
        traditional_extras = None
    assert derive_natal_sinsal_modifiers(_Dummy()) == []  # type: ignore[arg-type]


def test_domain_match_uses_override_threshold(chart) -> None:
    # career: month 가중 1.00 >= 0.85 → 월주 신살 domain_match True.
    career = derive_natal_sinsal_modifiers(chart, "career", reference_date=date(2026, 6, 25))
    month_mods = [m for m in career if m.position == "month"]
    year_mods = [m for m in career if m.position == "year"]
    for m in month_mods:
        assert m.domain_match is True  # 월주=사회궁, career 정렬
    for m in year_mods:
        assert m.domain_match is False  # year 0.55 < 0.85


def test_relationship_day_matches_not_month(chart) -> None:
    rel = derive_natal_sinsal_modifiers(chart, "relationship", reference_date=date(2026, 6, 25))
    for m in rel:
        if m.position == "day":
            assert m.domain_match is True  # relationship day=1.00
        if m.position == "month":
            assert m.domain_match is False  # relationship month=0.70 < 0.85


def test_general_domain_keyword_match() -> None:
    birth = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="07:30",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 25),
    )
    c = calculate(birth)
    # 키워드 없으면 GENERAL 은 domain_match False.
    no_kw = derive_natal_sinsal_modifiers(c, "general", reference_date=date(2026, 6, 25))
    assert all(m.domain_match is False for m in no_kw)
    # 시주 palace_tags(children 등) 키워드 주면 시주 신살만 매칭 가능.
    kw = derive_natal_sinsal_modifiers(
        c, "general", reference_date=date(2026, 6, 25), question_keywords=["children"],
    )
    for m in kw:
        if m.position != "hour":
            assert m.domain_match is False


def test_life_stage_daewoon_priority(chart) -> None:
    # 현재 대운 기반 나이(2026 기준 만 45세) → middle 또는 late.
    mods = derive_natal_sinsal_modifiers(chart, "career", reference_date=date(2026, 6, 25))
    if mods:
        assert mods[0].life_stage in ("middle", "late")


def test_life_stage_mode_curve_consistency(chart) -> None:
    # 각 modifier 의 (position, life_stage) → mode/weight 가 config 곡선과 일치.
    mods = derive_natal_sinsal_modifiers(chart, "wealth", reference_date=date(2026, 6, 25))
    for m in mods:
        mode, _w = cfg.LIFE_STAGE_CURVE[m.position][m.life_stage]
        assert m.life_stage_mode == mode


def test_to_llm_hides_internal_weight(chart) -> None:
    mods = derive_natal_sinsal_modifiers(chart, "career", reference_date=date(2026, 6, 25))
    for m in mods:
        llm = m.to_llm()
        dumped = llm.model_dump()
        assert "internal_weight" not in dumped
        assert "internal_factors" not in dumped
        assert dumped["llm_strength"] == m.llm_strength
        assert dumped["star"] == m.name


def test_original_sinsal_item_untouched(chart) -> None:
    # derive 후 원천 SinsalItem 에 신규 보정 필드가 추가되지 않았는지(비파괴).
    derive_natal_sinsal_modifiers(chart, "career", reference_date=date(2026, 6, 25))
    extras = chart.traditional_extras
    if extras and extras.sinsal and extras.sinsal.full_list:
        item = extras.sinsal.full_list[0]
        assert not hasattr(item, "internal_weight")
        assert not hasattr(item, "domain_match")


# ── pruning(payload 노출 선별) 단위 테스트 ──

def test_pruning_caps_max_three() -> None:
    mods = [
        _mod("a", "month", "neutral", True, "strongly_activated", 1.1),
        _mod("b", "day", "neutral", True, "activated", 0.9),
        _mod("c", "month", "positive", True, "background", 0.6),
        _mod("d", "day", "caution", True, "activated", 0.8),
    ]
    out = select_llm_sinsal_modifiers(mods)
    assert len(out) <= cfg.SINSAL_PAYLOAD_MAX_PER_EVENT == 3


def test_pruning_priority_order() -> None:
    mods = [
        _mod("bg", "day", "neutral", True, "background", 0.6),
        _mod("strong", "month", "neutral", True, "strongly_activated", 1.1),
        _mod("act", "day", "neutral", True, "activated", 0.9),
    ]
    out = select_llm_sinsal_modifiers(mods)
    # 1순위 strongly_activated 가 가장 먼저.
    assert out[0].star == "strong"
    assert out[1].star == "act"
    assert out[2].star == "bg"


def test_pruning_domain_unmatched_capped_to_one() -> None:
    mods = [
        _mod("u1", "month", "neutral", False, "strongly_activated", 1.0),
        _mod("u2", "day", "neutral", False, "strongly_activated", 0.9),
        _mod("m1", "month", "neutral", True, "activated", 0.8),
    ]
    out = select_llm_sinsal_modifiers(mods)
    unmatched = [m for m in out if not m.domain_match]
    assert len(unmatched) <= cfg.SINSAL_PAYLOAD_MAX_DOMAIN_UNMATCHED == 1


def test_pruning_year_background_capped_and_only_year() -> None:
    # dm=False 배경은 연주만 허용, 최대 1.
    mods = [
        _mod("yb1", "year", "positive", False, "background", 0.4),
        _mod("yb2", "year", "caution", False, "background", 0.3),
        _mod("hb", "hour", "neutral", False, "background", 0.5),  # 비연주 배경 → 제외
    ]
    out = select_llm_sinsal_modifiers(mods)
    assert all(m.position == "year" for m in out)  # 비연주 배경 제외
    assert len(out) <= cfg.SINSAL_PAYLOAD_MAX_YEAR_BACKGROUND == 1


def test_pruning_excludes_nonyear_domain_unmatched_background() -> None:
    mods = [_mod("hb", "hour", "neutral", False, "background", 0.9)]
    out = select_llm_sinsal_modifiers(mods)
    assert out == []  # dm=False·비연주·배경 → 노출 안 함
