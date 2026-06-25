"""C5b 슬래시/대시 날짜 + 과거시제 파싱 회귀 (실로그: '집 계약은 6/17에 했는데').

버그: '6/17'·'6-17' 슬래시/대시 M/D 형식이 파싱되지 않아 멀티턴 시점 승계로 이전 턴 시점이
잘못 적용됨. 또 과거시제('했는데')인데 연도 미지정 과거 날짜가 '내년 택일'로 밀리던 문제.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.time_parser import parse_time
from saju_shared_types.intent import Granularity, TimeScope

_TODAY = date(2026, 6, 25)


def _start(text: str) -> str | None:
    tr, _ = parse_time(text, _TODAY)
    return tr.start if tr else None


@pytest.mark.parametrize("text", [
    "집 계약은 6/17에 했는데 뭔가 사주적인 의미가 있었을까?",
    "계약 6-17에 했어",
    "2026-06-17에 계약했어",
    "2026/6/17에 계약했어",
])
def test_slash_dash_iso_past_date_parses_to_this_year(text: str) -> None:
    # 과거시제 + 연도 미지정/명시 → 올해(과거) 그대로(내년으로 밀지 않음).
    assert _start(text) == "2026-06-17"


def test_slash_date_granularity_and_scope() -> None:
    tr, scope = parse_time("6/17에 계약했어", _TODAY)
    assert tr is not None
    assert tr.granularity is Granularity.DAY
    assert tr.start == tr.end == "2026-06-17"  # 단일 일운(개방형 아님)
    assert scope is TimeScope.SHORT_TERM


def test_future_slash_date_without_past_marker_rolls_to_next_year() -> None:
    # 과거표지 없는 미래 택일 의도 → 이미 지난 날짜는 내년으로(기존 C5b 동작 유지).
    assert _start("6/17에 계약하려고 하는데") == "2027-06-17"


def test_future_slash_date_this_year_when_not_past() -> None:
    # 오늘(6/25)보다 뒤인 날짜는 올해 그대로.
    assert _start("8/20에 이사하려고 해") == "2026-08-20"


def test_existing_month_day_format_unaffected() -> None:
    assert _start("7월 4일에 이사하려고 해") == "2026-07-04"


def test_month_range_not_misparsed_as_slash_date() -> None:
    # '8-10월'은 월 단위(C5) — 슬래시 날짜(8월 10일=2026-08-10)로 오인하지 않는다.
    tr, _ = parse_time("8-10월 중 언제가 나아?", _TODAY)
    assert tr is not None and tr.granularity is Granularity.MONTH
    assert tr.start != "2026-08-10"  # 일(日)로 오인 금지


def test_year_duration_dash_not_date() -> None:
    # '3-4년'은 기간 — 슬래시 날짜로 오인하지 않는다(연/나이 규칙에 양보).
    tr, _ = parse_time("3-4년 뒤에 어때?", _TODAY)
    assert tr is None or tr.granularity is not Granularity.DAY
