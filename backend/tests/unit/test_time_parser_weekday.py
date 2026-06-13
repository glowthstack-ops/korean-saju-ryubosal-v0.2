"""요일 시점 파싱 — '다음주 월요일'은 주 전체가 아니라 단일 일운으로 해석(C3.5).

실로그 결함: '다음주 월요일 운세'가 주 범위(월~일)로 잡혀 월운으로 답한 시점 오류 수정.
"""

from __future__ import annotations

from datetime import date

from saju_engines.time_parser import parse_time
from saju_shared_types.intent import Granularity


def _tr(q: str, today: date = date(2026, 6, 14)):  # 2026-06-14 = 일요일
    return parse_time(q, today)[0]


def test_next_week_monday_is_single_day() -> None:
    tr = _tr("다음주 월요일 내 운세")
    assert tr.granularity is Granularity.DAY
    assert tr.start == "2026-06-15" and tr.end == "2026-06-15"  # 다음 주 월요일 = 단일일


def test_this_week_weekday() -> None:
    tr = _tr("이번주 금요일은 어때?")
    assert tr.granularity is Granularity.DAY
    assert tr.start == tr.end == "2026-06-12"  # 이번 주 금요일(명시 — 과거여도 존중)


def test_bare_weekday_picks_upcoming() -> None:
    # 오늘(일)이 지난 이번주 월요일(6/8)보다 뒤 → 다가오는 월요일 6/15.
    tr = _tr("월요일에 좋은 일 있을까")
    assert tr.start == tr.end == "2026-06-15"


def test_bare_next_week_still_full_range() -> None:
    # 요일 없는 '다음주'는 기존대로 주 전체(월~일).
    tr = _tr("다음주 어때?")
    assert tr.start == "2026-06-15" and tr.end == "2026-06-21"


def test_space_variant() -> None:
    assert _tr("다음 주 월요일").start == "2026-06-15"
