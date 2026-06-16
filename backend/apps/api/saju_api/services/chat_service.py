"""대화형 통변 오케스트레이션 서비스 (v2.2 MVP — 단일 질문 → 정확한 풀이).

파이프라인(docs/01·03): 파서(T3.1 룰 기반) → 대상/광범위 판정(T3.2) → 실행 계획(T3.3)
→ 만세 계산(캐시) → 이벤트 스코어링(P2) + 계층 필터 → Graph Retrieval(T2.2)
→ Context Reduction + LLM 입력 직렬화(T3.4/5, 가드 경유) → LLM 서술(또는 dry-run).

비분석 라우트(Q11~Q14)·too_broad·대상 확인은 LLM/엔진 호출 없이 정책 응답을 돌려준다.
대화 연속성(직전 intent 상속 등)은 Phase 4 Conversation Layer에서 확장한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from saju_manse_analysis.luck.luck_calendar import luck_month_label

from saju_engines import EventEngineV2, GraphIndex, filter_year_candidates, load_event_graph
from saju_engines.chart_interpretation import build_luck_grounding
from saju_engines.compatibility_engine import analyze_compatibility, compatibility_lines
from saju_engines.context_reducer import (
    build_birth_summary,
    build_llm_input,
    build_monthly_overview,
    event_ko,
    serialize_with_guard,
)
from saju_engines.conversation import ConversationEngine
from saju_engines.conversation_store import ConversationStore
from saju_engines.date_selection import DateSelectionEngine
from saju_engines.intent_event_filter import IntentEventFilter
from saju_engines.llm_guard import TokenBudgetExceeded
from saju_engines.persona import PersonaEngine
from saju_engines.planner import build_execution_plan
from saju_engines.precompute import CompositeBuilder
from saju_engines.query_parser import parse_message
from saju_engines.rewriter import QueryAssessment, assess
from saju_engines.topic_builder import build_lifestyle_context
from saju_engines.wealth_capacity import analyze_wealth_capacity
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState, ResultSummaryRef
from saju_shared_types.event_taxonomy_v2 import DATE_PURPOSES, EVENT_TYPE
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import Domain, IntentJson, QueryType, SubjectKind, SubjectRef
from saju_shared_types.llm_input import (
    DateChoiceRow,
    DateSelectionBlock,
    PeriodFortune,
    PeriodFortuneSlot,
)
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.precompute import CompositeLevel
from saju_shared_types.profile import PersonaConfig
from saju_shared_types.topic_context import PeriodSpec

from . import llm_client
from .manse_service import calculate, daily_luck_window, luck_days, luck_months
from .personalization import fetch_personal_inputs

_BACKEND = Path(__file__).resolve().parents[4]
_DICTS = _BACKEND / "dictionaries"
_COMPILED_GRAPH = _BACKEND / "compiled" / "event_graph_v1.1.0.json"


def _current_luck_month(today: date, timezone: str = "Asia/Seoul") -> str:
    """오늘이 속한 절기 월운 라벨(YYYY-MM) — 양력 today.month의 절기 경계 어긋남 보정.

    월운 LuckPillar 라벨이 생성된 차트 타임존과 동일 기준으로 잡아야 정합한다(미상 시 KST).
    """
    return luck_month_label(today, get_table(), timezone)


def _solar_month_range(label: str, timezone: str = "Asia/Seoul") -> tuple[date, date]:
    """절기 월 라벨(YYYY-MM)의 절입~다음 절입 전일 양력 범위를 반환한다(양끝 포함).

    월운은 절기 월이라 양력 두 달에 걸친다(예: 未월=소서 7/7~입추 8/7 직전). 당월 총운의
    일 단위(주의/기회 시기) 산정 범위를 양력 월이 아니라 절기 월로 맞추는 데 쓴다.

    Returns:
        (절입일, 다음 절입 전일) — 양끝 포함.
    """
    tz = ZoneInfo(timezone)
    y, m = int(label[:4]), int(label[5:7])
    # 그 달 15일 정오는 항상 그 달 節 이후·다음 節 이전(절기 월 내부)이라 경계 산출 기준점.
    mid = datetime(y, m, 15, 12, 0, tzinfo=tz)
    prev_jeol, next_jeol = get_table().bounding_month_terms(mid)
    return prev_jeol.astimezone(tz).date(), next_jeol.astimezone(tz).date() - timedelta(days=1)

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
_scorer: EventEngineV2 | None = None
_graph_index: GraphIndex | None = None
_date_engine: DateSelectionEngine | None = None
_persona_engine: PersonaEngine | None = None
_intent_filter: IntentEventFilter | None = None

# 택일 목적으로 인정되는 이벤트(purpose_profiles 키) — 그 외는 이사로 폴백. 21키 기준(Phase 7).
_DATE_PURPOSES = DATE_PURPOSES
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
# 과거 회고 신호 — 있으면 미래지향 앵커링(default_period)을 적용하지 않는다.
# 과거형 어미('쉬었던/언제였을까' 등) 포함 — 미감지 시 과거 질문이 미래 창으로
# 클램프돼 '이전 데이터 미제공' 회피가 발생(2026-06-12 지적).
_PAST_KEYWORDS = (
    "작년", "재작년", "지난", "과거", "예전", "그때", "했었", "였었",
    "무슨 일", "뭐였", "어땠", "있었",
    "였을까", "었을까", "았을까", "였던", "었던", "았던", "였지", "었지",
)


class ChatResponse(BaseModel):
    """대화형 응답 — answer가 본문, 나머지는 추적/디버그 메타."""

    status: str  # 'answered' | 'pending' | 'dry_run' | 'policy' | 'too_broad' | 'need_subject'
    answer: str | None = None
    message_id: int | None = None  # 'pending' 응답 — 백그라운드 생성 중인 답변 메시지 id
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
    # 백그라운드 생성용 — dry_run 응답이 LLM 호출에 필요한 모든 것을 운반한다.
    # (라우터가 이걸로 connection-독립 백그라운드 태스크를 띄운다.)
    system_prompt: str | None = None
    call_type: str | None = None


def _get_scorer() -> EventEngineV2:
    global _scorer
    if _scorer is None:
        _scorer = EventEngineV2(_DICTS)
    return _scorer


def _get_graph() -> GraphIndex:
    global _graph_index
    if _graph_index is None:
        _graph_index = GraphIndex(load_event_graph(_COMPILED_GRAPH))
    return _graph_index


def _get_intent_filter() -> IntentEventFilter:
    global _intent_filter
    if _intent_filter is None:
        _intent_filter = IntentEventFilter(_DICTS)
    return _intent_filter


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


def _months_between(start_month: str, end_month: str, cap: int = 13) -> list[str]:
    """'YYYY-MM' 구간의 월 라벨 목록(양끝 포함, cap 상한) — '지난 1년' 등 창 기반 표용."""
    sy, sm = int(start_month[:4]), int(start_month[5:7])
    ey, em = int(end_month[:4]), int(end_month[5:7])
    count = min((ey * 12 + em) - (sy * 12 + sm) + 1, cap)
    return _rolling_months(sy, sm, max(count, 1))


def _rolling_months(year: int, month: int, count: int = 12) -> list[str]:
    """주어진 (연, 월)부터 count개월의 'YYYY-MM' 라벨을 순서대로 반환한다.

    '앞으로 1년' 등 상대-미래 질문에서 오늘(기준 시점)의 달부터 시작하는 롤링
    창을 만든다. 달력상 1~12월이 아니라 기준 시점 기반이어야 한다(2026-06-12 지적).
    """
    out: list[str] = []
    for i in range(count):
        idx = (month - 1) + i
        yy = year + idx // 12
        mm = idx % 12 + 1
        out.append(f"{yy}-{mm:02d}")
    return out


def _period_fortune_type(intent: IntentJson, question: str) -> str | None:
    """총운 라우팅 대상이면 fortune_type('daily'/'monthly'/'yearly')을, 아니면 None.

    특정 기간(단일 일/월/연)의 종합운(fortune_overview)만 대상이다. 주간(일 범위)은
    날들의 종합이라 성격이 달라 제외하고, 도메인 한정 질문도 제외한다. '월별/달별/
    일별' 등 하위 단위 분해 요청은 총운이 아니라 월별 표 경로이므로 제외한다.
    """
    if intent.query_type is not QueryType.FORTUNE_OVERVIEW:
        return None
    if any(k in question for k in ("월별", "달별", "일별", "날짜별", "주별")):
        return None
    tr = intent.time_range
    if tr is None or not tr.start:
        return None
    if (tr.end or tr.start) != tr.start:  # 단일 기간만(범위는 기존 경로)
        return None
    g = tr.granularity.value
    if g == "day" and len(tr.start) == 10:
        return "daily"
    if g == "month" and len(tr.start) == 7:
        return "monthly"
    if g == "year" and len(tr.start) == 4:
        return "yearly"
    return None


def _build_period_fortune(
    birth: BirthInput, intent: IntentJson, today: date, fortune_type: str
) -> PeriodFortune | None:
    """특정 기간(일/월/연) 총운 — E9 Lifestyle 슬롯 + 해당 기간 간지 grounding 조립.

    운 위계(대운>세운>월>일)에서 상위가 형성한 기운이 하위 기간에서 사건화되며,
    슬롯 점수는 위계 가중 합산이다(topic_builder). 출력 framing은 해당 기간 단위
    사건·조짐으로 한정하고 인생 사건의 실행·확정은 단정하지 않는다(절대원칙 3·4).

    Args:
        birth: 대상 출생 정보.
        intent: 파서가 확정한 의도(time_range.start = 'YYYY-MM-DD'/'YYYY-MM'/'YYYY').
        today: 기준일(computed_at 결정성 유지용).
        fortune_type: 'daily' | 'monthly' | 'yearly'.

    Returns:
        조립된 PeriodFortune. 해당 기간 운을 찾지 못하면 None(일반 경로 폴백).
    """
    assert intent.time_range is not None and intent.time_range.start is not None
    start = intent.time_range.start
    computed_at = f"{today.isoformat()}T00:00:00+00:00"
    _DAY_LEVELS = {
        CompositeLevel.DAY, CompositeLevel.MONTH, CompositeLevel.YEAR, CompositeLevel.NATAL,
    }
    _YEAR_LEVELS = {CompositeLevel.MONTH, CompositeLevel.YEAR, CompositeLevel.NATAL}

    if fortune_type == "daily":
        try:
            target = date.fromisoformat(start)
        except ValueError:
            return None
        chart = calculate(birth.model_copy(update={"reference_date": target}))
        days = luck_days(birth, target.year, target.month)
        if chart.luck_cycles is not None:
            chart.luck_cycles.daily_luck = days
        pillar = next((p for p in days if p.label == start), None)
        period = PeriodSpec(start=start, end=start, granularity="day")
        levels = _DAY_LEVELS
        label = f"{start} ({_WEEKDAY_KO[target.weekday()]})"
    elif fortune_type == "monthly":
        year, mon = int(start[:4]), int(start[5:7])
        anchor = date(year, mon, 15)
        chart = calculate(birth.model_copy(update={"reference_date": anchor}))
        # 절기 월 범위(절입~다음 절입 전일) — 양력 월이 아니라 절기 경계로 일운을 잡는다.
        tz = chart.time_correction.timezone if chart.time_correction else "Asia/Seoul"
        sm_start, sm_end = _solar_month_range(start, tz)
        if chart.luck_cycles is not None:
            chart.luck_cycles.monthly_luck = luck_months(birth, year)
            # 절기 월은 양력 두 달에 걸치므로 걸치는 달들의 일운을 합친다. PeriodSpec를
            # 절기 범위로 둬 _in_period가 절기 경계의 일운만 남긴다(주의/기회 시기 정합).
            days = luck_days(birth, sm_start.year, sm_start.month)
            if (sm_end.year, sm_end.month) != (sm_start.year, sm_start.month):
                days += luck_days(birth, sm_end.year, sm_end.month)
            chart.luck_cycles.daily_luck = days
            pillar = next(
                (p for p in chart.luck_cycles.monthly_luck if p.label == start), None
            )
        else:
            pillar = None
        period = PeriodSpec(
            start=sm_start.isoformat(), end=sm_end.isoformat(), granularity="month"
        )
        levels = _DAY_LEVELS
        label = start
    else:  # yearly
        year = int(start[:4])
        anchor = date(year, 7, 1)
        chart = calculate(birth.model_copy(update={"reference_date": anchor}))
        if chart.luck_cycles is not None:
            chart.luck_cycles.monthly_luck = luck_months(birth, year)
            pillar = next(
                (p for p in chart.luck_cycles.yearly_luck if p.label == start), None
            )
        else:
            pillar = None
        period = PeriodSpec(start=f"{start}-01-01", end=f"{start}-12-31", granularity="year")
        levels = _YEAR_LEVELS
        label = start

    if pillar is None:
        return None

    composites = CompositeBuilder(_DICTS).build(chart, "chat", "1.0.0", computed_at, levels=levels)
    if fortune_type == "monthly":
        # 절기 범위가 두 양력 월에 걸쳐 인접 절기월의 월운 composite가 _in_period(월 비교)에
        # 섞이지 않도록, 월 단위는 당월(start) 라벨만 남긴다(일·연·원국 composite는 유지).
        composites = [
            c for c in composites
            if c.level is not CompositeLevel.MONTH or c.period_key == start
        ]
    ctx = build_lifestyle_context(
        [SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period, composites, dictionaries_dir=_DICTS,
    )
    grounding = build_luck_grounding(chart, pillar)
    slots = [
        PeriodFortuneSlot(
            name=f.key.removeprefix("slot:"), score=f.score, summary=f.summary,
        )
        for f in ctx.findings
    ]
    return PeriodFortune(
        fortune_type=fortune_type,
        period_label=label,
        ganji=pillar.ganji,
        pillar_line=grounding["pillar_line"],
        luck_label=pillar.luck_label,
        luck_summary=pillar.luck_summary,
        relation_lines=grounding["relation_lines"],
        sinsal_lines=grounding["sinsal_lines"],
        gongmang=grounding["gongmang"],
        slots=slots,
    )


def _next_month_label(d: date) -> str:
    """주어진 날짜 다음 달을 'YYYY년 M월' 형태로 — 택일 한 달 윈도우 재질문 예시용."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return f"{y}년 {m}월"


def _date_selection_block(
    birth: BirthInput, intent, today: date, yongsin: str | None
) -> DateSelectionBlock | None:
    """택일 라우트(P3): 질문 기간의 일운 합성을 만들어 E10 랭킹을 표로 제공.

    표가 있으면 LLM의 '날짜 정보 없음' 회피 답변을 지시로 차단한다(v1 원칙).
    """
    # 기간: 질문 해석 결과로 탐색 시작·종료를 정한다. 택일은 한 번에 약 한 달만 탐색하고,
    # 요청이 그보다 넓거나 개방형('이후')이면 끝을 한 달로 캡한 뒤 안내문을 덧붙인다(2026-06-16).
    tr = intent.time_range
    start_label = tr.start if tr else None
    end_label = tr.end if tr else None

    # 시작일: 일 단위(YYYY-MM-DD) > 월 단위(YYYY-MM, 1일) > 무시점(오늘). 과거면 오늘로 당김.
    if start_label and len(start_label) == 10:
        req_start = date.fromisoformat(start_label)
    elif start_label and len(start_label) == 7:
        req_start = date.fromisoformat(start_label + "-01")
    else:
        req_start = today
    if req_start < today:
        req_start = today

    # 요청 종료(있으면): 일 단위 그대로, 월 단위면 그 달 말일. 개방형/무시점이면 None.
    req_end: date | None = None
    if end_label and len(end_label) == 10:
        req_end = date.fromisoformat(end_label)
    elif end_label and len(end_label) == 7:
        ey, em = (int(x) for x in end_label.split("-"))
        nxt = date(ey + (em // 12), (em % 12) + 1, 1)
        req_end = nxt - timedelta(days=1)

    # 한 달 캡: 시작일 + 30일, 단 같은 해(연말)를 넘지 않게(월운 부모 결측 방지).
    year_end = date(req_start.year, 12, 31)
    scan_end = min(req_start + timedelta(days=30), year_end)
    if req_end is not None:
        scan_end = min(scan_end, req_end)
    if scan_end < req_start:
        scan_end = req_start
    # 요청이 탐색 윈도우를 넘으면(개방형 '이후' 또는 한 달 초과) 안내 대상.
    if req_end is None:
        truncated = start_label is not None  # 종료 미지정 + 시작 명시 = 개방형('이후')
    else:
        truncated = req_end > scan_end

    start_iso = req_start.isoformat()
    end_iso = scan_end.isoformat()
    anchor = req_start
    purpose = intent.event_key if intent.event_key in _DATE_PURPOSES else EventKey.RELOCATION

    chart = calculate(birth.model_copy(update={"reference_date": anchor}))
    # 일운을 탐색 윈도우([start, end])로 교체 — 기본 일운은 기준월 1개월치만 채워 월 경계를
    # 넘는 택일이 불가능하다(2026-06-16 결함 수정). 월운·세운 부모는 anchor 연도 기준 유지.
    # calculate()는 캐시 공유 객체를 반환하므로 in-place 변경 금지 — luck_cycles만 복제 후 교체.
    if chart.luck_cycles is not None:
        window_daily = daily_luck_window(chart, req_start, scan_end)
        chart = chart.model_copy(
            update={"luck_cycles": chart.luck_cycles.model_copy(
                update={"daily_luck": window_daily})}
        )
    composites = CompositeBuilder(_DICTS).build(
        chart, "chat", "1.0.0", f"{today.isoformat()}T00:00:00+00:00",
    )
    # 횡재(로또)·재물 택일은 재성 방위·시진을 함께 제공(번호 거부·당첨 단정 금지 유지).
    # 방위는 용희기구한 역할을 반영해 기신·구신·생구신 방향은 추천하지 않는다(2026-06-16).
    # 이사·이동도 favorability를 전달해 8방위 적합도 + 지정 방위(예: 남동) 길흉을 안내한다.
    is_windfall = purpose in (EventKey.WINDFALL, EventKey.WEALTH_CHANGE)
    wealth_element = analyze_wealth_capacity(chart).wealth_element if is_windfall else None
    is_relocation = purpose == EventKey.RELOCATION
    if is_windfall or is_relocation:
        from saju_engines.event_scoring import favorability_map
        favorability = favorability_map(chart)
    else:
        favorability = None
    # 현실 제약(주말만/평일만/평일 선호)과 지정 방위를 엔진에 전달, 표본은 8개로 확대해
    # 평일 후보까지 충분히 노출한다('주말만 추천처럼 보임' 완화 — 2026-06-16).
    constraints = intent.constraints
    result = _get_date_engine().select(
        purpose, composites, start_iso, end_iso, yongsin_element=yongsin,
        reality_constraints=constraints.reality_constraints or None,
        include_hour_fit=is_windfall, top_n=8,
        wealth_element=wealth_element, favorability=favorability,
        stated_direction=constraints.direction,
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
    # 시진은 원소 기반(날짜 무관 동일)이라 상위 후보 1건의 hour_fits를 블록 레벨로 노출.
    hour_fits = (
        [h.model_dump() for h in result.candidates[0].hour_fits]
        if result.candidates and result.candidates[0].hour_fits else []
    )
    # 한 달 윈도우 안내 — 요청이 더 넓으면(개방형/다월) 탐색 범위와 재질문 방법을 알린다.
    cautions = list(result.cautions)
    if truncated:
        cautions.append(
            f"택일은 한 번에 약 한 달 범위만 탐색합니다 — 이번에는 {start_iso} ~ {end_iso}를"
            f" 살폈어요. 그 이후 시기는 원하시는 달(예: '{_next_month_label(scan_end)} 이사일')을"
            " 지정해 다시 물어봐 주세요."
        )
    return DateSelectionBlock(
        purpose_ko=event_ko(purpose),
        period=f"{start_iso} ~ {end_iso}",
        rows=rows,
        avoid=result.avoid_dates,
        cautions=cautions,
        directions=[d.model_dump() for d in result.directions],
        hour_fits=hour_fits,
    )


# 대화형 전용 범위 지시 — 질문에 곧장·집중해 답하고 원국 통독을 막는다(리포트는 전체 서술 유지).
_CHAT_SCOPE_DIRECTIVE = (
    "[답변 범위 — 대화형]\n"
    "사용자의 이번 질문에 곧장 답한다. 질문이 특정 시점(그날·그달)이나 특정 주제이면 그 범위에"
    " 집중하고, 원국·성향·신살은 그 답에 꼭 필요한 근거만 골라 한두 줄로 인용한다 — 원국 전체를"
    " 처음부터 다시 설명하지 말 것. 앞 턴에서 이미 말한 내용은 반복하지 않는다. 인사말은 생략한다."
)

# 상황 제약 — 질문 맥락으로 형제 사건을 결정적으로 좁힌다. 묻힌 일반 안내로는 thinking LOW
# LLM이 다단계 추론(무직→이직 불가→이사)을 못 하므로, 감지 시 우선순위 높은 명시 지시를
# 프롬프트 말미에 주입한다(2026-06-14: '2025-08 백수인데 이직으로 단정' 오류 차단).
_UNEMPLOYED_KEYS = (
    "백수", "무직", "실직", "공백기", "재취업", "구직", "쉬고 있", "쉬는 중", "놀고 있",
)
# 사건형 intent — 내부 분석을 월단위로 하는 게 맞는 이벤트(단계 진행형 progress + 이동형
# hybrid). 연 질문이어도 12개월 후보를 봐야 강한 달을 짚는다(P1, 2026-06-14). str 키로 비교.
_EVENT_MONTHLY = {str(k) for k, t in EVENT_TYPE.items() if t in ("progress", "hybrid")}

# 응답 형식 — '월별' 명시 없이 사건형 연 질문이면 12개월 나열 대신 연간 요약+핵심 달로.
_KEY_MONTHS_DIRECTIVE = (
    "[응답 형식] 이 질문은 월별 표 전체 나열이 아니라 연간 요약 + 핵심 달만 추려 답하라 — "
    "해당 기간을 한 줄로 총평하고, 강하게 작동하는 달과 주의가 필요한 달만 골라 짚는다"
    "(12개월을 모두 나열하지 말 것). 사용자가 '월별'을 명시하면 그때만 전체 표를 서술한다."
)

_UNEMPLOYED_DIRECTIVE = (
    "[중요·상황 제약 — 다른 어떤 표기보다 우선 적용]\n"
    "질문 맥락상 사용자는 현재 직장이 없다(백수·공백기). 따라서 '이직·직업 변화'는 성립할 수 "
    "없다 — 표·종합에서 '이직'이 우세로 표기된 달이라도 그 이동·변동 에너지는 반드시 '이사'로 "
    "해석하고, 그 달을 '재취업'의 답으로 삼지 말 것. 재취업(취업·합격)은 '취업·합격'이 실제로 "
    "우세한 달에서만 지목하라."
)

# 비정직원(계약직·프리랜서·무급가족종사) 고용형태 — '직장운'에 '취업'도 대상이 된다.
_NONREGULAR_FORMS = frozenset({"계약직", "프리랜서", "무급가족종사"})
# 재직을 전제하는 사건 — 이직·승진. 무직·비정규면 '취업'으로 확장 해석한다.
_PRESUPPOSE_EMPLOYED = frozenset({"career_change", "promotion"})
# 직장운 맥락(재직 전제 사건)에서 대상이 비정직원일 때 — 취업을 핵심 대상에 포함.
_CAREER_NONREGULAR_DIRECTIVE = (
    "[중요·상황 제약 — 우선 적용]\n"
    "대상은 현재 정직원이 아니다(무직·계약직·프리랜서 등). 따라서 '직장운'은 이직·승진뿐 아니라 "
    "'취업·합격'(새 직장 진입)이 핵심 대상이다. 이직·승진이 우세한 달이라도 재직을 전제하지 말고, "
    "'취업·합격'이 실제로 우세한 달을 함께 '취업 가능 시기'로 짚어라. 당락 등 단정은 금지."
)


def _compat_prompt_block(
    result: ManseV2Result, partner_birth: BirthInput, today: date, partner_label: str,
) -> str | None:
    """본인↔상대 궁합 신호 블록(채팅 pairwise). 엔진 계산값만 + LLM 서술 가드."""
    partner_result = calculate(partner_birth.model_copy(update={"reference_date": today}))
    self_sum = build_birth_summary(result)
    partner_sum = build_birth_summary(partner_result)
    report = analyze_compatibility(
        result, partner_result, self_sum.useful_gods, partner_sum.useful_gods,
        self_label="본인", partner_label=partner_label,
    )
    if report is None:
        return None
    lines = ["", "[궁합 분석 — 아래 엔진 계산값만 근거로 두 사람 궁합을 설명할 것]"]
    lines += compatibility_lines(report)
    lines.append(
        "신호의 방향(보완/마찰)을 그대로 반영하되 '반드시 헤어진다/잘 된다' 류 단정·상대 탓·"
        "운명론은 금지. 마찰은 관리 가능한 영역으로, 극복할 마음가짐·행동도 덧붙일 것."
    )
    return "\n".join(lines)


def _structural_context(result: ManseV2Result, intent: IntentJson, today: date) -> list[str]:
    """질문 도메인에 맞는 구조 해석 블록(누출 안전 한글). intent 미확정(general)=총운으로 간주해
    모든 블록을, 확정 도메인은 해당 블록만 표면화한다(2026-06-16 사용자 확정).

    리포트와 동일한 structural_context 포맷터를 재사용해 표면화 일관성·누출 방지를 유지한다.
    """
    if result.pillars is None or result.force_analysis is None:
        return []
    from saju_engines.event_scoring import favorability_map
    from saju_engines.health_vulnerability import analyze_health_vulnerability
    from saju_engines.marriage_resource import analyze_marriage_resource
    from saju_engines.structural_context import (
        era_energy_lines,
        health_lines,
        marriage_resource_lines,
        wealth_capacity_lines,
        wealth_status_lines,
    )
    from saju_engines.wealth_capacity import analyze_wealth_capacity
    from saju_engines.wealth_status_lean import analyze_wealth_status_lean

    domain = intent.domain
    general = domain is Domain.GENERAL  # 확정 intent 아님 → 총운(모든 구조 블록)
    out: list[str] = []
    if general:
        out += era_energy_lines(result, today.year)  # 시대 기운 먼저(개인 앞 사회 맥락)
    if general or domain is Domain.WEALTH:
        out += wealth_capacity_lines(analyze_wealth_capacity(result))
    if general or domain in (Domain.WEALTH, Domain.CAREER):
        out += wealth_status_lines(analyze_wealth_status_lean(result))
    if general or domain is Domain.RELATIONSHIP:
        out += marriage_resource_lines(analyze_marriage_resource(result))
    if general or domain is Domain.HEALTH:
        hv = analyze_health_vulnerability(result, favorability_map(result))
        out += health_lines(result, hv, today.year)
    return out


def chat(
    birth: BirthInput,
    question: str,
    today: date | None = None,
    dry_run: bool = False,
    thread_id: str | None = None,
    store: ConversationStore | None = None,
    persona: PersonaConfig | None = None,
    owner_id: str | None = None,
    subject_id: str | None = None,
    subject_label: str = "회원",
    partner_birth: BirthInput | None = None,
    partner_label: str = "상대",
    partner_ref: dict | None = None,
    employment_form: str | None = None,
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
    # 절기 기준 당월 라벨 — '이번 달' 등 상대 시점 파싱에 주입(차트 미산출 시점이라 KST 기준;
    # 차트 타임존이 KST와 다른 드문 경우의 절기 경계 오차는 후속 창 재산출에서 보정된다).
    luck_month = _current_luck_month(today)

    # 멀티턴: 스레드 상태 복원 → 대화 엔진 경유(대상 해소·슬롯 상속·반복 감지).
    state: ConversationState | None = None
    repeated = False
    is_followup_turn = False
    prior_intent = None  # 직전 턴 intent — 활성 스레드 맥락 기반 broad 제안용.
    if thread_id is not None:
        store = store or ConversationStore()
        store.migrate()
        state = store.load(thread_id) or ConversationState(thread_id=thread_id)
        prior_intent = state.last_intent  # process_turn이 갱신하기 전 직전 intent 보존.
        engine = ConversationEngine()
        parsed, state, resolution, _link = engine.process_turn(
            state, question, today, birth_year=birth_year,
            current_month_label=luck_month,
        )
        is_followup_turn = _link.is_follow_up
        # 궁합 상대 첨부를 스레드 상태에 미러링(크로스 디바이스 재개 복원용). 매 턴 현재
        # 첨부(없으면 None)로 갱신 — 프론트 첨부/해제가 곧 서버 상태가 된다.
        state.partner = partner_ref
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
        parsed = parse_message(
            question, today, birth_year=birth_year, current_month_label=luck_month,
        )
    intent = parsed.intents[0]

    # 직장운 등 재직 전제 사건(이직·승진) + 대상이 비정직원(프로필 고용형태/질문 키워드)이면
    # '취업'도 핵심 대상에 포함한다 — event_keys에 추가하면 graph_scope(context_reducer)에 반영돼
    # 취업 후보가 함께 산출된다. plan보다 먼저 보강해 planner scope에도 반영되게 한다.
    nonregular = employment_form in _NONREGULAR_FORMS or any(
        k in question for k in _UNEMPLOYED_KEYS
    )
    career_presupposed = str(intent.event_key) in _PRESUPPOSE_EMPLOYED or any(
        str(k) in _PRESUPPOSE_EMPLOYED for k in intent.event_keys
    )
    if nonregular and career_presupposed and EventKey.JOB_GAIN not in intent.event_keys:
        intent = intent.model_copy(
            update={"event_keys": [*intent.event_keys, EventKey.JOB_GAIN]}
        )

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

    # 광범위/대상 판정(T3.2) — 추측 실행 금지. 단, 후속 정제 턴('평일도 없어?')은 직전
    # 의도를 상속했으므로 broad 안내로 빠뜨리지 않는다(스레드 단절 방지 — 2026-06-16).
    assessment = assess(intent, question, last_intent=prior_intent)
    if assessment.status in ("too_broad", "need_subject") and not (
        is_followup_turn and assessment.status == "too_broad"
    ):
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
    # 차트 타임존으로 당월 라벨 재확정 — 월운 라벨이 그 타임존으로 생성되므로 정합을 맞춘다.
    luck_month = _current_luck_month(
        today,
        result.time_correction.timezone if result.time_correction else "Asia/Seoul",
    )
    # 개인화(저장된 subject 한정): 현실 신호 시그니처 + 활성 코호트 → LEI 정렬축. 미설정·실패 시
    # life_fit·personal_match=0이라 기존 정렬과 동치(무개인화 폴백, 규칙11).
    _sig, _cohort = fetch_personal_inputs(owner_id, subject_id, result)
    all_scored = _get_scorer().score_legacy_personalized(
        result, levels=_SCORE_LEVELS, signature=_sig, cohort=_cohort,
    )

    # E9 Lifestyle — 특정 기간(일/월/연) 총운은 인생 사건이 아니라 생활 슬롯으로
    # 한정한다(2026-06-12 지적). 위계(대운>세운>월>일)에서 상위가 형성한 기운이 하위
    # 기간에서 사건화되며, 점수는 위계 가중 합산. 총운 경로면 거시 이벤트 후보·그래프·
    # 월별 요약을 메인에서 배제해 이직·이사 단정이 새지 않게 한다. 주간은 제외(날 종합).
    period_type = _period_fortune_type(intent, question)
    period_fortune = (
        _build_period_fortune(birth, intent, today, period_type)
        if period_type else None
    )

    # P5·P6(2026-06-12): 미래지향 질문의 유효 창은 '오늘이 속한 달'에서 시작한다.
    # ① 시점 미지정('이직 제안 들어올까?') → 현재 달 ~ +2년. ② '올해'처럼 연 단위 창이
    # 미래를 포함하면 시작을 현재 달로 클램프 — 이미 지난 1~5월 후보(4월 트리거 등)가
    # 메인에 올라 미래처럼 서술되는 시점 오류를 엔진 차원에서 차단(지난 달은 배경 분리).
    # 과거 회고(event_explanation·과거 키워드)와 명시적 과거 창은 클램프하지 않는다.
    current_month = luck_month  # 절기 기준 당월(양력 today.month의 절기 경계 어긋남 보정)
    is_retro = (
        intent.query_type is QueryType.EVENT_EXPLANATION
        or any(k in question for k in _PAST_KEYWORDS)
        # open_when = '언제였는지' 과거 개방 탐색(C15) — 후속 단답('년단위였어')처럼
        # 질문 텍스트에 과거 어미가 없어도 상속된 intent로 과거 회고를 식별(2026-06-12).
        or (
            intent.time_range is not None
            and intent.time_range.type == "open_when"
        )
    )
    default_period: tuple[str, str] | None = None
    if period_fortune is None and is_retro:
        # 과거 회고인데 시점 미정(open_when 포함 — '오래 쉬었던 기간 언제였을까') →
        # 과거 10년 창으로 후보 앵커링. 미래 창으로 흘러 '이전 데이터 미제공' 회피가
        # 나오는 것을 차단(2026-06-12 지적). 명시 과거 창은 그대로 둔다.
        tr = intent.time_range
        if tr is None or not tr.start:
            default_period = (str(today.year - 10), current_month)
    elif period_fortune is None:
        tr = intent.time_range
        if tr is None or not tr.start:
            default_period = (current_month, str(today.year + 2))
        else:
            end = tr.end or tr.start
            # 창의 끝/시작을 월 단위로 정규화해 '미래 포함 + 과거 시작' 여부 판정.
            end_month = end[:7] if len(end) >= 7 else f"{end}-12"
            start_month = tr.start[:7] if len(tr.start) >= 7 else f"{tr.start}-01"
            if end_month >= current_month and start_month < current_month:
                default_period = (current_month, end)

    # 구조 질문(CHART_ANALYSIS — 성격·격국·부귀·'귀한 사주?' 등 원국 자체 질문)은 시점/이벤트
    # 데이터가 불필요하다. 월별 이벤트 후보·근거 경로·과거 흐름을 빼고 원국 구조·명식 해석·구조
    # 블록만 남겨 답변이 엉뚱한 월별 사건으로 새지 않게 한다(2026-06-16 사용자 지적).
    is_structural = intent.query_type is QueryType.CHART_ANALYSIS
    if is_structural:
        default_period = None  # 시점 창 불요 — '질문 기간 내 후보 없음' 빈 안내까지 차단
    if period_fortune is not None or is_structural:
        candidates = []
        bundles = []
    else:
        candidates = filter_year_candidates(all_scored)
        # P2 보강: 계층 필터(Top5)가 과거 고점에 점유돼도 유효 창(클램프 반영) 후보는 보존.
        win_start: str | None
        win_end: str | None
        if default_period is not None:
            win_start, win_end = default_period
        elif intent.time_range is not None:
            win_start, win_end = intent.time_range.start, intent.time_range.end
        else:
            win_start = win_end = None
        if win_start or win_end:
            from saju_engines.context_reducer import in_question_range

            seen = {(c.event_key, c.period) for c in candidates}
            candidates += [
                c for c in all_scored
                if (c.event_key, c.period) not in seen
                and in_question_range(c.period, win_start, win_end)
            ]
        # 의도 필터(intent_event_filter) — 질문 도메인과 무관한 후보를 억제한다.
        # 빈 결과를 만들지 않으며(fallback 원본 유지), general 도메인은 전부 통과.
        candidates = _get_intent_filter().filter(candidates, str(intent.domain))
        # Graph Retrieval — plan의 graphScope만(전체 검색 금지).
        scope: list[EventKey] = plan.graph_scope or [c.event_key for c in candidates[:5]]
        bundles = _get_graph().retrieve(scope)

    # P4: 월 단위·시기 특정 요청이면 12개월 요약 동반 — '몇 월/언제' 질문엔 월운이 답이라
    # 세운만으로 답을 회피('달 특정 불가')하지 않도록 월별 표를 보장한다(2026-06-12 지적).
    overview = None
    gran_month = (
        intent.time_range is not None
        and intent.time_range.granularity.value == "month"
    )
    # P1(2026-06-14): 사건형 intent(이사·이직 등)는 '월별'을 명시 안 해도 내부는 월단위로 계산
    # (연 질문도 12개월 후보를 봐야 강한 달을 짚는다). monthly_explicit이면 표 전체, 아니면
    # 연간 요약+핵심 달로 응답하도록 아래에서 형식 지시를 준다.
    event_monthly = intent.event_key is not None and str(intent.event_key) in _EVENT_MONTHLY
    monthly_explicit = any(k in question for k in ("월별", "달별", "매월", "월운", "월단위"))
    wants_monthly = period_fortune is None and (
        monthly_explicit
        or event_monthly
        or intent.query_type is QueryType.TIMING_SEARCH
        or gran_month
        or any(k in question for k in ("몇 월", "몇월", "언제", "어느 달"))
        or any(k in question for k in ("앞으로", "향후", "다가오는", "1년 내", "1년내"))
    )
    result_for_llm = result  # on-demand 월운 주입 시 교체(간지·해석 lookup 커버용)
    if wants_monthly and result.luck_cycles is not None:
        start_label = intent.time_range.start if intent.time_range else None
        window_months: list[str] | None = None
        target_year: int | None = None
        end_label = intent.time_range.end if intent.time_range else None
        if is_retro and not start_label:
            # 과거 회고 + 시점 미정('오래 쉬었던 기간 언제') — 과거 10년 연도별 흐름 표.
            # 공백·정체는 신호 '부재'라 상위 후보로 안 나오므로, 연도별 점수 흐름으로
            # 저점(신호 없던 해)이 드러나게 한다(2026-06-12 지적).
            have = {pl.label for pl in result.luck_cycles.yearly_luck}
            years = [
                str(y) for y in range(today.year - 10, today.year + 1)
                if str(y) in have  # 세운 데이터 있는 연도만(거짓 '정보 없음' 행 방지)
            ]
            overview = build_monthly_overview(result, all_scored, months=years)
        elif start_label and len(start_label) == 10:
            # 상대 기준 앵커(YYYY-MM-DD = '앞으로/향후 1년' 등) — 그 달부터 12개월 롤링.
            window_months = _rolling_months(int(start_label[:4]), int(start_label[5:7]))
        elif (
            start_label and end_label
            and len(start_label) == 7 and len(end_label) == 7
            and start_label != end_label
        ):
            # 다중 월 창('지난 1년'=직전 12개월 등, 2026-06-12) — 질문 창 그대로 월별 표.
            window_months = _months_between(start_label, end_label)
        elif start_label and len(start_label) >= 4:
            # 명시 연·월('2025년 8월', '2025') — 해당 달력 연도.
            target_year = int(start_label[:4])
        elif any(k in question for k in ("앞으로", "향후", "다가오는", "1년 내", "1년내")):
            # 시점 미지정 상대-미래 — 오늘(기준 시점)의 달부터 12개월 롤링(2026-06-12 지적:
            # 달력상 1~12월이 아니라 오늘 기준 롤링 창이어야 한다). 절기 기준 당월에서 시작.
            window_months = _rolling_months(int(luck_month[:4]), int(luck_month[5:7]))
        elif any(k in question for k in ("최근", "지난", "작년", "올해까지")):
            target_year = today.year - 1
        else:
            target_year = today.year

        if overview is not None:
            pass  # 과거 회고 연도별 흐름 표 이미 생성(위 is_retro 분기)
        elif window_months is not None:
            # 롤링 창은 달력 연도 경계를 넘으므로(예: 2026-06~2027-05) 닿는 연도별
            # 월운을 on-demand로 합쳐 스코어한다. 월운은 기본 미래 12개월만 계산됨.
            years_needed = sorted({int(mm[:4]) for mm in window_months})
            monthly_all = []
            for yr in years_needed:
                monthly_all += luck_months(chart_birth, yr)
            result_win = result.model_copy(deep=True)
            assert result_win.luck_cycles is not None
            result_win.luck_cycles.monthly_luck = monthly_all
            scored_win = _get_scorer().score_legacy(result_win, levels={GanjiLevel.MONTH})
            overview = build_monthly_overview(result_win, scored_win, months=window_months)
            # 창 내 월 후보(기본 월운 범위 밖 과거 달 포함)를 메인 후보에도 보존 —
            # '재취업한 달은 언제' 류에서 표와 근거 경로가 같은 달을 가리키게(2026-06-12).
            win_set = set(window_months)
            seen_c = {(c.event_key, c.period) for c in candidates}
            candidates += [
                c for c in scored_win
                if c.period in win_set and (c.event_key, c.period) not in seen_c
            ]
            # 간지 lookup·incoming_note(천간 용기신 역할)가 창 월을 커버하게 —
            # 누락 시 '癸(水 구신)' 같은 불리 정보가 월 후보에서 사라진다(2026-06-12).
            result_for_llm = result_win
        else:
            # 과거/범위 밖 연도면 그 해 월운을 on-demand로 계산·스코어해서
            # 빈 표('정보 없음' 회피)를 막는다(2026-06-12 지적).
            assert target_year is not None
            years_in_result = {p.label[:4] for p in result.luck_cycles.monthly_luck}
            if str(target_year) in years_in_result:
                overview = build_monthly_overview(result, all_scored, year=target_year)
            else:
                year_months = luck_months(chart_birth, target_year)
                result_year = result.model_copy(deep=True)
                assert result_year.luck_cycles is not None
                result_year.luck_cycles.monthly_luck = year_months
                scored_year = _get_scorer().score_legacy(result_year, levels={GanjiLevel.MONTH})
                overview = build_monthly_overview(result_year, scored_year, year=target_year)
                result_for_llm = result_year
        # 신호가 하나도 없는 빈 표는 넣지 않는다(빈 표가 회피를 유발).
        if overview is not None and not any(r.score is not None for r in overview):
            overview = None

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
    # 후속 턴(2턴째 이상)이면 인사·재인용 절제 지시(항목 19).
    is_followup = state is not None and state.turn_no >= 2
    # 턴 간 모순 방지(2026-06-12) — 이전 턴에서 제시한 엔진 결과를 한글화해 동반.
    prior_claims: list[str] = []
    if is_followup and state is not None:
        for ref in state.last_results[:5]:
            label = ref.label
            if ref.kind == "event" and "@" in label:
                key, _, period = label.partition("@")
                try:
                    label = f"{event_ko(EventKey(key))} @ {period}"
                except ValueError:
                    pass
            prior_claims.append(f"{label}" + (f" — {ref.detail}" if ref.detail else ""))
    payload = build_llm_input(
        question, intent, result_for_llm, candidates, bundles, _get_scorer(),
        call_type="chat_compare" if plan.per_subject else "chat_single",
        today=today,
        monthly_overview=overview,
        period_fortune=period_fortune,
        date_selection=date_block,
        is_followup_turn=is_followup,
        default_period=default_period,
        prior_claims=prior_claims,
        current_month_label=luck_month,
        # 구조 해석 블록 — 단일 대상일 때만(궁합 비교는 대상 혼동 방지로 생략).
        structural_context=(
            _structural_context(result, intent, today) if not plan.per_subject else None
        ),
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

    # 대화형 답변은 질문 범위에 집중 — 원국 통독·정황 재설명을 막는다(리포트와 분리).
    prompt_text = prompt_text + "\n" + _CHAT_SCOPE_DIRECTIVE
    # 상황 제약 — 비정직원이면서 직장운(재직 전제 사건) 맥락이면 '취업'을 함께 짚게 하고,
    # 그 외(이사 등 비career 맥락)에서 무직 키워드가 잡히면 기존 '이직→이사' 분기를 적용한다.
    if nonregular and (career_presupposed or intent.domain is Domain.CAREER):
        prompt_text = prompt_text + "\n" + _CAREER_NONREGULAR_DIRECTIVE
    elif any(k in question for k in _UNEMPLOYED_KEYS):
        prompt_text = prompt_text + "\n" + _UNEMPLOYED_DIRECTIVE
    # P1 응답 형식 — 사건형인데 '월별' 미명시면 12개월 나열 대신 연간 요약+핵심 달로.
    if overview is not None and event_monthly and not monthly_explicit:
        prompt_text = prompt_text + "\n" + _KEY_MONTHS_DIRECTIVE

    # 궁합(pairwise) — 상대가 첨부되면 엔진 계산 궁합 신호 블록을 입력에 덧붙인다.
    if partner_birth is not None:
        compat = _compat_prompt_block(result, partner_birth, today, partner_label)
        if compat:
            prompt_text = prompt_text + "\n" + compat

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

    call_type = "chat_compare" if plan.per_subject else "chat_single"
    system = None
    if persona is not None:
        # 호칭 자리({resolvedHonorific})에 대화 기준 사주의 별명을 넣는다(하드코딩 '회원' 제거).
        block = _get_persona_engine().build_block(persona, subject_label or "회원")
        system = llm_client._SYSTEM_PROMPT + "\n\n" + block

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
            system_prompt=system,
            call_type=call_type,
        )

    answer = llm_client.generate_reading(
        prompt_text,
        call_type=call_type,
        system=system,
        owner_id=owner_id, surface="chat", ref_id=thread_id,
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
