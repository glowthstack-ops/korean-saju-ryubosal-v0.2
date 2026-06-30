"""claim recheck(B) — 직전 풀이 이의/반문 후속을 직전 주제 분석으로 전환.

핵심 검증: ① FEEDBACK_CORRECTION + 직전 분석 맥락 → 분석 query_type 전환·is_recheck ② 도메인/이벤트/
시점 상속 ③ 맥락 없으면(새 스레드) 전환 안 함(canned 유지) ④ 직전이 비분석이면 전환 안 함.
"""

from __future__ import annotations

from saju_api.services.chat_service import _recheck_continuation
from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeRange


def _intent(qt: QueryType, domain: Domain = Domain.GENERAL, time=None) -> IntentJson:
    return IntentJson(intent_id="x", query_type=qt, domain=domain, time_range=time)


def test_recheck_inherits_prior_analysis() -> None:
    prior = _intent(
        QueryType.TIMING_SEARCH, Domain.RELATIONSHIP,
        TimeRange(type="range", granularity="year", start="2026", end="2035"),
    )
    cur = _intent(QueryType.FEEDBACK_CORRECTION)  # "...아니야?"
    out, is_recheck = _recheck_continuation(cur, prior)
    assert is_recheck is True
    assert out.query_type is QueryType.TIMING_SEARCH       # 분석으로 전환
    assert out.domain is Domain.RELATIONSHIP               # 도메인 상속
    assert out.time_range is not None and out.time_range.start == "2026"  # 시점 상속


def test_no_prior_keeps_correction() -> None:
    """새 스레드(직전 맥락 없음) → 전환 안 함(canned claim_recheck 유지)."""
    cur = _intent(QueryType.FEEDBACK_CORRECTION)
    out, is_recheck = _recheck_continuation(cur, None)
    assert is_recheck is False
    assert out.query_type is QueryType.FEEDBACK_CORRECTION


def test_prior_non_analysis_keeps_correction() -> None:
    """직전이 분석 질문이 아니면(예: 용어교육) 재검토 대상 아님."""
    prior = _intent(QueryType.TERMINOLOGY_EDUCATION)
    cur = _intent(QueryType.FEEDBACK_CORRECTION)
    out, is_recheck = _recheck_continuation(cur, prior)
    assert is_recheck is False
    assert out.query_type is QueryType.FEEDBACK_CORRECTION


def test_non_correction_unchanged() -> None:
    prior = _intent(QueryType.TIMING_SEARCH, Domain.RELATIONSHIP)
    cur = _intent(QueryType.DOMAIN_ANALYSIS, Domain.WEALTH)
    out, is_recheck = _recheck_continuation(cur, prior)
    assert is_recheck is False
    assert out.query_type is QueryType.DOMAIN_ANALYSIS and out.domain is Domain.WEALTH


def test_current_domain_wins_over_prior_when_specific() -> None:
    """현재 턴이 구체 도메인이면 그것을 유지(prior로 덮어쓰지 않음)."""
    prior = _intent(QueryType.TIMING_SEARCH, Domain.RELATIONSHIP)
    cur = _intent(QueryType.FEEDBACK_CORRECTION, Domain.WEALTH)
    out, is_recheck = _recheck_continuation(cur, prior)
    assert is_recheck is True and out.domain is Domain.WEALTH
