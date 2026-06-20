"""CareerMobilityModifier 검증 (이벤트 엔진 Phase 6c).

특수직군 충형 길화(자료 9-6)와 천충지충 퇴직 리스크(자료 13-1)가 favorability 채널(fav_adj)과
reason_code로만 반영되고, 사건 종류·표시 점수는 불변임을 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.career_mobility_modifier import (
    CareerMobilityContext,
    CareerMobilityModifier,
)
from saju_shared_types.event_engine import EventCandidateV2, TenGod

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _eng() -> CareerMobilityModifier:
    return CareerMobilityModifier(_DICTS)


def _cand(event: str, score: int = 60) -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period="2026", score=score)


def test_special_occupation_clash_boosts_exam() -> None:
    # 의료(O07) + 충 활성 → education_admission favorability 가점(점수 불변).
    e = _eng()
    ctx = CareerMobilityContext(
        activation_kinds={"CHUNG"}, occupation_category="O07",
    )
    out = e.apply([_cand("education_admission", 60)], ctx)
    c = out[0]
    assert c.score == 60
    assert c.contributions["fav_adj"] > 0
    assert "CAREER_SPECIAL_OCC_CLASH_BOOST" in c.reason_codes


def test_non_special_occupation_no_clash_boost() -> None:
    # 일반 직군(O01)은 충형 길화 없음.
    e = _eng()
    ctx = CareerMobilityContext(activation_kinds={"CHUNG"}, occupation_category="O01")
    out = e.apply([_cand("education_admission", 60)], ctx)
    assert "fav_adj" not in out[0].contributions


def test_double_clash_with_officer_flags_exit_risk() -> None:
    # 천충+지충 동시 + 관성 활성 → career_change에 퇴직 리스크(favorability 감점).
    e = _eng()
    ctx = CareerMobilityContext(
        present_gods={TenGod.ZHENGGUAN}, stem_clash=True, branch_clash=True,
    )
    out = e.apply([_cand("career_change", 60)], ctx)
    c = out[0]
    assert c.score == 60
    assert c.contributions["fav_adj"] < 0
    assert "CAREER_EXIT_RISK" in c.reason_codes


def test_double_clash_without_officer_no_exit_risk() -> None:
    # 관성 없으면 퇴직 리스크 분기 안 함.
    e = _eng()
    ctx = CareerMobilityContext(
        present_gods={TenGod.SHISHEN}, stem_clash=True, branch_clash=True,
    )
    out = e.apply([_cand("career_change", 60)], ctx)
    assert "fav_adj" not in out[0].contributions


def test_single_clash_no_exit_risk() -> None:
    # 지충만(천충 없음)이면 퇴직 리스크 아님.
    e = _eng()
    ctx = CareerMobilityContext(
        present_gods={TenGod.ZHENGGUAN}, stem_clash=False, branch_clash=True,
    )
    out = e.apply([_cand("career_change", 60)], ctx)
    assert "fav_adj" not in out[0].contributions
