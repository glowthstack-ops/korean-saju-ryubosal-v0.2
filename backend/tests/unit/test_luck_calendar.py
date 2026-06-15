"""절기 기준 월운 라벨 정합 검증 (이벤트 엔진 월 기간 절기 경계 어긋남 수정).

월운 LuckPillar 라벨은 절기(節) 기준이라, 각 양력 달의 節 이전(보통 1~7일경) 구간은
간지상 전월에 속한다. luck_month_label 이 그 구간을 절기 기준으로 보정하는지, 그리고
parse_time 이 주입된 절기 당월로 '이번 달/다음 달/롤링 창'을 잡는지 확인한다.
"""

from __future__ import annotations

from datetime import date

from saju_manse_analysis.luck.luck_calendar import luck_month_label, shift_month_label

from saju_engines.time_parser import parse_time
from saju_manse_core.calendar.solar_terms import get_table


def _label(d: date) -> str:
    return luck_month_label(d, get_table())


def test_label_before_jeolgi_is_previous_ganzi_month() -> None:
    """節(소서 7/7) 이전 양력 7월 초는 간지상 午월(2026-06)."""
    assert _label(date(2026, 7, 1)) == "2026-06"
    assert _label(date(2026, 7, 6)) == "2026-06"


def test_label_on_and_after_jeolgi_is_current_ganzi_month() -> None:
    """소서(7/7) 당일·이후는 未월(2026-07)."""
    assert _label(date(2026, 7, 7)) == "2026-07"
    assert _label(date(2026, 7, 20)) == "2026-07"


def test_label_august_start_still_previous_until_ipchu() -> None:
    """입추(8/7) 이전 양력 8월 초는 간지상 未월(2026-07), 입추 이후 申월(2026-08)."""
    assert _label(date(2026, 8, 1)) == "2026-07"
    assert _label(date(2026, 8, 6)) == "2026-07"
    assert _label(date(2026, 8, 8)) == "2026-08"


def test_label_mid_month_matches_gregorian() -> None:
    """節을 지난 달 중순은 양력 달과 일치(경계 밖 구간은 영향 없음)."""
    assert _label(date(2026, 6, 15)) == "2026-06"


def test_shift_month_label() -> None:
    """라벨 산술은 달력 월 산술과 동일(연도 경계 포함)."""
    assert shift_month_label("2026-06", 1) == "2026-07"
    assert shift_month_label("2026-12", 1) == "2027-01"
    assert shift_month_label("2026-01", -1) == "2025-12"
    assert shift_month_label("2026-07", 11) == "2027-06"


def test_parse_this_month_uses_injected_luck_label() -> None:
    """양력 8/1(간지 未월)에 '이번 달' → 주입 라벨 2026-07로 파싱(양력 2026-08 아님)."""
    today = date(2026, 8, 1)
    cur = _label(today)  # '2026-07'
    tr = parse_time("이번 달 어때?", today, current_month_label=cur)[0]
    assert tr is not None
    assert tr.start == "2026-07" and tr.end == "2026-07"


def test_parse_this_month_falls_back_to_gregorian_without_injection() -> None:
    """주입 없으면 기존(양력) 동작 유지 — 하위 호환."""
    tr = parse_time("이번 달 어때?", date(2026, 8, 1))[0]
    assert tr is not None
    assert tr.start == "2026-08"


def test_parse_next_month_from_luck_label() -> None:
    """'다음 달' = 절기 당월의 +1 (8/1 간지 未월 → 다음은 申월 2026-08)."""
    today = date(2026, 8, 1)
    tr = parse_time("다음 달은?", today, current_month_label=_label(today))[0]
    assert tr is not None
    assert tr.start == "2026-08" and tr.end == "2026-08"


def test_parse_future_rolling_window_anchors_on_luck_label() -> None:
    """'향후 3개월' 창의 시작은 절기 당월(8/1 → 2026-07 시작, +2개월 = 2026-09)."""
    today = date(2026, 8, 1)
    tr = parse_time("향후 3개월 이사운", today, current_month_label=_label(today))[0]
    assert tr is not None
    assert tr.start == "2026-07" and tr.end == "2026-09"


def test_parse_past_rolling_window_anchors_on_luck_label() -> None:
    """'지난 3개월' 창의 끝은 절기 당월(8/1 → 끝 2026-07, 시작 2026-05)."""
    today = date(2026, 8, 1)
    tr = parse_time("지난 3개월", today, current_month_label=_label(today))[0]
    assert tr is not None
    assert tr.start == "2026-05" and tr.end == "2026-07"
