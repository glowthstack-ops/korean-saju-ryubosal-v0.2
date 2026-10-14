"""절기월 'YYYY-01' 라벨 조회 — 2026-10-14 검수 수정(기존 월 총운 경로까지).

`luck_months(birth, y)`는 입춘 기준 y-02 ~ (y+1)-01 이라 1월 라벨은 전년도 호출에만 있다.
chat_service 의 라벨 기반 조회는 모두 `_luck_months_for_label` 을 거친다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange

_BIRTH = BirthInput(
    birth_date=date(1975, 1, 1), birth_time="07:30:00", birth_place_name="서울", gender="female",
)


@pytest.mark.parametrize(
    ("label", "year"),
    [("2027-01", 2026), ("2026-01", 2025), ("2026-02", 2026), ("2026-12", 2026)],
)
def test_luck_year_for_label(label, year):
    assert chat_service._luck_year_for_label(label) == year


@pytest.mark.parametrize("label", ["2026-01", "2027-01", "2026-10"])
def test_luck_months_for_label_contains_label(label):
    assert any(p.label == label for p in chat_service._luck_months_for_label(_BIRTH, label))


@pytest.mark.parametrize("label", ["2026-01", "2027-01"])
def test_monthly_period_fortune_for_january(label):
    """'내년 1월 운세' 월 총운이 None(일반 경로 폴백)으로 떨어지지 않는다."""
    intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.MONTH, start=label, end=label,
        ),
    )
    pf = chat_service._build_period_fortune(_BIRTH, intent, date(2026, 10, 14), "monthly")
    assert pf is not None and pf.period_label == label
