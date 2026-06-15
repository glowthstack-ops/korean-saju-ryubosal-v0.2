"""'이번 달 총운'의 일 단위(주의/기회 시기)가 양력 월이 아니라 절기 월 범위를 따르는지 검증.

월운은 절기(節) 월이라 양력 두 달에 걸친다(예: 未월=소서 7/7~입추 8/7 직전). 월 총운의
주의/기회 날짜가 양력 월(7/1~7/31)이 아니라 절기 월 경계로 잡혀야, 절기 경계 직전 구간에서
전월 날짜가 섞이거나 당월 날짜가 누락되지 않는다.
"""

from __future__ import annotations

import re
from datetime import date

from saju_api.services.chat_service import _build_period_fortune, _current_luck_month
from saju_engines.query_parser import parse_message
from saju_shared_types.birth_input import BirthInput

_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1990, 5, 15), birth_time="09:30",
    birth_place_name="서울", gender="male",
)


def _fortune_days(today: date, label_expected: str):
    """'이번 달 운세' 파싱 → 월 총운 산출 후 슬롯에 등장한 날짜 집합을 돌려준다."""
    cur = _current_luck_month(today)
    intent = parse_message(
        "이번 달 운세 어때?", today, current_month_label=cur
    ).intents[0]
    assert intent.time_range is not None
    assert intent.time_range.start == label_expected  # 절기 기준 당월 라벨
    pf = _build_period_fortune(_BIRTH, intent, today, "monthly")
    assert pf is not None and pf.period_label == label_expected
    dates = sorted({
        d for s in pf.slots for d in re.findall(r"\d{4}-\d{2}-\d{2}", s.summary)
    })
    return dates


def test_days_within_solar_month_exclude_previous_month() -> None:
    """2026-08-01은 절기상 未월(2026-07, 소서 7/7~입추 8/7 직전).

    주의/기회 날짜가 절기 未월 범위 안이고, 午월(7/1~6) 날짜가 섞이지 않아야 한다
    (양력 월 기준이면 7/1 등 전월 절기 날짜가 새어 들어온다).
    """
    dates = _fortune_days(date(2026, 8, 1), "2026-07")
    assert dates, "주의/기회 날짜가 있어야 한다"
    for d in dates:
        assert "2026-07-07" <= d <= "2026-08-06", f"절기 未월 범위 밖: {d}"
        assert not ("2026-07-01" <= d <= "2026-07-06"), f"午월(전월) 날짜 누수: {d}"


def test_days_follow_solar_month_into_next_civil_month() -> None:
    """2026-07-03은 절기상 午월(2026-06, 망종 6/6~소서 7/7 직전).

    7/1~6은 양력 7월이지만 절기상 午월이므로 후보 범위에 포함되어야 하고, 절기 午월
    범위(6/6~7/6)를 벗어난 날짜(7/7 이후 未월)는 없어야 한다.
    """
    dates = _fortune_days(date(2026, 7, 3), "2026-06")
    assert dates
    for d in dates:
        assert "2026-06-06" <= d <= "2026-07-06", f"절기 午월 범위 밖: {d}"
