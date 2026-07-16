"""운세 길흉 표현 제한 (Phase 5b-2a) — 점수·랭킹 불변·문장 강도만 clamp.

legacy/shadow class 매트릭스로 표현 등급 결정. 조건부 희신/병은 길 승격 금지. 천간·지지 다르면
보수 병합. operability 낮은 용신운은 '강한 길운 단정 금지' 부기. score/rank/favorability 불변.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from saju_manse_analysis import analyze_chart

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_luck_grounding
from saju_engines.event_scoring import favorability_map
from saju_engines.shadow_scoring import (
    _element_expression_class,
    _merge_expression,
    luck_expression_clamp,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Stem

_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)
_STD_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


def _clamp(make_pillars, ganji):
    res = SimpleNamespace(yongsin_analysis=analyze_chart(make_pillars(*_STD)).yongsin)
    return luck_expression_clamp(res, ganji)


def test_standard_luck_expression_classes(make_pillars) -> None:
    cls = lambda gj: _clamp(make_pillars, gj)["expression_class"]  # noqa: E731
    # 희신 과다 교정(2026-07-12) 후 legacy(final)=모델맵: 水=한신·火=희신.
    assert cls("壬子") == "중립"            # 水 한신(0)·조건부 한신/병(0) — 승격 없음
    assert cls("丙午") == "길"              # 火 희신 → 조후보조신(0.35, 밴드 이상)
    assert cls("甲寅") == "길"              # 木 용신
    assert cls("戊辰") == "주의 속 일부 완화"  # 土 구신 → 조건부 제살보조
    assert cls("庚申") == "주의/흉"         # 金 기신


def test_conditional_heesin_never_promoted_to_gil() -> None:
    # ★ legacy positive(희신 0.6)인데 shadow 조건부 희신/병(0.0) → '길' 승격 금지 → 조건부·유보.
    assert _element_expression_class(0.6, 0.0) == "조건부·유보"
    assert _element_expression_class(1.0, 0.0) == "조건부·유보"


def test_mixed_ganji_conservative_merge(make_pillars) -> None:
    # 천간 水(중립)·지지 火(길) → 우선순위 병합으로 길. 병합 규칙 자체는 순수 함수로 검증.
    assert _clamp(make_pillars, "壬午")["expression_class"] == "길"
    assert _merge_expression(["보조 긍정", "조건부·유보"]) == "조건부·유보"
    assert _merge_expression(["길", "주의/흉"]) == "주의/흉"


def test_low_operability_yongsin_note(make_pillars) -> None:
    # 木 용신운: operability 0.595 < 0.9 → 작동성 낮음 부기.
    c = _clamp(make_pillars, "甲寅")
    assert c["low_operability"] == 0.595


def test_build_luck_grounding_surfaces_expression_limit() -> None:
    result = calculate(_STD_BIRTH)
    luck = SimpleNamespace(
        ganji="壬子", twelve_unseong="", relations_to_chart=[], yongsin_alignment="",
        gongmang_activation=[],
    )
    g = build_luck_grounding(result, luck)
    assert "[표현 제한] 중립" in g["pillar_line"]
    assert "점수·순위 불변" in g["pillar_line"]


def test_score_favorability_unchanged(make_pillars) -> None:
    # 표현 제한은 문장 가드 — favorability_map(final/canonical) 불변.
    ya = analyze_chart(make_pillars(*_STD)).yongsin
    fav = favorability_map(SimpleNamespace(yongsin_analysis=ya))  # type: ignore[arg-type]
    assert fav.get("水") == "한신" and fav.get("火") == "희신"


def test_period_prompt_has_expression_limit() -> None:
    import saju_api.services.chat_service as chat_service

    res = chat_service.chat(_STD_BIRTH, "올해 운 어때?", date(2026, 6, 11), dry_run=True)
    pv = res.prompt_preview or ""
    # [표현 제한] 라인이 운세 프롬프트(단일 기간 블록)에 노출 — 자체적으로 "(점수·순위 불변)" 포함.
    assert "[표현 제한]" in pv and "점수·순위 불변" in pv
