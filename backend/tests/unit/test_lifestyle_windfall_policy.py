"""생활형 횡재(로또·연금복권·주식) 정책 — 흐름·시기는 자유, 번호·종목픽·당첨단정은 거부.

CLAUDE.md 절대원칙 8(2026-06-20 개정): 픽/번호 요청만 OUT_OF_SCOPE로 거부하고,
흐름·시기·태도 질문은 통과시켜 _LIFESTYLE_WINDFALL_DIRECTIVE로 자유 서술한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _is_investment_flow, _is_lifestyle_windfall
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


# ── 투자·자산 운용 질문은 횡재가 아니다(2026-09-01 실로그) ─────────────────────────


def _intent(q: str, today: date = date(2026, 9, 1)):
    return parse_message(q, today).intents[0]


def test_investment_questions_are_not_lifestyle_windfall() -> None:
    """'주식' 한 단어로 횡재 판정돼 장기 투자 질문이 '오늘 복권' 답으로 흐르던 결함."""
    # 주의: 코인·펀드·청약·비트코인은 파서 재물 어휘(Domain.WEALTH)에 없어 general로 떨어진다
    # (기존 갭, 별건) — 여기서는 파서가 재물로 잡는 '주식' 형태로 판정 로직만 검증한다.
    for q in (
        "주식의 장기 투자가 실제 내 이익으로 돌아올까?",
        "주식 장기 투자 수익이 날까?",
        "주식 원금 회복될까",
        "주식 자산 배당 수익률 괜찮을까",
    ):
        intent = _intent(q)
        assert not _is_lifestyle_windfall(intent, q), q
        assert _is_investment_flow(intent, q), q
    # 상품 어휘 없는 투자 질문은 횡재도 아니고(복권 프레임 금지) 투자 지시문 대상도 아니다
    # (약한 키가 없으면 일반 재물 풀이 — 설계상 의도).
    q = "장기 투자 수익이 날까?"
    intent = _intent(q)
    assert not _is_lifestyle_windfall(intent, q)
    assert not _is_investment_flow(intent, q)


def test_flow_timing_questions_remain_lifestyle_windfall() -> None:
    """투자 표지 없는 흐름·시기 질문과 강한 횡재 키는 기존대로 생활형 횡재."""
    for q in ("주식운 어때", "로또 언제 사면 좋아", "연금복권 살만한 시기", "주식 소액으로 해볼까"):
        intent = _intent(q)
        assert _is_lifestyle_windfall(intent, q), q
        assert not _is_investment_flow(intent, q), q


def test_strong_windfall_key_wins_over_investment_marker() -> None:
    """강한 횡재 키가 있으면 투자 표지가 있어도 횡재(예: '로또 당첨금 투자')."""
    q = "로또 당첨금 투자하면 수익 날까"
    intent = _intent(q)
    assert _is_lifestyle_windfall(intent, q)
    assert not _is_investment_flow(intent, q)


def test_investment_flow_requires_wealth_context() -> None:
    """재물 맥락이 아니면 투자 지시문도 붙지 않는다."""
    q = "회사에서 장기 프로젝트 맡게 될까"
    intent = _intent(q)
    assert not _is_investment_flow(intent, q)
    assert not _is_lifestyle_windfall(intent, q)


def test_stock_pick_still_refused() -> None:
    """종목 픽 요청의 OUT_OF_SCOPE 거부는 그대로."""
    assert _qt("어떤 주식 살까 장기 투자로") is QueryType.OUT_OF_SCOPE
