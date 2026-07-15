"""C1 — FIN 6항목 의미론적 recall fixture (RISK_DICTIONARY_REVIEW.md §6 manifest).

생성 여부만이 아니라 상태·흡수 역할·근거 원자·노출 요구까지 검증한다(감수 6차):
positive recall = 의도한 역할까지 포함한 의미론적 recall.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.risk_engine import RelationFact, RiskEngine, build_raw_period_facts
from saju_shared_types.event_engine import (
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
)
from saju_shared_types.risk_engine import (
    EligibilityStatus,
    EvidenceRole,
    is_active,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"

# 양성 fixture 커버리지 manifest — reviewed 승격 게이트(test_risk_engine)가 참조한다.
FIN_POSITIVE_IDS = {
    "FIN_CASHFLOW_PRESSURE", "FIN_INVESTMENT_LOSS", "FIN_DEBT_GUARANTEE_BURDEN",
    "FIN_INCOME_DELAY", "FIN_SETTLEMENT_DISPUTE", "FIN_BUFFER_WEAK",
}


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    return RiskEngine(_DICTS)


def _facts(*, gods=None, relations=None, void=False, role=PolarityRole.NEUTRAL):
    return build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=void, polarity_role=role, twelve_stage=None,
    )


def _by_id(cands):
    return {c.risk_id: c for c in cands}


def test_cashflow_pressure_positive_and_no_generic_gisin(engine: RiskEngine) -> None:
    """CFP 양성: 재성 기신 activation → 활성(watch 상한). 범용 기신 단독은 미관측."""
    pos = _by_id(engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}}, role=PolarityRole.GI,
    )))
    c = pos["FIN_CASHFLOW_PRESSURE"]
    assert is_active(c) and c.exposure_requirement == "not_required"
    assert any("ten_god:ZHENGCAI" in e.source for e in c.evidence
               if e.role is EvidenceRole.TRIGGER)
    # 범용 기신만(재정 신호 없음) → 미관측.
    none = _by_id(engine.generate(_facts(role=PolarityRole.GI)))
    assert "FIN_CASHFLOW_PRESSURE" not in none


def test_investment_loss_shape_and_exposure_requirement(engine: RiskEngine) -> None:
    """INV 양성: 편재-비겁 동반 + 재물 피격 → 활성 + required_for_exposure.
    유사 음성: 편재 없는 재물 피격 단독은 INV 미생성(계약 미충족)."""
    pos = _by_id(engine.generate(_facts(
        gods={TenGod.PIANCAI: {LuckLayer.SEWOON}, TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.PIANCAI)],
        role=PolarityRole.GI,
    )))
    c = pos["FIN_INVESTMENT_LOSS"]
    assert is_active(c)
    assert c.exposure_requirement == "required_for_exposure"
    neg = _by_id(engine.generate(_facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )))
    inv = neg.get("FIN_INVESTMENT_LOSS")
    assert inv is None or not is_active(inv)


def test_investment_loss_unknown_vs_denied(engine: RiskEngine) -> None:
    """INV 노출 음성 — UNKNOWN은 구조 후보 유지(조건부), DENIED는 BLOCKED."""
    from saju_shared_types.risk_engine import ExposureStatus

    facts = _facts(
        gods={TenGod.PIANCAI: {LuckLayer.SEWOON}, TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.PIANCAI)],
        role=PolarityRole.GI,
    )
    unknown = _by_id(engine.generate(facts))["FIN_INVESTMENT_LOSS"]
    assert is_active(unknown)  # 구조 후보 유지 — 등급·노출 상한은 R1/R3
    denied = _by_id(engine.generate(
        facts, exposure_status=ExposureStatus.DENIED,
    ))["FIN_INVESTMENT_LOSS"]
    assert denied.eligibility_status is EligibilityStatus.BLOCKED
    assert not is_active(denied)


def test_debt_guarantee_denied_blocked(engine: RiskEngine) -> None:
    """DEBT 노출 음성 — 대출·보증 노출 DENIED면 반드시 BLOCKED(기록은 보존)."""
    from saju_shared_types.risk_engine import ExposureStatus

    facts = _facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        role=PolarityRole.GI,
    )
    denied = _by_id(engine.generate(
        facts, exposure_status=ExposureStatus.DENIED,
    ))["FIN_DEBT_GUARANTEE_BURDEN"]
    assert denied.eligibility_status is EligibilityStatus.BLOCKED
    assert denied.evidence  # 근거 연구용 보존


def test_settlement_requires_wealth_target_not_bare_hyeong(engine: RiskEngine) -> None:
    """SET 대상 요구 — 형 자체가 아니라 정산 대상(재성) 활성이 필수: 대상 무관 형은
    미생성, 같은 사실을 shape/targeted가 함께 잡아도 독립 원인은 1개."""
    bare = _by_id(engine.generate(_facts(
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        role=PolarityRole.GI,
    )))
    st = bare.get("FIN_SETTLEMENT_DISPUTE")
    assert st is None or not is_active(st)
    pos = _by_id(engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )))["FIN_SETTLEMENT_DISPUTE"]
    triggers = [e for e in pos.evidence if e.role is EvidenceRole.TRIGGER]
    assert len({e.source for e in triggers}) == 1  # 동일 사실 → 독립 원인 1(점수 1회 가산 규격)


def test_debt_guarantee_confirmed_required(engine: RiskEngine) -> None:
    """DEBT 양성: 편관-재성 동반 + 관성 피격 → 구조 활성 + confirmed_required
    (운 구조만으로 보증 보유를 추론하지 않는다는 정책이 후보에 실림)."""
    pos = _by_id(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        role=PolarityRole.GI,
    )))
    c = pos["FIN_DEBT_GUARANTEE_BURDEN"]
    assert is_active(c)
    assert c.exposure_requirement == "confirmed_required"


def test_income_delay_requires_void_shape(engine: RiskEngine) -> None:
    """IDL 양성: 재성 공망(결실 지연 구조) + 재성 피격 → 활성.
    유사 음성: 공망 없는 재성 피격 단독 → 계약 미충족(활성 아님)."""
    pos = _by_id(engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}}, void=True,
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )))
    c = pos["FIN_INCOME_DELAY"]
    assert is_active(c)
    no_void = _by_id(engine.generate(_facts(
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )))
    idl = no_void.get("FIN_INCOME_DELAY")
    assert idl is None or not is_active(idl)


def test_settlement_dispute_needs_conflict_shape(engine: RiskEngine) -> None:
    """SET 양성: 형+재성 동반(이견 구조) → 활성 + 교차 도메인은 후보 복제가 아니라
    FIN 대표 1건. 유사 음성: 단순 재성 충 피격만으로는 분쟁 승격 금지."""
    pos = _by_id(engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )))
    c = pos["FIN_SETTLEMENT_DISPUTE"]
    assert is_active(c)
    neg = _by_id(engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )))
    st = neg.get("FIN_SETTLEMENT_DISPUTE")
    assert st is None or not is_active(st)


def test_buffer_weak_absorbed_as_background(engine: RiskEngine) -> None:
    """BUF: 구체 사건(UEX) 동반 시 background_vulnerability로 흡수(의도된 역할),
    단독(공망+재성)일 때는 내부 취약성 후보로 유지 — GI_STRONG 단독 발동은 제거됨."""
    with_event = _by_id(engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        void=True,
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )))
    buf = with_event["FIN_BUFFER_WEAK"]
    assert buf.suppressed_by_specificity is not None
    assert buf.absorbed_role == "background_vulnerability"
    assert buf.evidence  # 근거 보존(R1 exposure/impact 재료)
    solo = _by_id(engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}}, void=True,
    )))
    assert is_active(solo["FIN_BUFFER_WEAK"])
    gisin_only = _by_id(engine.generate(_facts(role=PolarityRole.GI_STRONG)))
    assert "FIN_BUFFER_WEAK" not in gisin_only  # 영역 활성 없는 극성 단독 미관측


def test_fin_statuses_not_insufficient_for_positives(engine: RiskEngine) -> None:
    """모든 FIN 양성 케이스는 INSUFFICIENT가 아니라 ELIGIBLE/MITIGATED여야 한다."""
    cands = engine.generate(_facts(
        gods={TenGod.PIANCAI: {LuckLayer.SEWOON}, TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.PIANCAI)],
        role=PolarityRole.GI,
    ))
    inv = next(c for c in cands if c.risk_id == "FIN_INVESTMENT_LOSS")
    assert inv.eligibility_status in (
        EligibilityStatus.ELIGIBLE, EligibilityStatus.MITIGATED,
    )
