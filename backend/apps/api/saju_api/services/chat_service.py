"""대화형 통변 오케스트레이션 서비스 (v2.2 MVP — 단일 질문 → 정확한 풀이).

파이프라인(docs/01·03): 파서(T3.1 룰 기반) → 대상/광범위 판정(T3.2) → 실행 계획(T3.3)
→ 만세 계산(캐시) → 이벤트 스코어링(P2) + 계층 필터 → Graph Retrieval(T2.2)
→ Context Reduction + LLM 입력 직렬화(T3.4/5, 가드 경유) → LLM 서술(또는 dry-run).

비분석 라우트(Q11~Q14)·too_broad·대상 확인은 LLM/엔진 호출 없이 정책 응답을 돌려준다.
대화 연속성(직전 intent 상속 등)은 Phase 4 Conversation Layer에서 확장한다.
"""

from __future__ import annotations

import re
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
from saju_engines.conversation import ConversationEngine, is_affirm_continue
from saju_engines.conversation_store import ConversationStore
from saju_engines.date_selection import DateSelectionEngine
from saju_engines.intent_event_filter import IntentEventFilter
from saju_engines.llm_guard import TokenBudgetExceeded, estimate_tokens
from saju_engines.persona import PersonaEngine
from saju_engines.planner import build_execution_plan
from saju_engines.precompute import CompositeBuilder
from saju_engines.query_parser import parse_message
from saju_engines.rewriter import QueryAssessment, assess
from saju_engines.shadow_scoring import domain_to_expression_key
from saju_engines.structural_context import (
    DAEWOON_FRAMING_DIRECTIVE,
    DAEWOON_TRANSITION_SIGNALS_DIRECTIVE,
    PARTNER_SOURCE_DIRECTIVE,
    RELATIONSHIP_SELF_AWARENESS_DIRECTIVE,
    TENDENCY_SHIFT_DIRECTIVE,
    spouse_star_directive,
)
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
from .manse_service import (
    calculate,
    daily_luck_window,
    luck_days,
    luck_months,
    luck_years,
)
from .personalization import fetch_confirmed_yongsin_override, fetch_personal_inputs

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


def _date_solar_month_note(birth: BirthInput, target: date, timezone: str) -> str:
    """특정 날짜의 절기 월간지 + 양력 범위를 '엔진 확정 사실'로 명시하는 디렉티브.

    LLM이 monthly_luck 라벨('2026-07=乙未')을 보고 '7월 4일→7월→乙未'로 양력 달에 끌려 월간지를
    오답하는 것을 차단한다(2026-06-22 데굴님 지적 — 7/4는 소서 전이라 甲午월). 월운은 절입 기준이라
    양력 달과 어긋나므로 그 날이 실제로 속한 절기월 간지를 못박는다.

    Args:
        birth: 대상 출생 정보(절기월 라벨→간지 조회용).
        target: 질문 날짜.
        timezone: 차트 타임존(절기 경계 산정 기준).

    Returns:
        디렉티브 문자열(간지 조회 실패 시 빈 문자열).
    """
    label = _current_luck_month(target, timezone)
    ml = luck_months(birth, int(label[:4]))
    mp = next((p for p in ml if p.label == label), None)
    if mp is None:
        return ""
    sm_s, sm_e = _solar_month_range(label, timezone)
    return (
        f"[날짜 절기월 — 엔진 확정 사실] 질문 날짜 {target.isoformat()}의 월운(절기월)은 "
        f"{mp.ganji}이며 양력 {sm_s.isoformat()}~{sm_e.isoformat()}에 해당한다. 월운은 절입 "
        f"기준이라 양력 달과 다르다 — 이 날짜의 월간지를 양력 {target.month}월의 다음 절기월로 "
        f"답하지 말고 반드시 {mp.ganji}로 본다."
    )


# 'YYYY년 N월 N일' / 'N월 N일' 추출(연도 생략 시 기준 연도). 특정 날짜 운세 질문의 일운 grounding용.
_DATE_RE = re.compile(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def _explicit_dates(question: str, default_year: int) -> list[date]:
    """질문 본문의 명시 날짜('8월 31일' 등)를 추출(연도 생략 시 default_year). 중복·무효 제거."""
    out: list[date] = []
    seen: set[date] = set()
    for m in _DATE_RE.finditer(question):
        year = int(m.group(1)) if m.group(1) else default_year
        try:
            dt = date(year, int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if dt not in seen:
            seen.add(dt)
            out.append(dt)
    return out


def _date_day_fortune_note(birth: BirthInput, dates: list[date], timezone: str) -> str:
    """특정 날짜 질문 — 그 날(들)의 일운(日運) 간지·십성·길흉 + 절기월을 '엔진 확정 사실'로 주입.

    날짜를 물으면 월운(절기월)으로 뭉뚱그리지 말고 그 날의 일운을 중심으로 답하게 한다(2026-06-23
    데굴님 지적: '8/31·9/30 운' 질문에 丙申월·丁酉월만 답함). 월운은 절입 기준이라 양력 달과
    다르므로 함께 못박는다. 최대 4개 날짜.
    """
    segs: list[str] = []
    for tgt in dates[:4]:
        try:
            days = luck_days(birth, tgt.year, tgt.month)
        except (ValueError, RuntimeError):
            days = []
        dp = next((p for p in days if p.label == tgt.isoformat()), None)
        label = _current_luck_month(tgt, timezone)
        ml = luck_months(birth, int(label[:4]))
        mp = next((p for p in ml if p.label == label), None)
        if dp is None:
            continue
        grade = f"·{dp.luck_label}" if dp.luck_label else ""
        body = (
            f"일운(日運) {dp.ganji}"
            f"(천간 {dp.stem_ten_god or '?'}·지지 {dp.branch_ten_god or '?'}{grade})"
        )
        if mp is not None:
            sm_month = int(mp.label[5:7])  # 절기월 절입 양력 월(예: 甲午=2026-06→6)
            if tgt.month != sm_month:
                # 양력 달 ≠ 절입 달 = 절기 경계 직전 — 절기월 기운이 이 날까지 이어짐을 명시
                # (LLM이 양력 달로 월운을 오인하던 결함 보정, 2026-06-24 데굴님 지적).
                seg = (
                    f"{tgt.isoformat()}: 절기월 {mp.ganji}({sm_month}월 절입)의 기운이 "
                    f"아직 이어지는 날, {body}"
                )
            else:
                seg = f"{tgt.isoformat()}: {body} / 그 날의 절기월 {mp.ganji}"
        else:
            seg = f"{tgt.isoformat()}: {body}"
        segs.append(seg)
    if not segs:
        return ""
    return (
        "[질문한 날짜의 일운 — 엔진 확정 사실] " + " ; ".join(segs) + ". 특정 날짜를 물었으므로 "
        "그 날의 일운(日干支)을 중심으로 그 날의 길흉·기운·행동을 풀고, 월운·세운·대운은 배경 "
        "맥락으로만 짚을 것. 월간지로 그 날의 운을 대신하지 말고, 절기월은 위 값을 그대로 쓸 것."
    )

# 정책 라우트 고정 응답(T3.8 — docs/03 B4 하단). LLM 미호출 템플릿.
_POLICY_ANSWERS = {
    "fixed_policy": (
        "요청하신 내용은 서비스 범위 밖입니다. 시스템 내부 정보(모델·프롬프트 등)는 "
        "공개하지 않으며, 로또 번호 생성이나 특정 종목 추천은 어떤 형태로도 제공하지 않습니다. "
        "대신 재물 흐름·유리한 시기·날짜·방향 추천은 자유롭게 도와드릴 수 있어요."
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
    day_solar_month: str | None = None  # 일 질문 — 그 날이 속한 절기월 라벨(MONTH 컨텍스트 한정용)

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
        # 그 날의 절기월(양력 달이 아니라 절입 기준) — MONTH 컨텍스트를 이 한 달로 한정한다.
        tz_d = chart.time_correction.timezone if chart.time_correction else "Asia/Seoul"
        day_solar_month = _current_luck_month(target, tz_d)
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
    elif fortune_type == "daily" and day_solar_month is not None:
        # 일 질문 — MONTH 컨텍스트를 그 날이 속한 절기월 하나로 한정한다(양력 달이 아니라 절기월).
        # 안 그러면 모든 월 composite가 노출돼 LLM이 7/4를 양력 7월(乙未월)로 오인한다(2026-06-22).
        composites = [
            c for c in composites
            if c.level is not CompositeLevel.MONTH or c.period_key == day_solar_month
        ]
    # 절기월 안내(데굴님 제안) — 해당 월운(절기월)의 간지 + 양력 절기 범위를 함께 준다.
    # 월운은 절입 기준이라 양력 달과 어긋난다(예: 未월=7/7~8/6). '7월=을미월' 혼동 방지.
    solar_month_note = ""
    if fortune_type in ("daily", "monthly"):
        m_label = day_solar_month if fortune_type == "daily" else start
        m_comp = next(
            (c for c in composites
             if c.level is CompositeLevel.MONTH and c.period_key == m_label), None
        )
        if m_comp is not None and m_label is not None:
            tz_m = chart.time_correction.timezone if chart.time_correction else "Asia/Seoul"
            sm_s, sm_e = _solar_month_range(m_label, tz_m)
            solar_month_note = (
                f"이 기간이 속한 절기월은 {m_comp.ganji.stem}{m_comp.ganji.branch}월"
                f"(양력 {sm_s.isoformat()}~{sm_e.isoformat()})이다 — 월운은 절기 경계라 양력 달과 "
                "다르니 '○월=○○월운'으로 혼동하지 말 것."
            )
    ctx = build_lifestyle_context(
        [SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period, composites, dictionaries_dir=_DICTS,
    )
    # 표현 제한 도메인(Phase 5b-2b) — parser Domain.value(str)만 전달(enum 비종속).
    domain_key = domain_to_expression_key(intent.domain.value)
    grounding = build_luck_grounding(chart, pillar, domain_key=domain_key)
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
        solar_month_note=solar_month_note,
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
        relocation_kind=getattr(intent, "relocation_kind", "home"),  # R4 집/사무실 분기
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
    # 이사 — 십성 이유분류(천간=명분/지지=현장) surface. 택일 점수와 별개의 해석 라벨로,
    # 질의 시작 시점의 세운(연)·월운(월)·대운으로 '왜·어떤 집' 유형을 함께 제공한다(R2).
    relocation_reasons = (
        _relocation_reason_lines(composites, start_iso[:4], start_iso[:7])
        if is_relocation else []
    )
    return DateSelectionBlock(
        purpose_ko=event_ko(purpose),
        period=f"{start_iso} ~ {end_iso}",
        rows=rows,
        avoid=result.avoid_dates,
        cautions=cautions,
        directions=[d.model_dump() for d in result.directions],
        hour_fits=hour_fits,
        relocation_reasons=relocation_reasons,
    )


def _is_relocation_intent(intent: IntentJson) -> bool:
    """이사 도메인/이벤트 질문인가 — 그룹(다인) M10 분기 게이트."""
    return intent.domain is Domain.RELOCATION or intent.event_key is EventKey.RELOCATION


def _relocation_reason_lines(
    composites: list, year_key: str, month_key: str | None,
) -> list[str]:
    """이사 십성 이유분류 라벨 줄 — 천간=명분(이유)/지지=현장(집·지역) (R2, 단정 금지).

    질의 기간의 세운(대표)·월운(발동)·대운(장기 배경) 천간 십성으로 '왜·어떤 집' 유형을
    분류한다(RelocationResolver.classify_reasons 위임). 점수·날짜 미개입(절대원칙 1·12).
    """
    from saju_engines.relocation import RelocationResolver

    profiles = RelocationResolver(_DICTS).classify_reasons(
        composites, year_key, month_key)
    return [
        f"{p.source} {p.ten_god} → {p.type}: 이유 {'·'.join(p.move_reason)} / "
        f"집·지역 {'·'.join(p.property_tendency)} / "
        f"리스크({p.risk_level}) {'·'.join(p.risk)}"
        for p in profiles
    ]


def _relocation_reason_context(
    birth: BirthInput, intent: IntentJson, today: date,
) -> list[str]:
    """'이사하면 어때?'(기간 평가) 질문용 십성 이사 이유분류 블록 — structural_context 주입.

    택일(DATE_RECOMMENDATION)이 아닌 이사 domain_analysis 질문은 date_block을 만들지 않으므로,
    질의 기간의 세운·월운·대운 천간 십성 유형 분류를 구조 해석 블록에 실어 '무슨 십성이라 이런
    이사'를 설명하게 한다. 질의 기간 간지의 십성이 필요해 그 기간 기준으로 차트를 재계산한다
    (세운/월운/대운은 시점에 따라 달라짐). 실패·신호 약함이면 빈 리스트(차단 금지, 규칙 11).
    """
    tr = intent.time_range
    start = tr.start if tr else None
    date_mode = False  # YYYY-MM-DD — 월 발동축을 절기월(양력 달 아님)로 잡는다(2026-06-22)
    if start and len(start) == 10:  # YYYY-MM-DD
        anchor = date.fromisoformat(start)
        year_key, month_key, date_mode = start[:4], None, True
    elif start and len(start) >= 7:  # YYYY-MM — 월 라벨은 절기월(monthly_luck 라벨과 동일)
        year_key, month_key = start[:4], start[:7]
        anchor = date(int(year_key), int(start[5:7]), 1)
    elif start and len(start) == 4:  # YYYY — 연 단위(월 발동축 생략)
        year_key, month_key, anchor = start, None, date(int(start), 1, 1)
    else:  # 기간 미지정 — 올해 세운+대운으로 분류
        year_key, month_key, anchor = str(today.year), None, today
    try:
        chart = calculate(birth.model_copy(update={"reference_date": anchor}))
        if date_mode:
            # 그 날이 속한 절기월 라벨(양력 달 아님 — 예: 7/4는 소서 전이라 甲午월=2026-06).
            tz_r = chart.time_correction.timezone if chart.time_correction else "Asia/Seoul"
            month_key = _current_luck_month(anchor, tz_r)
        composites = CompositeBuilder(_DICTS).build(
            chart, "chat", "1.0.0", f"{today.isoformat()}T00:00:00+00:00")
        lines = _relocation_reason_lines(composites, year_key, month_key)
    except Exception:  # noqa: BLE001 — 이사 분류 실패가 일반 풀이를 막지 않도록
        return []
    if not lines:
        return []
    header = (
        "[이사 이유·집 성격 — 십성 분류. 천간=명분(이유)/지지=현장(집·지역), "
        "대운=장기 배경·세운=올해 대표·월운=그 달 발동. '이 시기에 이사한다면 무슨 십성이라 "
        "어떤 결의 이사인지' 유형 분류일 뿐, 실제 이사 발생 여부는 별개이며 단정 표현 금지]"
    )
    return [header, *(f"- {line}" for line in lines)]


def _normalize_region(phrase: str, known: list[str]) -> str | None:
    """사용자 지명 구를 등재 키('{시도} {시군구}')로 정규화한다.

    완전일치 → 그 키. 아니면 시군구명 접미 일치(예: '수원시'→'경기도 수원시')가 유일할 때만 채택.
    '중구'처럼 여러 시도에 걸쳐 모호하면 None(추측 금지 — 대상 우선 원칙 7과 동일 취지).
    """
    if phrase in known:
        return phrase
    suffix = [k for k in known if k.endswith(" " + phrase)]
    return suffix[0] if len(suffix) == 1 else None


def _relocation_region_context(
    birth: BirthInput, intent: IntentJson, today: date,
) -> list[str]:
    """이사 목적지 지역 오행 × 용신 적합(region_fit)을 surface한다(지역 궁합 — 2026-06-18 보완).

    '서울 중구로 이사 — 나랑 맞을까'류에서 빠지던 지역 오행 궁합을 채운다. 점수·판정 미개입,
    참고용 라벨(절대원칙 1·5: 지역오행 사전은 검수 전 초안 — 단정 금지). 미등재·모호 지명이면 빈 줄.
    """
    phrase = intent.constraints.target_region
    if not phrase:
        return []
    try:
        from saju_engines.event_scoring import favorability_map
        from saju_engines.relocation import RelocationResolver

        resolver = RelocationResolver(_DICTS)
        region = _normalize_region(phrase, resolver.known_regions())
        if region is None:
            return []
        chart = calculate(birth.model_copy(update={"reference_date": today}))
        fav = favorability_map(chart)
        yongsin = next((el for el, role in fav.items() if role == "용신"), None)
        if yongsin is None:
            return []
        element = resolver.region_element(region)
        fit = resolver.region_fit([region], {"본인": yongsin})[region]
    except Exception:  # noqa: BLE001 — 지역 적합 실패가 일반 풀이를 막지 않도록
        return []
    label = {1.0: "매우 유리", 0.8: "유리(지역이 용신을 생)"}.get(fit, "중립")
    out = [
        "[지역 오행 적합(참고) — 목적지 지역 오행 × 내 용신. 시군구 단위 검수 전 초안이라 "
        "'유리/중립' 참고로만 녹이고 단정 금지(실제 거주 만족은 생활 여건이 좌우)]",
        f"{region}(오행 {element}) × 용신({yongsin}) → 적합도 {fit} ({label})",
    ]
    # 이동 방위(현재지→목적지) 길흉 — 현재지(location_base)·목적지 좌표가 둘 다 있을 때만(참고).
    # 지역 오행 적합과 별개 축이다(목적지가 용신이어도 가는 방향은 기신일 수 있음).
    base = intent.constraints.location_base
    if base:
        try:
            from saju_engines.region_direction import RegionDirection

            move_dir = RegionDirection(_DICTS).move_direction(base, region)
            if move_dir:
                dir_el, dlabel, reason = RegionDirection(_DICTS).direction_fit(move_dir, fav)
                out.append(
                    "[이동 방위 적합(참고) — 현재지→목적지 방위 × 내 용희기구한. 간방(남동 등)은 "
                    "인접 두 사정의 혼합 전환 방위로 본다(명리 방향 적합). 근사 좌표 8방위 "
                    "초안이라 참고로만 녹이고 단정 금지 — 혼합 방위는 섞인 오행의 길흉을 함께 설명]"
                )
                out.append(
                    f"{base} → {region} 이동 방위 {move_dir}(방위 오행 {dir_el}) → "
                    f"{dlabel} ({reason})"
                )
        except Exception:  # noqa: BLE001 — 방위 산출 실패가 일반 풀이를 막지 않도록
            pass
    return out


def _subject_composites_yongsin(
    b: BirthInput, req_start: date, scan_end: date, today: date, label: str
) -> tuple[list, str]:
    """한 대상의 [req_start, scan_end] 윈도우 LuckComposite + 용신 오행을 산출한다."""
    from saju_engines.event_scoring import favorability_map

    chart = calculate(b.model_copy(update={"reference_date": req_start}))
    if chart.luck_cycles is not None:
        window_daily = daily_luck_window(chart, req_start, scan_end)
        chart = chart.model_copy(update={"luck_cycles": chart.luck_cycles.model_copy(
            update={"daily_luck": window_daily})})
    comps = CompositeBuilder(_DICTS).build(
        chart, label, "1.0.0", f"{today.isoformat()}T00:00:00+00:00",
    )
    fav = favorability_map(chart)
    yongsin = next((el for el, role in fav.items() if role == "용신"), None)
    return comps, yongsin or "土"


def _relocation_group_block(
    birth: BirthInput, partner_birth: BirthInput, intent: IntentJson, today: date,
    self_label: str, partner_label: str,
) -> DateSelectionBlock | None:
    """다인(본인+첨부 상대) 이사 택일 — M10 RelocationResolver 그룹 집계.

    구성원별 이동운을 집계(호주 우선)해 공통으로 무난한 이사일을 랭킹하고, 구성원 충돌
    경고·방위 적합을 동반한다(docs/09 7장). 단일 대상 택일과 달리 '함께 움직이는' 날을 본다.
    """
    from saju_engines.relocation import RelocationResolver
    from saju_shared_types.relocation import RelocationPeriod, RelocationQuery

    tr = intent.time_range
    start_label = tr.start if tr else None
    if start_label and len(start_label) == 10:
        req_start = date.fromisoformat(start_label)
    elif start_label and len(start_label) == 7:
        req_start = date.fromisoformat(start_label + "-01")
    else:
        req_start = today
    if req_start < today:
        req_start = today
    scan_end = min(req_start + timedelta(days=30), date(req_start.year, 12, 31))

    self_comps, self_y = _subject_composites_yongsin(
        birth, req_start, scan_end, today, self_label)
    partner_comps, partner_y = _subject_composites_yongsin(
        partner_birth, req_start, scan_end, today, partner_label)

    constraints = intent.constraints
    query = RelocationQuery(
        group_subjects=[
            SubjectRef(kind=SubjectKind.SELF, label=self_label),
            SubjectRef(kind=SubjectKind.COMPANION, label=partner_label),
        ],
        period=RelocationPeriod(
            start=req_start.strftime("%Y-%m"), end=scan_end.strftime("%Y-%m")),
        current_location=constraints.location_base or "미지정",
        candidate_directions=[constraints.direction] if constraints.direction else None,
        relocation_kind=getattr(intent, "relocation_kind", "home"),
        reality_constraints=constraints.reality_constraints,
    )
    result = RelocationResolver(_DICTS).resolve(
        query,
        {self_label: self_comps, partner_label: partner_comps},
        {self_label: self_y, partner_label: partner_y},
    )
    if not result.move_dates:
        return None

    rows = [
        DateChoiceRow(
            date=c.date,
            weekday=_WEEKDAY_KO[date.fromisoformat(c.date).weekday()],
            ganji=c.ganji,
            score=c.final_score,
            recommendation="recommended" if c.final_score >= 70 else "acceptable",
            notes=([*c.reasons, "손없는 날"] if c.son_eomneun_nal else list(c.reasons)),
        )
        for c in result.move_dates
    ]
    # 구성원 경고(중복 제거) + 그룹 충돌 월.
    seen: set[tuple[str, str]] = set()
    group_warnings: list[str] = []
    for c in result.move_dates:
        for w in c.member_warnings:
            key = (w.subject_label, w.signal)
            if key not in seen:
                seen.add(key)
                group_warnings.append(f"{w.subject_label} — {w.signal}")
    if result.group_summary.conflicts:
        group_warnings.append(
            "구성원 이동운이 엇갈리는 달: " + ", ".join(result.group_summary.conflicts))
    # 방위 적합(상위) — move_dates[0]의 분리 산출값.
    directions = [
        {"direction": d, "fit": f}
        for d, f in sorted(result.move_dates[0].direction_fit.items(), key=lambda x: -x[1])
    ]
    # 이사 십성 이유분류 — 의사결정 주체(첫 대상=호주, 대상 우선 원칙 7)의 운으로 분류한다.
    relocation_reasons = _relocation_reason_lines(
        self_comps, req_start.strftime("%Y"), req_start.strftime("%Y-%m"))
    return DateSelectionBlock(
        purpose_ko=f"이사(그룹: {self_label}·{partner_label})",
        period=f"{req_start.isoformat()} ~ {scan_end.isoformat()}",
        rows=rows,
        avoid=[{"date": a.date, "reason": a.reason} for a in result.avoid_dates],
        directions=directions,
        group_warnings=group_warnings,
        relocation_reasons=relocation_reasons,
    )


# 대화형 전용 범위 지시 — 질문에 곧장·집중해 답하고 원국 통독을 막는다(리포트는 전체 서술 유지).
_CHAT_SCOPE_DIRECTIVE = (
    "[답변 범위 — 대화형]\n"
    "사용자의 이번 질문에 곧장 답한다. 질문이 특정 시점(그날·그달)이나 특정 주제이면 그 범위에"
    " 집중하고, 원국·성향·신살은 그 답에 꼭 필요한 근거만 골라 한두 줄로 인용한다 — 원국 전체를"
    " 처음부터 다시 설명하지 말 것. 앞 턴에서 이미 말한 내용은 반복하지 않는다. 인사말은 생략한다."
)

# 직전 답변의 '제안' 표지 — '그래 봐줘' 수락 시 그 제안을 이어가도록 추출하는 단서.
_OFFER_MARKERS = (
    "봐드릴게요", "봐드려요", "봐 드릴", "풀어드릴", "짚어드릴", "알려드릴", "정리해드릴",
    "보고 싶으세요", "보고 싶은", "말씀해 주시면", "말씀해주시면", "말씀 주시면",
    "원하시면", "이어서", "더 자세히", "어느 쪽", "어느 흐름", "중 어느",
)
# 동의+이어보기('그래 봐줘')일 때, 직전 답변 끝에 제시한 제안을 이어 답하라는 우선 지시.
_OFFER_CONTINUE_DIRECTIVE = (
    "[중요·이어보기 — 다른 표기보다 우선 적용]\n"
    "사용자가 짧은 수락('그래/봐줘')으로 직전 답변의 제안을 받아들였다. 직전 답변 끝에서 네가 먼저 "
    "제안한 바로 그 갈래를 이번 답의 중심으로 곧장 이어서 풀어라 — 같은 분야·맥락을 유지하고, 일반 "
    "총운이나 다른 주제로 새로 시작하지 말 것. 네가 직전에 제안한 내용은 다음과 같다: 「{offer}」"
)


def _extract_offer(answer: str) -> str:
    """직전 답변 끝의 '이어서 봐드릴게요/어느 쪽 보고 싶으세요' 류 제안 문장을 뽑는다(없으면 '').

    페르소나 규칙상 답변 끝에 후속 제안/질문을 붙이므로 마지막 1~2문장에서 제안 표지가 있는
    부분만 취한다(토큰 가드 300자). 제안이 없으면 빈 문자열 → 이어보기 지시 미적용.
    """
    if not answer:
        return ""
    sents = [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+", answer.strip()) if s.strip()]
    tail = sents[-2:] if len(sents) >= 2 else sents
    picked = [s for s in tail if any(m in s for m in _OFFER_MARKERS)]
    return " ".join(picked)[:300].strip()

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

# 막연한 시점 질문 — 올해부터 10년 연(세운) 단위 흐름 + 대운 교운기 반영 + 연도 지정 유도.
# 특정 연/월 미지정('결혼 때를 알고 싶어' 등)에서 현재 연도 12개월로 좁혀 월을 단정하던 결함
# 보완(2026-06-18 데굴님 지적: 막연한 기간은 년운 중심, 이후 연도 지정으로 상세 유도).
_YEAR_DIGEST_DIRECTIVE = (
    "[응답 형식] 이 질문은 시점이 막연하다(특정 연·월 미지정) — 올해부터 약 10년의 흐름을 "
    "'연(세운) 단위'로 큰 줄기만 짚어라. 12개월 월별 나열·특정 달 단정은 하지 말 것(아직 "
    "범위가 넓다). 각 해가 어느 대운에 속하는지 배경을 깔고, 그 10년 안에서 대운이 바뀌는 "
    "교운기(전환기)가 있으면 그 시기의 갑작스럽고 비자발적인 전환 에너지를 반드시 함께 "
    "반영하라(교운 근접 해일수록 변동 폭이 크다). 강하게 작동하는 해와 주의가 필요한 해를 "
    "골라 총평하고, 답변 끝에 '어느 해를 더 자세히 보고 싶은지' 한 가지를 자연스럽게 물어 — "
    "사용자가 특정 연도를 지정하면 그때 그 해의 월별 상세를 풀어주겠다고 안내하라."
)

# 이사 해석 — 십성(이사 유형·이유)과 용신/기신(이사 길흉)을 분리시킨다. LLM이 천간의 기신
# 역할로 이사 '유형'을 설명하던 오류(2026-06-18 데굴님 지적: 甲을 정관이 아닌 기신으로만 서술)를
# 차단. 판정 우선순위 메모리(길흉=용신/기신, 사건종류=십성)를 프롬프트로 강제한다.
_RELOCATION_REASON_DIRECTIVE = (
    "[중요·이사 해석 규칙 — 다른 표기보다 우선 적용]\n"
    "이사의 '유형·이유·집 성격'은 [이사 이유·집 성격 — 십성 분류] 블록을 1차 근거로 삼아라. "
    "들어온 운의 '천간 십성'이 어떤 결의 이사인지를 정한다(예: 정관=직장·검증된 집·사회적 기준, "
    "편재=교통·상권·생활권, 정인=권리안정·임시거처) — 그 블록의 십성 라벨을 그대로 풀어 서술하라. "
    "천간의 용신·희신·기신·구신 역할은 그 이사의 '길흉(유리/불리)'만 가르는 축이다. "
    "같은 천간이라도 '무슨 이사인가'는 십성으로, '좋은가/나쁜가'는 용신·기신으로 답하라 — "
    "둘을 섞어 기신/희신으로 "
    "이사 '유형·이유'를 설명하지 말 것. 해당 기간에 이사 신호가 약하거나 없으면, 먼저 '이 시기엔 "
    "뚜렷한 이사 신호가 없다'고 밝힌 뒤 '다만 만약 이사를 한다면, 들어온 천간이 OO(십성)이라 △△한 "
    "이유의 이사가 될 가능성이 있다'처럼 조건부 유형으로 짧고 분명하게 서술하라. 발생 단정은 금지."
)

# 이사 목적지 명시 질문 — '언제 옮기나(타임라인)'가 아니라 '이 지역·이 방향이 나에게 맞는 이동인가'.
# 특정 목적지(target_region)를 대고 적합성을 물으면 10년 연 단위 나열로 답이 채워지던 결함 차단
# (2026-06-25 데굴님 지적: 지역오행·방위 의도가 묻히고 10년 풀이만 반복).
_RELOCATION_DESTINATION_DIRECTIVE = (
    "[중요·이사 목적지 질문 — 다른 표기보다 우선 적용]\n"
    "사용자가 특정 목적지를 명시하고 '그곳으로 옮기는 게 나에게 맞는·이로운 이동인지'를 물었다. "
    "답의 중심을 두 가지에 둘 것: ①[지역 오행 적합] — 그 지역 오행이 내 용신과 맞는 터전인지 "
    "②[이동 방위 적합] — 현재지→목적지 이동 방위가 길한 방위(용신·희신)인지 부담 방위(기신·구신)"
    "인지. 이 둘로 '이 지역·이 방향으로의 이동이 내 운을 살리는 이로운 이동인지'를 먼저 분명히 "
    "답하라 — 두 블록이 '참고' 표기여도 답의 핵심으로 다루되 단정은 피해 '유리/주의/중립'으로 "
    "풀고, 목적지 오행이 용신이어도 이동 방위는 기신일 수 있으니 둘을 구분해 설명하라. 연도별 "
    "흐름은 '굳이 옮긴다면 어느 해가 무난한지'의 보조 배경으로만 한두 줄 곁들이고, 10년 연 단위 "
    "나열로 답을 채우지 말 것."
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

# 생활형 횡재(로또·연금복권·소액 주식 등) — 일상적 재미·소액 시도 맥락. 번호 요청('로또 번호')은
# query_parser에서 OUT_OF_SCOPE로 이미 거부된다(여기 도달 = 흐름·시기 질문). CLAUDE.md 절대원칙 8
# (2026-06-20 개정): 생활형 횡재는 시기·흐름·유불리·태도를 자유롭게 풀되, 하드 가드만 유지.
_LIFESTYLE_WINDFALL_KEYS = (
    "로또", "복권", "연금복권", "주식", "코인", "비트코인", "펀드", "청약", "경마", "토토",
)
_LIFESTYLE_WINDFALL_DIRECTIVE = (
    "[생활형 횡재 — 표현 자유 우선 적용]\n"
    "이 질문은 로또·연금복권·소액 주식 같은 '생활형 횡재'다. 과도한 면책·경고를 반복하지 말고, "
    "재물 흐름·유리한 시기·임하는 태도(소액·분산·재미로)를 따뜻하고 자연스럽게 풀어라. "
    "용신/기신과 운의 유입 십성으로 '언제가 더 편안한지', 그 시기가 '유리한지/부담인지'를 "
    "구체적으로 짚어도 된다. 다만 다음만은 지킨다: ①구체적인 번호·종목을 찍어 주지 않는다 "
    "②'당첨된다/수익 확정' 같은 결과 단정은 하지 않는다(가능성·기류로) "
    "③전 재산 투입 등 과몰입은 권하지 않는다. "
    "이 세 가지 밖에서는 위축되지 말고 평소 운세처럼 충분히 이야기하라."
)


def _is_lifestyle_windfall(intent: IntentJson, question: str) -> bool:
    """생활형 횡재 질문 여부 — 재물/횡재 의도 + 생활형 키워드(번호 요청은 이미 정책 거부됨)."""
    wealth_ctx = intent.domain is Domain.WEALTH or str(intent.event_key) in (
        "windfall", "wealth_change",
    )
    return wealth_ctx and any(k in question for k in _LIFESTYLE_WINDFALL_KEYS)


# 큰 결정(결혼·이혼) 타이밍 — 운 저점이면 보류 권고(궁합 자료: 운이 안 좋을 땐 인생을 바꿀 결정을
# 미루라, 조급함이 신호). 결정 어미가 동반된 결혼·이혼 질문에만 적용한다.
_BIG_DECISION_KEYS = ("결혼", "이혼", "재혼", "파혼", "헤어")
_DECISION_MARKERS = ("할까", "말까", "해도", "좋을까", "결정", "하는 게", "하는게", "해야")
_BIG_DECISION_DIRECTIVE = (
    "[큰 결정 타이밍 — 결혼·이혼 등 인생을 바꾸는 결정]\n"
    "결혼·이혼 같은 큰 결정은 '시기'를 함께 보라. 제공된 운 품질(연·월 등급·후보 유불리)에서 "
    "이 시기가 기신운·저점이거나 돈·건강·관계가 함께 흔들리는 신호면, 결정을 서두르지 말고 "
    "'시간을 견디며 뒤로 미루는 것'을 권하라(운 저점엔 큰 결정 보류 — 조급함 자체가 신호). "
    "운이 받쳐주면 차분히 검토해도 좋다고 안내하라. '반드시 하라/하지 마라'식 단정·운명론은 "
    "금지 — 가능성·권유로만. 결정의 책임은 본인에게 있음을 존중하라."
)


def _is_big_decision(intent: IntentJson, question: str) -> bool:
    """결혼·이혼 등 인생 결정 질문 여부 — 결혼/이혼 키워드 + 결정 어미."""
    rel_ctx = intent.domain is Domain.RELATIONSHIP or any(
        k in question for k in _BIG_DECISION_KEYS
    )
    has_decision = any(m in question for m in _DECISION_MARKERS)
    return rel_ctx and any(k in question for k in _BIG_DECISION_KEYS) and has_decision


# 인연·만남 시기 질문 — 도메인 관계 또는 연애·배우자 키워드(GENERAL로 분류돼도 키워드로 보강).
_RELATIONSHIP_KEYS = (
    "연애", "연인", "인연", "애인", "짝", "배우자", "결혼", "재혼", "소개팅",
    "이상형", "남친", "여친", "남자친구", "여자친구", "솔로", "썸",
)


def _is_relationship_context(intent: IntentJson, question: str) -> bool:
    """관계(연애·결혼·인연) 맥락 질문 여부 — GENERAL로 분류돼도 키워드로 보강한다."""
    return intent.domain is Domain.RELATIONSHIP or any(
        k in question for k in _RELATIONSHIP_KEYS
    )


# 인연 출처 질문 — '주변 사람 vs 새로운 사람' 류(기존 지인이냐 새 인연이냐).
_PARTNER_SOURCE_KEYS = (
    "주변", "지인", "아는 사람", "아는사람", "소개", "새로운 사람", "새 사람", "새사람",
    "처음 보는", "처음보는", "기존", "원래 알", "어디서 만나",
)


def _is_partner_source_question(question: str) -> bool:
    """'기존 지인 vs 새 인연' 출처를 묻는 질문 여부."""
    return any(k in question for k in _PARTNER_SOURCE_KEYS)


_MEETING_TIMING_DIRECTIVE = (
    "[인연·만남 시기 — 만남은 택일이 아니다]\n"
    "연인·배우자를 '언제' 만나는지는 일정처럼 고르는 택일이 아니다. 특정 달을 선택지로 나열하거나 "
    "약한 달·기신 달을 끌어와 '○월에도 신호가 있지만…'처럼 곧장 무르지 말 것. 제공된 운에서 가장 "
    "유리한 시기 하나만 골라 연·반기·계절 단위로 제시하라(불리한 시기는 굳이 언급하지 않는다). "
    "또 '어디서·어떤 경로로' 만나는지는 사주로 단정할 수 없다 — 출장지·교육현장 같은 구체적 장소를 "
    "지어내지 말고 활동 성향 정도의 경향으로만(단정 금지) 가볍게 언급하라."
)


# 이혼 상담 — 사유 severity 분기(궁합 자료: 외도·폭력=회복 어려움 / 성격·건강=극복 가능).
_DIVORCE_KEYS = ("이혼", "별거", "파혼")
_DIVORCE_SEVERITY_DIRECTIVE = (
    "[이혼 상담 — 사유별 결]\n"
    "이혼 고민이면 사유의 결을 구분해 설명하라: 외도·폭력처럼 신뢰·안전이 깨지는 문제는 "
    "궁합·노력으로 회복하기 어려운 영역으로, 자신을 보호하는 선택을 존중하라. 반면 성격 차이·"
    "잦은 부딪힘·건강 같은 문제는 시간·성숙·대화·상담으로 달라질 수 있는 영역으로, 충분히 "
    "노력해 본 뒤 선택하도록 안내하라. 어느 쪽이든 '반드시 이혼/유지하라'는 단정·상대 탓·"
    "운명론은 금지. 사주는 참고이며 결정은 본인 몫임을 분명히 하라."
)


def _is_divorce_question(question: str) -> bool:
    """이혼·별거·파혼 상담 질문 여부."""
    return any(k in question for k in _DIVORCE_KEYS)


# 대운(10년 단위)·장기 인생 흐름 질문 — 대운 framing(환경/공간감)·교체기 신호를 붙일 트리거.
_DAEWOON_KEYS = (
    "대운", "교운", "평생", "인생 전체", "인생 흐름", "큰 흐름", "큰 운", "10년", "십년",
)


def _is_daewoon_question(intent: IntentJson, question: str) -> bool:
    """대운·장기 인생 흐름 질문 여부 — 명시 키워드 기반(막연한 장기 질문은 호출부에서 OR 보강)."""
    return any(k in question for k in _DAEWOON_KEYS)


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
        # 배우자성 성별 가드를 결혼 블록과 항상 동반 — general로 분류된 관계 질문('언제 만나' 등)도
        # 남=재성·여=관성 기준을 받게 한다(2026-06-22 데굴님 지적: GENERAL은 가드 누락이던 결함).
        out.append(spouse_star_directive(str(result.input_summary.get("gender", "unknown"))))
        # 배우자성=용신(배우자 덕) 판정에 용희신을 넘긴다(G). 자기인식 가드도 함께(C).
        _useful = build_birth_summary(result).useful_gods
        out += marriage_resource_lines(analyze_marriage_resource(result, _useful))
        out.append(RELATIONSHIP_SELF_AWARENESS_DIRECTIVE)
        out.append(TENDENCY_SHIFT_DIRECTIVE)
    if general or domain is Domain.HEALTH:
        hv = analyze_health_vulnerability(result, favorability_map(result))
        out += health_lines(result, hv, today.year)
    return out


def _daewoon_span_context(result: ManseV2Result, start_year: int, end_year: int) -> str:
    """[start_year, end_year] 구간과 겹치는 대운들을 배경으로 한 줄 요약(교운기 표시).

    막연한 시점의 10년 연 단위 흐름에서, 각 해가 어느 대운에 속하는지와 구간 안에서 대운이
    바뀌는 교운기(전환기)를 LLM에 전달한다(교운 가중은 이미 스코어에 반영 — 텍스트는 배경용).
    """
    lc = result.luck_cycles
    if lc is None or not lc.daewoon_table:
        return ""
    segs: list[str] = []
    transitions: list[int] = []
    for dw in lc.daewoon_table:
        s = dw.approx_start_date.year if dw.approx_start_date else None
        e = dw.approx_end_date.year if dw.approx_end_date else None
        if s is None or (e or 9999) < start_year or s > end_year:
            continue
        span = f"{s}~{e}" if e else f"{s}~"
        tg = dw.stem_ten_god or ""
        label = f", {dw.luck_label}" if dw.luck_label else ""
        segs.append(f"{dw.ganji}({span}, {tg}{label})")
        if start_year < s <= end_year:  # 구간 안에서 새 대운이 시작 = 교운기
            transitions.append(s)
    if not segs:
        return ""
    line = "대운 흐름(배경): " + " → ".join(segs)
    if transitions:
        years = ", ".join(f"{t}년 무렵" for t in transitions)
        line += f" · 이 10년 안에 대운 교운기({years}) — 전환 에너지가 강하게 작동"
    return "\n[대운 배경 — 10년 흐름]\n" + line


def _is_day_range(intent: IntentJson) -> bool:
    """일 단위 다중일 범위(주간 등) 질문인가 — 일별 일운 surface 게이트."""
    tr = intent.time_range
    return bool(
        tr is not None and tr.start and tr.end and tr.end != tr.start
        and tr.granularity.value == "day"
    )


def _weekly_overview_lines(
    birth: BirthInput, intent: IntentJson, today: date,
) -> list[str]:
    """주간(일 범위) 질문에 7일 일별 일운(간지·길흉·십성)을 surface한다(2026-06-18 보완).

    주간 질문이 일별 데이터 없이 월운으로 뭉뚱그려지던 결함 보완 — 날짜별 간지·길흉(용/희/한/기/
    구)·십성을 제공해 LLM이 하루씩 짚게 한다. 점수·간지는 엔진 계산값(절대원칙 1). 14일 이내만.
    """
    tr = intent.time_range
    if tr is None or not tr.start or not tr.end:
        return []
    try:
        start = date.fromisoformat(tr.start[:10])
        end = date.fromisoformat(tr.end[:10])
    except ValueError:
        return []
    if not (start < end and (end - start).days <= 14):
        return []
    try:
        chart = calculate(birth.model_copy(update={"reference_date": start}))
        if chart.luck_cycles is not None:
            window = daily_luck_window(chart, start, end)
            chart = chart.model_copy(update={"luck_cycles": chart.luck_cycles.model_copy(
                update={"daily_luck": window})})
        comps = CompositeBuilder(_DICTS).build(
            chart, "chat", "1.0.0", f"{today.isoformat()}T00:00:00+00:00")
        days = sorted(
            (c for c in comps if c.level is CompositeLevel.DAY
             and start.isoformat() <= c.period_key <= end.isoformat()),
            key=lambda c: c.period_key,
        )
    except Exception:  # noqa: BLE001 — 일별 산출 실패가 일반 풀이를 막지 않도록
        return []
    if not days:
        return []
    header = (
        f"[해당 기간({start.isoformat()}~{end.isoformat()}) 일별 흐름 — 일운 간지·길흉(용신/희신/"
        "한신/기신/구신)·십성. 날짜별로 하루씩 짚어 서술하고 월 단위로 뭉뚱그리지 말 것]"
    )
    lines = [header]
    for c in days:
        d = date.fromisoformat(c.period_key)
        lines.append(
            f"- {c.period_key}({_WEEKDAY_KO[d.weekday()]}) {c.ganji.stem}{c.ganji.branch} · "
            f"{c.favorability} · 십성 {c.ten_god.stem}/{c.ten_god.branch_main}"
        )
    return lines


# Intent 임베딩 보조 게이트 — 규칙이 domain을 못 정한(general) 경우에만 보강(rules-first).
# 보수적 임계·마진(2026-06-18 A안): 토이 평가셋 기준 초안 — 실제 로그 평가셋으로 재튜닝 대상.
_INTENT_SIM_MIN_SCORE = 0.55
_INTENT_SIM_MIN_MARGIN = 0.05
# 시점(TimeBucket) 임베딩 보조 게이트 — 규칙이 시점을 못 잡은(time_range None) 경우에만 보강.
# 시점 버킷은 의미가 인접해 주제어가 섞이면 마진이 매우 작다(측정값 0.00~0.10) — 마진 의존은
# recall을 죽인다. 대신 ①점수 게이트(비시점 질문은 0.55 미만이거나 ②비합성 앵커(vague/past/
# timeless, 높은 점수)로 흡수)로 안전성을 확보한다. reviewed:false 초안 — 실로그 평가셋 재튜닝 대상.
_TIME_SIM_MIN_SCORE = 0.58
_TIME_SIM_MIN_MARGIN = 0.0


def _augment_domain_by_similarity(intent: IntentJson, question: str) -> IntentJson:
    """규칙이 domain=GENERAL로만 잡은 질문을 임베딩 분류기로 보강한다(보조 신호, rules-first).

    domain(general→구체)과 event(미지정 시)만 채운다 — query_type·점수·간지·판정엔 미개입
    (절대원칙 1·9). 분류기 비활성(의존성·모델 부재)·저신뢰·general 제안이면 원본 그대로 반환한다.
    """
    if intent.domain is not Domain.GENERAL:
        return intent
    from saju_engines.intent_embedding import get_intent_classifier

    sug = get_intent_classifier().classify(question)
    if (
        sug is None
        or sug.domain == "general"
        or sug.score < _INTENT_SIM_MIN_SCORE
        or sug.margin < _INTENT_SIM_MIN_MARGIN
    ):
        return intent
    event = intent.event_key
    if event is None and sug.event is not None:
        event = EventKey(sug.event)
    return intent.model_copy(update={
        "domain": Domain(sug.domain),
        "event_key": event,
        "event_keys": intent.event_keys or ([event] if event else []),
    })


def _augment_time_by_similarity(
    intent: IntentJson, question: str, today: date, current_month_label: str | None,
) -> IntentJson:
    """규칙이 시점을 못 잡은(time_range None) 질문을 임베딩 분류기로 보강한다(보조, rules-first).

    합성 가능한 구체 버킷(이번 주/달·올해 등 변형 표현)만 결정론 TimeRange로 채운다. 분류기
    비활성·저신뢰·비합성 버킷(막연 미래/과거 회고/구조)이면 None을 유지해 다운스트림(vague_future·
    회고 경로)이 그대로 처리한다. 점수·간지·판정엔 미개입(절대원칙 1·9). 날짜는 결정론 계산.
    """
    if intent.time_range is not None:
        return intent  # 규칙이 이미 시점 확정 — rules-first
    from saju_engines.time_embedding import get_time_classifier
    from saju_engines.time_parser import bucket_to_range

    sug = get_time_classifier().classify(question)
    if (
        sug is None
        or sug.score < _TIME_SIM_MIN_SCORE
        or sug.margin < _TIME_SIM_MIN_MARGIN
    ):
        return intent
    tr, _scope = bucket_to_range(sug.label, today, current_month_label)
    if tr is None:
        return intent  # 비합성 버킷 — 막연/회고/구조는 합성하지 않고 다운스트림 위임
    return intent.model_copy(update={"time_range": tr})


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
    occupation_status: str | None = None,
    relationship_status: str | None = None,
    occupation_category: str | None = None,
    prior_answer: str | None = None,
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
    # 규칙이 domain을 못 정한(general) 질문만 임베딩 분류기로 보강(rules-first 보조 — 절대원칙 1·9).
    intent = _augment_domain_by_similarity(intent, question)
    # 규칙이 시점을 못 잡은 경우만 임베딩 시점 분류기로 보강(rules-first, 결정론 날짜 합성).
    intent = _augment_time_by_similarity(intent, question, today, luck_month)

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
    # 사용자 확정 용신 — 있으면 용희기구한 5역할을 그 용신으로 재도출해 fav_override로 점수에 반영.
    # 엔진 최초 도출값(result.yongsin_analysis.final = 확정 전 후보)은 비파괴 보존(되돌림 기준).
    _fav_override, _confirmed_yongsin = fetch_confirmed_yongsin_override(owner_id, subject_id)
    all_scored = _get_scorer().score_legacy_personalized(
        result, levels=_SCORE_LEVELS, fav_override=_fav_override,
        signature=_sig, cohort=_cohort,
        occupation_status=occupation_status, relationship_status=relationship_status,
        occupation_category=occupation_category,
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

    # 목적지가 정해진 이사 질문('이사할집은 서울 중구야')은 '언제 옮기나(타임라인)'가 아니라
    # '이 곳·이 이동이 나에게 맞는가(지역오행·방위·이사 결)'를 보는 평가형이다 — 시점을 묻지
    # 않았으면(언제/몇 월/시기 등 없음) 연·월 흐름 타임라인을 만들지 않는다(2026-06-25 데굴님:
    # 이미 집이 정해진 상태에서 이사 가능시기 나열은 비논리).
    _relo_dest = _is_relocation_intent(intent) and bool(intent.constraints.target_region)
    _asks_move_timing = bool(
        re.search(r"언제|몇\s*월|몇\s*년|어느\s*(해|달|연도|월|시기)|타이밍|이사\s*시기", question)
    )
    relo_decided = _relo_dest and not _asks_move_timing
    # 막연한 시점(특정 연·월 미지정, 미래) → 올해부터 10년 연(세운) 단위 흐름으로 답하고 연도
    # 지정을 유도한다. 현재 연도 12개월로 좁혀 특정 달을 단정하던 결함 보완(2026-06-18 데굴님).
    # 과거 회고·구조 질문·기간총운, 명시 시점(올해/내년/특정연월/향후 N년=start 있음)은 제외.
    vague_future = (
        period_fortune is None and not is_structural and not is_retro
        and not relo_decided
        and (intent.time_range is None or not intent.time_range.start)
    )
    year_digest_years: list[int] = []
    year_result = result        # 세운 10년 확장본(기본 창 밖 연도 온디맨드 보강)
    year_scored = all_scored
    if vague_future:
        year_digest_years = list(range(today.year, today.year + 10))
        default_period = (str(today.year), str(today.year + 9))
        if result.luck_cycles is not None:
            have = {pl.label for pl in result.luck_cycles.yearly_luck}
            missing = [y for y in year_digest_years if str(y) not in have]
            if missing:
                # 기본 yearly_luck 창(올해±5)을 넘는 연도(올해+6~+9)를 채워 10년을 완성.
                extra = luck_years(chart_birth, missing)
                year_result = result.model_copy(deep=True)
                assert year_result.luck_cycles is not None
                year_result.luck_cycles.yearly_luck = (
                    list(year_result.luck_cycles.yearly_luck) + extra
                )
                year_scored = _get_scorer().score_legacy_personalized(
                    year_result, levels={GanjiLevel.YEAR}, fav_override=_fav_override,
                    signature=_sig, cohort=_cohort,
                    occupation_status=occupation_status,
                    relationship_status=relationship_status,
                    occupation_category=occupation_category,
                )

    if period_fortune is not None or is_structural:
        candidates = []
        bundles = []
    elif vague_future:
        # 세운(연) 중심 — 월 후보는 빼서 LLM이 10년 연 단위 흐름에 집중하게 한다.
        lo, hi = str(today.year), str(today.year + 9)
        candidates = [
            c for c in year_scored if len(c.period) == 4 and lo <= c.period <= hi
        ]
        candidates = _get_intent_filter().filter(candidates, str(intent.domain))
        scope_v: list[EventKey] = plan.graph_scope or [c.event_key for c in candidates[:5]]
        bundles = _get_graph().retrieve(scope_v)
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

            # 날짜(YYYY-MM-DD) 단일일 질문이면 월 후보를 '양력 달'이 아니라 '그 날의 절기월'로
            # 잡는다 — 7/4는 소서(7/7) 전이라 甲午월(2026-06)이지 乙未월(2026-07)이 아니다.
            # (2026-06-22 데굴님 지적: 7/4 이사 질문이 계속 乙未월로 풀리던 결함).
            solar_m: str | None = None
            if win_start and win_start == win_end and len(win_start) == 10:
                tz_w = (
                    result.time_correction.timezone
                    if result.time_correction else "Asia/Seoul"
                )
                solar_m = _current_luck_month(date.fromisoformat(win_start), tz_w)

            def _in_win(period: str) -> bool:
                if solar_m is not None and len(period) == 7:  # 월 후보 — 절기월만
                    return period == solar_m
                return in_question_range(period, win_start, win_end)

            seen = {(c.event_key, c.period) for c in candidates}
            candidates += [
                c for c in all_scored
                if (c.event_key, c.period) not in seen and _in_win(c.period)
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
    wants_monthly = period_fortune is None and not vague_future and not relo_decided and (
        monthly_explicit
        or event_monthly
        or intent.query_type is QueryType.TIMING_SEARCH
        or gran_month
        or any(k in question for k in ("몇 월", "몇월", "언제", "어느 달"))
        or any(k in question for k in ("앞으로", "향후", "다가오는", "1년 내", "1년내"))
    )
    result_for_llm = result  # on-demand 월운 주입 시 교체(간지·해석 lookup 커버용)
    if vague_future and year_result.luck_cycles is not None:
        # 막연한 시점 → 올해부터 10년 세운 흐름 digest(연별 운 품질·우세 사건). 월별 표 미생성.
        avail = {pl.label for pl in year_result.luck_cycles.yearly_luck}
        labels = [str(y) for y in year_digest_years if str(y) in avail]
        if labels:
            overview = build_monthly_overview(year_result, year_scored, months=labels)
            result_for_llm = year_result
    elif wants_monthly and result.luck_cycles is not None:
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
            scored_win = _get_scorer().score_legacy(
                result_win, levels={GanjiLevel.MONTH}, fav_override=_fav_override,
            )
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
                scored_year = _get_scorer().score_legacy(
                    result_year, levels={GanjiLevel.MONTH}, fav_override=_fav_override,
                )
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
            # 이사 택일 + 동반자 첨부 → M10 그룹 집계(함께 무난한 날). 그 외엔 단일 택일.
            if partner_birth is not None and _is_relocation_intent(intent):
                date_block = _relocation_group_block(
                    birth, partner_birth, intent, today,
                    subject_label or "본인", partner_label or "상대",
                ) or _date_selection_block(birth, intent, today, yongsin)
            else:
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
    # 구조 해석 블록 — 단일 대상일 때만(궁합 비교는 대상 혼동 방지로 생략).
    structural = (
        _structural_context(result, intent, today) if not plan.per_subject else None
    )
    # 이사 평가 질문('이사하면 어때?' — 택일 아님)은 date_block이 없으므로, 십성 이사 이유분류를
    # 구조 블록에 실어 '무슨 십성이라 이런 이사' 서술을 가능케 한다(2026-06-18 결함 보완).
    if structural is not None and _is_relocation_intent(intent):
        structural = structural + _relocation_reason_context(birth, intent, today)
        # 목적지 지역이 명시되면 지역 오행 × 용신 궁합도 함께 surface(2026-06-18 보완).
        structural = structural + _relocation_region_context(birth, intent, today)
    # 주간(일 범위) 질문은 7일 일별 일운을 surface — 월운으로 뭉뚱그려지던 결함 보완(2026-06-18).
    if structural is not None and _is_day_range(intent):
        structural = structural + _weekly_overview_lines(birth, intent, today)
    # 막연한 시점 → 10년 연 단위 흐름의 대운 배경·교운기를 구조 블록에 실어 LLM이 반영하게 한다.
    if structural is not None and vague_future and year_digest_years:
        span = _daewoon_span_context(year_result, year_digest_years[0], year_digest_years[-1])
        if span:
            structural = structural + [span]
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
        structural_context=structural,
    )
    call_type = "chat_compare" if plan.per_subject else "chat_single"

    # 직렬화 본문 뒤에 덧붙는 후행 지시문·시스템 프롬프트를 먼저 모은다 — 이 고정 오버헤드를
    # 토큰 가드 예약분으로 넘겨야 컨텍스트 축소기가 '실제 총 입력(payload+오버헤드)' 기준으로
    # 줄인다. 안 그러면 serialize 통과 후 지시문·시스템이 더해져 generate_reading 재검사에서
    # 한도 초과 → 일반 오류로 마감되던 결함(2026-06-18, 10년 이사 질문 12,098tok 초과).
    trailing: list[str] = [_CHAT_SCOPE_DIRECTIVE]
    # 제안 이어보기 — '그래 봐줘' 류 수락이면 직전 답변에서 LLM이 제시한 제안을 그대로 이어 답하게
    # 한다(LLM 즉석 제안이 상태에 없어 일반 흐름으로 끊기던 결함 — 2026-06-25 데굴님 지적).
    if prior_answer and is_affirm_continue(question):
        _offer = _extract_offer(prior_answer)
        if _offer:
            trailing.append(_OFFER_CONTINUE_DIRECTIVE.format(offer=_offer))
    # 사용자 확정 용신 적용 안내 — 확정 5역할을 길흉 기준으로, 엔진 최초 도출은 기본값으로 병기.
    if _confirmed_yongsin is not None:
        from saju_engines.event_scoring import confirmed_yongsin_note
        _yongsin_note = confirmed_yongsin_note(result, _confirmed_yongsin)
        if _yongsin_note:
            trailing.append(_yongsin_note)
    # 특정 날짜 질문 — 그 날(들)의 일운(중심) + 절기월(양력 달 오답 방지)을 사실로 주입한다.
    # 질문의 명시 날짜(다중 포함)를 모두 잡고, 없으면 시점이 단일 날짜일 때 그 날을 쓴다.
    _tz = result.time_correction.timezone if result.time_correction else "Asia/Seoul"
    _ref_year = (
        int(intent.time_range.start[:4])
        if intent.time_range is not None
        and intent.time_range.start
        and intent.time_range.start[:4].isdigit()
        else today.year
    )
    _date_targets = _explicit_dates(question, _ref_year)
    if (
        not _date_targets
        and intent.time_range is not None
        and intent.time_range.start
        and len(intent.time_range.start) == 10
    ):
        try:
            _date_targets = [date.fromisoformat(intent.time_range.start)]
        except ValueError:
            _date_targets = []
    if _date_targets:
        _df_note = _date_day_fortune_note(birth, _date_targets, _tz)
        if _df_note:
            trailing.append(_df_note)
    # 상황 제약 — 비정직원이면서 직장운(재직 전제 사건) 맥락이면 '취업'을 함께 짚게 하고,
    # 그 외(이사 등 비career 맥락)에서 무직 키워드가 잡히면 기존 '이직→이사' 분기를 적용한다.
    if nonregular and (career_presupposed or intent.domain is Domain.CAREER):
        trailing.append(_CAREER_NONREGULAR_DIRECTIVE)
    elif any(k in question for k in _UNEMPLOYED_KEYS):
        trailing.append(_UNEMPLOYED_DIRECTIVE)
    # 이사 목적지 명시 질문(_relo_dest, 위에서 산출)은 10년 타임라인 강제(year digest)를 적용하지
    # 않고 지역오행·방위 중심 우선 지시로 대체한다(2026-06-25). vague_future는 relo_decided면 이미
    # False라 아래 분기는 자연히 스킵된다.
    # 응답 형식 — 막연한 시점이면 10년 연(세운) digest+연도 지정 유도, 그 외 사건형 연 질문은
    # 12개월 나열 대신 연간 요약+핵심 달로.
    if vague_future and not _relo_dest:
        trailing.append(_YEAR_DIGEST_DIRECTIVE)
    elif overview is not None and event_monthly and not monthly_explicit:
        trailing.append(_KEY_MONTHS_DIRECTIVE)
    # 대운·장기 인생 흐름 질문 — 대운을 '환경/공간감(플랫폼)이 닥쳐오는 흐름·이 대운이 나에게
    # 맞느냐'로 서술하고 교체기 체감 신호도 함께(리포트 대운 섹션과 공용 관점, 2026-06-23 확장).
    if (_is_daewoon_question(intent, question) or vague_future) and not _relo_dest:
        trailing.append(DAEWOON_FRAMING_DIRECTIVE)
        trailing.append(DAEWOON_TRANSITION_SIGNALS_DIRECTIVE)
    # 이사 질문 — 십성(유형)과 용신/기신(길흉)을 분리해 답하도록 강제(2026-06-18).
    if _is_relocation_intent(intent):
        trailing.append(_RELOCATION_REASON_DIRECTIVE)
    # 목적지 명시 이사 — 답의 중심을 지역오행·이동 방위 적합에 두게 한다(2026-06-25).
    if _relo_dest:
        trailing.append(_RELOCATION_DESTINATION_DIRECTIVE)
    # 생활형 횡재(로또·연금복권·소액 주식) — 흐름·시기·태도를 자유롭게 풀게 한다(번호·종목픽·
    # 당첨단정 거부는 유지). CLAUDE.md 절대원칙 8 개정(2026-06-20 데굴님 승인).
    if _is_lifestyle_windfall(intent, question):
        trailing.append(_LIFESTYLE_WINDFALL_DIRECTIVE)
    # 인연·만남 시기 — 만남은 '택일'이 아니므로 약한/기신 달을 선택지로 끌어와 무르지 말고,
    # 가장 유리한 시기 하나(연·반기·계절)로. 만날 장소·경로는 사주로 단정 불가(과도한 구체화 금지).
    if _is_relationship_context(intent, question):
        trailing.append(_MEETING_TIMING_DIRECTIVE)
    # 인연 출처 — '주변 사람 vs 새로운 사람' 질문이면 합·도화=가까운 / 충·역마=새 인연 근거(비단정).
    if _is_partner_source_question(question):
        trailing.append(PARTNER_SOURCE_DIRECTIVE)
    # 큰 결정(결혼·이혼) 타이밍 — 운 저점이면 보류 권고(궁합 자료). 이혼이면 사유 severity 분기도.
    if _is_big_decision(intent, question):
        trailing.append(_BIG_DECISION_DIRECTIVE)
    if _is_divorce_question(question):
        trailing.append(_DIVORCE_SEVERITY_DIRECTIVE)
    # 궁합(pairwise) — 상대가 첨부되면 엔진 계산 궁합 신호 블록을 입력에 덧붙인다.
    if partner_birth is not None:
        compat = _compat_prompt_block(result, partner_birth, today, partner_label)
        if compat:
            trailing.append(compat)

    system = None
    if persona is not None:
        # 호칭 자리({resolvedHonorific})에 대화 기준 사주의 별명을 넣는다(하드코딩 '회원' 제거).
        block = _get_persona_engine().build_block(persona, subject_label or "회원")
        system = llm_client._SYSTEM_PROMPT + "\n\n" + block
    # generate_reading은 system 미지정 시 _SYSTEM_PROMPT를 쓰므로 예약분도 실제 전송 시스템 기준.
    sys_for_budget = system or llm_client._SYSTEM_PROMPT
    reserve = estimate_tokens(sys_for_budget) + estimate_tokens("\n".join(trailing))

    try:
        prompt_text, tokens = serialize_with_guard(
            payload, call_type, reserve_tokens=reserve
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

    prompt_text = prompt_text + "".join("\n" + part for part in trailing)

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
