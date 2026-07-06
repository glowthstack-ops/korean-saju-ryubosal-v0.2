"""무시점·무분야 질문의 시점 유사도 보강 스킵 가드 (2026-07-06 회귀).

'앞으로 내 운세 알려줘'에 임베딩 시점 분류기가 구체 연도를 합성하면 B3 판정표의
too_broad('좁혀볼까요' 재작성 제안) 관문을 우회해 종합운으로 흘러간다. 무시점·무분야
(too_broad 판정) 질문은 보강 없이 time_range=None을 유지해야 한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _augment_time_by_similarity
from saju_engines.query_parser import parse_message
from saju_engines.rewriter import assess

_TODAY = date(2026, 7, 6)


def test_no_time_no_domain_skips_time_augment() -> None:
    """too_broad 대상 질문은 유사도 시점 합성 없이 time_range None 유지."""
    q = "앞으로 내 운세 알려줘"
    intent = parse_message(q, _TODAY).intents[0]
    assert assess(intent, q).status == "too_broad"  # 전제: B3 ✗시점 ✗분야
    out = _augment_time_by_similarity(intent, q, _TODAY, "2026-07")
    assert out.time_range is None


def test_domain_question_not_gated() -> None:
    """분야가 있는 질문은 too_broad가 아니므로 가드 대상이 아니다(보강 경로 유지)."""
    q = "요즘 직장운 어때"
    intent = parse_message(q, _TODAY).intents[0]
    assert assess(intent, q).status != "too_broad"
