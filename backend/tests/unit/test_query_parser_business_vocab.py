"""수주형·자영업 직업 어휘 + 사업 성과 재물 어휘 (2026-09-23).

'올 겨울 작업 수주가 잘될까?'가 general→too_broad로 바운스되던 결함의 회귀 고정.
"""

from __future__ import annotations

from datetime import date

from saju_engines import query_parser as qp
from saju_engines.rewriter import assess
from saju_shared_types.intent import Domain

_T = date(2026, 9, 23)


def _intent(q: str):
    return qp.parse_message(q, _T).intents[0]


def test_order_intake_question_is_answered_not_bounced() -> None:
    """실로그 원문: 직업 도메인 + 겨울 절기 창으로 바로 실행(ok)."""
    it = _intent("올 겨울 작업 수주가 잘될까?")
    assert it.domain is Domain.CAREER
    assert it.time_range is not None and it.time_range.start == "2026-11"
    assert assess(it, "올 겨울 작업 수주가 잘될까?").status == "ok"


def test_self_employment_words_map_to_career() -> None:
    """수주·일감·거래처·납품·발주·장사·자영업·프리랜서·외주·영업 → career."""
    for q in ["일감이 많을까?", "거래처가 늘어날까", "납품 문제 없을까", "발주가 들어올까",
              "장사가 잘될까", "자영업 해도 될까", "프리랜서로 괜찮을까", "외주 받을 수 있을까",
              "영업이 잘될까"]:
        assert _intent(q).domain is Domain.CAREER, q


def test_sales_and_profit_map_to_wealth() -> None:
    """매출·수익은 재성 흐름이라 재물 도메인."""
    assert _intent("올해 매출이 좋을까?").domain is Domain.WEALTH
    assert _intent("내년 수익이 늘까?").domain is Domain.WEALTH


def test_gage_verb_form_not_career() -> None:
    """'가게 될까'(가다)는 상점이 아니므로 직업 도메인으로 오분류하지 않는다."""
    assert _intent("가게 될까?").domain is Domain.GENERAL
