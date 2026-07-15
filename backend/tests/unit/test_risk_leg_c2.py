"""C2 — LEG 6항목(분쟁·소송 분리 포함) 의미론적 fixture + FIN-LEG 교차 도메인 검사."""

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
from saju_shared_types.risk_engine import ExposureStatus, is_active

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"

LEG_POSITIVE_IDS = {
    "LEG_CONTRACT_CANCEL", "LEG_DOCUMENT_ERROR", "LEG_ADMIN_DELAY",
    "LEG_DISPUTE_RISK", "LEG_LITIGATION_ESCALATION", "LEG_REVIEW_CAPACITY_WEAK",
}


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    return RiskEngine(_DICTS)


def _facts(*, gods=None, relations=None, void=False, role=PolarityRole.GI):
    return build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=void, polarity_role=role, twelve_stage=None,
    )


def _ids(cands, active_only=True):
    return {c.risk_id for c in cands if (not active_only) or is_active(c)}


def test_leg_positives_each_item(engine: RiskEngine) -> None:
    """LEG 항목별 명확 양성 — 각자의 사건 구조·대상에서만 활성."""
    # 계약 취소: 충+문서 동반이 문서를 직접 피격.
    a = _ids(engine.generate(_facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
    )))
    assert "LEG_CONTRACT_CANCEL" in a
    # 문서 오류: 편인+문서 공망 shape + 문서 피격 활성.
    b = _ids(engine.generate(_facts(
        gods={TenGod.PIANYIN: {LuckLayer.SEWOON}}, void=True,
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
    )))
    assert "LEG_DOCUMENT_ERROR" in b
    # 행정 지연(pressure 강등): 관성 공망 activation.
    c = _ids(engine.generate(_facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}}, void=True,
    )))
    assert "LEG_ADMIN_DELAY" in c
    # 분쟁 위험: 형+관성 동반이 관성을 피격.
    d = _ids(engine.generate(_facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )))
    assert "LEG_DISPUTE_RISK" in d
    # 검토력 약화(vulnerability): 문서 공망 structural_weakness — 단독 양성.
    e = _ids(engine.generate(_facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}}, void=True,
    )))
    assert "LEG_REVIEW_CAPACITY_WEAK" in e


def test_dispute_vs_litigation_separation(engine: RiskEngine) -> None:
    """분쟁 ≠ 소송 — 노출 미충족 escalation은 dispute를 흡수할 수 없다(역전 방지).

    UNKNOWN: 대표=DISPUTE_RISK(노출 가능), escalation은 구조 후보로만 보존.
    CONFIRMED: escalation(3)이 dispute(2)를 흡수. DENIED: escalation BLOCKED.
    """
    facts = _facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )
    unknown = {c.risk_id: c for c in engine.generate(facts)}
    dsr, lit = unknown["LEG_DISPUTE_RISK"], unknown["LEG_LITIGATION_ESCALATION"]
    assert is_active(dsr), "노출 미확인 상태의 대표는 일반 분쟁 경고(DISPUTE_RISK)"
    assert dsr.suppressed_by_specificity is None
    assert lit.exposure_requirement == "confirmed_required"
    confirmed = {c.risk_id: c for c in engine.generate(
        facts, exposure_status=ExposureStatus.CONFIRMED,
    )}
    assert is_active(confirmed["LEG_LITIGATION_ESCALATION"])
    assert confirmed["LEG_DISPUTE_RISK"].primary_risk_id == "LEG_LITIGATION_ESCALATION"
    denied = {c.risk_id: c for c in engine.generate(
        facts, exposure_status=ExposureStatus.DENIED,
    )}
    assert not is_active(denied["LEG_LITIGATION_ESCALATION"])


def test_document_error_needs_target_activation(engine: RiskEngine) -> None:
    """유사 음성 — 문서 대상 활성 없이 검토 취약성(공망+인성)만으로는 DOCUMENT_ERROR
    미생성(REVIEW_CAPACITY_WEAK 소관)."""
    by = {c.risk_id: c for c in engine.generate(_facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}}, void=True,
    ))}
    doc = by.get("LEG_DOCUMENT_ERROR")
    assert doc is None or not is_active(doc)
    assert is_active(by["LEG_REVIEW_CAPACITY_WEAK"])


def test_cross_domain_fin_leg(engine: RiskEngine) -> None:
    """FIN-LEG 교차 — ①재성 형만=FIN만 ②관성 형만=LEG만 ③독립 대상 둘=병존."""
    fin_only = engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
    ))
    ids = _ids(fin_only)
    assert "FIN_SETTLEMENT_DISPUTE" in ids and "LEG_DISPUTE_RISK" not in ids
    leg_only = engine.generate(_facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ))
    ids = _ids(leg_only)
    assert "LEG_DISPUTE_RISK" in ids and "FIN_SETTLEMENT_DISPUTE" not in ids
    both = engine.generate(_facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                         target_ten_god=TenGod.ZHENGCAI),
            RelationFact(RelationKind.HYEONG, Pillar4.YEAR,
                         target_ten_god=TenGod.ZHENGGUAN),
        ],
    ))
    ids = _ids(both)
    assert {"FIN_SETTLEMENT_DISPUTE", "LEG_DISPUTE_RISK"} <= ids  # 독립 대상 → 정당 병존
    # FIN 대표에는 교차 파급 효과 메타가 있다(후보 복제 금지 — R2 배선 재료).
    fin = next(c for c in both if c.risk_id == "FIN_SETTLEMENT_DISPUTE")
    assert fin.risk_family == "settlement"


def test_review_capacity_absorbed_by_contract_event(engine: RiskEngine) -> None:
    """REVIEW_CAPACITY_WEAK는 구체 계약 사건 성립 시 background_vulnerability로 흡수."""
    by = {c.risk_id: c for c in engine.generate(_facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}}, void=True,
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
    ))}
    rcw = by["LEG_REVIEW_CAPACITY_WEAK"]
    assert rcw.suppressed_by_specificity is not None
    assert rcw.absorbed_role == "background_vulnerability"
    assert rcw.evidence


def test_no_generic_gisin_leg(engine: RiskEngine) -> None:
    """범용 기신·공망만으로는 LEG 후보가 활성되지 않는다(45.5% 발동 원인 제거)."""
    ids = _ids(engine.generate(_facts(void=True, role=PolarityRole.GI_STRONG)))
    assert not (ids & LEG_POSITIVE_IDS)
