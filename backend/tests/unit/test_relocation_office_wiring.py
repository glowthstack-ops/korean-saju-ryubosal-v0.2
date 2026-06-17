"""Phase R4 배선 — 사무실 이전 질문이 택일 라우트 + relocation_kind=office에 도달한다.

집 이사는 기본 home으로 유지하고, '사무실/사업장 이전' 신호가 있으면 office로 분기해
월주 중심 점수표가 실제 채팅 택일에 적용되게 한다(R4 도달 가능화).
"""

from __future__ import annotations

from datetime import date

from saju_engines.query_parser import parse_message
from saju_shared_types.intent import Domain, QueryType


def _intent(question: str):
    return parse_message(question, date(2026, 6, 11), birth_year=1990).intents[0]


def test_office_relocation_routes_to_date_recommendation() -> None:
    """'사무실 이전 좋은 날' → 택일 라우트 + 이사 도메인 + relocation_kind=office."""
    intent = _intent("사무실 이전 좋은 날 언제야?")
    assert intent.query_type is QueryType.DATE_RECOMMENDATION
    assert intent.domain is Domain.RELOCATION
    assert intent.relocation_kind == "office"


def test_business_place_relocation_is_office() -> None:
    """'사업장 이사' 도 office로 판정."""
    assert _intent("사업장 이사 길일 알려줘").relocation_kind == "office"


def test_home_relocation_defaults_home() -> None:
    """일반 이사 질문은 home 유지(기존 동작 보존)."""
    intent = _intent("이사 좋은 날 언제가 좋아?")
    assert intent.query_type is QueryType.DATE_RECOMMENDATION
    assert intent.relocation_kind == "home"


def test_non_relocation_question_is_home_default() -> None:
    """이사와 무관한 질문도 relocation_kind 기본 home(필드 항상 존재)."""
    assert _intent("올해 재물운 어때?").relocation_kind == "home"
