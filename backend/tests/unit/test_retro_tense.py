"""과거 창 질문의 회고 판정·시제 강제 회귀 — 2026-07-21 데굴님 실로그.

'2025년 중 몇월에 취직에 성공했을까?'(오늘=2026-07-21)가 ①'했을까'(축약 과거형)가
_PAST_KEYWORDS에 안 걸리고 ②창 전체 과거라는 구조 신호를 안 봐서 미래 모드로 판정,
③회고여도 시제 디렉티브가 없어 전면 미래 시제("열릴 것으로 보여요")로 답변되던 결함.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import (
    _RETRO_TENSE_DIRECTIVE,
    _has_contracted_past,
    _question_time_direction,
)
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange

_TODAY = date(2026, 7, 21)


def _intent(tr: TimeRange | None, qt: QueryType = QueryType.DOMAIN_ANALYSIS) -> IntentJson:
    return IntentJson(intent_id="t", query_type=qt, time_range=tr)


def _year_2025() -> TimeRange:
    return TimeRange(
        type="absolute", granularity=Granularity.YEAR,
        start="2025-01-01", end="2025-12-31",
    )


# ── 축약 과거형 감지 ─────────────────────────────────────────────────────────


def test_contracted_past_detected() -> None:
    assert _has_contracted_past("몇월에 취직에 성공했을까?")
    assert _has_contracted_past("언제 잘됐을 때였지")
    assert _has_contracted_past("힘들게 갔던 시기")


def test_contracted_past_not_overtriggered() -> None:
    assert not _has_contracted_past("이직 언제 할까?")  # 미래 의문
    assert not _has_contracted_past("취직했어요")  # 표지 어미 없음
    assert not _has_contracted_past("언제쯤 될까요")
    assert not _has_contracted_past("성공할 수 있을까?")  # '있'=가능 의문(과거 아님)
    assert not _has_contracted_past("언제쯤이겠을까")  # '겠'=추측(과거 아님)


# ── 시간 방향 판정 ───────────────────────────────────────────────────────────


def test_real_log_turn_is_retro() -> None:
    # 실로그 2턴: 명시 과거 연도 + 축약 과거형 — 구조·문구 어느 쪽으로든 회고여야 한다.
    q = "그럼 2025년 중 몇월에 취직에 성공했을까?"
    assert _question_time_direction(q, _intent(_year_2025()), None, _TODAY) is True


def test_fully_past_window_is_retro_regardless_of_wording() -> None:
    # 문구 신호가 전혀 없어도(미래형 어미 '올까' 포함) 창 전체가 과거면 회고.
    q = "2025년에 어떤 기회가 올까?"
    assert _question_time_direction(q, _intent(_year_2025()), None, _TODAY) is True


def test_current_year_window_stays_future() -> None:
    tr = TimeRange(type="absolute", granularity=Granularity.YEAR,
                   start="2026-01-01", end="2026-12-31")
    assert _question_time_direction("올해 이직 될까?", _intent(tr), None, _TODAY) is False


def test_offset_window_not_treated_as_past() -> None:
    # 상대 창(end_offset_days)은 미래 창 — 구조 신호 판정에서 제외.
    tr = TimeRange(type="relative", granularity=Granularity.MONTH,
                   start="2026-07-21", end_offset_days=360)
    assert _question_time_direction("12개월 안에 될까?", _intent(tr), None, _TODAY) is False


def test_future_when_without_window_is_future() -> None:
    assert _question_time_direction(
        "이직 제안 언제 들어올까?", _intent(None), None, _TODAY,
    ) is False


def test_open_when_inherits_last_retro() -> None:
    tr = TimeRange(type="open_when", granularity=Granularity.MONTH)
    state = ConversationState(thread_id="t", last_retro=True)
    assert _question_time_direction("월단위로 알려줘", _intent(tr), state, _TODAY) is True
    state = ConversationState(thread_id="t", last_retro=False)
    assert _question_time_direction("월단위로 알려줘", _intent(tr), state, _TODAY) is False


# ── 시제 디렉티브·reference frame 노트 ──────────────────────────────────────


def test_retro_tense_directive_forbids_future_wording() -> None:
    assert "과거 추정형" in _RETRO_TENSE_DIRECTIVE
    assert "미래 예측·권고 표현 금지" in _RETRO_TENSE_DIRECTIVE


def test_reference_frame_marks_fully_past_window() -> None:
    from saju_api.services.manse_service import calculate
    from saju_engines.context_reducer import build_reference_frame
    from saju_shared_types.birth_input import BirthInput

    result = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-09-21",
        birth_time="10:00", birth_place_name="서울", gender="male",
        reference_date="2026-07-21"))
    frame = build_reference_frame(_TODAY, _intent(_year_2025()), result)
    assert "전부 이미 지났다" in frame.question_period_note
    assert "과거형·추정형" in frame.question_period_note


def test_reference_frame_straddling_window_unchanged() -> None:
    # 기존 P6(걸침 창) 동작 회귀 — '올해' 창은 지난 구간/남은 구간 분리 표기 유지.
    from saju_api.services.manse_service import calculate
    from saju_engines.context_reducer import build_reference_frame
    from saju_shared_types.birth_input import BirthInput

    result = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-09-21",
        birth_time="10:00", birth_place_name="서울", gender="male",
        reference_date="2026-07-21"))
    tr = TimeRange(type="absolute", granularity=Granularity.YEAR,
                   start="2026-01-01", end="2026-12-31")
    frame = build_reference_frame(_TODAY, _intent(tr), result)
    assert "이미 지났다" in frame.question_period_note
    assert "남은 구간" in frame.question_period_note
    assert "전부 이미 지났다" not in frame.question_period_note


# ── 절입 직전 '이달' 시제 — 2026-09-04 데굴님 실로그 ────────────────────────────
# 9/4는 백로(9/7) 전이라 '이달'=丙申월('2026-08'). 회고 판정이 이 라벨을 양력 '2026-09'와
# 비교해 "창 전체 과거"로 뒤집혀 10월 흐름까지 과거형으로 서술되던 결함.

_TODAY_PRE_JEOL = date(2026, 9, 4)
_LUCK_MONTH_PRE_JEOL = "2026-08"
_Q_THIS_MONTH = "이달에 사업에 대한 서류를 제출하면 선정될 가능성은 있을까?"


def _this_month_tr(label: str = _LUCK_MONTH_PRE_JEOL) -> TimeRange:
    return TimeRange(type="relative", granularity=Granularity.MONTH, start=label, end=label)


def test_current_solar_month_before_jeol_is_not_retro() -> None:
    assert _question_time_direction(
        _Q_THIS_MONTH, _intent(_this_month_tr()), None, _TODAY_PRE_JEOL, _LUCK_MONTH_PRE_JEOL,
    ) is False


def test_current_solar_month_without_label_keeps_calendar_fallback() -> None:
    # 라벨 미주입 = 기존 양력 폴백 동작 유지(호출자가 절기 라벨을 넘기는 것이 교정의 핵심).
    assert _question_time_direction(
        _Q_THIS_MONTH, _intent(_this_month_tr()), None, _TODAY_PRE_JEOL,
    ) is True


def test_previous_solar_month_still_retro_with_label() -> None:
    assert _question_time_direction(
        "7월에 무슨 일 있었을까", _intent(_this_month_tr("2026-07")), None,
        _TODAY_PRE_JEOL, _LUCK_MONTH_PRE_JEOL,
    ) is True


def test_extend_current_month_when_few_days_remain() -> None:
    from saju_api.services.chat_service import _extend_current_month_near_boundary

    out = _extend_current_month_near_boundary(
        _intent(_this_month_tr()), _TODAY_PRE_JEOL, _LUCK_MONTH_PRE_JEOL,
    )
    assert out.time_range is not None
    assert out.time_range.start == "2026-08"
    assert out.time_range.end == "2026-09"


def test_extend_current_month_not_applied_mid_month() -> None:
    from saju_api.services.chat_service import _extend_current_month_near_boundary

    out = _extend_current_month_near_boundary(
        _intent(_this_month_tr()), date(2026, 8, 15), _LUCK_MONTH_PRE_JEOL,
    )
    assert out.time_range is not None
    assert out.time_range.end == "2026-08"


def test_extend_current_month_leaves_absolute_and_multi_month_windows() -> None:
    from saju_api.services.chat_service import _extend_current_month_near_boundary

    absolute = TimeRange(
        type="absolute", granularity=Granularity.MONTH, start="2026-08", end="2026-08",
    )
    assert _extend_current_month_near_boundary(
        _intent(absolute), _TODAY_PRE_JEOL, _LUCK_MONTH_PRE_JEOL,
    ).time_range == absolute
    multi = TimeRange(
        type="relative", granularity=Granularity.MONTH, start="2026-08", end="2026-12",
    )
    assert _extend_current_month_near_boundary(
        _intent(multi), _TODAY_PRE_JEOL, _LUCK_MONTH_PRE_JEOL,
    ).time_range == multi


def test_reference_frame_marks_current_solar_month_as_ongoing() -> None:
    from saju_api.services.manse_service import calculate
    from saju_engines.context_reducer import build_reference_frame
    from saju_shared_types.birth_input import BirthInput

    result = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-09-21",
        birth_time="10:00", birth_place_name="서울", gender="male",
        reference_date="2026-09-04"))
    # 당월 단독 창
    frame = build_reference_frame(
        _TODAY_PRE_JEOL, _intent(_this_month_tr()), result,
        current_month_label=_LUCK_MONTH_PRE_JEOL,
    )
    assert "현재 진행 중인 절기월" in frame.question_period_note
    assert "이미 지났다" not in frame.question_period_note
    # 다음 절기월까지 늘어난 창 — 두 구간 구분 지시
    tr2 = TimeRange(type="relative", granularity=Granularity.MONTH, start="2026-08", end="2026-09")
    frame2 = build_reference_frame(
        _TODAY_PRE_JEOL, _intent(tr2), result, current_month_label=_LUCK_MONTH_PRE_JEOL,
    )
    assert "2026-08는 현재 진행 중인 절기월" in frame2.question_period_note
    assert "2026-09~2026-09는 곧 시작되는 다음 절기월" in frame2.question_period_note
    assert "이미 지났다" not in frame2.question_period_note
