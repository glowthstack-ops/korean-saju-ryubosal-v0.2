"""Phase 5b-2b 도메인별 표현 제한 — expression_class를 도메인 언어로 '번역만'.

score/rank/favorability/final/polarity 불변. 미상 domain은 base fallback, 등록 domain은
EXPRESSION_CLASSES 6종 완전성 필수. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §12
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis.yongsin.operational_role_config import (
    DOMAIN_EXPRESSION_PHRASE,
    EXPRESSION_CLASSES,
    EXPRESSION_GUIDANCE,
)

import saju_engines.chart_interpretation as ci
from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_luck_grounding
from saju_engines.event_scoring import favorability_map
from saju_engines.shadow_scoring import (
    domain_expression_phrase,
    domain_to_expression_key,
)
from saju_shared_types.birth_input import BirthInput

_STD_BIRTH = BirthInput(
    # 조건부 희신/병 유지 차트(희신 과다 교정 후 — 비겁 희신의 한습 강등, 癸巳 일주).
    calendar_type="solar", birth_date="1970-01-13", birth_time="04:30",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


# ── 완전성: 등록 domain × 6 class 전부 존재(누락=config 오류 fail-fast 보호) ──
def test_phrase_map_completeness() -> None:
    assert set(DOMAIN_EXPRESSION_PHRASE) == {
        "career", "wealth", "relationship", "relocation", "study_document",
    }
    for domain, table in DOMAIN_EXPRESSION_PHRASE.items():
        missing = [c for c in EXPRESSION_CLASSES if c not in table]
        assert not missing, f"{domain} 누락 등급: {missing}"
        assert all(table[c] for c in EXPRESSION_CLASSES)  # 빈 문자열 금지


# ── domain enum value → key 매핑(미상/건강 None) ──
def test_domain_to_expression_key() -> None:
    assert domain_to_expression_key("career") == "career"
    assert domain_to_expression_key("CAREER") == "career"  # lowercase normalize
    assert domain_to_expression_key("education") == "study_document"
    assert domain_to_expression_key("general") is None
    assert domain_to_expression_key("health") is None  # 건강 1차 제외 → base fallback
    assert domain_to_expression_key(None) is None
    assert domain_to_expression_key("") is None


# ── phrase helper: 미상/미매핑 base fallback, 등록 domain 번역, 변형 등급 재사용 ──
def test_phrase_fallback_and_translation() -> None:
    base = EXPRESSION_GUIDANCE["조건부·유보"]
    assert domain_expression_phrase(None, "조건부·유보", base) == base
    assert domain_expression_phrase("unknown", "조건부·유보", base) == base
    assert domain_expression_phrase("career", "조건부·유보", base) == "책임·압박·조직 이슈 동반"
    assert domain_expression_phrase("wealth", "조건부·유보", base) == "계약·현실 부담 동반"
    # 변형 등급 → 정규 등급 재사용(§12-2)
    assert domain_expression_phrase("career", "주의", base) == "규정·책임 부담 주의"
    variant = domain_expression_phrase("career", "조건부·유보+주의", base)
    assert variant == "책임·압박·조직 이슈 동반"


def test_registered_domain_missing_class_fail_fast() -> None:
    import pytest
    with pytest.raises(KeyError):
        domain_expression_phrase("career", "존재하지않는등급", "base")


def _grounding(domain_key):
    result = calculate(_STD_BIRTH)
    luck = SimpleNamespace(
        ganji="壬子", twelve_unseong="", relations_to_chart=[], yongsin_alignment="",
        gongmang_activation=[],
    )
    return result, build_luck_grounding(result, luck, domain_key=domain_key)


# ── 같은 水運(조건부·유보)이 도메인별로 다르게 표면화 ──
def test_same_luck_different_domain_phrase() -> None:
    _r, g_career = _grounding("career")
    _r2, g_wealth = _grounding("wealth")
    _r3, g_rel = _grounding("relationship")
    assert "책임·압박·조직 이슈 동반" in g_career["pillar_line"]
    assert "계약·현실 부담 동반" in g_wealth["pillar_line"]
    assert "감정 과다·관계 압박 가능" in g_rel["pillar_line"]
    # 모두 [표현 제한]·점수 불변 표기 유지
    for g in (g_career, g_wealth, g_rel):
        assert "[표현 제한]" in g["pillar_line"] and "점수·순위 불변" in g["pillar_line"]


# ── domain None/미매핑 → base 5b-2a guidance fallback ──
def test_none_domain_uses_base_guidance() -> None:
    _r, g = _grounding(None)
    assert "[표현 제한]" in g["pillar_line"]
    # 도메인 문구가 아니라 base guidance 가 들어감
    assert "책임·압박·조직 이슈 동반" not in g["pillar_line"]


# ── rollback: flag off → 도메인 문구 포함 라인 전체 미노출 ──
def test_rollback_hides_domain_phrase(monkeypatch) -> None:
    monkeypatch.setattr(ci._op_config, "EXPRESSION_CLAMP_ENABLED", False)
    _r, g = _grounding("career")
    assert "[표현 제한]" not in g["pillar_line"]
    assert "책임·압박·조직 이슈 동반" not in g["pillar_line"]


# ── 불변: domain_key 무관하게 favorability_map 동일(점수·판정 불변) ──
def test_favorability_unchanged_by_domain() -> None:
    result = calculate(_STD_BIRTH)
    fav = favorability_map(result)
    for dk in (None, "career", "wealth", "relationship", "relocation", "study_document"):
        luck = SimpleNamespace(
            ganji="壬子", twelve_unseong="", relations_to_chart=[],
            yongsin_alignment="", gongmang_activation=[],
        )
        build_luck_grounding(result, luck, domain_key=dk)
        assert favorability_map(result) == fav  # 호출이 판정을 바꾸지 않음
