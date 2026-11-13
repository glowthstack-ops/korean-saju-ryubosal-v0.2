"""방향이 있는 월 범위(해 넘김)와 '내 사주를 바탕으로' 머리말 라우팅(2026-11-13 데굴님 실답).

실답: 2026-11-13 에 "내 사주 구조를 바탕으로 11월부터 1월까지의 취업운을 정리해줘"를 물었는데
①다중 월 규칙이 월 번호를 작은 순으로 정렬해 2026-01~2026-11 로 풀어 지난 2~9월을 다가올 시기처럼
답했고 ②'내 사주' 머리말 때문에 명식 구조 질문(Q8)으로 분류됐다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.query_parser import _detect_query_type
from saju_engines.time_parser import parse_time
from saju_shared_types.intent import QueryType, SubjectMode

_NOV = date(2026, 11, 13)


def _span(text: str, today: date = _NOV) -> tuple[str | None, str | None]:
    rng, _scope = parse_time(text, today)
    return (rng.start, rng.end) if rng is not None else (None, None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("내 사주 구조를 바탕으로 11월부터 1월까지의 취업운을 정리해줘", ("2026-11", "2027-01")),
        ("11월~1월 취업운", ("2026-11", "2027-01")),
        ("11~1월 취업운", ("2026-11", "2027-01")),
        ("11월에서 1월 사이 이직운", ("2026-11", "2027-01")),
        ("12월부터 2월까지 재물운", ("2026-12", "2027-02")),
        # '내년'은 붙은 쪽 달에만 적용한다(종전: 양 끝 모두 내년 → 2027-01~2027-11).
        ("11월부터 내년 1월까지 취업운", ("2026-11", "2027-01")),
        ("내년 3월부터 5월까지 이직운", ("2027-03", "2027-05")),
        ("내년에는 3월부터 5월까지 어때", ("2027-03", "2027-05")),
        ("2027년 11월부터 1월까지", ("2027-11", "2028-01")),
        # 상대 표현으로 시작하는 범위.
        ("이번 달부터 1월까지 취업운", ("2026-11", "2027-01")),
        ("다음 달부터 2월까지", ("2026-12", "2027-02")),
        # 나열형이 해를 넘기는 경우.
        ("11월, 12월, 1월 취업운", ("2026-11", "2027-01")),
        ("11월과 1월 중 언제가 나아?", ("2026-11", "2027-01")),
    ],
)
def test_directed_month_range_wraps_into_next_year(text: str, expected: tuple[str, str]) -> None:
    assert _span(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 반례: 해를 넘기지 않는 범위·단일 달·비교는 종전 그대로다.
        ("8월부터 9월까지 취업운", ("2026-08", "2026-09")),
        ("8~9월 인테리어 주의점", ("2026-08", "2026-09")),
        ("3-5월 이사운", ("2026-03", "2026-05")),
        ("5월은 어때?", ("2026-05", "2026-05")),
        ("11월 취업운", ("2026-11", "2026-11")),
        ("8월과 10월 중 언제가 나아?", ("2026-08", "2026-10")),
        # 말한 순서가 거꾸로여도 두 달이 모두 지난 달이면 같은 해 비교로 둔다.
        ("10월과 8월 중 언제가 나아?", ("2026-08", "2026-10")),
        # 과거 시제면 지난 구간으로 읽는다.
        ("11월부터 1월까지 너무 힘들었어", ("2025-11", "2026-01")),
    ],
)
def test_month_expressions_without_wrap_are_unchanged(text: str, expected: tuple[str, str]) -> None:
    assert _span(text) == expected


def test_wrapped_range_in_progress_reads_current_span() -> None:
    # 1월에 "12월부터 2월까지"는 지금 진행 중인 겨울 구간이다(내년 12월이 아니다).
    assert _span("12월부터 2월까지 재물운", date(2027, 1, 5)) == ("2026-12", "2027-02")
    # 반례: 6월에 물으면 다가오는 구간이다. 두 달이 모두 남아 있는 비교는 넘기지 않는다.
    assert _span("11월부터 1월까지 취업운", date(2026, 6, 10)) == ("2026-11", "2027-01")
    assert _span("10월과 8월 중 언제가 나아?", date(2026, 6, 10)) == ("2026-08", "2026-10")


@pytest.mark.parametrize(
    "text",
    [
        "내 사주 구조를 바탕으로 11월부터 1월까지의 취업운을 정리해줘",
        "내 사주를 바탕으로 내년 이직운 알려줘",
        "내 사주로 볼 때 올해 연애운은?",
        "내 사주 기준으로 다음 달 재물운 알려줘",
    ],
)
def test_chart_preamble_with_domain_is_not_chart_analysis(text: str) -> None:
    assert _detect_query_type(text, SubjectMode.SINGLE) is not QueryType.CHART_ANALYSIS


@pytest.mark.parametrize(
    "text",
    [
        # 반례: 분야가 없거나 명식 구조 어휘가 함께 있으면 종전대로 명식 구조 질문이다.
        "내 사주 구조 설명해줘",
        "내 사주 어때?",
        "내 사주 구조를 바탕으로 성격 알려줘",
        "내 사주에서 용신이 뭐야",
        "내 사주에 재물복 있어?",  # 머리말이 아니라 원국에 묻는 질문
    ],
)
def test_chart_questions_stay_chart_analysis(text: str) -> None:
    assert _detect_query_type(text, SubjectMode.SINGLE) is QueryType.CHART_ANALYSIS
