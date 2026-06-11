"""Execution Planner 검증 (Phase 3 T3.3·T3.8 — docs/03 B4 고정 템플릿·결정성)."""

from __future__ import annotations

import pytest

from saju_engines.planner import build_execution_plan, build_plans
from saju_shared_types.events import EventKey
from saju_shared_types.intent import (
    Constraints,
    Domain,
    Granularity,
    IntentJson,
    QueryType,
    SubjectKind,
    SubjectMode,
    SubjectRef,
    TimeRange,
    TimeScope,
)

_SELF = SubjectRef(kind=SubjectKind.SELF, label="본인")


def _intent(**over) -> IntentJson:
    """기본 intent(본인·career·중기)."""
    base = dict(
        intent_id="i1",
        query_type=QueryType.DOMAIN_ANALYSIS,
        subjects=[_SELF],
        domain=Domain.CAREER,
        time_scope=TimeScope.MID_TERM,
    )
    base.update(over)
    return IntentJson(**base)


def test_same_intent_same_plan() -> None:
    """검수 포인트(docs/07): 동일 질문 → 동일 ExecutionPlan(결정성)."""
    a = build_execution_plan(_intent())
    b = build_execution_plan(_intent())
    assert a.model_dump() == b.model_dump()


def test_q2_routes_to_domain_module() -> None:
    """Q2 domain_analysis: career → topic:M07 + 분할 사전 로드."""
    plan = build_execution_plan(_intent())
    engines = [c.engine for c in plan.engine_calls]
    assert "topic:M07" in engines
    assert "events/career_change" in plan.dictionary_scope
    assert EventKey.CAREER_CHANGE in plan.graph_scope
    # 공통 마무리 체인: 그래프 검색 → 컨텍스트 축소 → LLM(서술만).
    assert engines[-3:] == ["graph_retrieval", "context_reduction", "llm"]


def test_q3_timing_search_progress_pipeline() -> None:
    """Q3: Event Scoring → Timeline → Manifestation → Advice (docs/03 B4)."""
    plan = build_execution_plan(_intent(
        query_type=QueryType.TIMING_SEARCH, event_key=EventKey.MARRIAGE,
        domain=Domain.RELATIONSHIP,
    ))
    engines = [c.engine for c in plan.engine_calls]
    order = [engines.index(e) for e in ("event_scoring", "timeline", "manifestation", "advice")]
    assert order == sorted(order)  # 순서 보장


def test_q4_date_recommendation_full_chain() -> None:
    """Q4: macro→월적합→일후보→리스크→캘린더→현실제약→랭킹 + 분기(방위/시진/체인)."""
    plan = build_execution_plan(_intent(
        query_type=QueryType.DATE_RECOMMENDATION, domain=Domain.RELOCATION,
        event_key=EventKey.RELOCATION,
        constraints=Constraints(
            direction="남동", location_base="일산 동구",
            chained_schedule=[{"step": "이사", "offset_from": "계약", "window": "2~3개월"}],
        ),
        time_range=TimeRange(type="deadline", granularity=Granularity.HOUR),
    ), taxonomy={EventKey.RELOCATION: "hybrid"})
    engines = [c.engine for c in plan.engine_calls]
    chain = ["macro_flow_check", "month_fit_filter", "day_candidates",
             "risk_filter", "calendar_rule", "reality_constraint", "ranking"]
    idx = [engines.index(e) for e in chain]
    assert idx == sorted(idx)
    assert "direction_rules" in engines and "hour_fit" in engines
    assert "chain_schedule" in engines
    assert plan.event_type == "hybrid"  # taxonomy 정적 분류 반영


def test_q6_comparison_per_subject() -> None:
    """Q6 비교: 다중 대상 → per_subject + M13."""
    other = SubjectRef(kind=SubjectKind.COMPANION, label="1호", companion_id="c1")
    plan = build_execution_plan(_intent(
        query_type=QueryType.COMPARISON, subjects=[_SELF, other],
        subject_mode=SubjectMode.PAIRWISE, domain=Domain.RELATIONSHIP,
    ))
    assert plan.per_subject is True
    assert any(c.engine == "topic:M13" for c in plan.engine_calls)
    # 다중 대상 → 비교용 LLM 예산(chat_compare).
    llm = next(c for c in plan.engine_calls if c.engine == "llm")
    assert llm.params["call_type"] == "chat_compare"


@pytest.mark.parametrize("qt,route", [
    (QueryType.TERMINOLOGY_EDUCATION, "terminology"),
    (QueryType.FEEDBACK_CORRECTION, "claim_recheck"),
    (QueryType.EMOTIONAL_SUPPORT, "empathy_first"),
    (QueryType.OUT_OF_SCOPE, "fixed_policy"),
])
def test_policy_routes_skip_analysis(qt: QueryType, route: str) -> None:
    """T3.8: Q11~Q14는 분석 파이프라인 미진입(정책 라우트)."""
    plan = build_execution_plan(_intent(query_type=qt))
    assert plan.policy_route == route
    engines = [c.engine for c in plan.engine_calls]
    assert "event_scoring" not in engines and "precompute:ensure_current" not in engines


def test_q14_out_of_scope_no_llm_required() -> None:
    """Q14: 고정 정책 응답 — 엔진/LLM 호출 없음(템플릿 응답)."""
    plan = build_execution_plan(_intent(query_type=QueryType.OUT_OF_SCOPE))
    assert plan.engine_calls == []


def test_multi_intent_plan_array() -> None:
    """다중 intent → intent 수만큼 plan(답변 섹션 보장 기반, docs/03 B4)."""
    intents = [
        _intent(intent_id="i1"),
        _intent(intent_id="i2", query_type=QueryType.TIMING_SEARCH,
                domain=Domain.RELATIONSHIP, event_key=EventKey.MARRIAGE),
    ]
    plans = build_plans(intents)
    assert len(plans) == 2
    assert plans[0].intent.intent_id == "i1" and plans[1].intent.intent_id == "i2"


def test_graph_scope_includes_explicit_event_keys() -> None:
    """명시 eventKey는 도메인 기본 graphScope에 추가된다."""
    plan = build_execution_plan(_intent(
        domain=Domain.GENERAL, event_key=EventKey.LAWSUIT,
    ))
    assert EventKey.LAWSUIT in plan.graph_scope