"""신강약 9단계 분류·경계·세력균형·왕상휴수사 단위 테스트."""

from __future__ import annotations

import pytest
from saju_manse_analysis.strength.strength_score import (
    classify_band,
    evaluate_strong_gate,
    is_borderline,
    side_balance_score,
)

from saju_shared_types.constants import season_state
from saju_shared_types.enums import Branch, Element


@pytest.mark.parametrize(
    "score,band",
    [
        (95, "극신강"), (70, "신강"), (30, "중화신강"), (0, "중화"),
        (-30, "중화신약"), (-60, "신약"), (-90, "극신약"),
    ],
)
def test_classify_band(score: float, band: str) -> None:
    # v1.3 7밴드(점수 -100~+100대).
    assert classify_band(score) == band


def test_borderline() -> None:
    assert is_borderline(48) is True  # within ±3 of 50
    assert is_borderline(50) is True  # boundary itself
    assert is_borderline(0) is False  # 중화 중심(경계에서 멀다)


def test_side_balance() -> None:
    base = {"peer": 0.0, "resource": 0.0, "output": 0.0, "wealth": 0.0, "officer": 0.0}
    # only allies → 100; only pressure → 0; empty → neutral 50.
    assert side_balance_score({**base, "peer": 10}) == pytest.approx(100)
    assert side_balance_score({**base, "officer": 10}) == pytest.approx(0)
    assert side_balance_score(base) == pytest.approx(50)


def test_season_state_spring_wood_month() -> None:
    # 寅월(목) — element states relative to the wood season.
    assert season_state(Element.WOOD, Branch.IN) == "wang"
    assert season_state(Element.FIRE, Branch.IN) == "xiang"
    assert season_state(Element.WATER, Branch.IN) == "xiu"
    assert season_state(Element.METAL, Branch.IN) == "qiu"
    assert season_state(Element.EARTH, Branch.IN) == "si"


def test_strong_gate_requires_ally_outside_month_day() -> None:
    # 월지만 동류 + 다른 자리 동류 없음 → ② 미충족으로 게이트 실패.
    assert evaluate_strong_gate(True, False, {"month_branch"})["passed"] is False
    # 월지 동류 + 시지(다른 자리)에도 동류 → 통과.
    assert evaluate_strong_gate(True, False, {"month_branch", "hour_branch"})["passed"] is True
    # 월지·일지 모두 동류 → 한쪽이 "다른 자리" 역할 → 통과.
    assert evaluate_strong_gate(True, True, {"month_branch", "day_branch"})["passed"] is True
    # 월·일지 모두 비동류 → 게이트 자체 실패.
    assert evaluate_strong_gate(False, False, {"year_stem"})["passed"] is False


def test_season_state_earth_day_master_policy() -> None:
    # Earth months treat 土 as the season element (codex earth policy reproduced).
    assert season_state(Element.EARTH, Branch.JIN) == "wang"  # 辰월 토 강
    assert season_state(Element.EARTH, Branch.SA) == "xiang"  # 巳월 화생토
    assert season_state(Element.EARTH, Branch.MYO) == "si"  # 卯월 목극토
