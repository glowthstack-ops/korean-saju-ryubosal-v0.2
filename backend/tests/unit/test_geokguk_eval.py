"""격국 평가(신뢰도/성패/파격구제/명확도/가중치) 불변식 + 1980 스냅샷."""

from __future__ import annotations

import pytest

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_DAMAGE_TYPES = {
    "shangguan_attacks_officer", "mixed_officer_killing", "killing_overwhelms_weak",
    "wealth_overwhelms_weak", "pyeonin_dosik", "bigyeob_jaengjae",
    "chung_month_branch", "void_month_branch",
}


@pytest.fixture(scope="module")
def evaluation():
    r = calculate(BirthInput(
        birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    ))
    assert r.geokguk.evaluation is not None
    return r.geokguk.evaluation


def test_confidence_range_and_grade(evaluation) -> None:
    assert 0 <= evaluation.confidence_score <= 100  # 마스터 7요소(0~100)
    assert 0.0 <= evaluation.pattern_confidence <= 1.0
    assert evaluation.confidence_grade in {"A", "B", "C", "D", "E"}


def test_success_failure_range(evaluation) -> None:
    assert -100.0 <= evaluation.success_failure_score <= 100.0


def test_final_weight_capped(evaluation) -> None:
    assert 0.10 <= evaluation.final_weight <= 0.60


def test_damage_types_within_defined_set(evaluation) -> None:
    assert set(evaluation.damage_types) <= _DAMAGE_TYPES


def test_active_failures_have_rescue_verdict(evaluation) -> None:
    active = [f for f in evaluation.failures if f["active"]]
    assert len(active) == evaluation.total_active
    for f in active:
        assert isinstance(f["rescued"], bool)
        assert f["rescue_evidence"] != ""


def test_1980_snapshot(evaluation) -> None:
    # 정재격: 투간(戊)·통근(壬)·상신·청정 다 충족 → 신뢰도 90(A). 월지 자형은 성패에서 감점.
    assert evaluation.confidence_score == 90
    assert evaluation.confidence_grade == "A"
    assert "chung_month_branch" in evaluation.damage_types
    assert evaluation.clarity_level == "clear_but_mixed"
    assert evaluation.final_weight == pytest.approx(0.30, abs=0.01)
    assert "성공" not in evaluation.social_expression  # '성공 크기' 단정 금지
