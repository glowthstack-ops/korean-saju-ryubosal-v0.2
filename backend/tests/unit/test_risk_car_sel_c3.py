"""C3 선행 — CAR_WORK_OVERLOAD·SEL_COMPETITION_INTENSIFY pressure 재저작 fixture."""

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

# 양성 fixture 커버리지 manifest — reviewed 승격 게이트가 참조.
CAR_SEL_POSITIVE_IDS = {"CAR_WORK_OVERLOAD", "SEL_COMPETITION_INTENSIFY"}


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    return RiskEngine(_DICTS)


def _facts(*, gods=None, relations=None, role=PolarityRole.GI):
    return build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=False, polarity_role=role, twelve_stage=None,
    )


def _get(cands, rid):
    return next((c for c in cands if c.risk_id == rid), None)


def test_work_overload_positive_and_negatives(engine: RiskEngine) -> None:
    """양성: 역할 활성+부담 구조. 음성: 관성 기신만 / 월주 활성만(부담 구조 없음)."""
    pos = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "CAR_WORK_OVERLOAD")
    assert pos is not None and is_active(pos)
    assert pos.exposure_requirement == "required_for_exposure"
    only_gisin = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
    )), "CAR_WORK_OVERLOAD")
    assert only_gisin is None or not is_active(only_gisin)  # 관성 기신만 — 부담 구조 없음
    only_palace = _get(engine.generate(_facts(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "CAR_WORK_OVERLOAD")
    assert only_palace is None or not is_active(only_palace)  # 월주 활성만


def test_work_overload_exposure_denied_blocked(engine: RiskEngine) -> None:
    """직업 역할 DENIED면 직업 압박은 차단(기록 보존)."""
    denied = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ), exposure_status=ExposureStatus.DENIED), "CAR_WORK_OVERLOAD")
    assert denied is not None and not is_active(denied)


def test_competition_positive_and_negatives(engine: RiskEngine) -> None:
    """양성: 경쟁 구조(비겁+관성)+심사 관문 피격. 음성: 비겁·관성만(선발 대상 없음)."""
    pos = _get(engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "SEL_COMPETITION_INTENSIFY")
    assert pos is not None and is_active(pos)
    no_target = _get(engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
    )), "SEL_COMPETITION_INTENSIFY")
    assert no_target is None or not is_active(no_target)  # 선발 관문 활성 없음
    denied = _get(engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ), exposure_status=ExposureStatus.DENIED), "SEL_COMPETITION_INTENSIFY")
    assert denied is not None and not is_active(denied)


def test_competition_does_not_spawn_outcome(engine: RiskEngine) -> None:
    """경쟁 심화가 탈락·추첨 실패 후보를 자동 생성하지 않는다(결과≠과정)."""
    cands = engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ))
    lot = _get(cands, "SEL_LOTTERY_MISS")
    assert lot is None or not is_active(lot)


def test_unlinked_shape_and_activation_insufficient(engine: RiskEngine) -> None:
    """대상 무관 조합 — 역할 활성(재성 피격)과 부담 shape(관성·식상)가 연결되지 않으면
    INSUFFICIENT(느슨한 조합 차단, requiresLinkedTargets)."""
    from saju_shared_types.risk_engine import EligibilityStatus

    cands = engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],  # 재물 대상 — 역할 무관
    ))
    ovl = _get(cands, "CAR_WORK_OVERLOAD")
    assert ovl is not None
    assert ovl.eligibility_status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    assert "targets_unlinked" in ovl.suppression_reasons


def test_linked_shape_and_activation_active(engine: RiskEngine) -> None:
    """대상 연결 양성 — 관성 피격(활성)과 편관 동반 shape가 같은 십성군(관성)이면 활성."""
    pos = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "CAR_WORK_OVERLOAD")
    assert pos is not None and is_active(pos)
