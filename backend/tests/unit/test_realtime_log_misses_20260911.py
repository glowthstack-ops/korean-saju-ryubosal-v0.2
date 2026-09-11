"""실로그 미인식 사례 회귀(2026-09-11 전수 점검 — 추천 순서 1·2·4).

DB 738쌍 재판정에서 현재 코드로도 바운스되던 사례 중 이번에 처리한 것:
  1. 시험일 질문의 동반자 바운스 — 본문 날짜가 즉석 출생일로 잡혀 본인이 빠짐
  2. 업무 변화 질문의 정서 지지 오분류 — '힘들어질까'가 감정 어휘에 삼켜짐
  4. 지원 경로 질문 — '원서·추천·제안'에 career 어휘 없음
"""
from __future__ import annotations

from datetime import date

import pytest

import saju_api.services.chat_service as cs
from saju_engines.query_parser import parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain, QueryType, SubjectKind

_TODAY = date(2026, 8, 21)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-08-21",
)


# ── 1. 본문 날짜 ≠ 즉석 출생일 ────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "2026년 8월 25일에 시험이 있어\n공부는 많이 못했는데 그날의 운세가 어떨지 알려줘",
    "2006년 8월 25일에 시험이 있습니다\n공부는 많이 못했는데 그날의 운세는 어떨까요?",  # 일정 표현
    "2026년 9월 30일에 이사가 예정되어 있어 주의할 점은?",
    "2027년 3월 2일 면접인데 그날 어때",  # 미래 날짜
])
def test_schedule_or_future_date_is_not_inline_birth(q: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    kinds = [s.kind for s in intent.subjects]
    assert kinds == [SubjectKind.SELF], kinds
    assert intent.time_range is not None  # 날짜는 시점으로는 살아 있다


@pytest.mark.parametrize("q", [
    "91년 10월 31일 오후 3시 부천에서 태어난 사람이랑 궁합 봐줘",
    "1972년 11월 7일생이 남편일 경우와 1980년 10월 8일생이 남편일 경우 둘 중 누가 더 잘 맞아?",
    "1998.07.23 여자랑 궁합 어때",
])
def test_genuine_inline_births_still_parsed(q: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    assert any(s.kind is SubjectKind.INLINE_TEMP for s in intent.subjects)


def test_exam_day_question_is_not_bounced_as_need_subject() -> None:
    """실로그 #1753 — 동반자 언급이 없는데 '비교할 대상' 바운스가 났다."""
    res = cs.chat(
        _BIRTH, "2026년 8월 25일에 시험이 있어\n공부는 많이 못했는데 그날의 운세가 어떨지 알려줘",
        _TODAY, dry_run=True, owner_id="t",
    )
    assert res.status == "dry_run", res.answer
    assert res.intents[0].domain is Domain.EDUCATION


# ── 2·4. 업무 변화 질문은 career 분석 경로 ───────────────────────────────

def test_work_change_question_is_career_not_emotional() -> None:
    q = "아 내 위의 리더가 다른팀으로가는데 그럼 나의업무 방향은 더 힘들어질까? 10월부터"
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.query_type is not QueryType.EMOTIONAL_SUPPORT
    assert intent.domain is Domain.CAREER
    res = cs.chat(_BIRTH, q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer


def test_application_channel_question_is_career() -> None:
    """실로그 #455 — 자발 지원 vs 추천·제안 경로 질문."""
    q = "내가 원서를 내야해 아님 추천이나 제안을 받게될까"
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.domain is Domain.CAREER
    res = cs.chat(_BIRTH, q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer
