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


# ── 진행 중 사업·동업 발화 → business_expansion 앵커(2026-11-03 데굴님 "그렇게 진행하는게 맞아") ──
def test_business_in_progress_anchors_business_expansion() -> None:
    """실사례: 자매 동업 질문이 career 도메인이지만 사건 키가 없어 이직·채용 제안 후보로 흘렀다."""
    from saju_shared_types.events import EventKey
    for q in ["언니랑 같이 작은 사업을 하고 있는데 동업 괜찮아?", "가게를 운영 중인데 올해 어때?",
              "동업 괜찮을까?", "장사하고 있는데 내년은 어떨까", "카페 차렸는데 잘 될까"]:
        it = _intent(q)
        assert it.event_key is EventKey.BUSINESS_EXPANSION, q
        assert it.domain is Domain.CAREER, q


def test_business_start_and_relocation_unchanged() -> None:
    """창업·개업은 기존 business_start, 사업장 이전은 거주 도메인(사업 사건 아님)."""
    from saju_shared_types.events import EventKey
    assert _intent("내년에 창업해도 될까?").event_key is EventKey.BUSINESS_START
    it = _intent("사업장 이전 시기가 언제가 좋을까?")  # 변경 전부터 career + domains[relocation]
    assert Domain.RELOCATION in (it.domain, *it.domains)
    assert it.event_key is not EventKey.BUSINESS_EXPANSION
    assert _intent("사업 운이 어때?").event_key is None  # '사업' 단독은 도메인 어휘로만


def test_business_in_progress_routes_to_m08() -> None:
    from saju_engines.planner import build_execution_plan
    plan = build_execution_plan(_intent("언니랑 같이 작은 사업을 하고 있는데 동업 괜찮아?"))
    engines = [c.engine for c in plan.engine_calls]
    assert "topic:M08" in engines and "topic:M07" not in engines
    plan2 = build_execution_plan(_intent("올 겨울 작업 수주가 잘될까?"))
    assert "topic:M07" in [c.engine for c in plan2.engine_calls]
