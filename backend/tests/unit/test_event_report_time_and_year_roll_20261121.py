"""사건 보고 절의 시점 분리 · 연도 없는 달·날짜의 해 넘김 (2026-11-21 데굴님 실답).

실답: 11월 21일에 "우리가 오늘 집이 팔렸어. 2월 12일 정도 이사를 해야해. … 좋은 선택일까?"를 묻자
대상 시점이 오늘로 잡혀(보고 문장의 '오늘'이 계획 날짜를 이김) 내년 2월 이사를 오늘 일진으로 풀었고,
후속 "이사의 방향이나 흐름은 어때?"도 오늘을 이어받아 2026년 흉방으로 답했다.

같은 계열(반례 포함): 다른 문장의 과거 표지가 날짜를 과거로 고정 / 월만 말하면 해를 넘기지 않음 /
근사 날짜를 그 날 하루로 읽음.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.conversation import ConversationEngine
from saju_engines.query_parser import parse_message
from saju_engines.time_parser import strip_event_report_clauses
from saju_engines.user_facts import extract_user_facts, user_facts_block
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import Granularity

_TODAY = date(2026, 11, 21)
_Q1 = (
    "우리가 오늘 집이 팔렸어. 2월 12일 정도 이사를 해야해. ㅠㅠ 우리 충청남도 아산으로 이사를 "
    "하려고 하는데 좋은 선택일까?"
)


def _window(question: str, today: date = _TODAY, month: str = "2026-11") -> tuple[str, str]:
    """(시작, 끝) — 시점이 없으면 ('', '')."""
    tr = parse_message(question, today, current_month_label=month).intents[0].time_range
    if tr is None:
        return "", ""
    return str(tr.start or ""), str(tr.end or "")


def test_reported_case_targets_next_february_with_stated_date_anchor() -> None:
    tr = parse_message(_Q1, _TODAY, current_month_label="2026-11").intents[0].time_range
    assert tr is not None and tr.granularity is Granularity.MONTH
    assert (tr.start, tr.end) == ("2027-02", "2027-02")
    assert [(a.label, a.date) for a in tr.anchor_dates] == [("2월 12일", "2027-02-12")]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # 보고 절 밖에 계획 시점이 있다 — 그 시점이 대상
        ("오늘 계약했어. 3월에 이사하려는데 괜찮을까?", ("2027-03", "2027-03")),
        ("어제 집을 계약했는데 2월에 이사해도 될까?", ("2027-02", "2027-02")),
        ("오늘 사표 냈어. 2월 12일에 새 회사 첫 출근인데 괜찮을까?", ("2027-02-12", "2027-02-12")),
        ("오늘 운세 봤는데 내일은 어때?", ("2026-11-22", "2026-11-22")),
        # 앞 문장의 과거 표지는 배경 보고 — 날짜를 과거로 고정하지 않는다
        ("집 계약했어. 2월 12일에 이사해야 해. 괜찮을까?", ("2027-02-12", "2027-02-12")),
        ("계약은 이미 했어. 3월 5일이 잔금일인데 괜찮을까?", ("2027-03-05", "2027-03-05")),
        # 월만 말했고 이미 지난 달 — 계획·미래 표지면 다음 해
        ("2월에 이사해도 될까?", ("2027-02", "2027-02")),
        ("1월과 2월 중 언제 이사가 나아?", ("2027-01", "2027-02")),
        ("상반기에 이직해도 될까?", ("2027-01", "2027-06")),
        ("3~5월 이사운", ("2027-03", "2027-05")),  # 범위형도 같은 기준
        # 중립 문장 — 지난 지 3개월을 넘으면 다가올 해
        ("2월은 어때?", ("2027-02", "2027-02")),
    ],
)
def test_plan_time_wins_over_report_time_and_past_month_rolls(
    question: str, expected: tuple[str, str]
) -> None:
    assert _window(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # 보고 절 밖에 시점이 없으면 종전대로 오늘
        ("오늘 면접 봤는데 붙을까?", ("2026-11-21", "2026-11-21")),
        ("오늘 계약했는데 잘한 걸까?", ("2026-11-21", "2026-11-21")),
        ("오늘 운세 어때?", ("2026-11-21", "2026-11-21")),
        # 소원형은 보고가 아니다
        ("오늘 면접 잘 됐으면 좋겠는데 어떨까", ("2026-11-21", "2026-11-21")),
        # 같은 문장의 과거 표지 — 회고 그대로
        ("2월 12일에 이사했는데 잘한 걸까?", ("2026-02-12", "2026-02-12")),
        ("2월에 이사했는데 잘한 걸까?", ("2026-02", "2026-02")),
        ("10월은 어땠어?", ("2026-10", "2026-10")),
        # 날짜 문장에 표지가 없으면 뒤 문장의 과거 표지를 따른다
        ("3월 5일 말이야. 그날 왜 그렇게 힘들었을까?", ("2026-03-05", "2026-03-05")),
        # 중립 문장 — 지난 지 3개월 이내는 올해
        ("9월은 어때?", ("2026-09", "2026-09")),
        # 연도를 말했으면 넘기지 않는다
        ("올해 2월은 어땠어?", ("2026-02", "2026-02")),
        # 아직 오지 않은 달·날짜는 그대로
        ("12월 3일에 이사해도 될까?", ("2026-12-03", "2026-12-03")),
        ("하반기는 어때?", ("2026-07", "2026-12")),
        ("8월부터 9월까지 취업운", ("2026-08", "2026-09")),  # 범위형 — 3개월 이내는 올해
        ("11월부터 1월까지 너무 힘들었어", ("2025-11", "2026-01")),  # 과거 시제 구간은 그대로
        # 근사 표지가 아닌 낱말('경기도')은 날짜 그대로
        ("2월 12일 경기도로 이사해", ("2027-02-12", "2027-02-12")),
    ],
)
def test_counter_examples_keep_previous_reading(question: str, expected: tuple[str, str]) -> None:
    assert _window(question) == expected


def test_june_question_about_may_stays_this_year() -> None:
    """실로그 B2 — 6월의 '5월은 어때?'는 올해 5월 비교 맥락 그대로(한 달 전)."""
    assert _window("5월은 어때?", date(2026, 6, 10), "2026-06") == ("2026-05", "2026-05")


def test_approximate_date_before_ipchun_lands_in_previous_solar_term_month() -> None:
    """'2월 2일쯤'은 입춘 전이라 丑월(라벨 01)이고, 말한 날짜는 앵커로 남는다."""
    tr = parse_message("2월 2일쯤 이사하려고 해", _TODAY, current_month_label="2026-11")
    got = tr.intents[0].time_range
    assert got is not None and (got.start, got.granularity) == ("2027-01", Granularity.MONTH)
    assert got.anchor_dates[0].date == "2027-02-02"


def test_reported_event_with_forward_ask_is_unchanged() -> None:
    """사건 보고형(대응 질문)은 종전대로 시점 없음 + reported_event."""
    it = parse_message(
        "오늘 해고통보를 받았어. 앞으로 어떻게 하면 좋을까", _TODAY, current_month_label="2026-11"
    ).intents[0]
    assert it.time_range is None and it.dialogue_act == "reported_event"


def test_strip_event_report_clauses_keeps_the_rest_of_the_sentence() -> None:
    out = strip_event_report_clauses("오늘 계약했는데 3월에 이사하려고 해. 괜찮을까?")
    assert "오늘" not in out and "3월에 이사하려고 해" in out
    # 완료형이 아닌 문장은 건드리지 않는다
    assert strip_event_report_clauses("오늘 운세 어때?") == "오늘 운세 어때?"


def test_followup_turn_inherits_planned_month_and_ledger_carries_resolved_date() -> None:
    eng = ConversationEngine()
    state = ConversationState(thread_id="t-20261121")
    _p1, state, _r1, _l1 = eng.process_turn(state, _Q1, _TODAY, current_month_label="2026-11")
    parsed, state, _r2, _l2 = eng.process_turn(
        state, "이사의 방향이나 흐름은 어때?", _TODAY, current_month_label="2026-11"
    )
    tr = parsed.intents[0].time_range
    assert tr is not None and (tr.start, tr.end) == ("2027-02", "2027-02")
    block = user_facts_block(state.user_facts) or ""
    assert "“2월 12일 정도 이사를 해야해” [달력 환산: 2027년 2월 12일]" in block


def test_user_fact_date_is_resolved_only_for_schedule_slots_and_with_today() -> None:
    facts = extract_user_facts("9월 30일에 이사가 예정되었어", 1, date(2026, 7, 22))
    assert [f.stated_date for f in facts if f.key == "fixed_schedule"] == ["2026-09-30"]
    # 기준일이 없으면 환산하지 않는다(종전 호출 호환)
    assert all(f.stated_date is None for f in extract_user_facts("9월 30일에 이사가 예정되었어", 1))
    # 일정 슬롯이 아닌 사실에는 붙이지 않는다
    other = extract_user_facts("이미 계약도 끝냈고 잔금만 남았어", 1, date(2026, 7, 22))
    assert other and all(f.stated_date is None for f in other)
