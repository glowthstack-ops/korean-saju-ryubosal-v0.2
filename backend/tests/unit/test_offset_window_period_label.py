"""'N개월 안에' 상대 창(end_offset_days)의 기간 표기·일운 블록 gating 회귀.

2026-07-17 데굴님 베타 실로그: '가까운 기간내에는 없어? 12개월안에'가
[질문 기간: 2026-07-17](하루)로 축소되고 '질문한 날짜의 일운' 블록까지
주입돼 답변이 일운 중심으로 좁혀지던 결함. ①reducer가 offset 창을 실제
끝 날짜로 환산해 기간으로 표기 ②chat의 일운 블록 fallback은 진짜 '그 날
하루'(granularity=DAY·offset 없음·end==start) 창에만 발동.
"""

from __future__ import annotations

from datetime import date

from saju_shared_types.intent import (
    Granularity,
    IntentJson,
    QueryType,
    TimeRange,
)


def _intent(tr: TimeRange) -> IntentJson:
    return IntentJson(intent_id="t", query_type=QueryType.DOMAIN_ANALYSIS,
                      time_range=tr)


def _frame(tr: TimeRange):
    from saju_api.services.manse_service import calculate
    from saju_engines.context_reducer import build_reference_frame
    from saju_shared_types.birth_input import BirthInput

    result = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-09-21",
        birth_time="10:00", birth_place_name="서울", gender="male",
        reference_date="2026-07-17"))
    return build_reference_frame(date(2026, 7, 17), _intent(tr), result)


def test_offset_window_renders_full_period() -> None:
    frame = _frame(TimeRange(type="relative", granularity=Granularity.MONTH,
                             start="2026-07-17", end_offset_days=360))
    assert frame.question_period == "2026-07-17 ~ 2027-07-12"
    assert "구간으로 해석" in frame.question_period_note


def test_single_day_window_unchanged() -> None:
    frame = _frame(TimeRange(type="relative", granularity=Granularity.DAY,
                             start="2026-07-17", end="2026-07-17"))
    assert frame.question_period == "2026-07-17"


def test_day_fortune_gate_excludes_offset_window() -> None:
    """chat 일운 블록 fallback 판정 로직과 동일 조건 검증."""
    def single_day(tr: TimeRange) -> bool:
        return bool(
            tr.start and len(tr.start) == 10 and not tr.end_offset_days
            and (tr.end is None or tr.end == tr.start)
            and tr.granularity is Granularity.DAY)

    assert single_day(TimeRange(
        type="relative", granularity=Granularity.DAY,
        start="2026-07-17", end="2026-07-17")) is True
    assert single_day(TimeRange(
        type="relative", granularity=Granularity.MONTH,
        start="2026-07-17", end_offset_days=360)) is False
    assert single_day(TimeRange(
        type="relative", granularity=Granularity.MONTH,
        start="2026-07-17", end_offset_days=90)) is False
