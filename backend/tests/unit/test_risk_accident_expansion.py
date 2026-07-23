"""사고수 위험 사전 확장(2026-07-23 승인) — relativeStarMatch·감수 우선 가드.

승인 조건 검증:
- 역마는 relativeStarMatch(연·일지 삼합국 상대 계산)로만 매칭 — 글자살 폴백 금지(조건 1).
- 상대 신살 정보 부재 시 fail-closed(미매칭).
- '역마 운 유입이 원국을 충'하는 방향은 충 쌍 고정성으로 판정한다.
- 미감수(reviewed:false) 신규 항목은 감수 완료 항목을 특이도 흡수로 밀어내지 못한다(조건 11).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.risk_engine import (
    RawPeriodFacts,
    RelationFact,
    RiskEngine,
    _apply_specificity_suppression,
    build_raw_period_facts,
)
from saju_shared_types.event_engine import (
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
)
from saju_shared_types.risk_engine import (
    EvidenceRole,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
    is_active,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    return RiskEngine(_DICTS)


def _facts(
    letter: str | None,
    yeokma: dict[str, set[str]] | None,
    kind: RelationKind = RelationKind.CHUNG,
) -> RawPeriodFacts:
    return build_raw_period_facts(
        period_key="2033",
        layer=LuckLayer.SEWOON,
        ten_god_layers={},
        relations=[RelationFact(kind, Pillar4.DAY, target_ten_god=TenGod.BIJIAN,
                                target_letter=letter)],
        void_active=False,
        polarity_role=PolarityRole.GI,
        twelve_stage=None,
        yeokma_by_reference=yeokma,
    )


def _ids(cands: list[RiskCandidate]) -> set[str]:
    return {c.risk_id for c in cands}


def test_yeokma_rule_matches_actual_yeokma(engine: RiskEngine) -> None:
    """일지 기준 역마(寅)가 충으로 피격 — 이동 교란 후보 생성."""
    cands = engine.generate(_facts("寅", {"day_branch": {"寅"}}))
    assert "HLT_TRAVEL_DISRUPTION_RISK" in _ids(cands)


def test_yeokma_rule_fail_closed_without_reference(engine: RiskEngine) -> None:
    """상대 신살 정보 부재 — 寅 충이어도 글자살 폴백 없이 미매칭(fail-closed)."""
    cands = engine.generate(_facts("寅", None))
    assert "HLT_TRAVEL_DISRUPTION_RISK" not in _ids(cands)


def test_non_yeokma_sasaeng_letter_not_matched(engine: RiskEngine) -> None:
    """사생지(巳) 충이지만 역마(寅)가 아니고 충 상대(亥)도 역마 아님 — 미매칭(과탐 방지)."""
    cands = engine.generate(_facts("巳", {"day_branch": {"寅"}}))
    assert "HLT_TRAVEL_DISRUPTION_RISK" not in _ids(cands)


def test_incoming_yeokma_clash_matched_via_pair(engine: RiskEngine) -> None:
    """역마(寅)가 운에서 들어와 원국 申을 충 — 피자극 申의 충 상대가 역마라 매칭."""
    cands = engine.generate(_facts("申", {"day_branch": {"寅"}}))
    assert "HLT_TRAVEL_DISRUPTION_RISK" in _ids(cands)


def test_hyeong_requires_natal_yeokma_hit(engine: RiskEngine) -> None:
    """형은 원국 역마 피격만 매칭(쌍 고정성 확장 없음) — 申 형·역마 寅이면 미매칭."""
    cands = engine.generate(_facts("申", {"day_branch": {"寅"}}, RelationKind.HYEONG))
    assert "HLT_TRAVEL_DISRUPTION_RISK" not in _ids(cands)


def test_new_items_registered_unreviewed(engine: RiskEngine) -> None:
    """신규 33종 shadow 등록 — 전부 reviewed:false로 개별 감수 승격 대기(승인 조건 11)."""
    new_ids = {
        "FIN_PERSONAL_BELONGINGS_LOSS", "FIN_HOME_PROPERTY_INTRUSION",
        "FIN_ACCOUNT_SECURITY_COMPROMISE", "LEG_GUARANTEE_STAMP_RISK",
        "LEG_NAME_LENDING_LIABILITY", "HLT_TRANSPORT_COLLISION_RISK",
        "HLT_FALL_SLIP_INJURY", "HLT_SLEEP_RECOVERY_DECLINE", "HLT_COLD_FLUID_BURDEN",
    }
    by_id = {i.risk_id: i for i in engine._items}
    for rid in new_ids:
        assert rid in by_id, f"{rid} 미등재"
        assert by_id[rid].reviewed is False


def _cand(rid: str, rank: int, family: str = "f1") -> RiskCandidate:
    return RiskCandidate(
        risk_id=rid, domain=RiskDomain.FINANCE, kind=RiskKind.INCIDENT_RISK,
        risk_family=family, period_key="2033", specificity_rank=rank,
        evidence=[RiskEvidence(
            evidence_id="2033|relation:CHUNG:day_pillar:branch",
            code="T1", period_key="2033", layer="sewoon",
            source="relation:CHUNG:day_pillar:branch", strength=0.4,
            role=EvidenceRole.TRIGGER, source_group="target_activation",
        )],
    )


def test_unreviewed_cannot_absorb_reviewed() -> None:
    """미감수 rank3 항목이 감수 완료 rank2 항목을 흡수하지 못한다(감수 우선 가드)."""
    reviewed_map = {"NEW_SHADOW": False, "OLD_REVIEWED": True}
    out = _apply_specificity_suppression(
        [_cand("NEW_SHADOW", 3), _cand("OLD_REVIEWED", 2)], reviewed_map)
    old = next(c for c in out if c.risk_id == "OLD_REVIEWED")
    assert is_active(old) and old.suppressed_by_specificity is None
    # 둘 다 감수 완료면 기존 특이도 규칙대로 흡수된다(가드는 미감수 방향만 차단).
    out2 = _apply_specificity_suppression(
        [_cand("NEW_SHADOW", 3), _cand("OLD_REVIEWED", 2)],
        {"NEW_SHADOW": True, "OLD_REVIEWED": True})
    old2 = next(c for c in out2 if c.risk_id == "OLD_REVIEWED")
    assert old2.suppressed_by_specificity == "NEW_SHADOW"
