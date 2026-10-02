"""C5d 복수 명시 일자·일 범위 파싱 — "10월 7일과 9일", "7일부터 9일까지"(2026-10-02 데굴님 승인).

실답 결함: 택일 답 뒤 "10월 7일과 9일은 어때?"가 C5b 첫 매치(10-07) 하나로만 파싱되어 9일이 입력에서
통째로 사라지고 LLM 이 "9일 세부 정보는 제공되지 않았다"고 답했다. 같은 날 "10월 7일부터 9일까지"도
단일 10-07 로 떨어지던 일 범위 규칙 부재를 함께 고친다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.time_parser import parse_multi_day, parse_time
from saju_shared_types.intent import Granularity, TimeScope

_TODAY = date(2026, 10, 2)


def _parse(q: str):
    return parse_time(q, _TODAY)


@pytest.mark.parametrize(
    "q",
    [
        "10월 7일과 9일은 어때?",
        "10월 7일, 9일 어때?",
        "10월 7일이랑 9일은?",
        "7일이랑 9일은 어때?",
        "10/7과 10/9는?",
        "10월 7일과 10월 9일 중 언제가 나아?",
    ],
)
def test_two_explicit_days_become_dates_list(q: str) -> None:
    """목록형 — start/end 는 min~max 스팬, dates 에 지목한 날만(사이 날 8일 없음)."""
    tr, scope = _parse(q)
    assert tr is not None
    assert tr.granularity is Granularity.DAY
    assert (tr.start, tr.end) == ("2026-10-07", "2026-10-09")
    assert tr.dates == ["2026-10-07", "2026-10-09"]
    assert scope is TimeScope.SHORT_TERM


@pytest.mark.parametrize(
    "q",
    [
        "10월 7일부터 9일까지는 어때?", "7일부터 9일까지 어때",
        "10월 7일~9일 운세", "10월 7일에서 9일 사이",
    ],
)
def test_day_range_spans_without_dates(q: str) -> None:
    """범위형 — 연속 창(start~end)이며 dates 는 비운다."""
    tr, _ = _parse(q)
    assert tr is not None
    assert (tr.start, tr.end) == ("2026-10-07", "2026-10-09")
    assert tr.dates == []


def test_three_days_with_month_inherited() -> None:
    """월 생략 연속 날은 직전 명시 달을 잇는다 — 셋 이상도 전부."""
    tr, _ = _parse("10월 7일, 9일, 11일 중에 뭐가 좋아?")
    assert tr is not None
    assert tr.dates == ["2026-10-07", "2026-10-09", "2026-10-11"]


def test_cross_month_full_dates_collected() -> None:
    """월이 각각 붙은 날짜들('8월 31일 … 9월 30일')도 모두 잡힌다 — 지난 날짜는 C5b 와 같이 내년."""
    tr, _ = _parse(
        "중도금을 치르는 8월 31일은 운이 어떤지, 이사를 하는 9월 30일은 운이 어떤지 봐줄래?"
    )
    assert tr is not None
    assert tr.dates == ["2027-08-31", "2027-09-30"]


def test_explicit_year_is_respected() -> None:
    tr, _ = _parse("2027년 1월 3일과 5일은?")
    assert tr is not None
    assert tr.dates == ["2027-01-03", "2027-01-05"]


def test_single_day_and_neighbors_unchanged() -> None:
    """단일 날짜·C5c·개방형·기간 용법은 C5d 를 지나쳐 기존 규칙 그대로."""
    tr, _ = _parse("10월 7일은 어때?")
    assert tr is not None and (tr.start, tr.end, tr.dates) == ("2026-10-07", "2026-10-07", [])
    tr, _ = _parse("28일 오전에 시험")
    assert tr is not None and tr.start == "2026-10-28" and tr.dates == []
    tr, _ = _parse("7월 4일 이후 이사일 추천")
    assert tr is not None and tr.start == "2027-07-04" and tr.end is None
    tr, _ = _parse("3일 동안 여행 가는데 10월 10일은 어때")
    assert tr is not None and (tr.start, tr.end) == ("2026-10-10", "2026-10-10")
    assert parse_multi_day("3일 동안 여행", _TODAY) is None
    assert parse_multi_day("3일에 한 번 운동", _TODAY) is None


def test_hour_level_keeps_dates() -> None:
    """'시간대' 동반이면 시진 단위로 올라가되 날짜 목록은 유지(로또 실행 패키지)."""
    tr, _ = _parse("10월 7일과 9일 로또 사기 좋은 시간대 알려줘")
    assert tr is not None
    assert tr.granularity is Granularity.HOUR
    assert tr.dates == ["2026-10-07", "2026-10-09"]
