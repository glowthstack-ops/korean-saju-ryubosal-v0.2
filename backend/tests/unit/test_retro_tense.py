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
