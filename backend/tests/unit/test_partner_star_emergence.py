"""P1-3 MT2 evidence 어댑터 검증 (RELATIONSHIP_EVENT_SYSTEM 부록 D §8)."""

from __future__ import annotations

from saju_engines.marriage_emergence_modifier import EmergedStem, MarriageEmergenceNatal
from saju_engines.partner_star_emergence import build_partner_star_emergence_evidence
from saju_shared_types.relationship_effect import TriggerPrecision


def _natal(partner: bool = True) -> MarriageEmergenceNatal:
    # 癸 일간 여성 — 일지 丑 지장간 己(편관=배우자성)가 년간에 투출된 구조.
    return MarriageEmergenceNatal(
        day_master="癸",
        emerged=(EmergedStem(
            stem="己", element="土", ten_god="편관", source_pillars=("year",),
            is_day_master_exposure=False, is_partner_star=partner,
        ),),
        gender="female",
    )


def test_same_stem_return_exact_trigger() -> None:
    """운 己 회귀 — EXACT signal trigger(운 글자 포함)·partner_star_emergence 그룹."""
    r = build_partner_star_emergence_evidence(
        _natal(), "己", layer="sewoon", period_key="2029",
    )
    assert r.hit and r.tier == "same_stem" and r.is_partner_star is True
    e = r.evidences[0]
    assert e.independent_cause_group == "partner_star_emergence"
    assert e.signal_trigger_id == "sewoon:2029:stem:己"
    assert e.trigger_precision is TriggerPrecision.EXACT
    assert e.period_trigger_id == "sewoon:2029"
    assert e.natal_participant == "己" and e.transit_participant == "己"
    assert e.base_relation_strength == 10.0  # partner×same_stem — legacy 표 스케일
    assert "MT2_EMERGENCE_SAME_STEM" in e.reason_codes


def test_no_return_empty_result() -> None:
    """회귀 없음(운 甲 — 다른 오행) — evidence 0(축 판정도 없음)."""
    r = build_partner_star_emergence_evidence(
        _natal(), "甲", layer="sewoon", period_key="2029",
    )
    assert not r.hit and r.evidences == [] and r.blocker_evidences == []


def test_clashed_becomes_blocker_not_zero() -> None:
    """배우자궁 충 동반 — 0점 evidence가 아니라 blocker evidence로 보존(§8)."""
    r = build_partner_star_emergence_evidence(
        _natal(), "己", layer="sewoon", period_key="2029", spouse_palace_clashed=True,
    )
    assert r.hit and r.evidences == []
    b = r.blocker_evidences[0]
    assert "SPOUSE_PALACE_CLASHED" in b.reason_codes
    assert b.trigger_precision is TriggerPrecision.EXACT  # trigger 정보는 보존


def test_same_element_tier_weaker_base() -> None:
    """same_element 회귀(운 戊 — 같은 토·글자 다름) — 낮은 기본 강도."""
    r = build_partner_star_emergence_evidence(
        _natal(), "戊", layer="sewoon", period_key="2029",
    )
    assert r.hit and r.tier == "same_element"
    assert r.evidences[0].base_relation_strength == 4.0
    assert "MT2_EMERGENCE_SAME_ELEMENT" in r.evidences[0].reason_codes


def test_distinct_root_from_palace_evidence_when_same_letter() -> None:
    """같은 글자의 RelationPalace evidence와 signal 기준 root 1개 판정 가능성 —
    MT2 evidence는 EXACT signal을 제공한다(§8: 증거 2종·root 1개는 합성기 소관)."""
    r = build_partner_star_emergence_evidence(
        _natal(), "己", layer="sewoon", period_key="2029",
    )
    e = r.evidences[0]
    # 합성기가 대조할 근거: 그룹은 다르지만 signal_trigger_id는 실제 글자 기준.
    assert e.independent_cause_group == "partner_star_emergence"
    assert e.signal_trigger_id and e.signal_trigger_id.endswith(":己")
