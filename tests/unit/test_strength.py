"""신강약 9단계 분류·경계·세력균형·왕상휴수사 단위 테스트."""

from __future__ import annotations

import pytest
from saju_manse_analysis.strength.strength_score import (
    classify_band,
    is_borderline,
    side_balance_score,
)

from saju_shared_types.constants import season_state
from saju_shared_types.enums import Branch, Element


@pytest.mark.parametrize(
    "score,band",
    [
        (5, "극신약"), (11, "극신약"), (12, "태신약"), (30, "신약"),
        (40, "중화신약"), (50, "중화"), (60, "중화신강"), (70, "신강"),
        (85, "태신강"), (95, "극신강"),
    ],
)
def test_classify_band(score: float, band: str) -> None:
    assert classify_band(score) == band


def test_borderline() -> None:
    assert is_borderline(33) is True  # within ±2 of 34
    assert is_borderline(44) is True  # boundary itself
    assert is_borderline(27) is False


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


def test_season_state_earth_day_master_policy() -> None:
    # Earth months treat 土 as the season element (codex earth policy reproduced).
    assert season_state(Element.EARTH, Branch.JIN) == "wang"  # 辰월 토 강
    assert season_state(Element.EARTH, Branch.SA) == "xiang"  # 巳월 화생토
    assert season_state(Element.EARTH, Branch.MYO) == "si"  # 卯월 목극토
