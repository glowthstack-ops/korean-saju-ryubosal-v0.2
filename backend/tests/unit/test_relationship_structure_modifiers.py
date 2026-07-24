"""P1-4 구조 패턴 → 관계 modifier 어댑터 검증 (RELATIONSHIP_EVENT_SYSTEM 부록 D §9)."""

from __future__ import annotations

from saju_engines.relationship_structure_modifiers import (
    StructureModifierEffect,
    build_relationship_structure_modifiers,
)
from saju_shared_types.structure_patterns import DetectedPattern


def _pat(pid: str, strength: float = 0.6) -> DetectedPattern:
    return DetectedPattern(
        pattern_id=pid, name_ko=pid, strength=strength, polarity_mode="context_only",
    )


def test_jaenghap_ambiguity_and_support_weaken() -> None:
    mods = build_relationship_structure_modifiers([_pat("JAENGHAP")])
    assert len(mods) == 1
    assert set(mods[0].effects) == {
        StructureModifierEffect.AMBIGUITY_INCREASE,
        StructureModifierEffect.STABILITY_SUPPORT_WEAKEN,
    }


def test_hapgeo_hapban_realization_effects() -> None:
    mods = build_relationship_structure_modifiers([_pat("HAPGEO"), _pat("HAPBAN")])
    by = {m.pattern_id: m for m in mods}
    assert by["HAPGEO"].effects == [StructureModifierEffect.REALIZATION_BLOCKER]
    assert by["HAPBAN"].effects == [StructureModifierEffect.REALIZATION_DELAY]


def test_gwansal_honjap_is_natal_static_no_fake_trigger() -> None:
    """관살혼잡 — natal 정적 출처, 가짜 transit trigger·파생 역추적 없음(§9).

    선택 복잡성·모호성 보조일 뿐 만남 발생 원인이 아니다.
    """
    mods = build_relationship_structure_modifiers(
        [_pat("GWANSAL_HONJAP")],
        derived_from_by_pattern={"GWANSAL_HONJAP": ["spa:should-not-apply"]},
    )
    m = mods[0]
    assert m.structural_context_id == "natal:GWANSAL_HONJAP"
    assert m.derived_from_evidence_ids == []  # natal 정적에는 파생 역추적 미적용
    assert StructureModifierEffect.SELECTION_COMPLEXITY in m.effects
    # 발생 원인 효과(만남·시작 생성)가 어휘에 존재하지 않는다 — modifier 전용 enum.
    assert all("start" not in e.value and "meeting" not in e.value for e in m.effects)


def test_transit_derived_pattern_traces_base_evidence() -> None:
    """운 파생 패턴(쟁합) — 기저 evidence 역추적 연결."""
    mods = build_relationship_structure_modifiers(
        [_pat("JAENGHAP")],
        derived_from_by_pattern={"JAENGHAP": ["spa:sewoon:HAP:day_pillar:branch::"]},
    )
    assert mods[0].derived_from_evidence_ids == ["spa:sewoon:HAP:day_pillar:branch::"]
    assert mods[0].structural_context_id is None


def test_non_relationship_patterns_ignored() -> None:
    """관계 소관 밖 패턴 — modifier 미생성(도메인 침범 금지)."""
    mods = build_relationship_structure_modifiers(
        [_pat("SIKSIN_SAENGJAE"), _pat("CHUNGDONG")]
    )
    assert mods == []


def test_modifiers_are_not_independent_causes() -> None:
    """modifier에는 원인 ID 개념이 없다 — 독립 원인·root trigger 수 기여 금지."""
    m = build_relationship_structure_modifiers([_pat("MULTI_RELATION_STRESS")])[0]
    assert not hasattr(m, "independent_cause_id")
    assert not hasattr(m, "signal_trigger_id")


def test_affects_axes_restricted_to_seven_axes() -> None:
    """modifier 작용 축은 7축 어휘 한정 — ambiguity를 숨은 축으로 수치화 금지(§3)."""
    seven = {"activation", "exposure", "realization", "experience_valence",
             "stability", "formalization", "separation_pressure"}
    mods = build_relationship_structure_modifiers([
        _pat("JAENGHAP"), _pat("HAPGEO"), _pat("GWANSAL_HONJAP"),
        _pat("MULTI_RELATION_STRESS"),
    ])
    for m in mods:
        assert m.affects_axes and set(m.affects_axes) <= seven, m.pattern_id
    # 쟁합은 activation 직접 상승 금지(stability·realization만).
    j = next(m for m in mods if m.pattern_id == "JAENGHAP")
    assert "activation" not in j.affects_axes


def test_static_modifier_not_period_accumulated() -> None:
    """natal 정적 modifier — 기간이 달라도 동일 structural_context_id(누적 금지 §5)."""
    a = build_relationship_structure_modifiers([_pat("GWANSAL_HONJAP")])
    b = build_relationship_structure_modifiers([_pat("GWANSAL_HONJAP")])
    assert a[0].structural_context_id == b[0].structural_context_id == "natal:GWANSAL_HONJAP"
