"""P1-5 합성기 검증 (RELATIONSHIP_EVENT_SYSTEM — 2026-07-24 승인 §10 필수 회귀).

최우선 규칙: 같은 signal root의 복수 evidence는 보존하되 축 기여 1회+제한 복합 보정.
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.relationship_effect_vector import (
    synthesize_relationship_effect_vector,
)
from saju_engines.relationship_structure_modifiers import (
    build_relationship_structure_modifiers,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.relationship_effect import AxisStatus
from saju_shared_types.structure_patterns import DetectedPattern

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _hit(kind: RelationKind, *, transit: str, natal: str = "丑",
         comp: str = "branch", layer: str = "sewoon",
         palace: Pillar4 = Pillar4.DAY) -> SpousePalaceHit:
    return SpousePalaceHit(
        kind=kind, palace=palace, layer=layer, transit_component=comp,
        transit_participant=transit, natal_participant=natal,
    )


def _evidences(*hits: SpousePalaceHit, period: str = "2027"):
    return build_spouse_palace_vector(list(hits), _DICTS, period_key=period).evidences


def _pat(pid: str, strength: float = 0.6) -> DetectedPattern:
    return DetectedPattern(pattern_id=pid, name_ko=pid, strength=strength,
                           polarity_mode="context_only")


def test_same_root_chung_hyeong_one_root_limited_composite() -> None:
    """같은 root(未) 충+형 — evidence 2·root 1·주 기여+0.3×보조(단순 합산 금지)."""
    evs = _evidences(
        _hit(RelationKind.CHUNG, transit="未"),
        _hit(RelationKind.HYEONG, transit="未"),
    )
    r = synthesize_relationship_effect_vector(evs)
    assert r.evidence_count == 2
    assert r.independent_root_trigger_count == 1
    c = r.root_contributions[0]
    strengths = sorted((e.base_relation_strength for e in evs), reverse=True)
    expected = strengths[0] + 0.3 * strengths[1]
    assert abs(c.activation - expected) < 1e-3
    assert c.activation < sum(strengths)  # 단순 합산 아님
    # separation도 최강(충 1.0)+제한 보정(형 0.6×0.3) — 두 원인 가산 아님.
    assert abs(c.separation_pressure - (1.0 + 0.3 * 0.6)) < 1e-3


def test_different_roots_two_chungs_two_roots() -> None:
    """서로 다른 root(다른 운 글자)의 충 2 — root 2로 합성(독립 신호 합산)."""
    evs = _evidences(
        _hit(RelationKind.CHUNG, transit="未"),
        _hit(RelationKind.CHUNG, transit="戌", natal="未"),
    )
    r = synthesize_relationship_effect_vector(evs)
    assert r.independent_root_trigger_count == 2
    assert len(r.root_contributions) == 2


def test_rp_plus_mt2_same_signal_root_one() -> None:
    """RP+MT2 동일 글자 — evidence 2종·semantic group 2·root 1(독립 원인 2 승격 금지)."""
    from saju_engines.marriage_emergence_modifier import (
        EmergedStem,
        MarriageEmergenceNatal,
    )
    from saju_engines.partner_star_emergence import build_partner_star_emergence_evidence

    palace = _evidences(
        _hit(RelationKind.HAP, transit="己", comp="stem"), period="2029",
    )
    natal = MarriageEmergenceNatal(
        day_master="癸",
        emerged=(EmergedStem(stem="己", element="土", ten_god="편관",
                             source_pillars=("year",), is_day_master_exposure=False,
                             is_partner_star=True),),
        gender="female")
    mt2 = build_partner_star_emergence_evidence(natal, "己", layer="sewoon",
                                                period_key="2029")
    r = synthesize_relationship_effect_vector(palace + mt2.evidences)
    assert r.evidence_count == 2
    assert r.semantic_evidence_group_count == 2
    assert r.independent_root_trigger_count == 1


def test_hap_only_separation_insufficient() -> None:
    r = synthesize_relationship_effect_vector(
        _evidences(_hit(RelationKind.HAP, transit="子"), period="2029"))
    assert r.axes.separation_pressure.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.axes.activation.status is AxisStatus.EVALUATED


def test_blocker_only_realization_insufficient_never_blocked() -> None:
    """positive base 없는 blocker — INSUFFICIENT+blocker 보존, BLOCKED 0건(정상)."""
    from saju_engines.marriage_emergence_modifier import (
        EmergedStem,
        MarriageEmergenceNatal,
    )
    from saju_engines.partner_star_emergence import build_partner_star_emergence_evidence

    natal = MarriageEmergenceNatal(
        day_master="癸",
        emerged=(EmergedStem(stem="己", element="土", ten_god="편관",
                             source_pillars=("year",), is_day_master_exposure=False,
                             is_partner_star=True),),
        gender="female")
    mt2 = build_partner_star_emergence_evidence(
        natal, "己", layer="sewoon", period_key="2029", spouse_palace_clashed=True)
    r = synthesize_relationship_effect_vector([], blockers=mt2.blocker_evidences)
    assert r.axes.realization.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.axes.realization.blocker_ids  # 보존
    assert all(
        getattr(r.axes, a).status is not AxisStatus.BLOCKED
        for a in ("activation", "exposure", "realization", "experience_valence",
                  "stability", "formalization", "separation_pressure")
    )


def test_offsetting_zero_is_evaluated_but_absence_is_none() -> None:
    """support·pressure 상쇄 0 = EVALUATED value(≈0) / 무근거 = value None."""
    evs = _evidences(
        _hit(RelationKind.HAP, transit="子"),
        _hit(RelationKind.PA, transit="戌"),
    )
    r = synthesize_relationship_effect_vector(evs)
    assert r.axes.stability.status is AxisStatus.EVALUATED
    assert r.axes.stability.value is not None
    empty = synthesize_relationship_effect_vector([])
    assert empty.axes.stability.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert empty.axes.stability.value is None


def test_static_modifier_period_dedupe() -> None:
    """natal static 두 기간 — structural_context_id dedupe·1회만 보존."""
    mods = (build_relationship_structure_modifiers([_pat("GWANSAL_HONJAP")])
            + build_relationship_structure_modifiers([_pat("GWANSAL_HONJAP")]))
    r = synthesize_relationship_effect_vector([], modifiers=mods)
    assert r.static_context_ids == ["natal:GWANSAL_HONJAP"]
    assert len(r.modifiers) == 1


def test_modifier_only_no_axis_creation() -> None:
    """modifier만 존재 — activation 등 축 신규 평가 금지(메타만 보존)."""
    mods = build_relationship_structure_modifiers([_pat("JAENGHAP")])
    r = synthesize_relationship_effect_vector([], modifiers=mods)
    assert r.axes.activation.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.modifiers  # 메타 보존


def test_jaenghap_weakens_binding_support() -> None:
    """쟁합 — base evidence의 stability support 약화(affects_axes 한정)."""
    evs = _evidences(_hit(RelationKind.HAP, transit="子"), period="2029")
    plain = synthesize_relationship_effect_vector(evs)
    weakened = synthesize_relationship_effect_vector(
        evs, modifiers=build_relationship_structure_modifiers([_pat("JAENGHAP")]))
    assert weakened.axes.stability.value is not None
    assert plain.axes.stability.value is not None
    assert weakened.axes.stability.value < plain.axes.stability.value


def test_result_has_no_promotion_fields() -> None:
    """승인 §9 — 사건 승격류 필드 부재(P3/P4 소관)·usage=shadow_only."""
    r = synthesize_relationship_effect_vector([])
    for banned in ("recommended_event_key", "relationship_stage_transition",
                   "marriage_probability", "breakup_probability"):
        assert not hasattr(r, banned)
    assert r.usage == "shadow_only"


def test_root_normalized_less_than_adapter_diagnostic_total() -> None:
    """사례 22 원칙 — 같은 root 복수 kind에서 합성 activation < 어댑터 진단 총량."""
    hits = [_hit(RelationKind.CHUNG, transit="未"),
            _hit(RelationKind.HYEONG, transit="未")]
    adapter = build_spouse_palace_vector(hits, _DICTS, period_key="2027")
    r = synthesize_relationship_effect_vector(adapter.evidences)
    assert r.axes.activation.value is not None
    assert r.axes.activation.value < adapter.base_activation_total
