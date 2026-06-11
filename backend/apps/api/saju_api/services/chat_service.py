"""대화형 통변 오케스트레이션 서비스 (v2.2 MVP — 단일 질문 → 정확한 풀이).

파이프라인(docs/01·03): 파서(T3.1 룰 기반) → 대상/광범위 판정(T3.2) → 실행 계획(T3.3)
→ 만세 계산(캐시) → 이벤트 스코어링(P2) + 계층 필터 → Graph Retrieval(T2.2)
→ Context Reduction + LLM 입력 직렬화(T3.4/5, 가드 경유) → LLM 서술(또는 dry-run).

비분석 라우트(Q11~Q14)·too_broad·대상 확인은 LLM/엔진 호출 없이 정책 응답을 돌려준다.
대화 연속성(직전 intent 상속 등)은 Phase 4 Conversation Layer에서 확장한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from saju_engines import EventScorer, GraphIndex, filter_year_candidates, load_event_graph
from saju_engines.context_reducer import (
    build_llm_input,
    build_monthly_overview,
    event_ko,
    serialize_with_guard,
)
from saju_engines.conversation import ConversationEngine
from saju_engines.conversation_store import ConversationStore
from saju_engines.date_selection import DateSelectionEngine
from saju_engines.llm_guard import TokenBudgetExceeded
from saju_engines.persona import PersonaEngine
from saju_engines.planner import build_execution_plan
from saju_engines.precompute import CompositeBuilder
from saju_engines.query_parser import parse_message
from saju_engines.rewriter import QueryAssessment, assess
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState, ResultSummaryRef
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import IntentJson, QueryType
from saju_shared_types.llm_input import DateChoiceRow, DateSelectionBlock
from saju_shared_types.profile import PersonaConfig

from . import llm_client
from .manse_service import calculate

_BACKEND = Path(__file__).resolve().parents[4]
_DICTS = _BACKEND / "dictionaries"
_COMPILED_GRAPH = _BACKEND / "compiled" / "event_graph_v1.0.0.json"

# 정책 라우트 고정 응답(T3.8 — docs/03 B4 하단). LLM 미호출 템플릿.
_POLICY_ANSWERS = {
    "fixed_policy": (
        "요청하신 내용은 서비스 범위 밖입니다. 시스템 내부 정보(모델·프롬프트 등)는 "
        "공개하지 않으며, 로또 번호 생성은 어떤 형태로도 제공하지 않습니다. "
        "대신 날짜·방향·시간대 추천은 도와드릴 수 있어요."
    ),
    "empathy_first": (
        "마음이 많이 힘드셨겠어요. 이야기해 주셔서 감사합니다. "
        "원하시면 관련된 운의 흐름도 함께 살펴볼 수 있어요 — 편하실 때 말씀해 주세요."
    ),
    "terminology": (
        "용어 설명을 준비 중입니다. 구체적으로 어떤 용어가 궁금하신지 알려주시면 "
        "본인 사주에 적용한 예시와 함께 설명드릴게요."
    ),
    "claim_recheck": (
        "이전 풀이에 대한 지적 감사합니다. 해당 판정을 재검산하려면 대화 이력 연동이 "
        "필요합니다(준비 중). 출생 정보를 다시 확인해 주시면 즉시 재계산해 드릴게요."
    ),
}

_SCORE_LEVELS = {GanjiLevel.YEAR, GanjiLevel.MONTH}

# 모듈 캐시(사전·그래프는 결정적 — 프로세스 1회 로드).
_scorer: EventScorer | None = None
_graph_index: GraphIndex | None = None
_date_engine: DateSelectionEngine | None = None
_persona_engine: PersonaEngine | None = None

# 택일 목적으로 인정되는 이벤트(purpose_profiles 키) — 그 외는 이사로 폴백.
_DATE_PURPOSES = {
    EventKey.RELOCATION, EventKey.CONTRACT, EventKey.MARRIAGE,
    EventKey.SURGERY, EventKey.BUSINESS_START, EventKey.WINDFALL,
}
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


class ChatResponse(BaseModel):
    """대화형 응답 — answer가 본문, 나머지는 추적/디버그 메타."""

    status: str  # 'answered' | 'dry_run' | 'policy' | 'too_broad' | 'need_subject'
    answer: str | None = None
    intents: list[IntentJson] = Field(default_factory=list)
    assessment: QueryAssessment | None = None
    candidate_count: int = 0
    prompt_preview: str | None = None  # dry-run: LLM 입력 본문
    input_tokens: int | None = None
    thread_id: str | None = None  # 멀티턴 스레드(Phase 4)
    turn_no: int | None = None
    repeated: bool = False  # F7 — 동일 질문 반복(다른 각도 제시 신호)
    # docs/10 5장: 분량 큰 요청 → 상품 제안 카드(강제 유도 금지 — 축약 답변 병행).
    product_suggestion: dict | None = None


def _get_scorer() -> EventScorer:
    global _scorer
    if _scorer is None:
        _scorer = EventScorer(_DICTS)
    return _scorer


def _get_graph() -> GraphIndex:
    global _graph_index
    if _graph_index is None:
        _graph_index = GraphIndex(load_event_graph(_COMPILED_GRAPH))
    return _graph_index


def _get_date_engine() -> DateSelectionEngine:
    global _date_engine
    if _date_engine is None:
        _date_engine = DateSelectionEngine(_DICTS)
    return _date_engine


def _get_persona_engine() -> PersonaEngine:
    global _persona_engine
    if _persona_engine is None:
        _persona_engine = PersonaEngine(_DICTS)
    return _persona_engine


def _date_selection_block(
    birth: BirthInput, intent, today: date, yongsin: str | None
) -> DateSelectionBlock | None:
    """택일 라우트(P3): 질문 기간의 일운 합성을 만들어 E10 랭킹을 표로 제공.

    표가 있으면 LLM의 '날짜 정보 없음' 회피 답변을 지시로 차단한다(v1 원칙).
    """
    # 기간: 질문 해석 결과(월 단위 권장). 연 단위/무시점이면 오늘부터 30일.
    start_label = intent.time_range.start if intent.time_range else None
    if start_label and len(start_label) == 7:
        anchor = date.fromisoformat(start_label + "-15")
        start_iso = start_label + "-01"
        end_iso = start_label + "-31"
    else:
        anchor = today
        start_iso = today.isoformat()
        end_iso = (today.replace(day=1) + __import__("datetime").timedelta(days=62)
                   ).replace(day=1).isoformat()
    purpose = intent.event_key if intent.event_key in _DATE_PURPOSES else EventKey.RELOCATION

    chart = calculate(birth.model_copy(update={"reference_date": anchor}))
    composites = CompositeBuilder(_DICTS).build(
        chart, "chat", "1.0.0", f"{today.isoformat()}T00:00:00+00:00",
    )
    result = _get_date_engine().select(
        purpose, composites, start_iso, end_iso, yongsin_element=yongsin,
    )
    if not result.candidates:
        return None
    rows = [
        DateChoiceRow(
            date=c.date,
            weekday=_WEEKDAY_KO[date.fromisoformat(c.date).weekday()],
            ganji=c.ganji,
            score=c.scores.final,
            recommendation=c.recommendation,
            notes=(
                c.reasons
                + (["손없는 날"] if c.son_eomneun_nal and "손없는 날" not in c.reasons else [])
                + (["주말"] if c.is_weekend else [])
            ),
        )
        for c in result.candidates
        if c.recommendation != "avoid"  # 추천 표에는 회피 등급 제외(회피일은 별도 목록)
    ]
    return DateSelectionBlock(
        purpose_ko=event_ko(purpose),
        period=f"{start_iso} ~ {end_iso}",
        rows=rows,
        avoid=result.avoid_dates,
        cautions=result.cautions,
    )


def chat(
    birth: BirthInput,
    question: str,
    today: date | None = None,
    dry_run: bool = False,
    thread_id: str | None = None,
    store: ConversationStore | None = None,
    persona: PersonaConfig | None = None,
) -> ChatResponse:
    """질문을 풀이한다(첫 intent 기준, 다중 intent는 메타로 동반).

    Args:
        birth: 대상 출생 정보(현 단계 subject=요청 본문의 차트).
        question: 사용자 질문 원문.
        today: 기준일(미지정 시 reference_date 또는 오늘).
        dry_run: True면 LLM 미호출, 직렬화된 입력 본문을 반환(검증/개발용).
        thread_id: 지정 시 멀티턴 — 스레드 상태를 복원/갱신(Phase 4 Conversation Layer).
        store: 스레드 저장소(미지정+thread_id 있으면 기본 DSN으로 생성).

    Returns:
        ChatResponse — 정책/판정 라우트는 LLM·엔진 미호출로 즉시 응답.
    """
    today = today or birth.reference_date or date.today()
    birth_year = birth.birth_date.year

    # 멀티턴: 스레드 상태 복원 → 대화 엔진 경유(대상 해소·슬롯 상속·반복 감지).
    state: ConversationState | None = None
    repeated = False
    if thread_id is not None:
        store = store or ConversationStore()
        store.migrate()
        state = store.load(thread_id) or ConversationState(thread_id=thread_id)
        engine = ConversationEngine()
        parsed, state, resolution, _link = engine.process_turn(
            state, question, today, birth_year=birth_year,
        )
        repeated = state.repeat_count >= 2
        if resolution.unresolved:
            store.save(state)
            return ChatResponse(
                status="need_subject",
                answer=(
                    f"'{', '.join(resolution.unresolved)}'가 어느 분인지 확인이 필요해요. "
                    "등록된 동반자 별칭을 알려주시거나 출생 정보를 입력해 주세요."
                ),
                intents=parsed.intents, thread_id=thread_id, turn_no=state.turn_no,
            )
    else:
        parsed = parse_message(question, today, birth_year=birth_year)
    intent = parsed.intents[0]

    # 비분석 라우트(T3.8) — 엔진/LLM 미호출.
    plan = build_execution_plan(intent)
    if plan.policy_route is not None:
        _save_thread(store, state)
        return ChatResponse(
            status="policy",
            answer=_POLICY_ANSWERS.get(plan.policy_route, _POLICY_ANSWERS["fixed_policy"]),
            intents=parsed.intents, thread_id=thread_id,
            turn_no=state.turn_no if state else None, repeated=repeated,
        )

    # 광범위/대상 판정(T3.2) — 추측 실행 금지.
    assessment = assess(intent, question)
    if assessment.status in ("too_broad", "need_subject"):
        suggestion_text = " / ".join(s.label for s in assessment.rewrite_suggestions)
        answer = (
            assessment.clarify_question
            if assessment.status == "need_subject"
            else f"질문 범위가 넓어요. 이렇게 좁혀볼까요? — {suggestion_text}"
        )
        _save_thread(store, state)
        suggestion = None
        if assessment.status == "too_broad":
            suggestion = {
                "products": ["RPT_FULL", "RPT_FOCUS"],
                "reason": "전체 흐름을 깊게 보려면 총운/집중 풀이 보고서가 적합해요",
                "note": "대화로도 범위를 좁혀 바로 답해드릴 수 있어요",
            }
        return ChatResponse(
            status=assessment.status, answer=answer,
            intents=parsed.intents, assessment=assessment, thread_id=thread_id,
            turn_no=state.turn_no if state else None, repeated=repeated,
            product_suggestion=suggestion,
        )

    # 만세 계산(캐시) + 스코어링 + 계층 필터.
    chart_birth = birth.model_copy(update={"reference_date": today})
    result = calculate(chart_birth)
    all_scored = _get_scorer().score(result, levels=_SCORE_LEVELS)
    candidates = filter_year_candidates(all_scored)
    # P2 보강: 계층 필터(Top5)가 과거 고점에 점유돼도 질문 기간 후보는 보존.
    if intent.time_range is not None:
        from saju_engines.context_reducer import in_question_range

        seen = {(c.event_key, c.period) for c in candidates}
        candidates += [
            c for c in all_scored
            if (c.event_key, c.period) not in seen
            and in_question_range(c.period, intent.time_range.start, intent.time_range.end)
        ]

    # Graph Retrieval — plan의 graphScope만(전체 검색 금지).
    scope: list[EventKey] = plan.graph_scope or [c.event_key for c in candidates[:5]]
    bundles = _get_graph().retrieve(scope)

    # P4: 월 단위 요청("월별로"/granularity=month)이면 질문 연도 12개월 요약 동반.
    overview = None
    wants_monthly = "월별" in question or (
        intent.time_range is not None
        and intent.time_range.granularity.value == "month"
        and intent.time_range.start is not None
        and len(intent.time_range.start) == 4
    )
    if wants_monthly:
        start_label = intent.time_range.start if intent.time_range else None
        target_year = int((start_label or str(today.year))[:4])
        overview = build_monthly_overview(result, all_scored, target_year)

    # P3: 택일 질문이면 E10 랭킹 표 동반(표가 있으면 회피성 답변 금지 지시).
    date_block = None
    if intent.query_type is QueryType.DATE_RECOMMENDATION:
        from saju_engines.event_scoring import favorability_map

        fav = favorability_map(result)
        yongsin = next((el for el, role in fav.items() if role == "용신"), None)
        try:
            date_block = _date_selection_block(birth, intent, today, yongsin)
        except Exception:  # 택일 실패는 일반 풀이로 폴백(차단 금지)
            date_block = None

    # Context Reduction + 직렬화 + 가드.
    payload = build_llm_input(
        question, intent, result, candidates, bundles, _get_scorer(),
        call_type="chat_compare" if plan.per_subject else "chat_single",
        today=today,
        monthly_overview=overview,
        date_selection=date_block,
    )
    try:
        prompt_text, tokens = serialize_with_guard(
            payload, "chat_compare" if plan.per_subject else "chat_single"
        )
    except TokenBudgetExceeded as exc:
        return ChatResponse(
            status="too_broad",
            answer=(
                "질문 범위가 넓어 분석량이 한도를 초과했어요. "
                f"기간이나 분야를 좁혀주세요. ({exc})"
            ),
            intents=parsed.intents,
        )

    if state is not None:
        # T4.5 — 시스템이 제시한 상위 이벤트를 claim/event 엔티티로 등록(이의 재검산 대비).
        summaries = [
            ResultSummaryRef(
                kind="event", label=f"{c.event_key}@{c.period}",
                detail=f"score {c.score} · {c.polarity}",
            )
            for c in payload.event_candidates[:3]
        ]
        state = ConversationEngine.register_system_results(state, summaries)

    if dry_run or not llm_client.is_available():
        _save_thread(store, state)
        return ChatResponse(
            status="dry_run",
            intents=parsed.intents,
            assessment=assessment,
            candidate_count=len(payload.event_candidates),
            prompt_preview=prompt_text,
            input_tokens=tokens,
            thread_id=thread_id,
            turn_no=state.turn_no if state else None,
            repeated=repeated,
        )

    system = None
    if persona is not None:
        block = _get_persona_engine().build_block(persona, "회원")
        system = llm_client._SYSTEM_PROMPT + "\n\n" + block
    answer = llm_client.generate_reading(
        prompt_text,
        call_type="chat_compare" if plan.per_subject else "chat_single",
        system=system,
    )
    _save_thread(store, state)
    return ChatResponse(
        status="answered",
        answer=answer,
        intents=parsed.intents,
        assessment=assessment,
        candidate_count=len(payload.event_candidates),
        input_tokens=tokens,
        thread_id=thread_id,
        turn_no=state.turn_no if state else None,
        repeated=repeated,
    )


def _save_thread(store: ConversationStore | None, state: ConversationState | None) -> None:
    """멀티턴 경로에서만 스레드 상태를 저장한다."""
    if store is not None and state is not None:
        store.save(state)
