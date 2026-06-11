"""Execution Planner (v2.2 Phase 3 T3.3·T3.8, docs/03 B4 — queryType별 고정 템플릿).

intent → 호출할 엔진 시퀀스 + 사전/그래프 범위. 템플릿은 docs/03 B4의 전체 규격을
그대로 코드화하며, LLM은 계획에 관여하지 않는다(동일 질문 → 동일 plan, 결정성).

Q11~Q14는 분석 파이프라인에 진입하지 않는 정책 라우트다(T3.8):
  Q11 용어 교육(사전+적용 예시), Q12 피드백 정정(claim 재검산), Q13 감정 우선(공감),
  Q14 범위 외(프롬프트 비공개·로또 번호 거부·악의 거절·스몰톡).
"""

from __future__ import annotations

from saju_shared_types.events import EventKey
from saju_shared_types.execution_plan import EngineCall, ExecutionPlan
from saju_shared_types.intent import Domain, IntentJson, QueryType, SubjectMode

# 분야별 Graph 조회 범위 (docs/03 C — graphScope 기본값).
_DOMAIN_GRAPH_SCOPE: dict[Domain, list[EventKey]] = {
    Domain.CAREER: [
        EventKey.CAREER_CHANGE, EventKey.PROMOTION, EventKey.RESIGNATION,
        EventKey.BUSINESS_START, EventKey.CONTRACT,
    ],
    Domain.RELATIONSHIP: [
        EventKey.RELATIONSHIP_START, EventKey.RELATIONSHIP_END,
        EventKey.MARRIAGE, EventKey.CHILDBIRTH,
    ],
    Domain.RELOCATION: [EventKey.RELOCATION, EventKey.TRAVEL, EventKey.CONTRACT],
    Domain.WEALTH: [
        EventKey.WEALTH_CHANGE, EventKey.INCOME_CHANGE, EventKey.EXPENSE_RISK,
        EventKey.WINDFALL, EventKey.SPECULATION_RISK, EventKey.ASSET_VOLATILITY,
        EventKey.DOCUMENT,
    ],
    Domain.EDUCATION: [
        EventKey.EDUCATION_START, EventKey.EDUCATION_COMPLETE, EventKey.EXAM,
        EventKey.DOCUMENT,
    ],
    Domain.HEALTH: [EventKey.HEALTH_ISSUE, EventKey.SURGERY],
    Domain.GENERAL: [],
}

# 분야별 사전 분할 로드 범위 (docs/05 — intent 중심 분할 로드).
_DOMAIN_DICTS: dict[Domain, list[str]] = {
    Domain.CAREER: ["common", "relations", "events/career_change", "favorability_rules"],
    Domain.RELOCATION: [
        "common", "relations", "events/relocation", "favorability_rules",
        "calendar", "region_elements", "housing_rules",
    ],
    Domain.RELATIONSHIP: ["common", "relations", "favorability_rules"],
    Domain.WEALTH: ["common", "relations", "favorability_rules"],
    Domain.EDUCATION: ["common", "relations", "favorability_rules"],
    Domain.HEALTH: ["common", "relations", "favorability_rules"],
    Domain.GENERAL: ["common", "relations", "favorability_rules"],
}

# 도메인 → Topic Builder 모듈 (docs/09 4장 — Q2 domain_analysis 라우팅).
_DOMAIN_MODULE: dict[Domain, str] = {
    Domain.CAREER: "M07",
    Domain.RELATIONSHIP: "M01",
    Domain.RELOCATION: "M10",
    Domain.WEALTH: "M09",
    Domain.EDUCATION: "M12",
    Domain.HEALTH: "M11",
    Domain.GENERAL: "M15",
}

# 비분석 라우트 정책 (T3.8 — docs/03 B4 Q11~Q14).
_POLICY_ROUTES: dict[QueryType, str] = {
    QueryType.TERMINOLOGY_EDUCATION: "terminology",  # 용어 사전 + 적용 예시, 엔진 미호출
    QueryType.FEEDBACK_CORRECTION: "claim_recheck",  # claim 재검산 → 정정/근거 재설명
    QueryType.EMOTIONAL_SUPPORT: "empathy_first",  # 공감 우선, 풀이는 동의 시에만
    QueryType.OUT_OF_SCOPE: "fixed_policy",  # 프롬프트 비공개/로또 거부/악의 거절/스몰톡
}


def _event_type(intent: IntentJson, taxonomy: dict[EventKey, str]) -> str:
    """intent의 이벤트 시간 성격 — taxonomy 사전 정적 분류, 문맥 오버라이드는 파서 몫."""
    if intent.event_key is not None:
        return taxonomy.get(intent.event_key, "progress")
    if intent.query_type is QueryType.DATE_RECOMMENDATION:
        return "instant"
    if intent.query_type in _POLICY_ROUTES or intent.query_type is QueryType.CHART_ANALYSIS:
        return "none"
    return "progress"


def _graph_scope(intent: IntentJson) -> list[EventKey]:
    """intent 도메인(복수 포함) → graphScope 합집합(순서 유지)."""
    domains = [intent.domain, *intent.domains]
    out: list[EventKey] = []
    for d in domains:
        for key in _DOMAIN_GRAPH_SCOPE.get(d, []):
            if key not in out:
                out.append(key)
    explicit: list[EventKey | None] = [intent.event_key, *intent.event_keys]
    for extra in explicit:
        if extra is not None and extra not in out:
            out.append(extra)
    return out


def _dict_scope(intent: IntentJson) -> list[str]:
    """intent 도메인 → 사전 분할 로드 목록(중복 제거·순서 유지)."""
    out: list[str] = []
    for d in [intent.domain, *intent.domains]:
        for name in _DOMAIN_DICTS.get(d, []):
            if name not in out:
                out.append(name)
    return out


def build_execution_plan(
    intent: IntentJson, taxonomy: dict[EventKey, str] | None = None
) -> ExecutionPlan:
    """단일 intent → 고정 템플릿 실행 계획 (docs/03 B4).

    Args:
        intent: 파싱된 의도(대상 확정 완료 전제 — 절대 원칙 7).
        taxonomy: EventKey → progress/instant/hybrid (events/taxonomy.json 산출).

    Returns:
        엔진 호출 시퀀스가 확정된 ExecutionPlan(결정론).
    """
    taxonomy = taxonomy or {}
    qt = intent.query_type
    per_subject = intent.subject_mode is not SubjectMode.SINGLE or len(intent.subjects) > 1
    base = dict(
        intent=intent,
        event_type=_event_type(intent, taxonomy),
        dictionary_scope=_dict_scope(intent),
        graph_scope=_graph_scope(intent),
        per_subject=per_subject,
    )

    # ── 비분석 라우트 (T3.8) ──
    if qt in _POLICY_ROUTES:
        calls: list[EngineCall] = []
        if qt is QueryType.TERMINOLOGY_EDUCATION:
            calls = [
                EngineCall(engine="dictionary:terminology"),
                EngineCall(engine="llm", params={"call_type": "chat_single"}),
            ]
        elif qt is QueryType.FEEDBACK_CORRECTION:
            calls = [
                EngineCall(engine="entity:claim_lookup"),
                EngineCall(engine="engine:recheck"),
                EngineCall(engine="cases:append"),  # 사실 피드백 → cases.jsonl 적재
                EngineCall(engine="llm", params={"call_type": "chat_single"}),
            ]
        elif qt is QueryType.EMOTIONAL_SUPPORT:
            calls = [EngineCall(engine="llm", params={"call_type": "chat_single"})]
        # OUT_OF_SCOPE: 고정 정책 응답 — 엔진/LLM 모두 미호출 가능(템플릿 응답).
        return ExecutionPlan(**base, engine_calls=calls, policy_route=_POLICY_ROUTES[qt])

    # ── 분석 라우트 (docs/03 B4 템플릿) ──
    calls = [EngineCall(engine="precompute:ensure_current")]

    if qt is QueryType.FORTUNE_OVERVIEW:  # Q1
        calls += [
            EngineCall(engine="event_scoring", params={"levels": ["daewoon", "year"]}),
            EngineCall(engine="hierarchy_filter"),
            EngineCall(engine="past_validation:summary"),
        ]
    elif qt is QueryType.DOMAIN_ANALYSIS:  # Q2
        calls += [EngineCall(
            engine=f"topic:{_DOMAIN_MODULE[intent.domain]}",
            params={"domain": str(intent.domain)},
        )]
    elif qt is QueryType.TIMING_SEARCH:  # Q3 (progress)
        calls += [
            EngineCall(engine="event_scoring", params={"levels": ["year", "month"]}),
            EngineCall(engine="timeline"),
            EngineCall(engine="manifestation"),
            EngineCall(engine="advice"),
        ]
    elif qt is QueryType.DATE_RECOMMENDATION:  # Q4 (instant/hybrid)
        calls += [
            EngineCall(engine="macro_flow_check"),
            EngineCall(engine="month_fit_filter"),
            EngineCall(engine="day_candidates"),
            EngineCall(engine="risk_filter"),
            EngineCall(engine="calendar_rule"),
            EngineCall(engine="reality_constraint"),
            EngineCall(engine="ranking"),
        ]
        if intent.constraints.direction is not None:
            calls.append(EngineCall(
                engine="direction_rules",
                params={"location_base": intent.constraints.location_base},
            ))
        if intent.time_range is not None and intent.time_range.granularity == "hour":
            calls.append(EngineCall(engine="hour_fit"))  # 시진 단위 (docs/08 C17)
        if intent.constraints.chained_schedule:
            calls.append(EngineCall(engine="chain_schedule"))  # 데드라인 역산 (C9)
    elif qt is QueryType.EVENT_EXPLANATION:  # Q5 (past)
        calls += [
            EngineCall(engine="event_scoring", params={"direction": "past"}),
            EngineCall(engine="evidence_path"),
        ]
    elif qt is QueryType.COMPARISON:  # Q6 ⓐⓑⓒ
        calls += [EngineCall(
            engine="topic:M13",
            params={"mode": str(intent.subject_mode)},
        )]
    elif qt is QueryType.DECISION_SUPPORT:  # Q7
        calls += [
            EngineCall(engine="event_scoring", params={"per_option": True}),
            EngineCall(engine="manifestation"),
            EngineCall(engine="comparison_table", params={
                "exclude_options": intent.constraints.exclude_options,
            }),
        ]
    elif qt is QueryType.CHART_ANALYSIS:  # Q8
        calls += [EngineCall(engine="chart_analysis:t0")]
    elif qt is QueryType.RELATIONSHIP_ANALYSIS:  # Q9
        calls += [EngineCall(engine="topic:M13", params={"mode": "pairwise"})]
    elif qt is QueryType.REMEDY:  # Q10
        calls += [
            EngineCall(engine="weakness_nodes"),
            EngineCall(engine="dictionary:remedy"),
            EngineCall(engine="advice"),
        ]

    calls += [
        EngineCall(engine="graph_retrieval", params={"max_hops": 5}),
        EngineCall(engine="context_reduction"),
        EngineCall(engine="llm", params={
            "call_type": "chat_compare" if per_subject else "chat_single",
        }),
    ]
    return ExecutionPlan(**base, engine_calls=calls)


def build_plans(
    intents: list[IntentJson], taxonomy: dict[EventKey, str] | None = None
) -> list[ExecutionPlan]:
    """다중 intent → plan 배열 (docs/03 B4 — intent별 답변 섹션 보장의 기반)."""
    return [build_execution_plan(i, taxonomy) for i in intents]
