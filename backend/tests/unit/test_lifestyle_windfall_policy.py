"""생활형 횡재(로또·연금복권·주식) 정책 — 흐름·시기는 자유, 번호·종목픽·당첨단정은 거부.

CLAUDE.md 절대원칙 8(2026-06-20 개정): 픽/번호 요청만 OUT_OF_SCOPE로 거부하고,
흐름·시기·태도 질문은 통과시켜 _LIFESTYLE_WINDFALL_DIRECTIVE로 자유 서술한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _is_lifestyle_windfall
from saju_engines.query_parser import parse_message
from saju_shared_types.intent import QueryType


def _qt(q: str) -> QueryType:
    return parse_message(q, date(2026, 6, 20)).intents[0].query_type


def test_number_and_pick_requests_refused() -> None:
    refused = (
        "로또 번호 알려줘", "번호 좀 찍어줘", "어떤 주식 살까", "종목 추천해줘", "무슨 코인 사",
    )
    for q in refused:
        assert _qt(q) is QueryType.OUT_OF_SCOPE, q


def test_flow_and_timing_questions_pass_through() -> None:
    # 흐름·시기 질문은 거부하지 않는다(생활형 횡재로 자유 풀이).
    for q in ("주식운 어때", "로또 언제 사면 좋아", "연금복권 살만한 시기", "이번 주 재물운"):
        assert _qt(q) is not QueryType.OUT_OF_SCOPE, q


def test_lifestyle_windfall_detection() -> None:
    intent = parse_message("로또 언제 사면 좋아", date(2026, 6, 20)).intents[0]
    assert _is_lifestyle_windfall(intent, "로또 언제 사면 좋아")
    # 횡재 키워드 없는 일반 재물 질문은 생활형 횡재 디렉티브 대상이 아니다.
    plain = parse_message("올해 돈 들어올까", date(2026, 6, 20)).intents[0]
    assert not _is_lifestyle_windfall(plain, "올해 돈 들어올까")
