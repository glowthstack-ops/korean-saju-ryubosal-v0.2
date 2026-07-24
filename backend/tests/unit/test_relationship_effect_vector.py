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


def _prov(kind: RelationKind):
    from saju_engines.relation_palace_engine import RelationActivation
    from saju_shared_types.event_engine import LuckLayer

    return RelationActivation(kind, Pillar4.DAY, LuckLayer.SEWOON)


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


def test_mixed_support_pressure_is_evaluated() -> None:
    """support·pressure 공존(net 음수) — EVALUATED(값 보존)."""
    evs = _evidences(
        _hit(RelationKind.HAP, transit="子"),
        _hit(RelationKind.PA, transit="戌"),
    )
    r = synthesize_relationship_effect_vector(evs)
    assert r.axes.stability.status is AxisStatus.EVALUATED
    assert r.axes.stability.value is not None


def test_true_net_zero_is_evaluated_absence_is_none() -> None:
    """폐쇄 §5 — 실제 상쇄 net=0(육합 2 root + 파 1 root: 0.3+0.3−0.6)은 EVALUATED
    value≈0, 무근거는 INSUFFICIENT·value None."""
    evs = _evidences(
        _hit(RelationKind.HAP, transit="子"),
        _hit(RelationKind.HAP, transit="辰", natal="酉"),
        _hit(RelationKind.PA, transit="戌"),
    )
    r = synthesize_relationship_effect_vector(evs)
    assert r.axes.stability.status is AxisStatus.EVALUATED
    assert r.axes.stability.value is not None and abs(r.axes.stability.value) < 1e-9
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


def test_jaenghap_weakens_only_derived_root() -> None:
    """쟁합 — derived root의 support만 약화, 다른 root는 유지(폐쇄 §3)."""
    evs = _evidences(
        _hit(RelationKind.HAP, transit="子"),          # root A(정상 육합)
        _hit(RelationKind.HAP, transit="辰", natal="酉"),  # root B(쟁합 대상)
        period="2029",
    )
    target_id = next(e.evidence_id for e in evs if e.transit_participant == "辰")
    mods = build_relationship_structure_modifiers(
        [_pat("JAENGHAP")], derived_from_by_pattern={"JAENGHAP": [target_id]})
    plain = synthesize_relationship_effect_vector(evs)
    weakened = synthesize_relationship_effect_vector(evs, modifiers=mods)
    p_roots = {c.signal_trigger_id: c for c in plain.root_contributions}
    w_roots = {c.signal_trigger_id: c for c in weakened.root_contributions}
    a_key = next(k for k in p_roots if k.endswith("子"))
    b_key = next(k for k in p_roots if k.endswith("辰"))
    assert w_roots[a_key].stability_support == p_roots[a_key].stability_support  # A 유지
    assert w_roots[b_key].stability_support < p_roots[b_key].stability_support  # B 약화


def test_unscoped_transit_modifier_held_not_applied() -> None:
    """derived도 static도 없는 운 파생 modifier — 적용 보류(대상 불명·메타 보존만)."""
    evs = _evidences(_hit(RelationKind.HAP, transit="子"), period="2029")
    plain = synthesize_relationship_effect_vector(evs)
    held = synthesize_relationship_effect_vector(
        evs, modifiers=build_relationship_structure_modifiers([_pat("JAENGHAP")]))
    assert held.axes.stability.value == plain.axes.stability.value
    assert held.modifiers  # 메타는 보존


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


# ── P1-5 폐쇄 보완 회귀(2026-07-24 §1~§4) ─────────────────────────────


def test_provisional_not_added_to_axis_numbers() -> None:
    """폐쇄 §1 — PROVISIONAL evidence는 축 숫자에 미가산(보존+계측만).

    같은 신호일 수 있는 잠정 2건 → unresolved 2·root 0·activation 숫자 없음.
    """
    from saju_engines.spouse_palace_activation import build_spouse_palace_vector as bv

    prov_evs = bv([_prov(RelationKind.CHUNG), _prov(RelationKind.HYEONG)], _DICTS).evidences
    r = synthesize_relationship_effect_vector(prov_evs)
    assert r.unresolved_trigger_evidence_count == 2
    assert r.independent_root_trigger_count == 0
    assert r.axes.activation.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.axes.activation.value is None
    assert r.contributing_evidence_count == 0
    assert r.noncontributing_evidence_count == 2


def test_mt2_only_stability_separation_insufficient() -> None:
    """폐쇄 §2 — MT2 emergence 단독: activation만 평가, stability·separation 근거 없음."""
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
    mt2 = build_partner_star_emergence_evidence(natal, "己", layer="sewoon",
                                                period_key="2029")
    r = synthesize_relationship_effect_vector(mt2.evidences)
    assert r.axes.activation.status is AxisStatus.EVALUATED
    assert r.axes.stability.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.axes.stability.value is None
    assert r.axes.separation_pressure.status is AxisStatus.INSUFFICIENT_EVIDENCE


def test_axis_evidence_ids_are_axis_specific() -> None:
    """폐쇄 §4 — 축별 evidence_ids 정확성: MT2는 stability·separation에 미표기."""
    from saju_engines.marriage_emergence_modifier import (
        EmergedStem,
        MarriageEmergenceNatal,
    )
    from saju_engines.partner_star_emergence import build_partner_star_emergence_evidence

    palace = _evidences(_hit(RelationKind.CHUNG, transit="未"), period="2027")
    natal = MarriageEmergenceNatal(
        day_master="癸",
        emerged=(EmergedStem(stem="己", element="土", ten_god="편관",
                             source_pillars=("year",), is_day_master_exposure=False,
                             is_partner_star=True),),
        gender="female")
    mt2 = build_partner_star_emergence_evidence(natal, "己", layer="sewoon",
                                                period_key="2027")
    r = synthesize_relationship_effect_vector(palace + mt2.evidences)
    mt2_id = mt2.evidences[0].evidence_id
    chung_id = palace[0].evidence_id
    assert mt2_id in r.axes.activation.evidence_ids
    assert mt2_id not in r.axes.stability.evidence_ids
    assert mt2_id not in r.axes.separation_pressure.evidence_ids
    assert chung_id in r.axes.separation_pressure.evidence_ids


def test_static_modifier_merge_order_invariant() -> None:
    """폐쇄 §3 — 동일 static ID 상이 강도: 순서 무관 max·union 병합."""
    a = build_relationship_structure_modifiers([_pat("GWANSAL_HONJAP", 0.4)])
    b = build_relationship_structure_modifiers([_pat("GWANSAL_HONJAP", 0.8)])
    r1 = synthesize_relationship_effect_vector([], modifiers=a + b)
    r2 = synthesize_relationship_effect_vector([], modifiers=b + a)
    assert r1.modifiers[0].strength == r2.modifiers[0].strength == 0.8
    assert [m.model_dump() for m in r1.modifiers] == [m.model_dump() for m in r2.modifiers]
