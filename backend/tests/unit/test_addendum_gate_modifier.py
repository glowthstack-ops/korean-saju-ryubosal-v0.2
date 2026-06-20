"""AddendumGateModifier 검증 (이벤트 엔진 재설계 Phase 5).

안전 게이트(과잉 라벨 약화·강등) + 프로필 분기 + 공망 지연을 확인한다.
"""

from __future__ import annotations

from saju_engines.addendum_gate_modifier import AddendumGateModifier, GateContext
from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventTiming,
    LuckLayer,
    TenGod,
)


def _cand(event: str, score: int = 70) -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period="2026", score=score)


def test_business_start_without_wealth_weakened() -> None:
    m = AddendumGateModifier()
    ctx = GateContext(present_gods={TenGod.BIJIAN})  # 비견 단독, 재성 없음
    out = m.apply([_cand("business_start", 70)], ctx)
    c = out[0]
    assert c.score < 70
    # 보류는 '타이밍'(지연)이지 길흉(quality)이 아니다 — quality는 방향 전용으로 보존.
    assert c.timing is EventTiming.DELAY
    assert c.quality is None
    assert "GATE_business_start_no_wealth" in c.reason_codes


def test_windfall_without_day_trigger_downgraded() -> None:
    m = AddendumGateModifier()
    ctx = GateContext(layers={LuckLayer.SEWOON})  # 월/일운 트리거 없음
    out = m.apply([_cand("windfall", 65)], ctx)
    assert {str(c.event_key) for c in out} == {"wealth_change"}


def test_childbirth_without_partner_to_creative() -> None:
    m = AddendumGateModifier()
    out = m.apply([_cand("childbirth", 60)], GateContext(relationship_status="single"))
    assert {str(c.event_key) for c in out} == {"creative_output"}


def test_job_gain_for_employee_to_promotion() -> None:
    m = AddendumGateModifier()
    ctx = GateContext(
        present_gods={TenGod.ZHENGGUAN, TenGod.ZHENGYIN}, occupation_status="employee",
    )
    out = m.apply([_cand("job_gain", 70)], ctx)
    assert {str(c.event_key) for c in out} == {"promotion"}


def test_public_official_job_gain_to_promotion_with_transfer() -> None:
    # 재직 공직자(O02): 취업 신호 → 승진, 발령·전보 동반 태그.
    m = AddendumGateModifier()
    ctx = GateContext(
        present_gods={TenGod.ZHENGGUAN, TenGod.ZHENGYIN},
        occupation_status="public_official",
    )
    out = m.apply([_cand("job_gain", 70)], ctx)
    c = next(c for c in out if str(c.event_key) == "promotion")
    assert "PROFILE_public_official_promotion" in c.reason_codes
    assert "PROFILE_public_official_transfer" in c.reason_codes


def test_public_official_promotion_keeps_label_adds_transfer() -> None:
    # 공직자 승진은 라벨 유지 + 발령·전보 동반 태그(점수 불변).
    m = AddendumGateModifier()
    ctx = GateContext(
        present_gods={TenGod.ZHENGGUAN}, occupation_status="public_official",
    )
    out = m.apply([_cand("promotion", 70)], ctx)
    c = out[0]
    assert str(c.event_key) == "promotion"
    assert c.score == 70
    assert "PROFILE_public_official_transfer" in c.reason_codes


def test_business_owner_wealth_to_expansion() -> None:
    m = AddendumGateModifier()
    ctx = GateContext(
        present_gods={TenGod.SHISHEN, TenGod.PIANCAI}, occupation_status="business_owner",
    )
    out = m.apply([_cand("wealth_change", 65)], ctx)
    assert {str(c.event_key) for c in out} == {"business_expansion"}


def test_void_adds_delay() -> None:
    m = AddendumGateModifier()
    out = m.apply([_cand("contract_document", 60)], GateContext(void_active=True))
    c = out[0]
    assert c.score < 60
    # 공망은 발현을 늦출 뿐 — 타이밍(지연)으로, 방향(quality)은 별도(여기선 미정).
    assert c.timing is EventTiming.DELAY
    assert c.quality is None
    assert "VOID_delay" in c.reason_codes


def test_merge_keeps_higher_score() -> None:
    # windfall→wealth_change 강등 후 기존 wealth_change와 병합(최댓값).
    m = AddendumGateModifier()
    out = m.apply(
        [_cand("windfall", 50), _cand("wealth_change", 65)],
        GateContext(layers={LuckLayer.SEWOON}),
    )
    by = {str(c.event_key): c for c in out}
    assert "wealth_change" in by
    assert by["wealth_change"].score == 65  # 더 높은 점수 유지
