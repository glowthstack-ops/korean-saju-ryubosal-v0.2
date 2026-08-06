"""대화형 통변 오케스트레이션 서비스 (v2.2 MVP — 단일 질문 → 정확한 풀이).

파이프라인(docs/01·03): 파서(T3.1 룰 기반) → 대상/광범위 판정(T3.2) → 실행 계획(T3.3)
→ 만세 계산(캐시) → 이벤트 스코어링(P2) + 계층 필터 → Graph Retrieval(T2.2)
→ Context Reduction + LLM 입력 직렬화(T3.4/5, 가드 경유) → LLM 서술(또는 dry-run).

비분석 라우트(Q11~Q14)·too_broad·대상 확인은 LLM/엔진 호출 없이 정책 응답을 돌려준다.
대화 연속성(직전 intent 상속 등)은 Phase 4 Conversation Layer에서 확장한다.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from saju_manse_analysis.luck.luck_calendar import luck_month_label

from saju_engines import (
    EventEngineV2,
    GraphIndex,
    filter_year_candidates,
    load_event_graph,
    period_v2_config,
)
from saju_engines.chart_interpretation import build_luck_grounding
from saju_engines.companion_alias import AliasEntry, merge_attached_partner
from saju_engines.companion_similarity import augment_relation_type, augment_subject_mode
from saju_engines.compatibility_engine import analyze_compatibility, compatibility_lines
from saju_engines.context_reducer import (
    build_birth_summary,
    build_llm_input,
    build_monthly_overview,
    event_ko,
    first_sentence,
    serialize_with_guard,
)
from saju_engines.conversation import (
    ConversationEngine,
    is_affirm_continue,
    overlaps_exclusions,
    tr_year_span,
)
from saju_engines.conversation_store import ConversationStore
from saju_engines.counterfactual_context import (
    build_counterfactual_context,
    counterfactual_lines,
)
from saju_engines.daewoon_progression import resolve_all_daewoon_progressions
from saju_engines.date_selection import DateSelectionEngine
from saju_engines.effective_subjects import AttachedCompanion, build_effective_subjects
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.horizon import horizon_directive, month_add, resolve_horizon
from saju_engines.intent_event_filter import IntentEventFilter
from saju_engines.llm_guard import TokenBudgetExceeded, estimate_tokens
from saju_engines.luck_hierarchy import build_luck_hierarchy
from saju_engines.luck_hierarchy_render import (
    render_hierarchy_appendix,
    render_hierarchy_narrative,
    render_period_role_summary,
    render_v2_slot_status,
)
from saju_engines.period_role_summary import build_period_role_summary
from saju_engines.period_safe_template import build_safe_period_answer
from saju_engines.persona import PersonaEngine
from saju_engines.planner import build_execution_plan
from saju_engines.policy_echo_audit import detect_policy_echo, strip_policy_echo
from saju_engines.precompute import CompositeBuilder
from saju_engines.profile_engine import profile_facts_for
from saju_engines.query_parser import (
    ACCIDENT_SAGO_RE,
    AFFIRMATION_RE,
    implies_self_counterpart,
    parse_message,
)
from saju_engines.relation_claim_audit import (
    audit_relation_claims,
    patch_relation_claims,
)
from saju_engines.relation_semantics import collect_luck_relation_semantics
from saju_engines.relation_shadow_config import should_build_relation_state_chain
from saju_engines.relation_state_chain import relation_state_chain_shadow
from saju_engines.relationship_hints import (
    COMPETITION_SAFETY_GUARDS,
    RANKING_SAFETY_GUARDS,
    SAFETY_GUARDS,
    infer_relation_type,
    is_competition,
    perspective_hints_for,
)
from saju_engines.rewriter import QueryAssessment, assess
from saju_engines.selection_intent import detect_selection_query
from saju_engines.shadow_scoring import domain_to_expression_key
from saju_engines.structural_context import (
    BARNUM_SUPPRESSION_DIRECTIVE,
    CONCLUSION_FIRST_DIRECTIVE,
    DAEWOON_FRAMING_DIRECTIVE,
    DAEWOON_TRANSITION_SIGNALS_DIRECTIVE,
    DECISION_ATTITUDE_DIRECTIVE,
    EVIDENCE_FIDELITY_DIRECTIVE,
    GONGMANG_ACTIVATION_DIRECTIVE,
    LOVE_MARRIAGE_UNIFIED_DIRECTIVE,
    MANAGE_NOT_OVERCOME_DIRECTIVE,
    NON_NORMATIVE_REASSURANCE_DIRECTIVE,
    PARTNER_SOURCE_DIRECTIVE,
    RELATIONSHIP_SELF_AWARENESS_DIRECTIVE,
    TENDENCY_SHIFT_DIRECTIVE,
    TRAIT_FEEDBACK_DIRECTIVE,
    UNCERTAINTY_TRANSLATION_DIRECTIVE,
    daewoon_progression_lines,
    spouse_star_directive,
)
from saju_engines.task_procedures import (
    build_capability_answer,
    detect_task_pack,
    procedure_reference_block,
)
from saju_engines.time_parser import DAY_WORD_OFFSETS as _TP_DAY_WORDS
from saju_engines.topic_builder import MODULES as _TOPIC_MODULES
from saju_engines.topic_builder import build_lifestyle_context, build_topic_context
from saju_engines.user_facts import user_facts_block
from saju_engines.v2_scoring import V2ScoringError, build_v2_scoring
from saju_engines.wealth_capacity import analyze_wealth_capacity
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.career_transition import CareerQueryResolution, CareerTransitionKind
from saju_shared_types.conversation import ConversationState, ResultSummaryRef, TimeExclusion
from saju_shared_types.event_taxonomy_v2 import DATE_PURPOSES, EVENT_TYPE
from saju_shared_types.events import EventKey
from saju_shared_types.execution_plan import ExecutionPlan, SubjectInjectionPolicy
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import (
    Domain,
    Granularity,
    IntentJson,
    QueryType,
    SubjectKind,
    SubjectRef,
    TimeScope,
)
from saju_shared_types.llm_input import (
    DateChoiceRow,
    DateSelectionBlock,
    PeriodFortune,
    PeriodFortuneSlot,
    RelationshipContext,
    SubjectBlock,
)
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.precompute import CompositeLevel
from saju_shared_types.profile import PersonaConfig
from saju_shared_types.topic_context import PeriodSpec

from . import (
    llm_client,
    relationship_legacy_comparison,
    relationship_shadow,
    relationship_vector_sidecar,
    relationship_vector_telemetry,
    risk_exposure_service,
)
from .manse_service import (
    calculate,
    daily_luck_window,
    luck_days,
    luck_months,
    luck_years,
)
from .personalization import (
    fetch_calibration_expression_hints,
    fetch_confirmed_yongsin_override,
    fetch_personal_inputs,
)

_BACKEND = Path(__file__).resolve().parents[4]
_DICTS = _BACKEND / "dictionaries"
_COMPILED_GRAPH = _BACKEND / "compiled" / "event_graph_v1.1.0.json"

_logger = logging.getLogger(__name__)


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


def _current_luck_month_detail(birth: BirthInput, today: date, timezone: str = "Asia/Seoul") -> str:
    """현재 절기월의 사람이 읽는 상세 — 간지·양력 절기 span·진행 상태(경과/남은 일수).

    LLM이 절기월 라벨(YYYY-MM)을 캘린더월로 오인해 '진행 중인 달'을 '다가오는 미래'로
    서술하는 것을 차단한다(2026-07-02 데굴님 지적: 소서 전 7/2는 여전히 甲午월='2026-06'인데
    풀이가 '다가오는 6월'로 서술). ReferenceFrame.this_luck_month_detail로 전달.

    Args:
        birth: 대상 출생 정보(절기월 라벨→간지 조회용).
        today: 기준일.
        timezone: 차트 타임존(절기 경계 산정 기준).

    Returns:
        상세 문자열(간지 조회 실패 시 빈 문자열 — 상세 없이 bare 라벨만 쓰이는 폴백).
    """
    label = _current_luck_month(today, timezone)
    ml = luck_months(birth, int(label[:4]))
    mp = next((p for p in ml if p.label == label), None)
    if mp is None:
        return ""
    sm_s, sm_e = _solar_month_range(label, timezone)
    total = (sm_e - sm_s).days + 1
    elapsed = (today - sm_s).days + 1
    remaining = (sm_e - today).days + 1  # 오늘 포함, 다음 절입 전일까지 남은 일수
    return (
        f"{label} = {mp.ganji}월(절기월). 양력 {sm_s.isoformat()}~{sm_e.isoformat()} 진행 중 — "
        f"오늘 {today.isoformat()}은 이 절기월 {elapsed}/{total}일차(남은 약 {remaining}일). "
        f"라벨의 '{label[5:7]}'월은 절입 시작 캘린더월이라 오늘 캘린더월({today.month}월)과 "
        f"다를 수 있다."
    )


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
# 지역 추천 오케스트레이터(P4-A 배선) — compiled 프로필·행정 registry 필요. 미빌드면 None.
_region_orchestrator: object | None = None
_region_orchestrator_init: bool = False
_COMPILED_REGION_PROFILES = _BACKEND / "compiled" / "region_element_profiles_v1.json"
_COMPILED_REGION_ADMIN = _BACKEND / "compiled" / "region_admin_units_v1.json"
_COMPILED_REGION_DIRECTIONAL = _BACKEND / "compiled" / "region_directional_summary_v1.json"

# 택일 목적으로 인정되는 이벤트(purpose_profiles 키) — 그 외는 이사로 폴백. 21키 기준(Phase 7).
_DATE_PURPOSES = DATE_PURPOSES
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
# 과거 회고 신호 — 있으면 미래지향 앵커링(default_period)을 적용하지 않는다.
# 과거형 어미('쉬었던/언제였을까' 등) 포함 — 미감지 시 과거 질문이 미래 창으로
# 클램프돼 '이전 데이터 미제공' 회피가 발생(2026-06-12 지적).
_PAST_KEYWORDS = (
    "작년",
    "재작년",
    "지난",
    "과거",
    "예전",
    "그때",
    "했었",
    "였었",
    "무슨 일",
    "뭐였",
    "어땠",
    "있었",
    "였을까",
    "었을까",
    "았을까",
    "였던",
    "었던",
    "았던",
    "였지",
    "었지",
)
# 미래지향 '언제 ~ㄹ까/들어올까/언제쯤' — open_when이어도 과거 회고가 아니라 미래 탐색이다.
# (open_when을 일괄 과거로 보던 결함: '이직 제안 언제 들어올까?'가 과거 10년 창으로 앵커링돼
#  이미 지난 달이 메인에 오르던 시점 오류 차단 — 2026-06-30 데굴님 지적.)
_FUTURE_WHEN_RE = re.compile(
    r"언제쯤|앞으로|향후|들어올까|들어오나|들어와|올까|올까요|올지|"
    r"될까|될지|할까|생길까|생길지|만날까|나올까|이뤄질까|가능할까|풀릴까|열릴까"
)

# 축약 과거형 어미 뒤 회고 표지 — '했을까/됐을 때/갔던' 류. '했'은 하+였 축약 음절이라
# _PAST_KEYWORDS의 '았을까' 부분 문자열에 안 걸린다(2026-07-21 데굴님 실로그: '2025년 몇월에
# 취직에 성공했을까?'가 미래 시제로 서술되던 결함). 종성 ㅆ을 유니코드 분해로 일반 판정한다.
_CONTRACTED_PAST_TAILS = ("을까", "을지", "을 때", "던")


def _has_contracted_past(question: str) -> bool:
    """음절 종성이 ㅆ(했/됐/갔/왔…)이고 곧바로 회고 표지가 이어지면 과거형으로 본다.

    '있'('있을까'=가능 의문)·'겠'(추측 선어말)은 종성이 ㅆ이어도 과거가 아니므로 제외.
    """
    for i, ch in enumerate(question):
        if ch in "있겠":
            continue
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172 and code % 28 == 20:  # 종성 인덱스 20 = ㅆ
            if question[i + 1 : i + 4].startswith(_CONTRACTED_PAST_TAILS):
                return True
    return False


def _question_time_direction(
    question: str,
    intent: IntentJson,
    state: ConversationState | None,
    today: date,
) -> bool:
    """질문의 시간 방향 판정 — True=과거 회고(retro).

    우선순위: ①창 전체가 오늘 이전인 절대창(구조 신호 — 문구와 무관, 2026-07-21 실로그:
    '2025년 몇월에 성공했을까'가 문구 매칭 실패로 미래 모드가 되던 결함) ②과거 문구
    (_PAST_KEYWORDS·축약 과거형) ③미래 문구 ④자체 신호 없는 open_when은 직전 방향 승계.
    """
    tr = intent.time_range
    if tr is not None and (tr.start or tr.end) and not tr.end_offset_days:
        end = tr.end or tr.start
        if end:
            end_m = end[:7] if len(end) >= 7 else f"{end}-12"
            if end_m < f"{today.year}-{today.month:02d}":
                return True
        # ①b 창 전체가 오늘 이후인 절대창 — 준비 완료 사실 나열('이미 계약도 끝냈고 잔금만
        # 남았는데')의 축약 과거형이 회고로 뒤집히지 않게 한다(2026-07-22 실로그: 9/30 명시
        # 미래 창 후속이 과거형 서술로 빠짐). 구조 신호가 문구 신호보다 우선(①과 대칭).
        start = tr.start
        if start:
            starts_future = (
                start[:10] > today.isoformat() if len(start) >= 10
                else start[:7] > f"{today.year}-{today.month:02d}"
            )
            if starts_future:
                return False
    if (
        intent.query_type is QueryType.EVENT_EXPLANATION
        or any(k in question for k in _PAST_KEYWORDS)
        or _has_contracted_past(question)
    ):
        return True
    if _FUTURE_WHEN_RE.search(question):
        return False
    if tr is not None and tr.type == "open_when":
        # 자체 방향 신호 없는 open_when(상속/단답) → 직전 방향 승계(기본 미래).
        return bool(state is not None and state.last_retro)
    return False


# 회고 질문 시제 강제 — is_retro여도 시제 지시가 없어 이벤트 후보·트리거류 미래 지향
# 디렉티브에 묻혀 과거 사건을 예측처럼 서술하던 결함 교정(2026-07-21 데굴님 실로그).
_RETRO_TENSE_DIRECTIVE = (
    "[회고 모드 — 질문 기간은 이미 지난 과거] 전체 답변을 과거 추정형('~였을 것으로 보여요', "
    "'~했을 가능성이 커요')으로만 서술할 것. '~될 것으로 보여요'·'~열릴 거예요'·'기대돼요' 같은 "
    "미래 예측·권고 표현 금지. 신호 데이터는 '그 시기에 그런 흐름이 있었다'는 확인·복원 용도로만 "
    "쓰고, 사용자가 묻지 않은 미래 조언을 덧붙이지 말 것. 마무리 확인 질문도 '실제로 그랬는지'를 "
    "묻는 형태로 할 것."
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
        # 공통 팩토리 — 채널 간 선정 모드가 갈리면 같은 명식·질문에서 대표 시점이
        # 달라진다(event_engine_config: chat mode == report mode).
        _scorer = build_event_engine_v2(_DICTS)
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
        CompositeLevel.DAY,
        CompositeLevel.MONTH,
        CompositeLevel.YEAR,
        CompositeLevel.NATAL,
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
            pillar = next((p for p in chart.luck_cycles.monthly_luck if p.label == start), None)
        else:
            pillar = None
        period = PeriodSpec(start=sm_start.isoformat(), end=sm_end.isoformat(), granularity="month")
        levels = _DAY_LEVELS
        label = start
    else:  # yearly
        year = int(start[:4])
        anchor = date(year, 7, 1)
        chart = calculate(birth.model_copy(update={"reference_date": anchor}))
        if chart.luck_cycles is not None:
            chart.luck_cycles.monthly_luck = luck_months(birth, year)
            pillar = next((p for p in chart.luck_cycles.yearly_luck if p.label == start), None)
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
            c for c in composites if c.level is not CompositeLevel.MONTH or c.period_key == start
        ]
    elif fortune_type == "daily" and day_solar_month is not None:
        # 일 질문 — MONTH 컨텍스트를 그 날이 속한 절기월 하나로 한정한다(양력 달이 아니라 절기월).
        # 안 그러면 모든 월 composite가 노출돼 LLM이 7/4를 양력 7월(乙未월)로 오인한다(2026-06-22).
        composites = [
            c
            for c in composites
            if c.level is not CompositeLevel.MONTH or c.period_key == day_solar_month
        ]
    # 절기월 안내(데굴님 제안) — 해당 월운(절기월)의 간지 + 양력 절기 범위를 함께 준다.
    # 월운은 절입 기준이라 양력 달과 어긋난다(예: 未월=7/7~8/6). '7월=을미월' 혼동 방지.
    solar_month_note = ""
    if fortune_type in ("daily", "monthly"):
        m_label = day_solar_month if fortune_type == "daily" else start
        m_comp = next(
            (c for c in composites if c.level is CompositeLevel.MONTH and c.period_key == m_label),
            None,
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
        period,
        composites,
        dictionaries_dir=_DICTS,
    )
    # 표현 제한 도메인(Phase 5b-2b) — parser Domain.value(str)만 전달(enum 비종속).
    domain_key = domain_to_expression_key(intent.domain.value)
    grounding = build_luck_grounding(chart, pillar, domain_key=domain_key)
    # P0(2026-07-27) — 운 스택(대운·세운·월운·해당 기간) 전체가 관여한 합의 구조화 의미.
    # 단일 pillar만 넘기면 세운 午와 일진 寅의 반합처럼 층간 결합이 통째로 빠진다.
    _TARGET_LEVEL = {
        "daily": CompositeLevel.DAY,
        "monthly": CompositeLevel.MONTH,
        "yearly": CompositeLevel.YEAR,
    }
    relation_semantics = _period_relation_semantics(
        chart, composites, _TARGET_LEVEL[fortune_type], start, pillar
    )
    # P1 계층형 grounding(2026-07-27) — ON이면 관계 렌더를 **이쪽으로 완전히 대체**한다.
    # 기존 build_luck_grounding의 형충회합 줄과 함께 내보내면 같은 관계가 두 표현으로
    # 들어가 LLM이 서로 다른 사실로 읽는다.
    hierarchy_lines: list[str] = []
    hierarchy_appendix: list[str] = []
    hierarchy = None
    if period_v2_config.PERIOD_HIERARCHY_ENABLED:
        stack_keys = {"year": start[:4]}
        if fortune_type == "daily" and day_solar_month:
            stack_keys["month"] = day_solar_month
        elif fortune_type == "monthly":
            stack_keys["month"] = start
        hierarchy = build_luck_hierarchy(
            composites, _TARGET_LEVEL[fortune_type].value, start,
            relation_semantics, stack_keys=stack_keys,
        )
        # P2 — 연·월·일 역할 요약을 관계 블록 **앞**에 둔다(배경 → 대상 순서).
        from saju_engines.event_scoring import favorability_map as _fav_map
        role_summary = build_period_role_summary(hierarchy, _fav_map(chart))
        hierarchy_lines = (
            render_period_role_summary(role_summary)
            + render_hierarchy_narrative(hierarchy)
        )
        hierarchy_appendix = render_hierarchy_appendix(hierarchy)
        # P3-b dual-run — V2 실패는 V2 결과만 폐기하고 V1 점수를 유지한다.
        # P1·P2 계층 설명은 그대로 남고, 사용자 요청은 정상 완료된다.
        # 범위 = 요청 스택 전체(대상 기간 + 상위 층위). stack_keys에는 상위만 있어
        # start(대상 기간)를 반드시 더해야 한다 — 빠지면 일진 신호가 통째로 누락된다.
        scope_keys = {*stack_keys.values(), start}
        scope = [c for c in composites if c.period_key in scope_keys]
        try:
            v2_scoring = build_v2_scoring(
                scope, hierarchy,
                enabled=period_v2_config.PILLAR_POLARITY_V2_ENABLED,
            )
        except V2ScoringError:
            _logger.exception("v2_scoring_failed period=%s — V1 점수 유지", start)
            v2_scoring = None
        _logger.info(
            "v2_scoring period=%s status=%s raw=%s dedup=%s removed=%s "
            "coverage_complete=%s unavailable=%s struct=%s conflict=%s mixed=%s "
            "invariants=%s",
            start,
            v2_scoring.activation_status.value if v2_scoring else "ERROR",
            getattr(v2_scoring, "raw_signal_count", 0),
            getattr(v2_scoring, "deduplicated_signal_count", 0),
            getattr(v2_scoring, "duplicate_removed_count", 0),
            v2_scoring.coverage.complete if v2_scoring else None,
            v2_scoring.coverage.unavailable_signal_count if v2_scoring else None,
            v2_scoring.coverage.structural_only_count if v2_scoring else None,
            v2_scoring.coverage.engine_conflict_count if v2_scoring else None,
            v2_scoring.coverage.mixed_unallocated_count if v2_scoring else None,
            v2_scoring.invariant_failure_codes if v2_scoring else None,
        )
        if v2_scoring is not None:
            # P0.5 shadow — 부정 방향 국소 캡 후보를 계량만 한다(상태 미변경).
            _shadow = {
                cat: st.shadow_status.value
                for cat, st in v2_scoring.slot_status.items()
                if st.shadow_status is not None
            }
            _capped = {
                cat: st.raw_status.value if st.raw_status else ""
                for cat, st in v2_scoring.slot_status.items()
                if st.guard_codes
            }
            if _shadow or _capped:
                _logger.info(
                    "slot_layer_gate period=%s capped=%s shadow_local_adverse=%s",
                    start, _capped, _shadow,
                )
        if v2_scoring is not None and v2_scoring.narrative_eligible:
            hierarchy_lines += render_v2_slot_status(v2_scoring)
    slots = [
        PeriodFortuneSlot(
            name=f.key.removeprefix("slot:"),
            score=f.score,
            summary=f.summary,
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
        # 계층형 ON이면 관계는 hierarchy_lines 하나만 쓴다(중복 삽입 금지).
        relation_lines=[] if hierarchy_lines else grounding["relation_lines"],
        sinsal_lines=grounding["sinsal_lines"],
        gongmang=grounding["gongmang"],
        slots=slots,
        relation_semantics=relation_semantics,
        hierarchy_lines=hierarchy_lines,
        hierarchy_appendix=hierarchy_appendix,
        luck_hierarchy=hierarchy,
    )


def _period_relation_semantics(chart, composites, target_level, target_key, pillar) -> list:
    """이번 기간의 운 스택이 관여한 합의 구조화 의미(P0).

    운 스택은 **대상 기간 composite 하나**의 `parent_context`(대운·세운·월운)와 그 기간
    간지로 한정한다 — 사전계산 결과를 그대로 쓰되(절대원칙 9), composite 목록 전체를
    훑으면 질문과 무관한 연도(예: 2024 甲辰·2031 辛亥)의 간지까지 스택에 섞여
    `甲己合`·`丙辛合` 같은 허위 관계가 만들어진다.

    Args:
        chart: 만세 결과.
        composites: 이 기간에 대해 빌드된 LuckComposite 목록.
        target_level: 대상 기간의 CompositeLevel(일=DAY / 월=MONTH / 연=YEAR).
        target_key: 대상 기간 키('2026-07-27' / '2026-07' / '2026').
        pillar: 해당 기간 LuckPillar(일진/월운/세운).

    Returns:
        운 관여 합의 RelationSemantics 목록. 두 플래그가 모두 꺼져 있으면 빈 리스트.
    """
    if not (period_v2_config.RELATION_SEMANTIC_PATCH_ENABLED
            or period_v2_config.PERIOD_HIERARCHY_ENABLED):
        return []
    target = next(
        (c for c in composites
         if c.level is target_level and c.period_key == target_key),
        None,
    )
    ganji_set: list[str] = [pillar.ganji]
    if target is not None:
        parent = target.parent_context
        ganji_set += [g for g in (parent.daewoon, parent.year, parent.month) if g]
    unique = [g for g in dict.fromkeys(ganji_set) if len(g) >= 2]
    semantics = collect_luck_relation_semantics(
        chart, [g[0] for g in unique], [g[1] for g in unique]
    )
    # 운 관계 상태 shadow (P1-b2) — 플래그 OFF 가 기본이고, ON 이어도 반환값에 손대지 않는다.
    # 실패해도 위 semantics 는 그대로 나간다.
    _build_relation_state_shadow(chart, target, target_key)
    return semantics


def _build_relation_state_shadow(chart, target, target_key: str) -> None:
    """운 관계 상태 체인을 shadow 로 조립한다. **반환값도 응답도 바꾸지 않는다.**

    플래그가 꺼져 있으면 wrapper 가 즉시 None 을 돌려주므로 노드 생성조차 하지 않는다.
    조립이 실패해도 예외를 밖으로 내보내지 않는다 — shadow 가 생산 요청을 실패시키면 안 된다.
    """
    if not should_build_relation_state_chain():
        return
    if chart.pillars is None or target is None:
        return
    # 지역 import — OFF 경로에서는 import 비용도 들지 않는다(모듈 상단 관례와 동일).
    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap

    from saju_engines.event_scoring import favorability_map

    parent = target.parent_context
    daewoon = parent.daewoon[1] if parent.daewoon and len(parent.daewoon) >= 2 else None
    sewoon = parent.year[1] if parent.year and len(parent.year) >= 2 else None
    pillars = chart.pillars
    natal = [
        (pos, getattr(pillars, pos).branch)
        for pos in ("year", "month", "day", "hour")
        if getattr(pillars, pos, None) is not None
    ]

    def _call(luck_branches=None):
        return resolve_branch_hap(
            pillars, favorability=favorability_map(chart),
            luck_branches=list(luck_branches or []),
        )

    relation_state_chain_shadow(
        natal_branches=natal, daewoon_branch=daewoon, sewoon_branch=sewoon,
        resolve_branch_hap=_call,
        period_keys={"natal": "natal", "daewoon": parent.daewoon or "daewoon",
                     "sewoon": target_key},
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
            update={
                "luck_cycles": chart.luck_cycles.model_copy(update={"daily_luck": window_daily})
            }
        )
    composites = CompositeBuilder(_DICTS).build(
        chart,
        "chat",
        "1.0.0",
        f"{today.isoformat()}T00:00:00+00:00",
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
        purpose,
        composites,
        start_iso,
        end_iso,
        yongsin_element=yongsin,
        reality_constraints=constraints.reality_constraints or None,
        include_hour_fit=is_windfall,
        top_n=8,
        wealth_element=wealth_element,
        favorability=favorability,
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
        if result.candidates and result.candidates[0].hour_fits
        else []
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
        _relocation_reason_lines(composites, start_iso[:4], start_iso[:7]) if is_relocation else []
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
    composites: list,
    year_key: str,
    month_key: str | None,
) -> list[str]:
    """이사 십성 이유분류 라벨 줄 — 천간=명분(이유)/지지=현장(집·지역) (R2, 단정 금지).

    질의 기간의 세운(대표)·월운(발동)·대운(장기 배경) 천간 십성으로 '왜·어떤 집' 유형을
    분류한다(RelocationResolver.classify_reasons 위임). 점수·날짜 미개입(절대원칙 1·12).
    """
    from saju_engines.relocation import RelocationResolver

    profiles = RelocationResolver(_DICTS).classify_reasons(composites, year_key, month_key)
    return [
        f"{p.source} {p.ten_god} → {p.type}: 이유 {'·'.join(p.move_reason)} / "
        f"집·지역 {'·'.join(p.property_tendency)} / "
        f"리스크({p.risk_level}) {'·'.join(p.risk)}"
        for p in profiles
    ]


def _relocation_reason_context(
    birth: BirthInput,
    intent: IntentJson,
    today: date,
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
            chart, "chat", "1.0.0", f"{today.isoformat()}T00:00:00+00:00"
        )
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


_GANJI_CH = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
# 중첩 병기: '갑오(甲午(갑오))'(한글 외곽) / '甲午(갑오(甲午))'(한자 외곽).
_GLOSS_NEST_KO = re.compile(r"([가-힣]{2})\(([" + _GANJI_CH + r"]{2})\(\1\)\)")
_GLOSS_NEST_CH = re.compile(r"([" + _GANJI_CH + r"]{2})\(([가-힣]{2})\(\1\)\)")
# 중복 괄호: '己卯(기묘)(기묘)' / '기묘(己卯)(己卯)'.
_GLOSS_DUP_KO = re.compile(r"([" + _GANJI_CH + r"]{2})\(([가-힣]{2})\)\(\2\)")
_GLOSS_DUP_CH = re.compile(r"([가-힣]{2})\(([" + _GANJI_CH + r"]{2})\)\(\2\)")


def _normalize_ganji_gloss(text: str) -> str:
    """간지 한글 병기의 중첩·중복을 한 번으로 정규화한다(LLM 과글로싱 보정).

    엔진 입력은 순수 한자 간지(甲午·己卯)라 '갑오(甲午(갑오))'·'己卯(기묘)(기묘)' 같은 이중 병기는
    LLM 출력 아티팩트다(2026-06-26 데굴님 지적). 외곽이 한글이면 '갑오(甲午)', 한자면 '甲午(기묘)'로
    collapse하고, 중첩이 여러 겹이어도 수렴할 때까지 반복 적용한다. 점수·간지 값은 바꾸지 않는다.
    """
    prev: str | None = None
    out = text
    while prev != out:
        prev = out
        out = _GLOSS_NEST_KO.sub(r"\1(\2)", out)
        out = _GLOSS_NEST_CH.sub(r"\1(\2)", out)
        out = _GLOSS_DUP_KO.sub(r"\1(\2)", out)
        out = _GLOSS_DUP_CH.sub(r"\1(\2)", out)
    return out


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
    birth: BirthInput,
    intent: IntentJson,
    today: date,
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


def _get_region_orchestrator() -> object | None:
    """지역 추천 오케스트레이터 lazy 싱글턴(P4-A). compiled 미빌드 시 None(graceful)."""
    global _region_orchestrator, _region_orchestrator_init
    if _region_orchestrator_init:
        return _region_orchestrator
    _region_orchestrator_init = True
    if not (_COMPILED_REGION_PROFILES.exists() and _COMPILED_REGION_ADMIN.exists()):
        return None
    from saju_engines.region_element_engine import RegionElementEngine
    from saju_engines.region_geo_stubs import DirectionalFeatureAdapter
    from saju_engines.region_recommendation_orchestrator import (
        RegionRecommendationOrchestrator,
    )

    engine = RegionElementEngine(_DICTS, _COMPILED_REGION_PROFILES, _COMPILED_REGION_ADMIN)
    directional = DirectionalFeatureAdapter(
        _COMPILED_REGION_DIRECTIONAL if _COMPILED_REGION_DIRECTIONAL.exists() else None
    )
    _region_orchestrator = RegionRecommendationOrchestrator(engine, directional)
    return _region_orchestrator


def _region_recommendation_context(
    birth: BirthInput,
    intent: IntentJson,
    today: date,
) -> list[str]:
    """이사 '지역 추천'(목적지 미지정/시도·수도권 scope)을 시군구 후보로 surface(P4-A 배선).

    특정 시군구 목적지는 _relocation_region_context가 단건 궁합으로 다루므로 여기선 제외한다.
    엔진이 용희기구신×지역오행으로 매칭한 결과(점수·근거·방위)만 LLM에 싣고, LLM은 계산 없이
    '유리/보완성/기류'로 설명한다(절대원칙 1·2·3). 지형 GIS 미반영 1차 추정 — 단정 금지.
    """
    from saju_engines.region_recommendation_orchestrator import resolve_intent_mode
    from saju_shared_types.region_element import RegionLevel, RegionResolution

    orch = _get_region_orchestrator()
    if orch is None:
        return []
    try:
        phrase = intent.constraints.target_region
        base = intent.constraints.location_base
        scope: str | None = None
        if phrase:
            code, _amb = orch._engine.resolve_region(phrase, RegionLevel.SIG)  # type: ignore[attr-defined]
            if code is not None:
                return []  # 특정 시군구 → 단건 궁합 경로가 담당
            scope = phrase  # 시도·수도권 등 범위로 해석(미해소 시 엔진이 전국 폴백+노트)
        from saju_engines.event_scoring import favorability_map

        chart = calculate(birth.model_copy(update={"reference_date": today}))
        fav = favorability_map(chart)
        if not fav:
            return []
        role_key = {"용신": "yongsin", "희신": "huisin", "기신": "gisin", "구신": "gusin"}
        roles: dict[str, list[str]] = {"yongsin": [], "huisin": [], "gisin": [], "gusin": []}
        for element, ro in fav.items():
            key = role_key.get(ro)
            if key:
                roles[key].append(element)
        if not roles["yongsin"]:
            return []
        # 계산은 읍면동(emd) 단위, 표시는 시군구 grouping(요구사항 1: 동·읍 판별 유지).
        query = orch.build_query(  # type: ignore[attr-defined]
            intent_mode=resolve_intent_mode("이사"),
            roles=roles,
            base_location=base,
            candidate_scope=scope,
            resolution=RegionResolution.EUP_MYEON_DONG,
            top_n=20,
        )
        payload = orch.recommend_payload(query)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — 지역 추천 실패가 일반 풀이를 막지 않도록
        return []
    surface = payload.get("surface", [])
    regions = payload.get("regions", [])
    if not surface:
        return []
    by_code = {r["region_code"]: r for r in regions}
    out = [
        "[지역 오행 추천(참고) — 내 용희기구신 × 지역 오행 매칭. 읍면동 단위로 계산하고 시군구로 "
        "묶어 표시. 산·하천·해안·DEM 원천 미연결 1차 추정이라 '유리/보완성/기류'로만 녹이고 단정 "
        "금지(실거주 만족은 생활 여건이 좌우). 데이터 미연결 상태에선 '북쪽에 산/배산임수' 류 실제 "
        "지형 주장 금지]"
    ]
    for i, g in enumerate(surface[:5], 1):
        emds = g["top_emd_candidates"]
        rep = by_code.get(emds[0]["region_code"], {}) if emds else {}
        parts = [f"{i}. {g['sigungu_full_name']} 적합 {g['match_score']}"]
        pos = "·".join(
            f"{f['element']}({f['role']})" for f in rep.get("fit_summary", {}).get("positive", [])
        )
        neg = "·".join(
            f"{f['element']}({f['role']})" for f in rep.get("fit_summary", {}).get("negative", [])
        )
        if pos:
            parts.append(f"유리 {pos}")
        if neg:
            parts.append(f"주의 {neg}")
        if rep.get("direction"):
            parts.append(f"방위 {rep['direction']} {rep['direction_fit']}")
        emd_names = ", ".join(c["full_name_ko"].split()[-1] for c in emds[:3])
        if emd_names:
            parts.append(f"세부 {emd_names}")
        out.append(" / ".join(parts))
    if not payload.get("terrain_data_available", False):
        out.append("(지형·풍수 원천 미연결 — 확정도 낮음, 방위·생활 여건과 함께 보세요)")
    return out


# 지역 오행 사실 질문('창원 성산구의 오행은?') — 시군구/지명 + '오행'. 사주·시점 무관 단순 조회.
_REGION_ELEMENT_Q_RE = re.compile(
    r"([가-힣]{2,}\s+[가-힣]{1,}(?:특별자치시|시|군|구)|[가-힣]{2,}(?:특별자치시|시|군|구))"
    r"\s*(?:의|은|는|이|가)?\s*오행"
)
_ELEMENT_KO = {"木": "목(木)", "火": "화(火)", "土": "토(土)", "金": "금(金)", "水": "수(水)"}


def _region_element_fact(question: str) -> str | None:
    """'X 지역의 오행은?' 사실 질문에 지역 엔진 프로파일로 직접 답한다(LLM 미호출).

    지역 오행은 고정 사전계산값이라 사주·시점과 무관한 단순 조회다 — too_broad 안내로 빠지지 않게
    별도 사실 라우트로 처리한다. compiled 미빌드·미등재면 None(일반 흐름), 모호 지명이면 확인 질문.
    """
    m = _REGION_ELEMENT_Q_RE.search(question)
    if m is None:
        return None
    orch = _get_region_orchestrator()
    if orch is None:
        return None
    name = m.group(1).strip()
    engine = orch._engine  # type: ignore[attr-defined]
    code, ambiguous = engine.resolve_region(name)
    if code is None:
        if ambiguous:
            opts = ", ".join(ambiguous[:4])
            return f"'{name}'이 어느 지역인지 모호해요 — 혹시 {opts} 중 어디일까요?"
        return None  # 미등재 → 일반 흐름으로 폴백
    profile = engine.get_profile(code)
    if profile is None or not profile.dominant_elements:
        return None
    doms = [_ELEMENT_KO.get(e, e) for e in profile.dominant_elements[:2]]
    full = profile.full_name or name
    body = f"{full}의 지역 오행은 {doms[0]} 기운이 가장 강해요"
    if len(doms) > 1:
        body += f". 그다음으로 {doms[1]} 기운이 받쳐 주고요"
    body += (
        ". 다만 산·하천·해안 등 지형 GIS 원천이 아직 연결되지 않은 1차 추정값이라 참고로만 봐 "
        "주세요 — 실제 거주 만족은 생활 여건이 더 크게 좌우해요."
    )
    return body


# 질문 도메인 → Topic Builder 모듈(채팅 배선, 옵션1). relocation은 별도 지역/이사 경로가 담당.
_DOMAIN_TOPIC_MODULE = {
    Domain.CAREER: "M07",
    Domain.WEALTH: "M09",
    Domain.HEALTH: "M11",
    Domain.EDUCATION: "M12",
    Domain.RELATIONSHIP: "M01",
}


def _topic_module_context(
    birth: BirthInput,
    intent: IntentJson,
    today: date,
    future_floor: str | None = None,
) -> list[str]:
    """질문 도메인에 해당하는 Topic Builder 모듈을 실행해 확정 신호+정책 톤을 구조 블록에 싣는다.

    채팅 토픽 질문(직업·재물·건강·시험·연애)에서 topic_builder를 실제로 소비한다(옵션1). findings는
    점수 확정값, 모듈 특화 정책 톤(절대원칙 8 가드)을 함께 주입. 비토픽·실패는 graceful(빈 줄).

    future_floor('YYYY-MM')가 주어지면 그 달 이전의 월 findings를 버린다 — 미래지향 질문('언제
    들어올까')에서 토픽 참고 신호가 이미 지난 달을 메인처럼 노출하던 시점 오류 차단(2026-06-30).
    """
    module_id = _DOMAIN_TOPIC_MODULE.get(intent.domain)
    if module_id is None:
        return []
    try:
        tr = intent.time_range
        start = tr.start[:4] if tr and tr.start else str(today.year)
        end = tr.end[:4] if tr and tr.end else str(today.year + 5)
        chart = calculate(birth.model_copy(update={"reference_date": today}))
        composites = CompositeBuilder(_DICTS).build(
            chart,
            "chat",
            "1.0.0",
            f"{today.isoformat()}T00:00:00+00:00",
            levels={CompositeLevel.YEAR, CompositeLevel.MONTH},
        )
        period = PeriodSpec(start=start, end=end, granularity="year")
        extras: dict = {}
        if module_id in ("M03", "M04", "M05", "M06"):
            tg = getattr(chart.force_analysis, "ten_gods", None)
            if not (tg and tg.distribution):
                return []
            extras["natal_ten_god_dist"] = dict(tg.distribution)
        ctx = build_topic_context(module_id, intent.subjects, period, composites, **extras)
    except Exception:  # noqa: BLE001 — 토픽 모듈 실패가 풀이를 막지 않도록(규칙11)
        return []
    findings = ctx.findings
    if future_floor:
        # 월 단위(YYYY-MM) findings 중 현재 달 이전은 제외(연 단위 키는 유지). 미래 질문 시점 정합.
        findings = [
            f
            for f in findings
            if not (
                f.period_key
                and re.fullmatch(r"\d{4}-\d{2}", f.period_key)
                and f.period_key < future_floor
            )
        ]
    if not findings:
        return []
    out = [
        f"[{module_id}·{_TOPIC_MODULES[module_id]} 토픽 신호(참고) — 엔진 확정 점수·근거. "
        "새 수치 생성 금지, 단정 금지]"
    ]
    out += [f"- {f.summary} (점수 {f.score})" for f in findings[:3]]
    module_notes = ctx.style_rules.tone_notes[1:]
    if module_notes:
        out.append("표현 지침(정책): " + " / ".join(module_notes))
    return out


def _subject_composites_yongsin(
    b: BirthInput, req_start: date, scan_end: date, today: date, label: str
) -> tuple[list, str]:
    """한 대상의 [req_start, scan_end] 윈도우 LuckComposite + 용신 오행을 산출한다."""
    from saju_engines.event_scoring import favorability_map

    chart = calculate(b.model_copy(update={"reference_date": req_start}))
    if chart.luck_cycles is not None:
        window_daily = daily_luck_window(chart, req_start, scan_end)
        chart = chart.model_copy(
            update={
                "luck_cycles": chart.luck_cycles.model_copy(update={"daily_luck": window_daily})
            }
        )
    comps = CompositeBuilder(_DICTS).build(
        chart,
        label,
        "1.0.0",
        f"{today.isoformat()}T00:00:00+00:00",
    )
    fav = favorability_map(chart)
    yongsin = next((el for el, role in fav.items() if role == "용신"), None)
    return comps, yongsin or "土"


def _relocation_group_block(
    birth: BirthInput,
    partner_birth: BirthInput,
    intent: IntentJson,
    today: date,
    self_label: str,
    partner_label: str,
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

    self_comps, self_y = _subject_composites_yongsin(birth, req_start, scan_end, today, self_label)
    partner_comps, partner_y = _subject_composites_yongsin(
        partner_birth, req_start, scan_end, today, partner_label
    )

    constraints = intent.constraints
    query = RelocationQuery(
        group_subjects=[
            SubjectRef(kind=SubjectKind.SELF, label=self_label),
            SubjectRef(kind=SubjectKind.COMPANION, label=partner_label),
        ],
        period=RelocationPeriod(start=req_start.strftime("%Y-%m"), end=scan_end.strftime("%Y-%m")),
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
            "구성원 이동운이 엇갈리는 달: " + ", ".join(result.group_summary.conflicts)
        )
    # 방위 적합(상위) — move_dates[0]의 분리 산출값.
    directions = [
        {"direction": d, "fit": f}
        for d, f in sorted(result.move_dates[0].direction_fit.items(), key=lambda x: -x[1])
    ]
    # 이사 십성 이유분류 — 의사결정 주체(첫 대상=호주, 대상 우선 원칙 7)의 운으로 분류한다.
    relocation_reasons = _relocation_reason_lines(
        self_comps, req_start.strftime("%Y"), req_start.strftime("%Y-%m")
    )
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
    " 첫 문장은 이번 질문에 대한 답(결론·방향)으로 바로 시작한다 — '회원님은 ~한 사주/일간/성향'"
    " 류 명식 공통 묘사로 답변을 열지 말 것(답변마다 같은 자기소개가 반복되는 인상 방지). 명식"
    " 언급이 필요하면 답의 근거로 본문 중간에 짧게 녹인다."
    " 입력에 없는 점수·확률·백분율 수치('98점'·'확률 70%' 류)를 만들어 말하지 않는다 — 강도는"
    " 제공된 표현('신호가 매우 강합니다' 등) 그대로 쓴다. 사용자가 점수 환산을 명시적으로 요청한"
    " 경우에만 상대 강도를 어림 환산하되 정밀 수치가 아니라 감각적 환산임을 밝힌다(2026-07-14"
    " 수치 환각 가드)."
)

# 스레드 내 서두 반복 금지(2026-07-06 테스터 지적) — 직전 답변의 실제 첫 문장을 제시해 같은
# 패턴 서두·판박이 전개 반복을 막는다(리포트 섹션의 동적 서두 차단과 동일 원리, 서술 전용).
_THREAD_OPENING_BAN = (
    "[서두 반복 금지 — 직전 답변의 첫 문장] “{opening}” — 이번 답변을 이 문장과 같은 "
    "패턴·유사 표현으로 시작하지 말 것. 전개 구성도 직전 답변을 그대로 본뜨지 말고, 이번 질문 "
    "고유의 내용으로 서두를 열 것."
)

# 직전 답변의 '제안' 표지 — '그래 봐줘' 수락 시 그 제안을 이어가도록 추출하는 단서.
_OFFER_MARKERS = (
    "봐드릴게요",
    "봐드려요",
    "봐 드릴",
    "풀어드릴",
    "짚어드릴",
    "알려드릴",
    "정리해드릴",
    "보고 싶으세요",
    "보고 싶은",
    "말씀해 주시면",
    "말씀해주시면",
    "말씀 주시면",
    "원하시면",
    "이어서",
    "더 자세히",
    "어느 쪽",
    "어느 흐름",
    "중 어느",
    # 되물음형 마감(2026-07-22) — 페르소나가 '…인지 궁금해요'로 답을 끝내는 경우도 offer로
    # 취급해, 사용자의 서술형 답변이 offer-answer 링킹으로 직전 스레드에 이어지게 한다
    # (실로그: '제품형인지 서비스형인지 궁금해요' 뒤 문장형 답변이 NEW→too_broad로 단절).
    "궁금해요",
    "궁금합니다",
    "알려주시면",
    "알려 주시면",
)
# 답변 말미 고지 줄(`※ …`) — offer 추출 시 tail 계산에서 제외한다.
_NOTICE_LINE_RE = re.compile(r"^\s*[※*]\s*")

# 되물음에 대한 답변일 때의 우선 지시(2026-08-04) — 수락('그래/봐줘')이 아니라 네가 던진
# 질문에 사용자가 내용으로 답한 경우다. 수락용 문구를 그대로 쓰면 LLM 이 '제안 수락'으로
# 오해해 사용자의 답 내용을 버리므로 분리한다.
_OFFER_ANSWER_DIRECTIVE = (
    "[중요·되물음 답변 — 다른 표기보다 우선 적용]\n"
    "직전 답변 끝에서 네가 사용자에게 질문했고, 이번 발화는 그 질문에 대한 답이다. 새 질문으로 "
    "취급하거나 범위를 다시 좁혀 달라고 되묻지 말 것. 사용자의 답을 전제로 받아들여 직전 "
    "주제·시점·대상을 그대로 이어 풀어라. 네가 직전에 던진 질문은 다음과 같다: 「{offer}」"
)
# 동의+이어보기('그래 봐줘')일 때, 직전 답변 끝에 제시한 제안을 이어 답하라는 우선 지시.
_OFFER_CONTINUE_DIRECTIVE = (
    "[중요·이어보기 — 다른 표기보다 우선 적용]\n"
    "사용자가 짧은 수락('그래/봐줘')으로 직전 답변의 제안을 받아들였다. 직전 답변 끝에서 네가 먼저 "
    "제안한 바로 그 갈래를 이번 답의 중심으로 곧장 이어서 풀어라 — 같은 분야·맥락을 유지하고, 일반 "
    "총운이나 다른 주제로 새로 시작하지 말 것. 네가 직전에 제안한 내용은 다음과 같다: 「{offer}」"
)


def _extract_offer(answer: str) -> str:
    """직전 답변 끝의 제안·되물음 문장을 뽑는다(없으면 '').

    페르소나 규칙상 답변 끝에 후속 제안/질문을 붙이므로 마지막 1~2문장에서 제안 표지가 있는
    부분만 취한다(토큰 가드 300자). 제안이 없으면 빈 문자열 → 이어보기 지시 미적용.

    **질문형 마감**(2026-08-04 실로그): 마커 목록은 제안 어구('짚어드릴까요'·'궁금해요')만
    담고 있어, 페르소나가 사용자에게 직접 묻고 끝낸 경우('…절대 양보할 수 없는 한 가지는
    무엇인가요?')를 하나도 잡지 못했다. 그 결과 last_offer 가 비고 → offer-answer 링킹이
    통째로 죽어 사용자의 답('역시 외모지')이 NEW 로 끊겨 "질문 범위가 넓어요"로 바운스됐다.
    마커를 늘리는 대신 **마지막 문장이 물음표로 끝나면 대기 질문으로 인정**한다.

    - '마지막 문장'으로 한정하는 이유: tail 2문장 전체에 적용하면 본문 중간 수사의문문
      ('이 시기가 정말 좋을까요? 결론적으로는 …')까지 제안으로 잡힌다.
    - 답변 말미의 고지 줄(`※ 관계 신호는 시험(beta) 관측치예요`)은 tail 계산에서 제외한다.
      고지가 붙으면 실제 질문이 마지막 문장 밖으로 밀려나기 때문이다.
    """
    if not answer:
        return ""
    body = "\n".join(
        line for line in answer.strip().splitlines() if not _NOTICE_LINE_RE.match(line)
    )
    sents = [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+", body.strip()) if s.strip()]
    if not sents:
        return ""
    tail = sents[-2:] if len(sents) >= 2 else sents
    picked = [s for s in tail if any(m in s for m in _OFFER_MARKERS)]
    if sents[-1].endswith("?") and sents[-1] not in picked:
        picked.append(sents[-1])
    return " ".join(picked)[:300].strip()


def _offer_is_question(offer: str) -> bool:
    """추출된 offer 가 사용자에게 던진 질문인가(수락형 제안과 구분)."""
    return offer.rstrip().endswith("?")


def update_thread_offer(
    thread_id: str, answer: str, store: ConversationStore | None = None
) -> None:
    """백그라운드 생성 완료 후 스레드 last_offer 갱신 — 비동기 경로 offer-slot 링킹 소생.

    베타(로그인+스레드) 경로는 prep(dry-run)이 상태를 저장한 뒤 답변을 백그라운드에서
    생성하므로, 동기 경로 전용이던 last_offer 갱신이 한 번도 실행되지 않아 offer-slot
    후속 링킹('…짚어드릴까요?' 뒤 짧은 되물음)이 죽은 규칙이었다(2026-07-21 데굴님 실로그:
    '12개월 내에는 없어?'가 NEW→too_broad). 동기 경로와 동일 계약: 비offer·실패 답변이면
    ''(자동 만료). 사용자가 답변 생성 중 새 턴을 보내는 드문 경합에선 늦게 끝난 쪽이
    남지만, 폴링 UI 특성상 실사용 영향은 무시 가능. 로드/저장 실패는 무해(링킹만 비활성).
    """
    try:
        store = store or ConversationStore()
        state = store.load(thread_id)
        if state is None:
            return
        state.last_offer = _extract_offer(answer)
        store.save(state)
    except Exception:  # noqa: BLE001 — offer 갱신 실패가 답변 영속을 막으면 안 된다
        _logger.exception("last_offer 갱신 실패 — offer-slot 링킹만 비활성 thread=%s", thread_id)


# 상황 제약 — 질문 맥락으로 형제 사건을 결정적으로 좁힌다. 묻힌 일반 안내로는 thinking LOW
# LLM이 다단계 추론(무직→이직 불가→이사)을 못 하므로, 감지 시 우선순위 높은 명시 지시를
# 프롬프트 말미에 주입한다(2026-06-14: '2025-08 백수인데 이직으로 단정' 오류 차단).
_UNEMPLOYED_KEYS = (
    "백수",
    "무직",
    "실직",
    "공백기",
    "재취업",
    "구직",
    "쉬고 있",
    "쉬는 중",
    "놀고 있",
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
    "골라 총평하라. 마무리 질문을 따로 더 만들지 말고, 시스템 지시의 마지막 마무리 질문 "
    "하나의 소재를 '어느 해를 더 자세히 보고 싶은지'로 삼아 — 사용자가 특정 연도를 "
    "지정하면 그때 그 해의 월별 상세를 풀어주겠다고 안내하라."
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

#: 기준 시점 대비 날짜 관계를 한국어로. 어휘는 파서 사전(`time_parser._DAY_WORDS`)을
#: 역인덱스로 재사용한다 — 같은 말이 파싱 쪽과 서술 쪽에서 갈라지지 않게 한다.
_DAY_OFFSET_LABEL: dict[int, str] = {
    **{v: k for k, v in _TP_DAY_WORDS.items()}, -1: "어제", -2: "그제",
}


def _relative_day_label(target: date, today: date) -> str:
    """대상 날짜가 오늘 기준 언제인지 — '오늘'·'내일'·'모레'·'5일 뒤'·'3일 전'.

    LLM 이 날짜만 보고 그 날을 '오늘'로 부르던 결함(2026-08-06)의 대응이다. 지칭을
    계산으로 확정해 넘기고, 서술은 그 말을 그대로 쓰게 한다.
    """
    delta = (target - today).days
    if delta in _DAY_OFFSET_LABEL:
        return _DAY_OFFSET_LABEL[delta]
    return f"{abs(delta)}일 {'뒤' if delta > 0 else '전'}"


# 특정일(단일 날짜) 질문 — 당일 중심 상세 서술 강제(2026-07-22 테스터 신고: '9/30 이사
# 주의점'에 월·연 기간 기운 서술이 답을 채우고, 당일 지침은 두루뭉술하게 흐려지던 결함).
# 서술 전용 — 위 [해당 일 운세] 블록(엔진 계산값)이 함께 주입된다.
#
# 블록명은 실제 헤더와 같아야 한다(2026-08-06). 예전에는 이 문구가 `[해당 일 일운]` 을
# 가리켰는데 그런 헤더는 어디에도 없었다 — 끊어진 참조였다.
#
# 기준 시점 대비 관계({relative})를 함께 준다. 날짜만 주면 LLM 이 그 날을 '오늘'로
# 부르는 일이 잦았다(실측: '내일' 질문 17건 중 5건이 답변에서 '오늘'로 지칭).
_SINGLE_DAY_FOCUS_DIRECTIVE = (
    "[중요·특정일 질문 — 다른 표기보다 우선 적용]\n"
    "사용자가 특정한 '그 날'({date} = 기준 시점 대비 {relative})을 물었다. 그 날을 "
    "지칭할 때 이 관계를 그대로 쓰고, 오늘이 아닌 날을 '오늘'이라고 부르지 마라. "
    "답의 중심은 그 날이다: 위 [해당 일 운세] "
    "블록의 간지·길흉·십성을 1차 근거로, 그 날 실행할 행동 지침을 구체적 단위(계약·서류 "
    "확인, 금전 지출, 이동 동선·일정 관리, 컨디션·감정 관리 등)로 정리하라. 월·연 단위 "
    "기운 서술은 배경 설명 한두 줄로만 제한하고, 질문받지 않은 다른 기간의 흐름을 늘어놓지 "
    "말 것 — 질문 창 밖의 다른 해 흐름(내년 용신운 등)은 위로·전망용으로도 언급 금지. "
    "제공된 데이터에 없는 간지 상호작용(합·충·형 성립 여부)을 임의로 계산해 "
    "서술하는 것은 금지 — 근거 블록에 있는 신호만 쓰라.{solar_month_note}"
)
# 기간×과업 점검(2026-07-22 테스터 요청 형식 — "8~9월 인테리어·대출 진행 중 문제점 체크").
# 과업 명사 + 점검 질문 + 명시 창이면 과업별 소제목 구조를 강제한다(서술 전용).
_TASK_NOUNS = ("대출", "인테리어", "공사", "계약", "잔금", "입주", "서류", "이직 준비", "이사 준비")
_RISK_CHECK_RE = re.compile(r"주의|조심|문제|체크|점검|리스크|잘\s*진행|챙겨야|확인해야")
# 질문 속 월 구간 표현('8~9월'·'8월과 9월'·'8월부터 9월') — 확정 일정 날짜(9/30)가 단일일로
# 파싱돼도 과업 점검 창은 이 구간이다(2026-07-22: '9/30 이사 결정, 8~9월 대출·인테리어 주의점'
# 이 특정일 경로에 흡수돼 과업 점검 구조가 안 나오던 결함).
_MONTH_SPAN_RE = re.compile(
    r"(\d{1,2})\s*(?:~|∼|-)\s*(\d{1,2})\s*월"
    r"|(\d{1,2})\s*월\s*(?:과|부터|에서|하고|,)\s*(\d{1,2})\s*월"
)
_TASK_RISK_CHECK_DIRECTIVE = (
    "[중요·기간 과업 점검 — 다른 표기보다 우선 적용]\n"
    "사용자가 특정 기간({start}~{end}) 동안 진행할 과업({tasks})의 점검을 요청했다. 답을 "
    "과업별 소제목으로 나눠 구성하라: 각 과업마다 ①그 과업이 걸린 절기월의 엔진 신호(제공 "
    "데이터만) ②일어날 수 있는 구체적 문제 ③실무 체크포인트(서류·일정·비용 확인 단위)를 "
    "짧게 제시한다. 질문 창 밖의 다른 해·다른 달 흐름은 위로·전망용으로도 언급하지 말고, "
    "과업과 무관한 일반 운세 서술로 채우지 말 것. 서술할 때 네 층위를 구분하라: 사용자가 "
    "밝힌 사실 / 엔진이 산출한 운 신호 / 일반 절차상 점검 항목 / 아직 모르는 정보. 진행 "
    "단계가 확인되지 않은 과업은 단정하지 말고 '신청 전이라면 ~을, 이미 진행 중이라면 ~을 "
    "확인하라'처럼 단계 분기로 안내할 것."
)

# 특정일의 절기월 앵커 — 질문일이 양력 달과 다른 절기월에 속할 때만 붙는다(2026-07-22
# 데굴님 지적 재발: 7/4는 소서(7/7) 전이라 甲午월(라벨 2026-06) 소속인데 '7월 운'으로 서술).
_SINGLE_DAY_SOLAR_MONTH_NOTE = (
    " 그 날이 속한 절기월은 {ganji}월(라벨 {label})이다 — 양력 {cal_month}월이지만 절기 "
    "경계상 {ganji}월 기운이 적용된다. 월 기운은 반드시 이 절기월 기준으로 서술하고, 다른 "
    "절기월(그 다음 달 등)의 기운을 그 날에 적용하거나 '양력 달 이름 운세'로 뭉뚱그리지 말 것."
)

# 부부 공동 이사 질문 — 세대주(호주)가 누구인지에 따라 기준 명식이 달라지므로 두 갈래 분리
# 풀이를 강제한다(2026-07-22 데굴님 지시). 서술 전용 — 점수·판정·엔진 경로 불변. 배우자
# 명식은 [대상별 명식] 블록(pairwise)의 엔진 계산값만 근거로 하며, 블록 밖 간지 관계를 LLM이
# 계산하는 것은 금지(절대원칙 1·2 — fail-closed 안내로 대체).
_RELOCATION_HOJU_SPLIT_DIRECTIVE = (
    "[중요·이사 세대주(호주) 분리 풀이 — 다른 표기보다 우선 적용]\n"
    "이사·입주 판단은 전통적으로 세대주(호주) 사주를 중심으로 본다. 이 대화에서는 누가 "
    "세대주인지 확인되지 않았으므로 답을 반드시 두 갈래로 나눠 각각 풀이하라: "
    "① '{self_label}'이(가) 세대주인 경우 — 본문의 본인 기준 엔진 분석(시기 신호·상호작용·"
    "용신 역할)을 근거로. ② '{companion_label}'이(가) 세대주인 경우 — [대상별 명식] 블록의 "
    "'{companion_label}' 명식 구조와 현재 대운·세운 정보만 근거로 서술하되, 그 블록에 없는 "
    "간지 관계·월별 신호를 임의로 계산하거나 지어내지 말 것. 월 단위 정밀 신호가 필요하면 "
    "'{companion_label} 기준의 상세 시기 풀이는 그분 사주로 별도 확인이 필요하다'고 안내하라. "
    "두 갈래의 결론이 다르면 그 차이를 명확히 밝히고, 공통 주의점(계약·문서·일정·지출 관리)은 "
    "묶어서 한 번에 제시하라. 누가 세대주인지 추측하거나 단정하지 말 것."
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
    "로또",
    "복권",
    "연금복권",
    "주식",
    "코인",
    "비트코인",
    "펀드",
    "청약",
    "경마",
    "토토",
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
        "windfall",
        "wealth_change",
    )
    return wealth_ctx and any(k in question for k in _LIFESTYLE_WINDFALL_KEYS)


# 사고수(事故數) 해석 지식팩(2026-07-23 데굴님 제공 강의 자료 증류) — 사고·안전 질문에서
# 답이 건강 일반론·재물 잡탕으로 흩어지지 않고 '사고'라는 주제 축으로 모이게 한다.
# 원자료의 살(煞)·귀신·조상 서사는 서비스 정책상 배제하고, 명리 신호 축 4개
# (이동 역마 충형 / 문서 인성 충극 / 통제력 관성 손상·태왕 고집 / 외부 유입 대비)만 남겼다.
# LLM은 제공된 후보·형충회합 근거에 붙여서만 각 축을 언급한다(엔진 계산 우선 원칙).
_ACCIDENT_RISK_KEYS = ("횡액", "다치", "다칠", "부상", "낙상", "골절")
_ACCIDENT_RISK_DIRECTIVE = (
    "[사고수 풀이 — 사고·안전 위험 질문 전용]\n"
    "이 질문의 주제는 '사고 위험'이다. 재물·직업 등 다른 주제로 흩어지지 말고, 아래 축 중 "
    "**제공된 후보·근거(충·형·기신 시기, 위험 신호 블록)에 실제로 존재하는 축만** 골라 "
    "'주의가 필요한 시기와 장면'으로 풀어라. 근거에 없는 축은 언급하지 않는다.\n"
    "①이동·교통 축: 역마성 지지(寅申巳亥)가 충·형(특히 寅巳申)으로 흔들리는 시기는 이동 중 "
    "돌발·차량·낙상 같은 횡액성 주의 시기다. 방어운전·일정 여유·무리한 이동 자제처럼 실행 "
    "가능한 대비로 연결하라.\n"
    "②문서·계약 사고 축: 인성(문서·도장·보증)이 기신운·재성운에 충극당하는 시기는 계약서·"
    "보증·도장·명의 관련 실수나 사기 주의 시기다. 원국에 인성이 과다한데 인성운이 겹치면 "
    "부동산·매매 문서를 특히 꼼꼼히. '보증은 서지 않기, 도장 찍기 전 한 번 더 확인' 같은 "
    "구체 습관으로 안내하라.\n"
    "③통제력 축: 관성(제어 장치)이 충·극으로 손상되는 시기이거나 비겁·식상 태왕으로 신강한 "
    "구조면, 내 속도와 고집이 사고를 부르는 장면(조언을 안 듣고 밀어붙이다 탈)이 된다. "
    "구조가 그렇다면 '결정 전에 남의 말을 한 번 더 듣는 습관'을 처방으로 제시하라.\n"
    "④외부 유입 축: 아무리 조심해도 상대 과실처럼 통제 밖에서 오는 변수는 있다 — 이 축은 "
    "겁주기가 아니라 보험·정기 점검·안전 습관 등 '대비'로만 짧게 서술한다.\n"
    "출력 순서(3층 분리 — 한 문장에 섞지 마라, 2026-07-23 데굴님 승인 D-1): "
    "①전통 해석 — '전통적으로 ~로 해석하기도 합니다' 형으로, 제공된 위험 신호 블록의 "
    "classicalInterpretation·구조 패턴의 전통 해석 문구를 활용해 감추거나 완화하지 말고 전달 "
    "②이번 판정의 근거 — 원국의 어떤 관계가 운의 무엇과 다시 충·형을 이루는지, 제공된 근거로만 "
    "③현실 확인 항목 — exposureCheckItems·노출 예시를 활용해 '실제로 운전·보증·기계 작업이 "
    "많다면 주의 수준을 높이라'는 확인 질문·조건으로 ④보호·반대 신호 — 같은 기간의 합·생조 등 "
    "완화 신호가 있으면 함께 ⑤사용자가 확인할 사항 목록. "
    "지나친 완화 금지: '조금 조심하면 아무 문제 없습니다'·'큰 걱정 마세요'식으로 위험을 상쇄해 "
    "숨기지 마라 — 전통 해석은 그대로 전하되 발생 단정만 하지 않는 것이 원칙이다. "
    "횡액 질문·suddenAdversitySummary가 있으면: '횡액'을 단독 사건으로 말하지 말고, '예상하지 "
    "못한 변수(이동 사고·분실·컨디션 저하 등)가 같은 시기에 겹칠 가능성을 묶어 전통적으로 "
    "횡액수라 부른다'로 풀며 반드시 구성 위험을 함께 나열하라. "
    "금지: '사고가 난다/안 난다' 같은 발생·시점 단정 금지('주의가 필요한 시기' 프레임으로). "
    "살(煞)·귀신·조상 등 초자연 원인 서술 금지(신살은 제공된 데이터에 있는 것만, 공포 조장 "
    "금지). 질문 기간이 길면(수년~10년) 주의 시기를 2~3개로 압축하고, 나머지 기간은 비교적 "
    "평온하다는 균형도 함께 말하라."
)


def _is_accident_risk_question(question: str) -> bool:
    """사고·안전 위험 질문 여부 — '사고'는 경계 정규식(매수·동형어 차단), 나머지는 부분문자열."""
    return bool(ACCIDENT_SAGO_RE.search(question)) or any(
        k in question for k in _ACCIDENT_RISK_KEYS
    )


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
    rel_ctx = intent.domain is Domain.RELATIONSHIP or any(k in question for k in _BIG_DECISION_KEYS)
    has_decision = any(m in question for m in _DECISION_MARKERS)
    return rel_ctx and any(k in question for k in _BIG_DECISION_KEYS) and has_decision


# 인연·만남 시기 질문 — 도메인 관계 또는 연애·배우자 키워드(GENERAL로 분류돼도 키워드로 보강).
_RELATIONSHIP_KEYS = (
    "연애",
    "연인",
    "인연",
    "애인",
    "짝",
    "배우자",
    "결혼",
    "재혼",
    "소개팅",
    "이상형",
    "남친",
    "여친",
    "남자친구",
    "여자친구",
    "솔로",
    "썸",
)


def _is_relationship_context(intent: IntentJson, question: str) -> bool:
    """관계(연애·결혼·인연) 맥락 질문 여부 — GENERAL로 분류돼도 키워드로 보강한다."""
    return intent.domain is Domain.RELATIONSHIP or any(k in question for k in _RELATIONSHIP_KEYS)


# 관계 신호 beta 노출(슬라이스 1) — 3축 라벨·가드 지시문.
_REL_BETA_ACT = {"strong": "강", "moderate": "중", "weak": "약", "low": "미약"}
_REL_BETA_STAB = {"favorable": "우호", "neutral": "중립", "adverse": "불리"}
_RELATIONSHIP_BETA_DIRECTIVE = (
    "위 [관계 신호(beta)] 블록은 아직 사람 감수 전의 잠정 관측값이다. '활성'은 관계 영역이 "
    "움직이는 에너지의 세기일 뿐 결혼·이별의 확정이 아니다. 성사 여부·현실 접촉·공식화는 "
    "아직 판정하지 않으므로 단정하지 말고, 활성·유지 우호도·종료압력 세 흐름만 자연어로 참고해 "
    "부드럽게 설명한다. 답변 말미에 '※ 관계 신호는 시험(beta) 관측치예요'라고 짧게 밝힌다."
)


def _relationship_beta_block(signals: list) -> str | None:
    """관계 벡터 3축 요약 → LLM 입력용 beta 블록(평가된 3축만·간지 미노출)."""
    if not signals:
        return None
    lines = ["[관계 신호(beta) — 잠정 관측치, 확정 아님]"]
    for s in signals:
        act = _REL_BETA_ACT.get(s.activation_band or "", s.activation_band or "관측")
        stab = _REL_BETA_STAB.get(s.stability_sign or "", "관측 안 됨")
        sep = _REL_BETA_ACT.get(s.separation_band or "", "관측 안 됨")
        lines.append(f"- {s.label}: 관계 활성 {act} · 유지 우호도 {stab} · 종료압력 {sep}")
    return "\n".join(lines)


# 관계 위험 dev beta 노출(슬라이스 3 — RELATIONSHIP_RISK_BETA_EXPOSE) — 도메인·밴드만.
_REL_RISK_DOMAIN_LABEL = {
    "finance": "재물",
    "career": "일·직장",
    "contract_legal": "계약·법적",
    "health_safety": "건강·안전",
    "relationship": "관계",
    "relocation": "이동·이사",
    "selection": "선발·경쟁",
}
# PRESSURE→주의 에너지, INCIDENT_RISK→사건 가능 신호. VULNERABILITY는 위험 엔진 규격상
# 사용자에게 별도 사건처럼 노출하지 않으므로 beta 블록에서도 제외한다.
_REL_RISK_KIND_BAND = {
    "pressure": "주의 신호",
    "incident_risk": "사건 가능 신호",
}
_RELATIONSHIP_RISK_BETA_DIRECTIVE = (
    "위 [관계 주의 신호(beta)] 블록은 아직 사람 감수 전의 미검증 잠정 관측값이다(calibration "
    "감수·증거 계약 미완). '주의 신호'는 그 관계 영역에서 신경 쓸 에너지가 있다는 방향일 뿐 "
    "사고·갈등·이별의 확정이 절대 아니다. 구체적 사건·날짜·상대에 대한 단정, 불안 조장·과장은 "
    "금지하고, 미평가 축(성사·공식화 등)은 언급하지 않는다. 도메인·강도 흐름만 부드럽게 참고해 "
    "예방적·차분한 톤으로만 설명하고, 답변 말미에 '※ 관계 주의 신호는 시험(beta) 관측치예요'라고 "
    "짧게 밝힌다."
)


def _relationship_risk_beta_block(candidates: list) -> str | None:
    """live 관계 유래 위험 후보 → dev beta 블록(도메인·밴드만·구체 사건 미노출).

    확률·구체 사고·날짜·상대는 노출하지 않는다. 활성(적격·미억제) 후보 중 PRESSURE·
    INCIDENT_RISK만 (도메인, 밴드) 단위로 dedup 후 최대 4건. 없으면 None.
    """
    seen: set[tuple[str, str]] = set()
    rows: list[tuple[str, str]] = []
    for c in candidates:
        if getattr(c, "suppressed_by_specificity", None):
            continue
        if getattr(getattr(c, "eligibility_status", None), "value", "eligible") != "eligible":
            continue
        band = _REL_RISK_KIND_BAND.get(getattr(getattr(c, "kind", None), "value", ""))
        if band is None:  # VULNERABILITY 등 — 사용자 비노출
            continue
        dom = _REL_RISK_DOMAIN_LABEL.get(
            getattr(getattr(c, "domain", None), "value", ""), None)
        if dom is None:
            continue
        key = (dom, band)
        if key in seen:
            continue
        seen.add(key)
        rows.append(key)
    if not rows:
        return None
    lines = ["[관계 주의 신호(beta) — 미검증 잠정 관측치, 사건 확정 아님]"]
    for dom, band in rows[:4]:
        lines.append(f"- {dom} 영역: {band}")
    return "\n".join(lines)


# 인연 출처 질문 — '주변 사람 vs 새로운 사람' 류(기존 지인이냐 새 인연이냐).
_PARTNER_SOURCE_KEYS = (
    "주변",
    "지인",
    "아는 사람",
    "아는사람",
    "소개",
    "새로운 사람",
    "새 사람",
    "새사람",
    "처음 보는",
    "처음보는",
    "기존",
    "원래 알",
    "어디서 만나",
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
    "대운",
    "교운",
    "평생",
    "인생 전체",
    "인생 흐름",
    "큰 흐름",
    "큰 운",
    "10년",
    "십년",
)


def _is_daewoon_question(intent: IntentJson, question: str) -> bool:
    """대운·장기 인생 흐름 질문 여부 — 명시 키워드 기반(막연한 장기 질문은 호출부에서 OR 보강)."""
    return any(k in question for k in _DAEWOON_KEYS)


# ── 기간 미지정 + '달/날짜' 입도 명시 질문(2026-07-03 데굴님 지적) ────────────────
# 실사례: '연애를 시작하는 달은 언제야?' → 기간이 없어 vague_future(10년 연 단위 digest)로
# 빠지며 연 나열로 오답. 질문이 입도(월/일)를 명시하면 연 단위가 아니라 그 입도로 답해야
# 한다. '한 달(기간)'·'다음 달(시점)'은 여기 표지와 다르고, 시점 표지는 time_parser가
# time_range로 잡아 이 판정과 무관해진다(gran_no_period 게이트).
_MONTH_GRAN_RE = re.compile(
    r"몇\s*월|몇\s*달|어느\s*달|무슨\s*달|어떤\s*달|좋은\s*달|유리한\s*달"
    r"|[가-힣]{1,6}[는할될]\s*달|달\s*(?:은|이)\s*언제|월\s*(?:은|이)\s*언제"
)
_DAY_GRAN_RE = re.compile(
    r"며칠|몇\s*일에|길일|날짜|(?:어느|무슨|어떤|좋은|유리한)\s*날(?!씨)"
    r"|[가-힣]{1,6}[는할될]\s*날(?!씨)|날\s*(?:은|이)\s*언제"
)


def _timing_granularity(question: str) -> str | None:
    """질문이 명시적으로 요구한 시점 입도 — 'month' / 'day' / None(입도 미지정)."""
    if _MONTH_GRAN_RE.search(question):
        return "month"
    if _DAY_GRAN_RE.search(question):
        return "day"
    return None


_MONTH_PICK_DIRECTIVE = (
    "[응답 형식 — '어느 달' 질문] 사용자가 특정 기간 없이 '달(월)'을 물었다. 연 단위 "
    "나열로 답하지 말고, 아래 월별 흐름(오늘부터 12개월)에서 유리한 달 1~3개를 골라 월 "
    "단위로 답하라. 각 달은 '이 달에 된다' 단정이 아니라 기운이 열리는 창으로 표현하고, "
    "12개월 너머에 더 강한 해가 있으면 '길게 보면 ○○○○년이 더 크다' 정도로만 짧게 "
    "덧붙여라. 마무리 질문을 따로 더 만들지 말고, 시스템 지시의 마지막 마무리 질문 하나의 "
    "소재를 '특정 달의 상세나 다른 해의 달을 이어 볼지'로 삼아라."
)
_DAY_PICK_DIRECTIVE = (
    "[응답 형식 — '어느 날(날짜)' 질문] 사용자가 특정 기간 없이 날짜를 물었다. 대화 "
    "풀이로 특정 날짜를 즉석 단정할 수 없으니, 먼저 아래 월별 흐름(오늘부터 12개월)에서 "
    "유리한 달로 좁혀 월 단위로 답하고, '달을 정해 주시면 그 달 안에서 날짜 단위로 더 "
    "좁혀 볼 수 있다'고 안내하라. 연 단위 나열 금지, 특정 일자 즉석 단정 금지."
)
# 만남 시기 디렉티브의 달 단위 변형 — 사용자가 '달'을 명시하면 '연·반기·계절로 제시' 지시가
# 질문 입도와 충돌하므로(실사례 오답의 한 축), 비택일·장소 단정 금지 원칙만 유지한 채
# 월 단위로 좁혀 답하게 한다.
_MEETING_TIMING_MONTH_DIRECTIVE = (
    "[인연·만남 시기 — 달 단위 요청]\n"
    "연인·배우자를 만나는 시기는 일정처럼 고르는 택일이 아니지만, 사용자가 '달'을 명시해 "
    "물었으므로 연·계절 단위로 뭉개지 말고 제공된 월별 흐름에서 가장 유리한 달 1~2개로 "
    "좁혀 답하라. 약한 달·기신 달을 선택지로 끌어와 곧장 무르지 말고, '어디서·어떤 "
    "경로로' 만나는지는 장소를 지어내지 말 것(활동 성향 경향까지만, 단정 금지)."
)

# 결론 요약 모드(2026-07-14 P4) — "그래서 붙는다는거야 아니라는거야?"류 결론 재확인 후속.
# 새 월별 분석·연도 나열 대신 직전 분석과 같은 시점 창의 압축 결론을 계약한다. 실측 결함:
# 이 유형이 domain_analysis로 떨어져 현재 연도 월운을 통째 재서술(질문에 정면 응답 안 함).
_CONCLUSION_SUMMARY_DIRECTIVE = (
    "[결론 요약 모드] 이 질문은 직전 분석의 결론을 재확인하는 후속이다. 새로운 월별 "
    "흐름·연도 나열을 생성하지 말고, 직전 분석과 같은 시점 창 기준으로 이 순서로 짧게 "
    "답하라: ①한 문장 결론(가능성의 방향) ②확실성 수준(단정 불가 명시) ③핵심 근거 "
    "2~3개 ④성립 조건·변수. 합격·당락·승패는 확정 표현 금지 — '유리한 흐름이나 확정할 "
    "수는 없다' 수준으로. 직전 답변과 이번 계산 결과가 충돌하면 요약 대신 정정을 먼저 "
    "밝혀라. 질문에 정면으로 답하는 것이 최우선이다."
)

# 미성년 대상 서사 적합도(2026-07-14 P5) — 분석 대상이 목표 시점에 미성년이면 성인 중심
# 사건 서사를 연령 적합 표현으로 변환한다(억제 아닌 적합도 조정 — 청소년도 자격시험·선발·
# 인증은 유효). 점수·판정에는 영향 없음(서술 계층 전용).
_MINOR_LIFESTAGE_DIRECTIVE = (
    "[분석 대상 연령 주의] 이 풀이의 대상은 분석 시점({target_year}년) 기준 만 {age}세 "
    "안팎({stage} 시기)이다. 성인 중심 사건 표현(계약 성립·채용·이직·창업·부동산 문서· "
    "혼인)은 그대로 쓰지 말고 연령에 맞게 변환하라 — 예: 계약·문서 → 선발·등록·합격· "
    "과정 진입, 채용·이직 → 진학·반 편성·활동 전환. 학업·진학·시험·성장 사건을 우선 "
    "서술하고, 이 연령에 명백히 불가능한 사건(혼인·창업 등)은 서술하지 마라. 점수·시기 "
    "판정 자체는 바꾸지 않는다."
)


# 총운 다변화(2026-07-14 데굴님 설계 확정) — '가장 큰 사건 하나' 요구는 다양화보다
# 최고점 중심이 적절하므로 제외한다(overview ≠ single_major_event).
_SINGLE_MAJOR_RE = re.compile(
    r"(?:가장|제일|최고로?)\s*(?:큰|중요한|주의할|조심할)|하나만|한\s*가지만|딱\s*하나"
)

# P2 — 총운 서술 계약: 후보가 존재하는 영역만 조망(다섯 영역 강제 채움 환각 방지),
# 집중은 집중으로 명시, 미선정 영역은 '신호 없음' 단정 금지·언급 생략(Top-N 결과만으로는
# 전체 후보군 부재/임계 미달/중복 병합을 구분할 수 없다).
_OVERVIEW_COVERAGE_DIRECTIVE = (
    "[총운 조망 지침] 선정된 주요 후보를 생활 영역별로 묶어 앞으로의 흐름을 조망하라. "
    "**선정된 이벤트 후보는 각각 최소 한 번씩 직접 다루고**, 강도가 가장 높은 후보는 "
    "영역과 무관하게 답변 앞부분에서 비중 있게 서술하라 — 월별 용신·기신 흐름 서술이 "
    "이벤트 후보 조망을 대체하거나 특정 영역(직업 등)으로 비중을 쏠리게 하면 안 된다. "
    "여러 후보가 같은 사건군·같은 영역에 집중돼 있으면 반복 나열하지 말고 하나의 "
    "흐름으로 통합하고, 그 집중을 명시하라('이 기간은 ○○ 영역 신호가 특히 강하다'). "
    "'반복 신호' 표기가 있으면 대표 시기와 재등장 시기를 하나의 흐름으로 설명하라. "
    "후보에 포함되지 않은 생활 영역은 상태를 임의로 추론하거나 '신호 없음·문제없음'으로 "
    "단정하지 말고 언급을 생략하라 — 후보가 존재하는 영역들만 조망한다."
)


def _is_overview_multi_domain(intent: IntentJson, question: str) -> bool:
    """총운 다변화 모드 여부(2026-07-14) — general 전체가 아니라 명시 조건으로 제한.

    FORTUNE_OVERVIEW + 멀티도메인(주도메인 general·부도메인 없음·이벤트 미지정) +
    단일 최대 사건 요구('가장 중요한 일 하나')가 아닐 때만. 특정 도메인·이벤트 질문은
    기존 순수 점수순 Top-N 그대로(회귀 0).
    """
    return (
        intent.query_type is QueryType.FORTUNE_OVERVIEW
        and intent.domain is Domain.GENERAL
        and not intent.domains
        and intent.event_key is None
        and not _SINGLE_MAJOR_RE.search(question)
    )


def _time_exclusion_directive_text(
    intent: IntentJson, exclusions: list[TimeExclusion]
) -> str:
    """배제 시점 서술 제한 지시문(2026-07-14 P2) — 구조화된 시점 제약을 LLM에 전달한다.

    단순 금지문 대신 '확정 시점 + 배제 기간 + 근거'를 함께 제시해, 배제 기간이 주요
    분석 시점으로 재등장하는 회귀를 서술 계층에서도 차단한다.
    """
    spans = ", ".join(
        f"{e.start_year}~{e.end_year}년" if e.start_year != e.end_year
        else f"{e.start_year}년"
        for e in exclusions
    )
    tr = intent.time_range
    resolved = (
        f"{tr.start}{'~' + tr.end if tr.end and tr.end != tr.start else ''}"
        if tr is not None and tr.start else "미지정"
    )
    return (
        f"[시점 제약] 확정 분석 시점: {resolved}. 사용자가 이번 주제에서 배제한 기간: "
        f"{spans}. 배제 기간을 주요 분석 시점으로 서술하지 말고 그 기간의 세운·월운 "
        "나열도 하지 마라. 흐름상 꼭 필요하면 '요청하신 대로 제외했다'고 한 줄만 언급하라. "
        "확정 분석 시점이 미지정이면 먼저 어느 시점을 볼지 확인하라."
    )


def _minor_lifestage_directive_text(
    birth: BirthInput, intent: IntentJson, today: date
) -> str | None:
    """분석 대상이 목표 연도에 미성년이면 연령 적합도 지시문을 만든다(2026-07-14 P5).

    나이는 현재가 아니라 **분석 대상 연도의 만 나이 근사**(목표연도-출생연도)로 계산한다.
    성인(만 19세 이상)이면 None — 기존 서술 무변경.
    """
    span = tr_year_span(intent.time_range)
    target_year = span[0] if span is not None else today.year
    age = target_year - birth.birth_date.year  # 생일 경과 전이면 -1일 수 있는 근사치
    # 연도차 근사는 최대 1살 과대 — 19는 수능 해의 고3일 수 있어 미성년으로 취급한다.
    if age < 0 or age > 19:
        return None
    stage = (
        "미취학" if age < 7 else "초등" if age < 13 else "중등" if age < 16 else "고등"
    )
    return _MINOR_LIFESTAGE_DIRECTIVE.format(target_year=target_year, age=age, stage=stage)


def _drop_excluded_candidates(
    candidates: list, exclusions: list[TimeExclusion]
) -> list:
    """배제 기간(연 단위)에 속한 이벤트 후보를 제거한다(2026-07-14 후속①).

    period 형식은 'YYYY'(세운)·'YYYY-MM'(월운) — 연도 접두로 판정한다. 사용자 명시
    배제이므로 결과가 비어도 유지한다(의도 필터의 fallback-원본-유지와 다른 정책 —
    배제는 지시이지 보정이 아니다).
    """
    return [
        c for c in candidates
        if not (
            c.period[:4].isdigit()
            and overlaps_exclusions(
                (int(c.period[:4]), int(c.period[:4])), exclusions
            )
        )
    ]


# 총운 커버리지 검증(2026-07-14 6차 — 관측 전용, 데굴님 확정: 재생성 금지·비용 증가 반대).
# 지시문 강화로도 LLM이 최강 후보(관계 갈등)를 뭉개는 위반이 반복돼 누락을 로그로 계측한다
# — LLM 재호출 없음. 개선은 입력 구조(총운 후보 블록 후치·순번 체크리스트)로 유도한다.
_COVERAGE_GENERIC_TOKENS = frozenset({"변화", "신호", "관련"})


def _overview_missed_candidates(answer: str, candidates: list) -> list[str]:
    """총운 답변에서 서술되지 않은 선정 후보 목록(라벨@기간).

    문장 단위로 '라벨 토큰 + 기간 마커' 동시 출현을 요구한다 — 전역 검사는
    '관계'·'7월'이 서로 다른 문장에 흩어져 있어도 통과시키는 오탐이 있다(실측:
    관계 기회 @2026-07이 문장 없이 지나갔는데 전역 검사로는 잡히지 않음).
    """
    sentences = re.split(r"[.!?\n]", answer)
    missed: list[str] = []
    for c in candidates:
        label = c.event_ko or str(c.event_key)
        tokens = [
            t for t in re.split(r"[·\s]", label)
            if t and t not in _COVERAGE_GENERIC_TOKENS
        ]
        if len(c.period) >= 7:  # 'YYYY-MM' — 월 마커('12월')와 연 마커 둘 다 허용
            markers = [f"{int(c.period[5:7])}월", c.period[:4]]
        else:  # 'YYYY'
            markers = [c.period[:4]]
        covered = any(
            any(t in s for t in tokens) and any(m in s for m in markers)
            for s in sentences
        )
        if not covered:
            missed.append(f"{label} @ {c.period}")
    return missed


def _response_primary_year(answer: str) -> tuple[int, int] | None:
    """답변 본문의 중심 연도와 그 언급 횟수 — (연도, 횟수). 연도 언급이 없으면 None."""
    years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", answer)
    if not years:
        return None
    counts = Counter(years)
    y, c = counts.most_common(1)[0]
    return int(y), c


def _time_commit_guard(
    state: ConversationState,
    prior_time: dict,
    intent: IntentJson,
    answer: str,
    exclusions: list[TimeExclusion],
) -> ConversationState:
    """상태 커밋 전 시점 정합성 검사(2026-07-14 P3 — 2단계 커밋).

    불변식: 파싱 확정 시점 = 엔진 창 = 답변 중심 시점. 답변의 중심 연도가 엔진 창
    밖이거나 배제 연도이면 이번 턴의 시점 슬롯 커밋을 되돌린다(직전 정상 상태 유지) —
    파서가 한 번 잘못 읽어도 오염된 시점이 다음 턴으로 퍼지지 않게 한다(실측:
    turn2 파서=2026 vs 답변=2033 불일치가 감지 없이 저장돼 turn3 회귀).
    """
    primary = _response_primary_year(answer)
    if primary is None:
        return state
    year, count = primary
    span = tr_year_span(intent.time_range)
    engine_max = (
        max(
            (c for y, c in Counter(
                re.findall(r"(?<!\d)(20\d{2})(?!\d)", answer)
            ).items() if span[0] <= int(y) <= span[1]),
            default=0,
        )
        if span is not None else None
    )
    mismatch = (
        span is not None and not (span[0] <= year <= span[1])
        and count >= 2 and engine_max is not None and count > engine_max
    )
    excluded_hit = count >= 2 and overlaps_exclusions((year, year), exclusions)
    if not mismatch and not excluded_hit:
        return state
    _logger.warning(
        "time consistency violation — engine=%s response_primary=%s(%d회) excluded=%s; "
        "시점 슬롯 커밋 되돌림(thread=%s turn=%s)",
        span, year, count, excluded_hit, state.thread_id, state.turn_no,
    )
    reverted_intent = (
        state.last_intent.model_copy(update={
            "time_range": prior_time.get("time_range"),
        })
        if state.last_intent is not None else None
    )
    return state.model_copy(update={
        "last_intent": reverted_intent if reverted_intent is not None else state.last_intent,
        "active_time_scope": prior_time.get("active_time_scope"),
        "active_time_meta": prior_time.get("active_time_meta") or {},
    })


# 성향 반박(풀이 인용 + 부정) 감지 — 인용 표지와 부정 표지가 함께 있을 때만(과잉 트리거 방지).
# 상담 사례 파생 P0-7(doc/v2_2/cases/1980_1122_job_report_case.md §5): '풀이에는 말이 매력적이라는데
# 실제 나는 면접에서 말을 못한다' 류 피드백에 수용·재해석 지시를 싣는다.
_TRAIT_QUOTE_KEYS = (
    "라는데",
    "라던데",
    "라면서",
    "라고 하던데",
    "라고 나왔",
    "나왔는데",
    "풀이에는",
    "풀이에서는",
    "리포트에",
    "보고서에",
    "사주에는",
    "사주에서는",
)
_TRAIT_NEGATE_KEYS = (
    "아닌데",
    "아니에요",
    "아닌 것 같",
    "안 그래",
    "안 그런",
    "안 그렇",
    "잘 못",
    "못하는",
    "못해요",
    "다른데",
    "다릅니다",
    "안 맞",
    "반대",
    "지 않",
    "없는데",
    "없어요",
)


def _is_trait_mismatch(question: str) -> bool:
    """'풀이에는 그렇다는데 실제 나는 아니다' 성향 반박 여부 — 인용+부정 동시 감지."""
    return any(k in question for k in _TRAIT_QUOTE_KEYS) and any(
        k in question for k in _TRAIT_NEGATE_KEYS
    )


# 규범 질문('결혼 꼭 해야 하나요') 감지 — 강한 당위 표지만(일반 의사결정 질문 오탐 방지).
_NORMATIVE_KEYS = (
    "꼭 해야",
    "꼭 가야",
    "해야만",
    "필수인가",
    "필수예요",
    "필수인지",
    "안 하면 안 되",
    "안하면 안되",
    "무조건 해야",
    "다들 하니까",
)


def _is_normative_question(question: str) -> bool:
    """사회 규범 당위형 질문 여부('꼭 해야 하나' 류) — 탈규범 안심 디렉티브 트리거."""
    return any(k in question for k in _NORMATIVE_KEYS)


def _compat_prompt_block(
    result: ManseV2Result,
    partner_birth: BirthInput,
    today: date,
    partner_label: str,
) -> str | None:
    """본인↔상대 궁합 신호 블록(채팅 pairwise). 엔진 계산값만 + LLM 서술 가드."""
    partner_result = calculate(partner_birth.model_copy(update={"reference_date": today}))
    self_sum = build_birth_summary(result)
    partner_sum = build_birth_summary(partner_result)
    report = analyze_compatibility(
        result,
        partner_result,
        self_sum.useful_gods,
        partner_sum.useful_gods,
        self_label="본인",
        partner_label=partner_label,
    )
    if report is None:
        return None
    lines = ["", "[궁합 분석 — 아래 엔진 계산값만 근거로 두 사람 궁합을 설명할 것]"]
    lines += compatibility_lines(report)
    # 12신살 상대위치(P2) — 년지(사회)·일지(친밀) 기준 상대 12신살 양방향 체감(설명, 점수 미개입).
    from saju_engines.relationship_relative_sinsal import relative_sinsal_lines

    lines += relative_sinsal_lines(result, partner_result, "본인", partner_label)
    # 삼합국 관계 역학(P1) — 년지 삼합국 오행 생극 경향(설명 레이어, 점수 미개입).
    from saju_engines.relationship_trine_dynamics import trine_dynamics_lines

    lines += trine_dynamics_lines(result, partner_result, "본인", partner_label)
    lines.append(
        "신호의 방향(보완/마찰)을 그대로 반영하되 '반드시 헤어진다/잘 된다' 류 단정·상대 탓·"
        "운명론은 금지. 마찰은 관리 가능한 영역으로, 극복할 마음가짐·행동도 덧붙일 것."
    )
    return "\n".join(lines)


def _current_period_line(result: ManseV2Result, year: int) -> str:
    """대상의 현재 대운 + 지정 연 세운 간지를 compact 한 줄로(없으면 빈 문자열)."""
    lc = result.luck_cycles
    if lc is None:
        return ""
    parts: list[str] = []
    idx = lc.current_daewoon_index
    if idx is not None and 0 <= idx < len(lc.daewoon_table):
        parts.append(f"대운 {lc.daewoon_table[idx].ganji}")
    se = next((p for p in lc.yearly_luck if p.label == str(year)), None)
    if se is not None:
        parts.append(f"세운 {se.ganji}({year})")
    return " · ".join(parts)


def _pairwise_subject_blocks(
    injection: SubjectInjectionPolicy,
    self_result: ManseV2Result,
    companion_result: ManseV2Result,
    self_label: str,
    companion_label: str,
    relation_type: str,
    relation_basis: str,
    year: int,
) -> tuple[list[SubjectBlock], RelationshipContext]:
    """P2a/P3a pairwise — 본인+동반자 대상별 명식 블록(compact) + 관계 맥락(관점 힌트).

    각 대상의 원국 구조(build_birth_summary 재사용)와 현재 운 한 줄만 담는다(토큰 절약 —
    원국 전체 dump 금지). 본인 base 분석은 별개로 유지되며 이 블록은 가산 정보다.
    perspective_hints/safety_guards는 관점 제어용(점수·우열 아님).
    """
    cid = injection.companion_subject_ids[0]
    self_block = SubjectBlock(
        subject_id=injection.primary_subject_id or "self",
        role="self",
        label=self_label or "본인",
        is_primary=True,
        relation_to_user="self",
        chart=build_birth_summary(self_result),
        current_period=_current_period_line(self_result, year),
    )
    companion_block = SubjectBlock(
        subject_id=cid,
        role="companion",
        label=companion_label or "상대",
        is_primary=False,
        relation_to_user=relation_type,
        chart=build_birth_summary(companion_result),
        current_period=_current_period_line(companion_result, year),
    )
    rc = RelationshipContext(
        mode=injection.mode,
        relation_type=relation_type,
        relation_basis=relation_basis,
        perspective_hints=perspective_hints_for(relation_type),
        safety_guards=list(SAFETY_GUARDS),
        primary_subject_id=self_block.subject_id,
        companion_subject_ids=[cid],
        compatibility_overlay_available=True,
    )
    return [self_block, companion_block], rc


def _compare_subject_blocks(
    injection: SubjectInjectionPolicy,
    primary_result: ManseV2Result,
    other_result: ManseV2Result,
    primary_label: str,
    other_label: str,
    other_subject_id: str,
    relation_type: str,
    relation_basis: str,
    year: int,
) -> tuple[list[SubjectBlock], RelationshipContext]:
    """P3b compare_exclude_self — 동반자 A(primary=base) vs 동반자 B. 본인 미포함.

    primary(A)는 이미 본문 base로 교체돼 있어 '위 [원국·명식 구조] 참조'로, B는 compact 명식으로
    노출한다. 궁합 오버레이는 본인↔상대용이라 비활성. 우열·승패 단정 금지 가드 포함.
    """
    primary_block = SubjectBlock(
        subject_id=injection.primary_subject_id or "companion_a",
        role="companion",
        label=primary_label,
        is_primary=True,
        chart=build_birth_summary(primary_result),
        current_period=_current_period_line(primary_result, year),
    )
    other_block = SubjectBlock(
        subject_id=other_subject_id,
        role="companion",
        label=other_label,
        is_primary=False,
        chart=build_birth_summary(other_result),
        current_period=_current_period_line(other_result, year),
    )
    rc = RelationshipContext(
        mode=injection.mode,
        relation_type=relation_type,
        relation_basis=relation_basis,
        perspective_hints=perspective_hints_for(relation_type),
        safety_guards=list(SAFETY_GUARDS),
        primary_subject_id=primary_block.subject_id,
        companion_subject_ids=injection.companion_subject_ids,
        compatibility_overlay_available=False,
    )
    return [primary_block, other_block], rc


def _ranking_subject_blocks(
    injection: SubjectInjectionPolicy,
    primary_result: ManseV2Result,
    primary_label: str,
    others: list[tuple[str, str, ManseV2Result]],
    year: int,
) -> tuple[list[SubjectBlock], RelationshipContext]:
    """P3c-2 ranking — 동반자 3~4명 다자 비교. A(primary=base)=참조, 나머지는 compact 명식.

    본인 미포함. '순위 산출'이 아니라 항목별 조건부 상대 경향 비교(RANKING_SAFETY_GUARDS).
    others: (subject_id, label, result) 목록(cap 적용 후). 순위·점수·확률은 만들지 않는다.
    """
    blocks: list[SubjectBlock] = [
        SubjectBlock(
            subject_id=injection.primary_subject_id or "companion_a",
            role="companion",
            label=primary_label,
            is_primary=True,
            chart=build_birth_summary(primary_result),
            current_period=_current_period_line(primary_result, year),
        )
    ]
    for sid, label, res in others:
        blocks.append(
            SubjectBlock(
                subject_id=sid,
                role="companion",
                label=label,
                is_primary=False,
                chart=build_birth_summary(res),
                current_period=_current_period_line(res, year),
            )
        )
    rc = RelationshipContext(
        mode=injection.mode,
        relation_type=None,
        relation_basis="unknown",
        perspective_hints=[],
        safety_guards=list(RANKING_SAFETY_GUARDS),
        primary_subject_id=blocks[0].subject_id,
        companion_subject_ids=[b.subject_id for b in blocks],
        compatibility_overlay_available=False,
    )
    return blocks, rc


def _structural_context(
    result: ManseV2Result,
    intent: IntentJson,
    today: date,
    question: str = "",
) -> list[str]:
    """질문 도메인에 맞는 구조 해석 블록(누출 안전 한글). intent 미확정(general)=총운으로 간주해
    모든 블록을, 확정 도메인은 해당 블록만 표면화한다(2026-06-16 사용자 확정).

    리포트와 동일한 structural_context 포맷터를 재사용해 표면화 일관성·누출 방지를 유지한다.
    외적 인상·매력 신호는 자체 allowlist(관계·총운·명식분석·외모 직접질문)로 별도 게이트한다.
    """
    if result.pillars is None or result.force_analysis is None:
        return []
    from saju_engines.event_scoring import favorability_map
    from saju_engines.external_impression import analyze_external_impression
    from saju_engines.health_vulnerability import analyze_health_vulnerability
    from saju_engines.marriage_resource import analyze_marriage_resource
    from saju_engines.palace_relationship_network import (
        analyze_palace_network,
        palace_network_lines,
    )
    from saju_engines.preparation_context import build_preparation_context
    from saju_engines.structural_context import (
        era_energy_lines,
        external_impression_lines,
        health_lines,
        marriage_age_prior_lines,
        marriage_resource_lines,
        preparation_context_lines,
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
        # 재물 준비기(P3, 데굴님 확정 2026-07-12) — 발현 후보년·선행 준비년 서술 전용 맥락.
        # 점수·순위·시기·확신도 불변(inert). 세운 미보유 시 빈 목록(무언급).
        if result.luck_cycles is not None:
            out += preparation_context_lines(build_preparation_context(
                result.luck_cycles.yearly_luck, today.year,
            ))
    if general or domain in (Domain.WEALTH, Domain.CAREER):
        out += wealth_status_lines(analyze_wealth_status_lean(result))
    if general or domain is Domain.RELATIONSHIP:
        # 배우자성 성별 가드를 결혼 블록과 항상 동반 — general로 분류된 관계 질문('언제 만나' 등)도
        # 남=재성·여=관성 기준을 받게 한다(2026-06-22 데굴님 지적: GENERAL은 가드 누락이던 결함).
        out.append(spouse_star_directive(str(result.input_summary.get("gender", "unknown"))))
        # 배우자성=용신(배우자 덕) 판정에 용희신을 넘긴다(G). 자기인식 가드도 함께(C).
        _useful = build_birth_summary(result).useful_gods
        out += marriage_resource_lines(analyze_marriage_resource(result, _useful))
        out += marriage_age_prior_lines(result)  # MT6 혼기 static prior(프로파일 off면 빈 줄)
        # 궁위 관계망(P3) — 연·월·일·시 궁위 간 관계질(설명 레이어, 점수 미개입).
        out += palace_network_lines(analyze_palace_network(result), domain)
        out.append(RELATIONSHIP_SELF_AWARENESS_DIRECTIVE)
        out.append(TENDENCY_SHIFT_DIRECTIVE)
        # P2(2026-07-21) — '연애운 없으면 결혼운 좋다' 류 이원 구도 질문에만 통합 관점 주입.
        _q_compact = question.replace(" ", "")
        if "연애운" in _q_compact and "결혼운" in _q_compact:
            out.append(LOVE_MARRIAGE_UNIFIED_DIRECTIVE)
    if general or domain is Domain.HEALTH:
        hv = analyze_health_vulnerability(result, favorability_map(result))
        out += health_lines(result, hv, today.year)
    # 외적 인상·매력 신호 — 자체 allowlist·gender·band 게이트(미해당 시 무언급). 외모 직접질문은
    # suppress 도메인에서도 예외 노출하므로 도메인 분기 밖에서 항상 호출한다.
    out += external_impression_lines(analyze_external_impression(result), intent, question)
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
        line += f" · 이 구간 안에 대운 교운기({years}) — 전환 에너지가 강하게 작동"
    return f"\n[대운 배경 — {end_year - start_year + 1}년 흐름]\n" + line


def _is_day_range(intent: IntentJson) -> bool:
    """일 단위 범위(주간·단일일 포함) 질문인가 — 일별 일운 surface 게이트.

    단일 날짜(start==end)도 포함한다(2026-07-22 실로그: '9월 30일 이사 주의점'이
    당일 일운 데이터 없이 월·연 후보만 받아 두루뭉술한 기간 서술 + LLM 임의 간지
    서술로 빠지던 결함 — 특정일 질문일수록 그 날의 간지·길흉이 필수 근거다).
    """
    tr = intent.time_range
    return bool(
        tr is not None
        and tr.start
        and tr.end
        and tr.granularity.value == "day"
    )


def _is_single_day(intent: IntentJson) -> bool:
    """특정 하루(start==end, 일 단위)를 물은 질문인가 — 당일 집중 디렉티브 게이트."""
    tr = intent.time_range
    return bool(
        tr is not None and tr.start and tr.end
        and tr.start == tr.end and tr.granularity.value == "day"
    )


def _weekly_overview_lines(
    birth: BirthInput,
    intent: IntentJson,
    today: date,
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
    # 단일 날짜(start==end)도 허용 — 특정일 질문의 당일 간지·길흉 근거(2026-07-22).
    if not (start <= end and (end - start).days <= 14):
        return []
    try:
        chart = calculate(birth.model_copy(update={"reference_date": start}))
        if chart.luck_cycles is not None:
            window = daily_luck_window(chart, start, end)
            chart = chart.model_copy(
                update={"luck_cycles": chart.luck_cycles.model_copy(update={"daily_luck": window})}
            )
        comps = CompositeBuilder(_DICTS).build(
            chart, "chat", "1.0.0", f"{today.isoformat()}T00:00:00+00:00"
        )
        days = sorted(
            (
                c
                for c in comps
                if c.level is CompositeLevel.DAY
                and start.isoformat() <= c.period_key <= end.isoformat()
            ),
            key=lambda c: c.period_key,
        )
    except Exception:  # noqa: BLE001 — 일별 산출 실패가 일반 풀이를 막지 않도록
        return []
    if not days:
        return []
    header = (
        f"[해당 일({start.isoformat()}) 일운 — 간지·길흉(용신/희신/한신/기신/구신)·십성. "
        "이 날을 중심으로 서술할 것]"
        if start == end
        else (
            f"[해당 기간({start.isoformat()}~{end.isoformat()}) 일별 흐름 — 일운 간지·길흉"
            "(용신/희신/한신/기신/구신)·십성. 날짜별로 하루씩 짚어 서술하고 월 단위로 "
            "뭉뚱그리지 말 것]"
        )
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
    return intent.model_copy(
        update={
            "domain": Domain(sug.domain),
            "event_key": event,
            "event_keys": intent.event_keys or ([event] if event else []),
        }
    )


def _augment_time_by_similarity(
    intent: IntentJson,
    question: str,
    today: date,
    current_month_label: str | None,
) -> IntentJson:
    """규칙이 시점을 못 잡은(time_range None) 질문을 임베딩 분류기로 보강한다(보조, rules-first).

    합성 가능한 구체 버킷(이번 주/달·올해 등 변형 표현)만 결정론 TimeRange로 채운다. 분류기
    비활성·저신뢰·비합성 버킷(막연 미래/과거 회고/구조)이면 None을 유지해 다운스트림(vague_future·
    회고 경로)이 그대로 처리한다. 점수·간지·판정엔 미개입(절대원칙 1·9). 날짜는 결정론 계산.
    """
    if intent.time_range is not None:
        return intent  # 규칙이 이미 시점 확정 — rules-first
    # 기간 없이 '달/날짜' 입도만 명시한 질문('이직하기 좋은 달 추천해줘')은 시점 표현이
    # 아니라 입도 요청이다 — 유사도 분류기가 '이번 달' 같은 구체 시점으로 오주입하면
    # 12개월 창이 한 달로 좁혀지고 입도 라우팅이 막힌다(2026-07-03 실사례 결함). 보강 스킵
    # (멀티턴 '언제·추천형 질문 시점 미승계' 가드와 동일 원리).
    if _timing_granularity(question) is not None:
        return intent
    # 무시점·무분야 질문(B3 판정표 too_broad — '앞으로 내 운세 알려줘' 류)은 시점을 합성하지
    # 않는다. 완곡 표현에 시점이 주입되면 too_broad '좁혀볼까요' 관문을 우회해 종합운으로
    # 흘러가는 회귀 방지(2026-07-06). 도메인 유사도 보강 이후에 호출되므로, 여기서 too_broad면
    # 유사도로도 분야를 못 잡은 질문이다.
    if assess(intent, question).status == "too_broad":
        return intent
    from saju_engines.time_embedding import get_time_classifier
    from saju_engines.time_parser import bucket_to_range

    sug = get_time_classifier().classify(question)
    if sug is None or sug.score < _TIME_SIM_MIN_SCORE or sug.margin < _TIME_SIM_MIN_MARGIN:
        return intent
    tr, _scope = bucket_to_range(sug.label, today, current_month_label)
    if tr is None:
        return intent  # 비합성 버킷 — 막연/회고/구조는 합성하지 않고 다운스트림 위임
    return intent.model_copy(update={"time_range": tr})


def _augment_companion_mode_by_similarity(intent: IntentJson, question: str) -> IntentJson:
    """규칙이 비교 mode를 못 잡은 완곡·변형 표현을 유사도로 보강한다(P3d-2, rules-first, gated).

    augment_subject_mode가 안전장치 조합(rules-first + 2명 이상 대상 구성 + companion_only 제외 +
    score≥0.60/margin≥0.05)을 모두 만족할 때만 subject_mode를 승격한다. 승격되면 query_type도
    COMPARISON으로 올려 assess의 '2명+single=모호' need_subject를 피한다. 점수·간지·판정 미개입.
    현 ONNX 이득은 modest(전용 튜닝은 후속) — 규칙이 못 잡은 좁은 잔여만 보강.
    """
    subs = intent.subjects
    non_self = [s for s in subs if s.kind is not SubjectKind.SELF]
    has_self = any(s.kind is SubjectKind.SELF for s in subs)
    new_mode = augment_subject_mode(
        intent.subject_mode,
        question,
        len(non_self),
        has_self,
    )
    if new_mode is intent.subject_mode:
        return intent
    updates: dict[str, object] = {"subject_mode": new_mode}
    if intent.query_type not in (
        QueryType.FEEDBACK_CORRECTION,
        QueryType.TERMINOLOGY_EDUCATION,
        QueryType.EMOTIONAL_SUPPORT,
        QueryType.OUT_OF_SCOPE,
    ):
        updates["query_type"] = QueryType.COMPARISON
    return intent.model_copy(update=updates)


# 직전 풀이 재검토(claim recheck) 시 LLM에 주입하는 지시문 — 출생정보 재요청 금지·엔진 근거 재검토.
_RECHECK_DIRECTIVE = (
    "[직전 풀이 재검토 — 사용자가 직전 답변에 이의·반문을 제기함] 사주·출생정보는 이미 확정돼 "
    "있으니 절대 다시 묻지 말 것. 위 '이전 판정(prior_claims)'과 아래 엔진 후보·근거로 직전 "
    "풀이를 재검토하라. 사용자의 반문이 타당하면 솔직히 인정·정정하고, 직전 판정이 맞으면 "
    "간지·신호 근거를 들어 차분히 재확인하라. 특히 '관계가 시작되는 시기'와 '신호가 발생하는 "
    "시기'의 차이(트리거≠실행), 가능성 단계(관심·인연 의식 → 관계 진전)를 구분해 설명하라. "
    "단정·예언은 금지."
)
# claim recheck 상속 대상이 되는 '분석' query_type(정책·구조 라우트 제외).
_RECHECK_ANALYSIS_QTYPES = frozenset(
    {
        QueryType.FORTUNE_OVERVIEW,
        QueryType.DOMAIN_ANALYSIS,
        QueryType.TIMING_SEARCH,
        QueryType.EVENT_EXPLANATION,
        QueryType.RELATIONSHIP_ANALYSIS,
        QueryType.REMEDY,
        QueryType.DECISION_SUPPORT,
        QueryType.DATE_RECOMMENDATION,
    }
)


def _recheck_continuation(
    intent: IntentJson,
    prior_intent: IntentJson | None,
) -> tuple[IntentJson, bool]:
    """FEEDBACK_CORRECTION(이의/반문) + 직전 분석 맥락이면 직전 주제 상속해 분석 intent로 전환한다.

    canned 'claim_recheck' 폴백(출생정보 재요청) 대신 직전 도메인·이벤트·시점을 이어받아 정상
    분석 경로로 흘려, recheck 지시문으로 엔진 근거 재검토를 시킨다(B — 멀티턴 재검산). 직전 맥락이
    없거나 직전이 분석 질문이 아니면 전환하지 않는다(기존 canned 유지 — 새 스레드·진짜 정정 보호).

    Args:
        intent: 현재 턴 intent(query_type=FEEDBACK_CORRECTION일 수 있음).
        prior_intent: 직전 턴 intent(스레드 상태). None이면 맥락 없음.

    Returns:
        (전환된 intent, is_recheck). is_recheck=True면 recheck 지시문을 주입해야 한다.
    """
    if intent.query_type is not QueryType.FEEDBACK_CORRECTION or prior_intent is None:
        return intent, False
    if prior_intent.query_type not in _RECHECK_ANALYSIS_QTYPES:
        return intent, False  # 직전이 분석 질문이 아니면 재검토 대상 아님
    new = intent.model_copy(
        update={
            "query_type": prior_intent.query_type,
            "domain": intent.domain if intent.domain is not Domain.GENERAL else prior_intent.domain,
            "event_key": intent.event_key or prior_intent.event_key,
            "event_keys": intent.event_keys or prior_intent.event_keys,
            "time_range": intent.time_range or prior_intent.time_range,
        }
    )
    return new, True


def _attach_subject_plan(
    plan: ExecutionPlan,
    intent: IntentJson,
    base_subject_id: str | None,
    base_label: str,
    partner_ref: dict | None,
    alias_index: dict[str, list[AliasEntry]] | None,
    question: str = "",
) -> ExecutionPlan:
    """P1 — 대상 조합(effective_subjects/mode/injection)을 계산해 plan에 shadow로 싣는다.

    per_subject 등 실행 분기는 바꾸지 않는다(계산/실행 분리). P0 해소 대상(intent.subjects)과
    FE 칩 첨부 동반자(partner_ref)를 병합하며, alias_index로 관계·매칭 별칭을 보강한다.

    question은 상호 술어 판정에만 쓴다 — 칩으로만 첨부돼 발화에 상대 언급이 없으면
    intent.subject_mode가 동반자를 세지 못해 '다시 만날 수 있을까'류가 companion_only로
    떨어진다(2026-07-31 실로그 '나 × 전남친': 궁합인데 상대 명식만 풀이).
    """
    companion_meta: dict[str, AliasEntry] = {}
    for entries in (alias_index or {}).values():
        for e in entries:
            companion_meta.setdefault(e.subject_id, e)

    attached: list[AttachedCompanion] = []
    if partner_ref:
        label = partner_ref.get("label") or "상대"
        sid = partner_ref.get("subjectId") if partner_ref.get("mode") == "registered" else None
        if sid:
            rel = companion_meta[sid].relation_to_user if sid in companion_meta else None
            attached.append(AttachedCompanion(subject_id=sid, label=label, relation_to_user=rel))
        elif partner_ref.get("mode") == "inline":
            # 즉석 상대도 관계를 싣는다 — 등록 동반자만 관계가 전달되던 결함(2026-07-31).
            # 관계가 빠지면 대인 관계 근거로 본인을 함께 볼 수 없어 companion_only 로
            # 떨어지고, 궁합인데 상대 명식만 풀이된다.
            attached.append(AttachedCompanion(
                subject_id="inline:partner", label=label,
                relation_to_user=partner_ref.get("relationType") or None,
            ))

    eff, mode, injection = build_effective_subjects(
        intent.subjects,
        intent.subject_mode,
        base_subject_id=base_subject_id,
        base_label=base_label,
        attached=attached,
        companion_meta=companion_meta,
        self_implied=implies_self_counterpart(question),
    )
    return plan.model_copy(
        update={
            "effective_subjects": eff,
            "companion_read_mode": mode,
            "subject_injection": injection,
        }
    )


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
    companion_alias_index: dict[str, list[AliasEntry]] | None = None,
    companion_births: dict[str, BirthInput] | None = None,
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
        # P3(2단계 커밋) — 시점 슬롯의 직전 정상 상태 스냅샷. 답변 생성 후 정합성 검사에
        # 실패하면 이 값으로 되돌려 오염이 다음 턴으로 퍼지지 않게 한다.
        _prior_time = {
            "time_range": prior_intent.time_range if prior_intent is not None else None,
            "active_time_scope": state.active_time_scope,
            "active_time_meta": dict(state.active_time_meta),
        }
        # FE 칩 첨부 동반자를 별칭 인덱스에 병합 — 서버 미등록(게스트·인라인 첨부)이어도
        # 발화 속 첨부 라벨 지칭("남편 사주로")이 need_subject 반복으로 빠지지 않게 한다.
        # 명시 선택(칩)이 텍스트 별칭 해소보다 우선(원칙 7 — 대상 혼동 방지).
        engine = ConversationEngine(
            alias_index=merge_attached_partner(companion_alias_index or {}, partner_ref)
        )
        parsed, state, resolution, _link = engine.process_turn(
            state,
            question,
            today,
            birth_year=birth_year,
            current_month_label=luck_month,
        )
        is_followup_turn = _link.is_follow_up
        # P0 — 턴별 시점 해소 추적(extracted/resolved/excluded/inherited·dialogue_act).
        _logger.debug(
            "turn_trace thread=%s turn=%s trace=%s", thread_id, state.turn_no, parsed.trace
        )
        # 궁합 상대 첨부를 스레드 상태에 미러링(크로스 디바이스 재개 복원용). 매 턴 현재
        # 첨부(없으면 None)로 갱신 — 프론트 첨부/해제가 곧 서버 상태가 된다.
        state.partner = partner_ref
        repeated = state.repeat_count >= 2
        if resolution.unresolved:
            store.save(state)
            return ChatResponse(
                status="need_subject",
                answer=(
                    f"'{', '.join(resolution.unresolved)}'이(가) 어느 분인지 확인이 필요해요. "
                    "등록된 동반자 별칭을 알려주시거나 출생 정보를 입력해 주세요."
                ),
                intents=parsed.intents,
                thread_id=thread_id,
                turn_no=state.turn_no,
            )
    else:
        _prior_time = {}
        parsed = parse_message(
            question,
            today,
            birth_year=birth_year,
            current_month_label=luck_month,
        )
    intent = parsed.intents[0]
    # 규칙이 domain을 못 정한(general) 질문만 임베딩 분류기로 보강(rules-first 보조 — 절대원칙 1·9).
    intent = _augment_domain_by_similarity(intent, question)
    # 규칙이 시점을 못 잡은 경우만 임베딩 시점 분류기로 보강(rules-first, 결정론 날짜 합성).
    intent = _augment_time_by_similarity(intent, question, today, luck_month)
    # 규칙이 비교 mode를 못 잡은 완곡·변형 표현만 유사도로 보강(P3d-2, strict gated·rules-first).
    intent = _augment_companion_mode_by_similarity(intent, question)

    # P2 불변식(2026-07-14) — 배제 기간은 엔진 창이 될 수 없다: 승계·임베딩 시점 보강이
    # 배제 연도를 시점으로 합성하면 시점 미확정으로 되돌린다(명시적 재요청 승격은 대화
    # 엔진이 배제를 이미 해제하므로 여기 도달하는 겹침은 전부 비정상).
    _active_exclusions: list[TimeExclusion] = (
        list(state.time_exclusions) if state is not None
        else [
            TimeExclusion(
                start_year=x.start_year, end_year=x.end_year,
                explicit=x.explicit, reason=x.reason, confidence=x.confidence,
            )
            for x in intent.time_exclusions
        ]
    )
    if _active_exclusions and overlaps_exclusions(
        tr_year_span(intent.time_range), _active_exclusions
    ):
        _logger.warning(
            "배제 기간이 엔진 창에 진입 — 시점 미확정으로 재설정: span=%s thread=%s",
            tr_year_span(intent.time_range), thread_id,
        )
        intent = intent.model_copy(
            update={"time_range": None, "time_scope": TimeScope.TIMELESS}
        )

    # 후속②(2026-07-14) — 결론 요구형 변형 표현 폴백(rules-first): 룰(_CONCLUSION_SEEK_RE)이
    # 못 잡은 완곡 표현("한마디로 돼 안 돼?", "요약 좀")을 유사도로 보강한다. 1차 안전은
    # '후속 턴 + 같은 도메인 + 룰 미확정'이라는 대화 구성 게이트 — 새 질문·도메인 전환은
    # 여기 못 들어온다. conclusion_summary 라벨만 소비(점수·간지·판정 미개입).
    if (
        intent.dialogue_act is None
        and is_followup_turn
        and prior_intent is not None
        and prior_intent.query_type not in (
            QueryType.FEEDBACK_CORRECTION, QueryType.TERMINOLOGY_EDUCATION,
            QueryType.EMOTIONAL_SUPPORT, QueryType.OUT_OF_SCOPE,
        )
        and (intent.domain is prior_intent.domain or intent.domain is Domain.GENERAL)
    ):
        from saju_engines.dialogue_act_similarity import (
            DIALOGUE_ACT_MIN_MARGIN,
            DIALOGUE_ACT_MIN_SCORE,
            get_dialogue_act_classifier,
        )

        _act = get_dialogue_act_classifier().classify(question)
        if (
            _act is not None
            and _act.label == "conclusion_summary"
            and _act.score >= DIALOGUE_ACT_MIN_SCORE
            and _act.margin >= DIALOGUE_ACT_MIN_MARGIN
        ):
            intent = intent.model_copy(update={"dialogue_act": "conclusion_summary"})

    # 직전 풀이 재검토(B) — 이의/반문 + 활성 스레드 분석 맥락이면 canned 폴백 대신 직전 주제를
    # 상속해 정상 분석 경로로 흘리고, recheck 지시문으로 엔진 근거 재검토를 시킨다(subject 확정 시).
    is_recheck = False
    if subject_id is not None:
        intent, is_recheck = _recheck_continuation(intent, prior_intent)
        # 재검토로 분석 전환되면 스레드 맥락(last_intent)도 분석으로 갱신한다 — 다음 턴('그래' 등
        # 약한 후속)이 FEEDBACK_CORRECTION을 상속해 다시 canned로 빠지는 연쇄를 끊는다.
        if is_recheck and state is not None:
            state = state.model_copy(update={"last_intent": intent})

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
        intent = intent.model_copy(update={"event_keys": [*intent.event_keys, EventKey.JOB_GAIN]})

    # 비분석 라우트(T3.8) — 엔진/LLM 미호출.
    plan = build_execution_plan(intent)
    if plan.policy_route is not None:
        _save_thread(store, state)
        return ChatResponse(
            status="policy",
            answer=_POLICY_ANSWERS.get(plan.policy_route, _POLICY_ANSWERS["fixed_policy"]),
            intents=parsed.intents,
            thread_id=thread_id,
            turn_no=state.turn_no if state else None,
            repeated=repeated,
        )

    # P1(계산/실행 분리) — 해소 대상 + 칩 동반자를 병합해 effective_subjects/mode/injection을
    # 계산해 plan에 shadow로 싣는다. 실행 분기(per_subject)는 절대 건드리지 않는다 — 라이브
    # 회귀 0. P2가 subject_injection(execution_enabled)을 소비해 대상별 명식 주입을 켠다.
    plan = _attach_subject_plan(
        plan,
        intent,
        subject_id,
        subject_label,
        partner_ref,
        companion_alias_index,
        question=question,
    )

    # 능력 탐문('너 집 계약 절차 알아?')·절차 질문('계약 순서가 어떻게 돼?') — 사주 질문이
    # 아니므로 명식·이벤트 엔진·LLM을 호출하지 않고 절차 지식팩으로 즉답한다(2026-07-22
    # 데굴님 승인 CAPABILITY_PROBE/PROCEDURE_QUERY — 아는 범위+한계 고지+상담 유도).
    # policy 라우트와 동일 취급이라 질문권 차감 대상이 아니다.
    capability = build_capability_answer(question)
    if capability is not None:
        _save_thread(store, state)
        return ChatResponse(
            status="policy",
            answer=capability,
            intents=parsed.intents,
            thread_id=thread_id,
            turn_no=state.turn_no if state else None,
            repeated=repeated,
        )

    # 지역 오행 사실 질문('창원 성산구의 오행은?') — 사주·시점 무관 단순 조회라 too_broad로
    # 빠지지 않게 엔진 프로파일로 직접 답한다(LLM 미호출, 2026-06-26 데굴님 지적).
    region_fact = _region_element_fact(question)
    if region_fact is not None:
        _save_thread(store, state)
        return ChatResponse(
            status="answered",
            answer=region_fact,
            intents=parsed.intents,
            thread_id=thread_id,
            turn_no=state.turn_no if state else None,
            repeated=repeated,
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
            status=assessment.status,
            answer=answer,
            intents=parsed.intents,
            assessment=assessment,
            thread_id=thread_id,
            turn_no=state.turn_no if state else None,
            repeated=repeated,
            product_suggestion=suggestion,
        )

    # P2b/P3b — companion_only('엄마 사주만')·compare_exclude_self('엄마랑 아빠 궁합'):
    # 본문 분석 base를 동반자(primary)로 교체한다(본인 명식 미사용). self_only/pairwise·
    # per_subject 경로는 불변. 필요한 동반자 birth가 없으면 self로 대체하지 않고 '등록 정보 확인'.
    _inj = plan.subject_injection
    _mode = _inj.mode if _inj is not None else "self_only"
    companion_only = _mode == "companion_only"
    compare_mode = _mode == "compare_exclude_self"
    ranking_mode = _mode == "ranking"
    _RANKING_CAP = 4  # 다자 비교는 앞 4명까지만(초과는 디렉티브에 명시)

    def _companion_birth(cid: str) -> BirthInput | None:
        b = (companion_births or {}).get(cid)
        if b is None and cid == "inline:partner":
            return partner_birth
        return b

    if (
        (companion_only or compare_mode or ranking_mode)
        and _inj is not None
        and _inj.companion_subject_ids
    ):
        _primary = _inj.primary_subject_id or _inj.companion_subject_ids[0]
        # compare/ranking은 비교 대상 모두(ranking은 cap까지), companion_only는 primary 1명.
        if ranking_mode:
            _needed = _inj.companion_subject_ids[:_RANKING_CAP]
        elif compare_mode:
            _needed = _inj.companion_subject_ids
        else:
            _needed = [_primary]
        if any(_companion_birth(c) is None for c in _needed):
            _save_thread(store, state)
            return ChatResponse(
                status="need_subject",
                answer=(
                    "비교할 대상의 출생 정보를 확인할 수 없어요. 등록된 동반자인지 "
                    "확인하시거나 생년월일시를 알려주시면 그 분들 기준으로 봐드릴게요."
                ),
                intents=parsed.intents,
                thread_id=thread_id,
                turn_no=state.turn_no if state else None,
                repeated=repeated,
            )
        _eff = next((e for e in plan.effective_subjects if e.subject_id == _primary), None)
        _pb_birth = _companion_birth(_primary)
        assert _pb_birth is not None  # 위 _needed 검증에서 보장
        birth = _pb_birth
        subject_label = (_eff.label if _eff else partner_label) or "동반자"
        # personalization은 등록 동반자일 때만 그 subject_id로(즉석/미등록은 무개인화).
        subject_id = _primary if (companion_births and _primary in companion_births) else None
        partner_birth = None  # 동반자가 primary — 본인 기준 궁합 오버레이·상대 그룹핑 비활성

    # ── P2-3a 요청 스코프 진행 사실 컨텍스트 ────────────────────────────────
    # subject_id 확정 직후 · 후보 축소 전에 만든다. 저장소 조회와 발화 파싱은 요청당
    # 각 1회이며, 뒤의 커리어 지시문 블록이 같은 준비 결과를 재사용한다 — 각자 읽으면
    # 한 답변 안에서 서로 다른 Episode 상태를 말하게 된다.
    _career_turn, _process_context = _build_request_process_context(
        question, thread_id=thread_id, subject_id=subject_id,
        turn=(state.turn_no if state else None),
    )
    #: 후보별 범위 판정 수집처(감사 전용). 선별에는 쓰이지 않는다 — P2-3c 이후.
    _process_scope_audit: dict = {}

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
    # P0-B4(RELATIONSHIP_EVENT_SYSTEM 부록 C-4) — REL shadow 라이브 배선(관측 전용).
    # 순서: 발화 parse→대상 resolve→decide→apply(이번 turn 반영)→갱신 상태로 컨텍스트
    # 생성→shadow 주입. 실패해도 본 응답 비차단(내부 격리). 첨부 상대 role 연결은
    # P5(관계 유형 확정 경로)에서 — 오귀속 방지 위해 현재는 발화·프로필 소스만.
    _rel_ctxs, _rel_shadow_tel = relationship_shadow.build_relationship_shadow_contexts(
        question=question, state=state, turn=(state.turn_no if state is not None else 0),
        profile_relationship_status=relationship_status,
    )
    if _rel_ctxs:
        _get_scorer().set_risk_shadow_contexts(relationship_contexts=_rel_ctxs)
    all_scored = _get_scorer().score_legacy_personalized(
        result,
        levels=_SCORE_LEVELS,
        fav_override=_fav_override,
        signature=_sig,
        cohort=_cohort,
        occupation_status=occupation_status,
        relationship_status=relationship_status,
        occupation_category=occupation_category,
    )
    # 요청 로컬 위험 스냅샷(감수 62차 P0③) — 본 요청 1차 대상의 주 채점
    # 직후 즉시 확보(불변 tuple). 싱글턴 scorer.risk_shadow는 이후의 보조
    # 채점·동시 요청으로 덮일 수 있어 EXPOSE 경로에서 읽지 않는다.
    _subject_risk_shadow = _get_scorer().take_risk_shadow()
    # P1-6 §12 — 관계 벡터 shadow: 주 채점 직후 불변 projection 확보(이후 보조
    # 채점 year_scored로 tls가 덮이기 전) → Top-N 이전 Draft 생성 + 전체 aggregate
    # 즉시 누적 + 상세 후보만 bounded 보존. 관측 전용(후보·점수·LLM 델타 0) —
    # 실패해도 본 응답 비차단(sidecar 내부 격리). 최종 audit 결합·emit은 payload
    # (Top-N) 확정 이후 단일 지점에서.
    _rel_vec_subject_scope = "self" if subject_id is None else f"companion:{subject_id}"
    _rel_vec_sidecar = None
    _rel_projections: tuple = ()   # beta 노출(슬라이스 1)에서 재사용 — try 실패 대비 초기화
    try:
        _rel_projections = _get_scorer().take_relationship_shadow()
        if _rel_projections:
            _rel_vec_sidecar = relationship_vector_sidecar.build_relationship_effect_accumulator(
                _rel_projections, result,
                dictionaries_dir=_DICTS,
                thread_scope=thread_id or "no-thread",
                turn=(state.turn_no if state is not None else 0),
                subject_scope=_rel_vec_subject_scope,
                input_signature=question,
            )
    except Exception:  # noqa: BLE001 — 관계 벡터 shadow 실패는 본 응답 비차단
        _logger.exception("relationship_vector_sidecar build 실패 — 본 응답 비차단")
        _rel_vec_sidecar = None
    # P0-B4 — 요청 로컬성: 관계 컨텍스트 즉시 해제(싱글턴 잔류·타 요청 오염 방지) +
    # REL 후보 수 계측(텔레메트리 emit은 노출 필터 이후 단일 지점에서).
    if _rel_ctxs:
        _get_scorer().set_risk_shadow_contexts()
    _rel_shadow_tel.risk_candidate_count = sum(
        1 for _c in _subject_risk_shadow
        if str(getattr(_c, "risk_id", "")).startswith("REL_"))

    # E9 Lifestyle — 특정 기간(일/월/연) 총운은 인생 사건이 아니라 생활 슬롯으로
    # 한정한다(2026-06-12 지적). 위계(대운>세운>월>일)에서 상위가 형성한 기운이 하위
    # 기간에서 사건화되며, 점수는 위계 가중 합산. 총운 경로면 거시 이벤트 후보·그래프·
    # 월별 요약을 메인에서 배제해 이직·이사 단정이 새지 않게 한다. 주간은 제외(날 종합).
    period_type = _period_fortune_type(intent, question)
    period_fortune = (
        _build_period_fortune(birth, intent, today, period_type) if period_type else None
    )

    # P5·P6(2026-06-12): 미래지향 질문의 유효 창은 '오늘이 속한 달'에서 시작한다.
    # ① 시점 미지정('이직 제안 들어올까?') → 현재 달 ~ +2년. ② '올해'처럼 연 단위 창이
    # 미래를 포함하면 시작을 현재 달로 클램프 — 이미 지난 1~5월 후보(4월 트리거 등)가
    # 메인에 올라 미래처럼 서술되는 시점 오류를 엔진 차원에서 차단(지난 달은 배경 분리).
    # 과거 회고(event_explanation·과거 키워드)와 명시적 과거 창은 클램프하지 않는다.
    current_month = luck_month  # 절기 기준 당월(양력 today.month의 절기 경계 어긋남 보정)
    # 시간 방향 판정 — 창 전체 과거(구조) > 과거 문구 > 미래 문구, 둘 다 없는 open_when 후속
    # ('월단위로')은 직전 턴 방향(state.last_retro)을 상속해 미래/과거 창을 일관 유지
    # (2026-06-30 시점 정합, 2026-07-21 구조 신호 추가 — _question_time_direction).
    is_retro = _question_time_direction(question, intent, state, today)
    if state is not None:
        state = state.model_copy(update={"last_retro": is_retro})
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
    # 기간 없이 '달/날짜' 입도만 명시한 질문(2026-07-03) — vague_future(연 단위 digest)보다
    # 먼저 판정한다. 택일로 분류된 질문(DATE_RECOMMENDATION)은 기존 택일 라우트가 담당.
    timing_gran = _timing_granularity(question)
    gran_no_period = (
        timing_gran is not None
        and not is_retro
        and not is_structural
        and period_fortune is None
        and not relo_decided
        and (intent.time_range is None or not intent.time_range.start)
        and intent.query_type is not QueryType.DATE_RECOMMENDATION
    )
    # 막연한 시점(특정 연·월 미지정, 미래) → 올해부터 10년 연(세운) 단위 흐름으로 답하고 연도
    # 지정을 유도한다. 현재 연도 12개월로 좁혀 특정 달을 단정하던 결함 보완(2026-06-18 데굴님).
    # 과거 회고·구조 질문·기간총운, 명시 시점(올해/내년/특정연월/향후 N년=start 있음)은 제외.
    # 입도(달/날짜) 명시 질문도 제외(gran_no_period) — 연 나열은 질문 입도와 어긋난다.
    vague_future = (
        period_fortune is None
        and not is_structural
        and not is_retro
        and not relo_decided
        and not gran_no_period
        and (intent.time_range is None or not intent.time_range.start)
    )
    # 답변 지평 정책(2026-07-09 데굴님) — 무시점 미래 질문의 서술 범위를 질문 유형별로
    # 제한한다(즉시형 3개월/전망형 6개월+5년/구조 결정형 원국+대운+5년+3개월/분야 기본).
    # None = 명시적 장기 질문(대운·인생 흐름)만 — 그 경우에만 기존 10년 digest 유지.
    horizon = resolve_horizon(question, intent) if vague_future else None
    year_digest_years: list[int] = []
    year_result = result  # 세운 10년 확장본(기본 창 밖 연도 온디맨드 보강)
    year_scored = all_scored
    if horizon is not None:
        if horizon.years_span:
            year_digest_years = list(range(today.year, today.year + horizon.years_span))
            default_period = (current_month, str(today.year + horizon.years_span - 1))
        else:
            default_period = (current_month, month_add(current_month, horizon.months_detail))
    elif vague_future:
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
                    year_result,
                    levels={GanjiLevel.YEAR},
                    fav_override=_fav_override,
                    signature=_sig,
                    cohort=_cohort,
                    occupation_status=occupation_status,
                    relationship_status=relationship_status,
                    occupation_category=occupation_category,
                )

    if period_fortune is not None or is_structural:
        candidates = []
        bundles = []
    elif horizon is not None:
        # 지평 창 내 후보만 — 월 후보는 상세 창(N개월), 연 후보는 연 span 내.
        # 즉시형·분야기본(years_span=0)은 연 후보를 빼서 장기 서술 재료 자체를 차단.
        _m_end = month_add(current_month, horizon.months_detail)
        _y_hi = today.year + horizon.years_span - 1 if horizon.years_span else None

        def _in_horizon(period: str) -> bool:
            if len(period) == 7:
                return current_month <= period < _m_end
            if len(period) == 4 and _y_hi is not None:
                return today.year <= int(period) <= _y_hi
            return False

        candidates = [c for c in all_scored if _in_horizon(c.period)]
        candidates = _get_intent_filter().filter(candidates, str(intent.domain))
        scope_h: list[EventKey] = plan.graph_scope or [c.event_key for c in candidates[:5]]
        bundles = _get_graph().retrieve(scope_h)
    elif vague_future:
        # 세운(연) 중심 — 월 후보는 빼서 LLM이 10년 연 단위 흐름에 집중하게 한다.
        lo, hi = str(today.year), str(today.year + 9)
        candidates = [c for c in year_scored if len(c.period) == 4 and lo <= c.period <= hi]
        candidates = _get_intent_filter().filter(candidates, str(intent.domain))
        scope_v: list[EventKey] = plan.graph_scope or [c.event_key for c in candidates[:5]]
        bundles = _get_graph().retrieve(scope_v)
    else:
        # 원거리 시점 창(2026-07-23): 질문 창이 기본 세운 창(올해±5)을 벗어나면
        # 해당 연도 세운을 온디맨드로 채워 **실제 채점 근거**를 만든다 — 나이
        # 기반 질문("88세쯤" → 2067~2069)이 빈 후보로 '신호 없음' 서술되던
        # 결함 방지. vague_future 경로와 동일한 결정론 재계산(창 상한 12년).
        _far_span = tr_year_span(intent.time_range)
        if _far_span is not None and result.luck_cycles is not None:
            _have_years = {pl.label for pl in result.luck_cycles.yearly_luck}
            _lo_y, _hi_y = _far_span
            # 개방형 창("80세 이후" 등 end 미상)은 시작 연도 단일점으로
            # 붕괴하지 않고 10년 범위를 훑어 시기 탐색 근거를 만든다.
            if (intent.time_range is not None
                    and intent.time_range.start
                    and not intent.time_range.end):
                _hi_y = max(_hi_y, _lo_y + 9)
            _fill_years = [
                y for y in range(_lo_y, min(_hi_y, _lo_y + 11) + 1)
                if str(y) not in _have_years]
            if _fill_years:
                _far_extra = luck_years(chart_birth, _fill_years)
                _far_result = result.model_copy(deep=True)
                assert _far_result.luck_cycles is not None
                _far_result.luck_cycles.yearly_luck = (
                    list(_far_result.luck_cycles.yearly_luck) + _far_extra)
                _far_scored = _get_scorer().score_legacy_personalized(
                    _far_result,
                    levels={GanjiLevel.YEAR},
                    fav_override=_fav_override,
                    signature=_sig,
                    cohort=_cohort,
                    occupation_status=occupation_status,
                    relationship_status=relationship_status,
                    occupation_category=occupation_category,
                )
                _seen_far = {(c.event_key, c.period) for c in all_scored}
                all_scored = all_scored + [
                    c for c in _far_scored
                    if (c.event_key, c.period) not in _seen_far]
                # 이후 직렬화(간지 lookup 등)도 확장된 세운을 보도록 요청
                # 로컬 사본으로 교체 — LRU 캐시 원본은 불변 유지.
                result = _far_result
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
                tz_w = result.time_correction.timezone if result.time_correction else "Asia/Seoul"
                solar_m = _current_luck_month(date.fromisoformat(win_start), tz_w)

            def _in_win(period: str) -> bool:
                if solar_m is not None and len(period) == 7:  # 월 후보 — 절기월만
                    return period == solar_m
                return in_question_range(period, win_start, win_end)

            seen = {(c.event_key, c.period) for c in candidates}
            candidates += [
                c for c in all_scored if (c.event_key, c.period) not in seen and _in_win(c.period)
            ]
            # 단일일 질문 — 다른 절기월의 월 후보를 제거한다(2026-07-22 실로그: 계층 필터
            # Top-N이 미리 뽑은 '현재 진행 중' 乙未월(2026-07) 이사 후보가 7/4(甲午월=
            # 2026-06 소속) 질문 입력에 남아 답이 '7월 운' 중심으로 서술되던 결함 —
            # 위 solar_m 게이트는 '추가'만 거르고 기존 후보는 안 걸렀다). 연 후보는 유지.
            if solar_m is not None:
                candidates = [
                    c for c in candidates if len(c.period) != 7 or c.period == solar_m
                ]
        # 의도 필터(intent_event_filter) — 질문 도메인과 무관한 후보를 억제한다.
        # 빈 결과를 만들지 않으며(fallback 원본 유지), general 도메인은 전부 통과.
        candidates = _get_intent_filter().filter(candidates, str(intent.domain))
        # Graph Retrieval — plan의 graphScope만(전체 검색 금지).
        scope: list[EventKey] = plan.graph_scope or [c.event_key for c in candidates[:5]]
        bundles = _get_graph().retrieve(scope)

    # 후속①(2026-07-14) — 배제 기간의 이벤트 후보를 산출 단계에서 제외한다. 서술 차단
    # 지시문만으로는 후보·근거가 LLM 입력에 남아 배제 연도가 재언급될 여지가 있다.
    if _active_exclusions and candidates:
        _n_before = len(candidates)
        candidates = _drop_excluded_candidates(candidates, _active_exclusions)
        if len(candidates) != _n_before:
            _logger.debug(
                "배제 기간 이벤트 후보 %d건 제외(thread=%s)",
                _n_before - len(candidates), thread_id,
            )

    # P4: 월 단위·시기 특정 요청이면 12개월 요약 동반 — '몇 월/언제' 질문엔 월운이 답이라
    # 세운만으로 답을 회피('달 특정 불가')하지 않도록 월별 표를 보장한다(2026-06-12 지적).
    overview = None
    gran_month = intent.time_range is not None and intent.time_range.granularity.value == "month"
    # P1(2026-06-14): 사건형 intent(이사·이직 등)는 '월별'을 명시 안 해도 내부는 월단위로 계산
    # (연 질문도 12개월 후보를 봐야 강한 달을 짚는다). monthly_explicit이면 표 전체, 아니면
    # 연간 요약+핵심 달로 응답하도록 아래에서 형식 지시를 준다.
    event_monthly = intent.event_key is not None and str(intent.event_key) in _EVENT_MONTHLY
    monthly_explicit = any(k in question for k in ("월별", "달별", "매월", "월운", "월단위"))
    wants_monthly = (
        period_fortune is None
        and not vague_future
        and not relo_decided
        and (
            monthly_explicit
            or event_monthly
            or gran_no_period  # 기간 미지정 '달/날짜' 입도 질문 — 월별 흐름이 답의 재료
            or intent.query_type is QueryType.TIMING_SEARCH
            or gran_month
            or any(k in question for k in ("몇 월", "몇월", "언제", "어느 달"))
            or any(k in question for k in ("앞으로", "향후", "다가오는", "1년 내", "1년내"))
        )
    )
    result_for_llm = result  # on-demand 월운 주입 시 교체(간지·해석 lookup 커버용)
    if horizon is not None and result.luck_cycles is not None:
        # 지평 결합 표 — 앞 N개월 월 단위 흐름 + (span 있으면) 5년 연 단위 요약.
        # 월운은 롤링 창이 연 경계를 넘을 수 있어 닿는 연도별로 on-demand 계산.
        horizon_months = _rolling_months(
            int(luck_month[:4]), int(luck_month[5:7]), horizon.months_detail
        )
        monthly_all = []
        for yr in sorted({int(mm[:4]) for mm in horizon_months}):
            monthly_all += luck_months(chart_birth, yr)
        result_win = result.model_copy(deep=True)
        assert result_win.luck_cycles is not None
        result_win.luck_cycles.monthly_luck = monthly_all
        scored_win = _get_scorer().score_legacy(
            result_win,
            levels={GanjiLevel.MONTH},
            fav_override=_fav_override,
        )
        labels = list(horizon_months)
        if year_digest_years:
            avail_y = {pl.label for pl in result_win.luck_cycles.yearly_luck}
            labels += [str(y) for y in year_digest_years if str(y) in avail_y]
        year_cands = [c for c in all_scored if len(c.period) == 4]
        overview = build_monthly_overview(result_win, scored_win + year_cands, months=labels)
        if not any(r.score is not None for r in overview):
            overview = None  # 신호 전무한 빈 표는 회피 유발 — 미부착
        # 창 내 월 후보를 메인 후보에도 보존(표와 근거 경로가 같은 달을 가리키게).
        win_set = set(horizon_months)
        seen_h = {(c.event_key, c.period) for c in candidates}
        candidates += [
            c for c in scored_win if c.period in win_set and (c.event_key, c.period) not in seen_h
        ]
        result_for_llm = result_win
    elif vague_future and year_result.luck_cycles is not None:
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
                str(y)
                for y in range(today.year - 10, today.year + 1)
                if str(y) in have  # 세운 데이터 있는 연도만(거짓 '정보 없음' 행 방지)
            ]
            overview = build_monthly_overview(result, all_scored, months=years)
        elif start_label and len(start_label) == 10:
            # 상대 기준 앵커(YYYY-MM-DD = '앞으로/향후 1년' 등) — 그 달부터 12개월 롤링.
            window_months = _rolling_months(int(start_label[:4]), int(start_label[5:7]))
        elif (
            start_label
            and end_label
            and len(start_label) == 7
            and len(end_label) == 7
            and start_label != end_label
        ):
            # 다중 월 창('지난 1년'=직전 12개월 등, 2026-06-12) — 질문 창 그대로 월별 표.
            window_months = _months_between(start_label, end_label)
        elif start_label and len(start_label) >= 4:
            # 명시 연·월('2025년 8월', '2025') — 해당 달력 연도.
            target_year = int(start_label[:4])
        elif gran_no_period or any(
            k in question for k in ("앞으로", "향후", "다가오는", "1년 내", "1년내")
        ):
            # 시점 미지정 상대-미래(+기간 없는 '달/날짜' 입도 질문) — 오늘(기준 시점)의
            # 달부터 12개월 롤링(2026-06-12 지적: 달력상 1~12월이 아니라 오늘 기준 롤링
            # 창이어야 한다). 절기 기준 당월에서 시작. '달은 언제' 질문이 올해 달력 연도로
            # 좁혀지던 회귀 방지(2026-06-18 결정과 동일 취지).
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
                result_win,
                levels={GanjiLevel.MONTH},
                fav_override=_fav_override,
            )
            overview = build_monthly_overview(result_win, scored_win, months=window_months)
            # 창 내 월 후보(기본 월운 범위 밖 과거 달 포함)를 메인 후보에도 보존 —
            # '재취업한 달은 언제' 류에서 표와 근거 경로가 같은 달을 가리키게(2026-06-12).
            win_set = set(window_months)
            seen_c = {(c.event_key, c.period) for c in candidates}
            candidates += [
                c
                for c in scored_win
                if c.period in win_set and (c.event_key, c.period) not in seen_c
            ]
            # 간지 lookup·incoming_note(천간 용기신 역할)가 창 월을 커버하게 —
            # 누락 시 '癸(水 구신)' 같은 불리 정보가 월 후보에서 사라진다(2026-06-12).
            result_for_llm = result_win
        else:
            # 과거/범위 밖 연도면 그 해 월운을 on-demand로 계산·스코어해서
            # 빈 표('정보 없음' 회피)를 막는다(2026-06-12 지적).
            assert target_year is not None
            # 대상 연도의 12개월이 '전부' monthly_luck에 있어야 result를 그대로 쓴다 — 기존엔
            # 그 해 한 달(예: 2027-01)만 있어도 커버로 오판해 나머지 달이 빈 간지→'입춘 전'
            # 오라벨로 새던 결함(2026-07-01 데굴님 지적). 부분 커버면 그 해 월운을 온디맨드 계산.
            have_months = {p.label for p in result.luck_cycles.monthly_luck}
            if all(f"{target_year}-{m:02d}" in have_months for m in range(1, 13)):
                overview = build_monthly_overview(result, all_scored, year=target_year)
            else:
                # 그 해 세운의 월운(입춘~ 절기월, 예: 2027-02~2028-01)을 온디맨드 계산하되,
                # 기존 창에 있던 그 해 달력월(예: 2027-01 = 전년 세운 끝자락)도 보존해 1~12월을
                # 빠짐없이 채운다(2026-07-01 데굴님 지적: 2027-01만 있고 02~12가 '입춘 전'으로 샘).
                by_label = {p.label: p for p in luck_months(chart_birth, target_year)}
                for p in result.luck_cycles.monthly_luck:
                    if p.label.startswith(f"{target_year}-"):
                        by_label.setdefault(p.label, p)
                year_months = [by_label[k] for k in sorted(by_label)]
                result_year = result.model_copy(deep=True)
                assert result_year.luck_cycles is not None
                result_year.luck_cycles.monthly_luck = year_months
                scored_year = _get_scorer().score_legacy(
                    result_year,
                    levels={GanjiLevel.MONTH},
                    fav_override=_fav_override,
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
                    birth,
                    partner_birth,
                    intent,
                    today,
                    subject_label or "본인",
                    partner_label or "상대",
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
        _structural_context(result, intent, today, question) if not plan.per_subject else None
    )
    # 이사 평가 질문('이사하면 어때?' — 택일 아님)은 date_block이 없으므로, 십성 이사 이유분류를
    # 구조 블록에 실어 '무슨 십성이라 이런 이사' 서술을 가능케 한다(2026-06-18 결함 보완).
    if structural is not None and _is_relocation_intent(intent):
        structural = structural + _relocation_reason_context(birth, intent, today)
        # 목적지 지역이 명시되면 지역 오행 × 용신 궁합도 함께 surface(2026-06-18 보완).
        structural = structural + _relocation_region_context(birth, intent, today)
        # 목적지 미지정/시도·수도권 범위면 시군구 후보를 매칭·랭킹해 추천(P4-A 배선, 2026-06-26).
        structural = structural + _region_recommendation_context(birth, intent, today)
    # 토픽 질문(직업·재물·건강·시험·연애)은 해당 Topic Builder 모듈을 실행해 확정 신호·정책 톤
    # 주입(옵션1 채팅 배선, 2026-06-26). relocation은 위 지역/이사 경로가 담당.
    if structural is not None and not _is_relocation_intent(intent):
        # 미래지향 질문(비회고)은 토픽 참고 신호도 현재 달부터 — 지난 달 노출 차단(시점 정합).
        _floor = current_month if (not is_retro and current_month) else None
        structural = structural + _topic_module_context(birth, intent, today, _floor)
    # 주간(일 범위) 질문은 7일 일별 일운을 surface — 월운으로 뭉뚱그려지던 결함 보완(2026-06-18).
    if structural is not None and _is_day_range(intent):
        structural = structural + _weekly_overview_lines(birth, intent, today)
    # 막연한 시점 → 10년 연 단위 흐름의 대운 배경·교운기를 구조 블록에 실어 LLM이 반영하게 한다.
    if structural is not None and vague_future and year_digest_years:
        span = _daewoon_span_context(year_result, year_digest_years[0], year_digest_years[-1])
        if span:
            structural = structural + [span]
    # P2a — pairwise(본인+동반자 1명)이고 동반자 birth가 확보되면 대상별 명식 블록을 가산 주입.
    # per_subject/chat_compare는 건드리지 않는다(본인 base 유지). birth 없으면 블록 생략(본인
    # 명식으로 대체하지 않음 — 기존 pairwise 경로 그대로). companion_only 등은 P2b 이후.
    subject_blocks: list[SubjectBlock] = []
    relationship_context: RelationshipContext | None = None
    ranking_truncated = False
    _inj = plan.subject_injection
    if _inj is not None and _inj.mode == "pairwise" and len(_inj.companion_subject_ids) == 1:
        _cid = _inj.companion_subject_ids[0]
        _comp_birth = (companion_births or {}).get(_cid)
        if _comp_birth is None and _cid == "inline:partner":
            _comp_birth = partner_birth
        if _comp_birth is not None:
            _comp_result = calculate(_comp_birth.model_copy(update={"reference_date": today}))
            _eff = next((e for e in plan.effective_subjects if e.subject_id == _cid), None)
            # P3a — 관계유형 추론(질문 키워드 > relation_to_user > 도메인 > unknown).
            _rtype, _rbasis = infer_relation_type(
                question,
                _eff.relation_to_user if _eff else None,
                [str(d) for d in intent.domains],
            )
            # P3d-3 — unknown이면 유사도로 관점 힌트만 보강(실행 경로 불변, rules-first).
            _rtype, _rbasis = augment_relation_type(_rtype, _rbasis, question, has_companion=True)
            subject_blocks, relationship_context = _pairwise_subject_blocks(
                _inj,
                result,
                _comp_result,
                self_label=subject_label,
                companion_label=(_eff.label if _eff else partner_label),
                relation_type=_rtype,
                relation_basis=_rbasis,
                year=today.year,
            )
            plan = plan.model_copy(
                update={
                    "subject_injection": _inj.model_copy(update={"execution_enabled": True}),
                }
            )
    elif compare_mode and _inj is not None and len(_inj.companion_subject_ids) == 2:
        # P3b — 동반자끼리(A=base 이미 교체, B는 블록). 본인 미포함. birth는 base-swap에서 검증됨.
        _pa = _inj.primary_subject_id or _inj.companion_subject_ids[0]
        _pb = next(c for c in _inj.companion_subject_ids if c != _pa)
        _b_birth = _companion_birth(_pb)
        if _b_birth is not None:
            _b_result = calculate(_b_birth.model_copy(update={"reference_date": today}))
            _effa = next((e for e in plan.effective_subjects if e.subject_id == _pa), None)
            _effb = next((e for e in plan.effective_subjects if e.subject_id == _pb), None)
            _rtype, _rbasis = infer_relation_type(question, None, [str(d) for d in intent.domains])
            # P3d-3 — 두 동반자 관계는 relation_to_user 없음 → unknown이면 유사도로 힌트 보강.
            _rtype, _rbasis = augment_relation_type(_rtype, _rbasis, question, has_companion=True)
            subject_blocks, relationship_context = _compare_subject_blocks(
                _inj,
                result,
                _b_result,
                primary_label=(_effa.label if _effa else "대상1"),
                other_label=(_effb.label if _effb else "대상2"),
                other_subject_id=_pb,
                relation_type=_rtype,
                relation_basis=_rbasis,
                year=today.year,
            )
            plan = plan.model_copy(
                update={
                    "subject_injection": _inj.model_copy(update={"execution_enabled": True}),
                }
            )
    elif ranking_mode and _inj is not None and len(_inj.companion_subject_ids) >= 3:
        # P3c-2 — 다자 비교(동반자 3~4명, 본인 미포함). A=primary(base 교체), 나머지는 블록.
        _capped = _inj.companion_subject_ids[:_RANKING_CAP]
        _truncated = len(_inj.companion_subject_ids) > _RANKING_CAP
        _pa = _inj.primary_subject_id or _capped[0]

        def _label_of(cid: str) -> str:
            e = next((x for x in plan.effective_subjects if x.subject_id == cid), None)
            return e.label if e else "대상"

        _others: list[tuple[str, str, ManseV2Result]] = []
        for _cid in _capped:
            if _cid == _pa:
                continue
            _cb = _companion_birth(_cid)
            if _cb is None:
                continue
            _others.append(
                (
                    _cid,
                    _label_of(_cid),
                    calculate(_cb.model_copy(update={"reference_date": today})),
                )
            )
        subject_blocks, relationship_context = _ranking_subject_blocks(
            _inj,
            result,
            _label_of(_pa),
            _others,
            year=today.year,
        )
        ranking_truncated = _truncated
        plan = plan.model_copy(
            update={
                "subject_injection": _inj.model_copy(update={"execution_enabled": True}),
            }
        )
    # P3c-1 — 경쟁 비교: pairwise/compare 실행 경로는 그대로 두고 관계맥락을 competition으로,
    # 안전 가드를 승부 단정 금지로 교체(승률·순위·당락 산출 금지). 대상 2명일 때만.
    competition_active = False
    if relationship_context is not None and is_competition(question):
        relationship_context = relationship_context.model_copy(
            update={
                "mode": "competition",
                "safety_guards": list(COMPETITION_SAFETY_GUARDS),
            }
        )
        competition_active = True
    # 총운 다변화(2026-07-14) — 총운형 멀티도메인 질문만 의미 클러스터링+품질 게이트
    # 선별을 쓴다(한 사건이 기간만 바꿔 Top5를 독점 → 단일 도메인 쏠림 답변 차단).
    _overview_mode = _is_overview_multi_domain(intent, question)
    payload = build_llm_input(
        question,
        intent,
        result_for_llm,
        candidates,
        bundles,
        _get_scorer(),
        call_type="chat_compare" if plan.per_subject else "chat_single",
        today=today,
        monthly_overview=overview,
        period_fortune=period_fortune,
        date_selection=date_block,
        is_followup_turn=is_followup,
        default_period=default_period,
        prior_claims=prior_claims,
        current_month_label=luck_month,
        current_month_detail=_current_luck_month_detail(
            chart_birth,
            today,
            result.time_correction.timezone if result.time_correction else "Asia/Seoul",
        ),
        structural_context=structural,
        subject_blocks=subject_blocks,
        relationship_context=relationship_context,
        # 물상(2단계 프로필) 사실 맥락 — 질문 도메인 관련 항목만 풀이에 사실로 주입.
        profile_facts=profile_facts_for(
            subject_id, str(intent.domains[0]) if intent.domains else "general"
        ),
        overview_mode=_overview_mode,
        # P2-3a — 축소 전에 후보 범위를 산출한다. 플래그 OFF 동안 선별·출력 불변.
        process_context=_process_context,
        process_scope_audit=_process_scope_audit,
        # P2-3b — dual-run 결과를 redacted JSONL로 적재한다(질문 원문 미저장).
        audit_context=_dual_run_audit_context(
            thread_id=thread_id, subject_id=subject_id, question=question,
            turn=(state.turn_no if state else None), intent=intent,
            prepared=_career_turn,
        ),
    )
    call_type = "chat_compare" if plan.per_subject else "chat_single"

    # P1-6 §12 — 관계 벡터 shadow 최종화(reducer 이후 단일 지점): production Top-N
    # (payload.event_candidates)이 확정된 지금, 상세 Draft에만 legacy audit/rank를
    # 결합해 Envelope finalize → allowlist batch 1회 emit → sidecar 폐기. 관측 전용
    # (payload·후보·점수 무변경). 실패해도 본 응답 비차단.
    if _rel_vec_sidecar is not None:
        try:
            _rel_envelopes = relationship_vector_sidecar.finalize_relationship_envelopes(
                _rel_vec_sidecar.accumulator.detailed_drafts,
                subject_scope=_rel_vec_subject_scope,
                all_scored=list(all_scored),
                pre_reduce_candidates=list(candidates),
                final_candidates=list(payload.event_candidates),
            )
            _rel_vec_batch = relationship_vector_telemetry.build_batch_from_accumulator(
                _rel_vec_sidecar.accumulator, _rel_envelopes,
                period_failure_counts=_rel_vec_sidecar.period_failure_counts,
            )
            relationship_vector_telemetry.emit_batch(_rel_vec_batch)
            # P1-7d-lite — legacy 비교 coarse aggregate(관측 전용·delta 없음): 상세
            # envelope(벡터+audit)에서 후보 coverage·분포만 집계해 emit. 상세 legacy
            # 비교(cap·blind spot)는 결정적 harness 전담(라이브는 relation_delta None).
            _rel_cmp_agg = (
                relationship_legacy_comparison.build_comparison_prod_aggregate(
                    _rel_envelopes))
            relationship_legacy_comparison.emit_comparison_prod_aggregate(_rel_cmp_agg)
        except Exception:  # noqa: BLE001 — 관계 벡터 telemetry 실패는 본 응답 비차단
            _logger.exception("relationship_vector telemetry finalize 실패 — 본 응답 비차단")
        finally:
            _rel_vec_sidecar = None  # sidecar 폐기(요청 내 ephemeral — §8)

    # 직렬화 본문 뒤에 덧붙는 후행 지시문·시스템 프롬프트를 먼저 모은다 — 이 고정 오버헤드를
    # 토큰 가드 예약분으로 넘겨야 컨텍스트 축소기가 '실제 총 입력(payload+오버헤드)' 기준으로
    # 줄인다. 안 그러면 serialize 통과 후 지시문·시스템이 더해져 generate_reading 재검사에서
    # 한도 초과 → 일반 오류로 마감되던 결함(2026-06-18, 10년 이사 질문 12,098tok 초과).
    trailing: list[str] = [
        _CHAT_SCOPE_DIRECTIVE,
        GONGMANG_ACTIVATION_DIRECTIVE,
        # 추상 불확실성 문구('가능성 열림·조건 확인 필요') 금지 — 상시(2026-07-22 P0,
        # structural_context 공용 — 테마 리포트 전 섹션 prefix에도 동일 적용).
        UNCERTAINTY_TRANSLATION_DIRECTIVE,
        # 근거 밖 사건 창작·저신뢰 정밀 단정·억지 긍정 보완 금지 — 상시(P4, 리포트 공용).
        EVIDENCE_FIDELITY_DIRECTIVE,
        # 질문 무관 성격 칭찬 서두 금지 — 상시(2026-07-22, 리포트 공용).
        BARNUM_SUPPRESSION_DIRECTIVE,
    ]
    # 관계 신호 beta 노출(슬라이스 1 — 테스터 피드백용, RELATIONSHIP_BETA_EXPOSE 플래그).
    # 플래그 off면 이 분기가 실행되지 않아 기존 출력 byte-identical. 관계·결혼 질문일 때만
    # 질문 창 기간의 관계 벡터 3축(평가분)을 beta 블록으로 주입 + 단정 금지 가드. 미평가
    # 4축(성사·공식화 등)은 노출하지 않는다. 실패해도 본 응답 비차단.
    if (relationship_shadow.RELATIONSHIP_BETA_EXPOSE
            and _rel_projections and _is_relationship_context(intent, question)):
        try:
            _beta_signals = relationship_vector_sidecar.build_relationship_beta_signals(
                _rel_projections, result, dictionaries_dir=_DICTS,
                window=default_period)
            _beta_block = _relationship_beta_block(_beta_signals)
            if _beta_block:
                trailing.append(_beta_block)
                trailing.append(_RELATIONSHIP_BETA_DIRECTIVE)
        except Exception:  # noqa: BLE001 — beta 노출 실패는 본 응답 비차단
            _logger.exception("relationship beta 블록 생성 실패 — 본 응답 비차단")
    # 관계 위험 dev beta 노출(슬라이스 3 — RELATIONSHIP_RISK_BETA_EXPOSE, dev 전용 우회).
    # production 위험 노출 파이프라인(RISK_ENGINE_MODE=expose·manifest·HMAC)은 건드리지
    # 않고, strip이 제거하는 live 관계 유래 위험 후보만 별도로 골라 도메인·밴드 수준 beta
    # 블록으로 보여준다. 플래그 off면 미실행 → byte-identical. 실패해도 본 응답 비차단.
    if (relationship_shadow.RELATIONSHIP_RISK_BETA_EXPOSE
            and _rel_ctxs and _is_relationship_context(intent, question)):
        try:
            _rel_risk_cands = (
                relationship_shadow.select_live_relationship_risk_candidates(
                    list(_subject_risk_shadow)))
            _risk_beta_block = _relationship_risk_beta_block(_rel_risk_cands)
            if _risk_beta_block:
                trailing.append(_risk_beta_block)
                trailing.append(_RELATIONSHIP_RISK_BETA_DIRECTIVE)
        except Exception:  # noqa: BLE001 — beta 노출 실패는 본 응답 비차단
            _logger.exception("relationship risk beta 블록 생성 실패 — 본 응답 비차단")
    # 사용자 제공 사실 원장(P0, 2026-07-22) — 이전 턴들에서 사용자가 직접 밝힌 사실을
    # compact 블록으로 주입해 모순 서술·되묻기를 차단한다(원문 전체 상속 없이 연속성 보존.
    # user_explicit만 저장되므로 엔진·LLM 산출물 오염 없음. 상한 20k→22k 상향분이 흡수 —
    # 2026-07-22 데굴님 승인).
    if state is not None:
        _facts_block = user_facts_block(state.user_facts)
        if _facts_block:
            trailing.append(_facts_block)
            _logger.debug(
                "user_facts injected thread=%s n=%d", thread_id, len(state.user_facts)
            )
    # 회고 질문 — 전체 답변 시제를 과거 추정형으로 강제(미래 예측 표현 차단, 2026-07-21).
    if is_retro:
        trailing.append(_RETRO_TENSE_DIRECTIVE)
    # P2b — companion_only: 이 풀이의 대상이 본인이 아니라 동반자임을 못박는다(본인 명식 혼동 차단).
    if companion_only:
        trailing.append(
            f"[분석 대상] 이 풀이의 대상은 '{subject_label}'(동반자) 한 사람입니다. "
            "본인(질문자)이 아니라 이 분의 명식·운을 기준으로 답하고, 호칭도 이 분 기준으로 "
            "서술하세요. 본인 명식과 섞지 마세요."
        )
    # P3b — compare_exclude_self: 본인이 아니라 두 동반자의 관계 비교임을 못박는다(본인 배제).
    elif compare_mode:
        trailing.append(
            "[분석 대상] 이 풀이는 질문자 본인이 아니라 두 동반자의 관계 비교입니다. "
            "본인 명식을 끌어들이지 말고 [함께 보기]의 두 대상만으로 협력·충돌·보완을 "
            "설명하세요. 누가 더 낫다는 우열·승패로 단정하지 마세요."
        )
    # P3c-1 — 경쟁 비교: 승패·당락 확정 금지, 조건부 유리 요인·부담·보완 중심(절대원칙 8).
    if competition_active:
        trailing.append(
            "[경쟁 비교 지침] 승패·우승·합격·당락을 확정하지 말고, 승률·확률·점수·순위도 "
            "만들지 마세요. 두 대상 각각의 강점·부담 요인·리스크·준비 포인트를 나누어 설명하고, "
            "비교가 필요하면 '이 조건에서는 A 쪽 신호가 강하고 B는 이런 보완이 필요하다'처럼 "
            "조건부로만 말하세요. 결론은 결과 보장이 아니라 준비 전략·조율 포인트로 정리하세요."
        )
    # P3c-2 — 다자 비교: 순위 산출이 아니라 항목별 조건부 상대 경향(절대원칙 8).
    if ranking_mode:
        _rank_dir = (
            "[다자 비교 지침] 이 요청은 여러 사람을 조건별로 비교하는 요청이지, 절대 순위를 "
            "확정하는 요청이 아니다. 1등/2등/꼴찌 같은 순위 단정, 점수화, 확률화, 승률 산출을 하지 "
            "말 것. 추진력, 안정성, 관계 조율력, 재물 관리, 리스크 감수 성향 등 항목별 상대 경향만 "
            "설명할 것."
        )
        if ranking_truncated:
            _rank_dir += " (대상이 많아 등록 순 최대 4명까지만 반영했다.)"
        trailing.append(_rank_dir)
    # 직전 풀이 재검토(B) — 이의/반문 후속이면 엔진 근거로 재검토하도록 지시(출생정보 재요청 금지).
    if is_recheck:
        trailing.append(_RECHECK_DIRECTIVE)
    # P2 — 시점 제약 구조화 전달: 확정 시점 + 배제 기간 + 서술 금지(2026-07-14).
    if _active_exclusions:
        trailing.append(_time_exclusion_directive_text(intent, _active_exclusions))
    # P4 — 결론 요약 모드: 새 월별 분석 대신 직전 분석 압축 결론(1문장 결론→확실성→근거→조건).
    if intent.dialogue_act == "conclusion_summary":
        trailing.append(_CONCLUSION_SUMMARY_DIRECTIVE)
    # 총운 다변화 P2(2026-07-14) — 조망 서술 계약: 후보 존재 영역만, 집중은 집중으로
    # 명시, 미선정 영역은 '신호 없음' 단정 금지·생략.
    if _overview_mode:
        trailing.append(_OVERVIEW_COVERAGE_DIRECTIVE)
    # P5 — 분석 대상이 목표 연도에 미성년이면 성인 사건 서사를 연령 적합 표현으로 변환.
    _minor_dir = _minor_lifestage_directive_text(birth, intent, today)
    if _minor_dir is not None:
        trailing.append(_minor_dir)
    # 선발·배치(selection_allocation) 풀이 보조(2026-07-14 설계, shadow-first) — 군입대·
    # 청약·배정 등 추첨형 질문이면 단계별 성립도 + 무작위성 표현 정책을 주입한다.
    # 기존 후보 산출·점수·실행 경로는 불변(설명 보조 전용). 결론 요구형 후속이면
    # 초점 단계만 요약하도록 위 결론 요약 모드와 자연 결합된다.
    _sel_q = detect_selection_query(
        question, prior_text=prior_answer if is_followup_turn else None
    )
    if _sel_q is not None:
        from saju_engines.selection_allocation import (
            analyze_selection_allocation,
            format_selection_reading_block,
            rank_timing_windows,
        )

        _sel_reading = analyze_selection_allocation(
            result, domain=_sel_q.domain, focus_stage=_sel_q.stage,
            objective_odds=_sel_q.odds,
        )
        # 상대 유리 창(잔여 ③) — 향후 12개월 월운의 초점 단계 신호 유입 스윕.
        # 결과 보장 아님(relative_timing_comparison 허용 범위) — 실패 시 무창.
        try:
            _sel_months = [
                lp for lp in (
                    luck_months(birth, today.year) + luck_months(birth, today.year + 1)
                )
                if lp.label >= luck_month
            ][:12]
            _sel_windows = rank_timing_windows(_sel_months, _sel_q.stage)
        except ValueError:
            _sel_windows = []
        _sel_block = format_selection_reading_block(_sel_reading, _sel_windows)
        if _sel_q.waitlist_focus:
            _sel_block += (
                " 사용자가 대기·재지원 시나리오를 물었으므로 대기 순번 전환과 다음 "
                "회차 흐름을 중심에 두고 답하라."
            )
        trailing.append(_sel_block)
    # 성향 반박('풀이에는 그렇다는데 나는 아니다') — 수용·정적 vs 작동 재해석·확인 질문
    # (상담 사례 파생 P0-7 — 상담사가 회피하던 지점을 명시 규칙화).
    if _is_trait_mismatch(question):
        trailing.append(TRAIT_FEEDBACK_DIRECTIVE)
    # 선택형(비교·의사결정) 질문 — 결론(권고 방향) 선제시 후 근거(상담 사례 파생 P0-1).
    if intent.query_type in (QueryType.COMPARISON, QueryType.DECISION_SUPPORT):
        trailing.append(CONCLUSION_FIRST_DIRECTIVE)
    # 개운/보완 질문 — 결핍·기신은 극복 아니라 관리 프레임(상담 사례 파생 P0-4).
    if intent.query_type is QueryType.REMEDY:
        trailing.append(MANAGE_NOT_OVERCOME_DIRECTIVE)
    # 규범 당위형 질문('결혼 꼭 해야 하나') — 사회적 정답 강요 차단(상담 사례 파생 P0-3).
    if _is_normative_question(question):
        trailing.append(NON_NORMATIVE_REASSURANCE_DIRECTIVE)
    # 제안 이어보기 — '그래 봐줘' 류 수락, 또는 슬롯 답변('2026년')처럼 후속으로 판정된 턴이면
    # 직전 답변의 제안을 그대로 이어 답하게 한다(수락어 없는 슬롯 답변도 제안과 연결 — 2026-07-01
    # 데굴님 지적: '어느 해의 월별 흐름?' 뒤 '2026년'이 제안 맥락을 잃던 결함).
    if prior_answer and (is_affirm_continue(question) or is_followup_turn):
        _offer = _extract_offer(prior_answer)
        if _offer:
            # 되물음 답변과 제안 수락을 구분한다(2026-08-04) — 질문형 마감에 내용으로
            # 답한 턴에 수락용 문구를 쓰면 사용자의 답이 버려진다. 수락어('그래/봐줘')로
            # 받은 경우는 질문형이어도 기존 이어보기 지시가 맞다.
            _accepted = is_affirm_continue(question) or AFFIRMATION_RE.fullmatch(
                question.strip()
            )
            _directive = (
                _OFFER_ANSWER_DIRECTIVE
                if _offer_is_question(_offer) and not _accepted
                else _OFFER_CONTINUE_DIRECTIVE
            )
            trailing.append(_directive.format(offer=_offer))
    # 스레드 내 서두 반복 금지 — 직전 답변이 있으면 그 첫 문장을 제시해 같은 패턴 서두를
    # 차단한다(2026-07-06 테스터: 한 스레드 안에서도 비슷한 형태의 답변 반복).
    if prior_answer:
        _prev_opening = first_sentence(prior_answer)
        if _prev_opening:
            trailing.append(_THREAD_OPENING_BAN.format(opening=_prev_opening))
    # 사용자 확정 용신 적용 안내 — 확정 5역할을 길흉 기준으로, 엔진 최초 도출은 기본값으로 병기.
    if _confirmed_yongsin is not None:
        from saju_engines.event_scoring import confirmed_yongsin_note

        _yongsin_note = confirmed_yongsin_note(result, _confirmed_yongsin)
        if _yongsin_note:
            trailing.append(_yongsin_note)
    # 캘리브레이션 표현 조정 힌트(CAL-P0 trait 반박 + CAL-P1 pair 매트릭스) — 저장된 검증
    # 응답이 있으면 서술 방식만 조정(판정·점수 불변, 처방 금지 조항 내장). 실패=무주입.
    trailing.extend(fetch_calibration_expression_hints(subject_id))
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
    _tr = intent.time_range
    if (
        not _date_targets
        and _tr is not None
        and _tr.start
        and len(_tr.start) == 10
        # 진짜 '그 날 하루' 창일 때만(2026-07-17 데굴님 지적: '12개월
        # 안에' 상대 창이 start가 오늘 날짜라는 이유로 단일 날짜로
        # 오판돼 일운 중심 블록이 주입되던 결함) — offset 창·기간 창·
        # 월 granularity는 제외한다.
        and not _tr.end_offset_days
        and (_tr.end is None or _tr.end == _tr.start)
        and _tr.granularity is Granularity.DAY
    ):
        try:
            _date_targets = [date.fromisoformat(_tr.start)]
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
    # 응답 형식 — 막연한 시점이면 10년 연(세운) digest+연도 지정 유도, 기간 없는 '달/날짜'
    # 입도 질문이면 12개월 월별 흐름에서 달 단위로(연 나열 금지 — 2026-07-03), 그 외 사건형
    # 연 질문은 12개월 나열 대신 연간 요약+핵심 달로.
    if vague_future and not _relo_dest:
        # 지평 정책이 잡힌 질문은 10년 digest 대신 지평 강제 지시(밖 서술 금지 + 한 줄 안내).
        trailing.append(
            horizon_directive(horizon) if horizon is not None else _YEAR_DIGEST_DIRECTIVE
        )
    elif gran_no_period and not _relo_dest:
        trailing.append(_MONTH_PICK_DIRECTIVE if timing_gran == "month" else _DAY_PICK_DIRECTIVE)
    elif overview is not None and event_monthly and not monthly_explicit:
        trailing.append(_KEY_MONTHS_DIRECTIVE)
    # 대운·장기 인생 흐름 질문 — 대운을 '환경/공간감(플랫폼)이 닥쳐오는 흐름·이 대운이 나에게
    # 맞느냐'로 서술하고 교체기 체감 신호도 함께(리포트 대운 섹션과 공용 관점, 2026-06-23 확장).
    # 지평 정책 질문 중 대운 배경이 필요한 건 구조 결정형(natal_fit)뿐 — 즉시형·전망형에
    # 대운 프레이밍을 붙이면 다시 장기 서술로 흐른다(2026-07-09 지평 정책).
    _wants_daewoon_frame = _is_daewoon_question(intent, question) or (
        vague_future and (horizon is None or horizon.natal_fit)
    )
    # 반사실 컨텍스트(2026-07-21 데굴님 확정) — '왜 늦어/왜 안 됐지/했다면 어땠을까' 류를
    # 도메인 범용으로 처리. fail-closed: 기간·근거 미확정이면 제한 지시만(체리피킹·자동
    # 보호 서사 차단), 성립 시 부담·지원·회복 증거를 서술 전용으로 주입(점수·판정 불변).
    _cf_lines = counterfactual_lines(build_counterfactual_context(
        question, intent, result, today,
        prior_time_scope=state.active_time_scope if state is not None else None,
        life_events=_sig,
    ))
    if _cf_lines:
        trailing.extend(_cf_lines)
    if _wants_daewoon_frame and not _relo_dest:
        trailing.append(DAEWOON_FRAMING_DIRECTIVE)
        # 발현 진행 예외 모드(2026-07-21) — 기본 그라데이션(계기→현실화)을 뒤집는 대운만
        # 주입(서술 전용, 점수·판정 불변). 예외 없으면 빈 목록(디렉티브 기본 prior로 충분).
        if result.luck_cycles is not None and result.pillars is not None:
            trailing.extend(daewoon_progression_lines(resolve_all_daewoon_progressions(
                result.luck_cycles.daewoon_table, result.pillars,
            )))
        trailing.append(DAEWOON_TRANSITION_SIGNALS_DIRECTIVE)
        # 운 품질 → 의사결정 태도 번역(좋은 시기=직감 실행, 불안정=점검·내실 — 사례 P0-5).
        trailing.append(DECISION_ATTITUDE_DIRECTIVE)
    # 기간×과업 점검(2026-07-22 테스터 요청 형식) — 명시 창 + 과업 명사 + 점검 질문이면
    # 과업별 소제목 구조 강제. 과업은 질문과 사실 원장(planned_task/remaining 인용) 양쪽에서
    # 수집한다(이전 턴에 밝힌 과업도 포함).
    _fact_task_text = " ".join(
        f.quote for f in (state.user_facts if state is not None else [])
        if f.key in ("planned_task", "remaining")
    )
    _task_scan = f"{question} {_fact_task_text}"
    _tasks_found = [t for t in _TASK_NOUNS if t in _task_scan]
    _month_span = _MONTH_SPAN_RE.search(question)
    _task_check = bool(
        _tasks_found
        and _RISK_CHECK_RE.search(question)
        and (
            _month_span  # 질문에 월 구간 명시 — 파싱이 단일일(확정일)로 잡혀도 우선
            or (
                intent.time_range is not None
                and intent.time_range.start
                and not _is_single_day(intent)
            )
        )
    )
    if _task_check:
        if _month_span:
            _g = [x for x in _month_span.groups() if x]
            _start_lbl, _end_lbl = f"{_g[0]}월", f"{_g[1]}월"
        else:
            assert intent.time_range is not None
            _start_lbl = intent.time_range.start or ""
            _end_lbl = intent.time_range.end or _start_lbl
        trailing.append(_TASK_RISK_CHECK_DIRECTIVE.format(
            start=_start_lbl, end=_end_lbl, tasks="·".join(_tasks_found),
        ))
        # 절차 지식팩(L1/L2) 가산 — 점검을 실제 단계·의존관계·실패 형태에 연결(2026-07-22
        # 승인 문서 §5·§8). 팩 없으면 생략(운 신호만으로 점검 — 기존 동작).
        _pack = detect_task_pack(_task_scan)
        if _pack is not None:
            trailing.append(procedure_reference_block(_pack))
    # 특정일 질문 — 당일 중심·기간 서술 최소화·데이터 밖 간지 계산 금지(2026-07-22).
    # 과업 점검이 발동했으면 생략 — 질문의 실창은 과업 기간이지 확정일 당일이 아니다.
    if (
        not _task_check
        and _is_single_day(intent)
        and intent.time_range is not None
        and intent.time_range.start
    ):
        _d0_iso = intent.time_range.start[:10]
        _sm_note = ""
        try:
            _tz0 = result.time_correction.timezone if result.time_correction else "Asia/Seoul"
            _d0 = date.fromisoformat(_d0_iso)
            _sm_label = _current_luck_month(_d0, _tz0)
            # 절기월이 양력 달과 어긋나는 날만 앵커 주입(예: 7/4 → 甲午월=2026-06).
            if _sm_label != _d0_iso[:7]:
                _sm_ganji = next(
                    (
                        pl.ganji
                        for pl in luck_months(birth, int(_sm_label[:4]))
                        if pl.label == _sm_label
                    ),
                    None,
                )
                if _sm_ganji:
                    _sm_note = _SINGLE_DAY_SOLAR_MONTH_NOTE.format(
                        ganji=_sm_ganji, label=_sm_label, cal_month=int(_d0_iso[5:7]),
                    )
        except Exception:  # noqa: BLE001 — 앵커 산출 실패가 특정일 지시 자체를 막지 않도록
            _sm_note = ""
        trailing.append(
            _SINGLE_DAY_FOCUS_DIRECTIVE.format(
                date=_d0_iso,
                relative=_relative_day_label(date.fromisoformat(_d0_iso), today),
                solar_month_note=_sm_note,
            )
        )
    # 이사 질문 — 십성(유형)과 용신/기신(길흉)을 분리해 답하도록 강제(2026-06-18).
    if _is_relocation_intent(intent):
        trailing.append(_RELOCATION_REASON_DIRECTIVE)
        # 부부 공동 이사(배우자 pairwise 명식 블록 확보 시) — 본인/배우자 각각이 세대주인
        # 두 갈래 분리 풀이 강제(2026-07-22 데굴님 지시). 블록이 없으면(birth 미확보 등)
        # 미주입 — 근거 없는 배우자 서술을 만들지 않는다(fail-closed).
        if (
            relationship_context is not None
            and relationship_context.mode == "pairwise"
            and relationship_context.relation_type == "spouse"
            and subject_blocks
        ):
            _comp_label = next(
                (b.label for b in subject_blocks if not b.is_primary), None
            ) or (partner_label or "배우자")
            trailing.append(_RELOCATION_HOJU_SPLIT_DIRECTIVE.format(
                self_label=subject_label or "본인", companion_label=_comp_label,
            ))
    # 목적지 명시 이사 — 답의 중심을 지역오행·이동 방위 적합에 두게 한다(2026-06-25).
    if _relo_dest:
        trailing.append(_RELOCATION_DESTINATION_DIRECTIVE)
    # 생활형 횡재(로또·연금복권·소액 주식) — 흐름·시기·태도를 자유롭게 풀게 한다(번호·종목픽·
    # 당첨단정 거부는 유지). CLAUDE.md 절대원칙 8 개정(2026-06-20 데굴님 승인).
    if _is_lifestyle_windfall(intent, question):
        trailing.append(_LIFESTYLE_WINDFALL_DIRECTIVE)
    # 사고수 — 사고·안전 위험 질문이면 해석 축(이동·문서·통제력·외부유입)과 단정 금지
    # 프레임을 고정한다(2026-07-23 데굴님 제공 자료 증류). 파서가 HEALTH로 흡수하므로
    # 후보·위험 신호는 건강·안전 축으로 이미 필터돼 들어온다.
    if _is_accident_risk_question(question):
        trailing.append(_ACCIDENT_RISK_DIRECTIVE)
    # 인연·만남 시기 — 만남은 '택일'이 아니므로 약한/기신 달을 선택지로 끌어와 무르지 말고,
    # 가장 유리한 시기 하나(연·반기·계절)로. 만날 장소·경로는 사주로 단정 불가(과도한 구체화 금지).
    # 단 사용자가 '달'을 명시하면 '연·계절로 제시' 지시가 질문 입도와 충돌하므로(실사례 오답의
    # 한 축, 2026-07-03) 월 단위 변형을 쓴다 — 비택일·장소 단정 금지 원칙은 유지.
    if _is_relationship_context(intent, question):
        trailing.append(
            _MEETING_TIMING_MONTH_DIRECTIVE if timing_gran == "month" else _MEETING_TIMING_DIRECTIVE
        )
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

    # ── P4-1 커리어 전이 chat beta(최소 cohort) ────────────────────────
    # prepare 는 LLM을 호출하지 않는다 — 기존 단일 generate_reading 호출을 유지한다.
    # flag OFF(기본)면 지시문이 없어 프롬프트·응답이 byte 동일하다.
    _career_prep = _prepare_career_transition_block(
        question, thread_id=thread_id, subject_id=subject_id, candidates=candidates,
        prepared=_career_turn,   # P2와 같은 조회·파싱 결과를 쓴다(요청당 1회)
    )
    if _career_prep is not None and _career_prep.directive:
        trailing.append(_career_prep.directive)

    system = None
    if persona is not None:
        # 호칭 자리({resolvedHonorific})에 대화 기준 사주의 별명을 넣는다(하드코딩 '회원' 제거).
        block = _get_persona_engine().build_block(persona, subject_label or "회원")
        system = llm_client._SYSTEM_PROMPT + "\n\n" + block
    # generate_reading은 system 미지정 시 _SYSTEM_PROMPT를 쓰므로 예약분도 실제 전송 시스템 기준.
    sys_for_budget = system or llm_client._SYSTEM_PROMPT
    reserve = estimate_tokens(sys_for_budget) + estimate_tokens("\n".join(trailing))

    # ── 위험 노출 사전 계산(감수 62차 P0⑥ — reserve는 진짜 예약) ──────
    # 직렬화 **이전**에 매핑·payload·adapter를 해소해, 실제 주입 예정
    # 요청에만 RISK_CONTEXT_RESERVE 만큼 일반 본문 예산을 줄인다
    # (base_content_budget = CALL_LIMIT − reserve). BYPASS 사전 확정
    # (매핑 실패·episode 0건·adapter 미검증·kill switch)에는 미적용 —
    # 일반 답변이 공연히 짧아지지 않는다. OFF/SHADOW는 분기 자체가
    # 실행되지 않아 byte 불변.
    _mapped = None
    _risk_payload = None
    _risk_inputs: dict | None = None
    _stored_risk_keys: tuple[tuple[str, str, str], ...] = ()
    _cmp_periods: tuple[str, ...] = ()
    if risk_exposure_service.exposure_mode_active():
        from saju_engines import risk_engine_config as _risk_cfg

        from . import risk_exposure_bootstrap as _reb
        if state is not None:
            _parsed_refs: list[tuple[str, str, str]] = []
            for ent in state.entities:
                if str(ent.id).startswith("risk_episode_"):
                    parts = str(ent.label).rsplit("|", 2)
                    while len(parts) < 3:
                        parts.append("")
                    _parsed_refs.append((parts[0], parts[1], parts[2]))
            _stored_risk_keys = tuple(_parsed_refs[-3:])
        _mapped = risk_exposure_service.map_intent_for_exposure(
            intent, _stored_risk_keys)
        if (_mapped and _mapped.get("question_type")
                == "multi_episode_compare"
                and _mapped.get("future_period_range")):
            _s, _e = _mapped["future_period_range"]
            _cmp_periods = tuple(
                str(y) for y in range(
                    int(str(_s)[:4]),
                    min(int(str(_e)[:4]), int(str(_s)[:4]) + 2) + 1))
        # P0-B4 하드 게이트(부록 C-4 불변식 1) — live 관계 컨텍스트 유래 REL 후보는
        # 위험 모드와 무관하게 P5 전 LLM 노출 금지(전용 target 네임스페이스로 식별).
        _exposable_shadow, _rel_blocked = (
            relationship_shadow.strip_live_relationship_candidates(
                list(_subject_risk_shadow)))
        _rel_shadow_tel.risk_blocked_or_suppressed_count = _rel_blocked
        _risk_payload = _reb.build_risk_payload(
            _exposable_shadow,
            question_type=(_mapped or {}).get("question_type"),
            comparison_periods=_cmp_periods)
        _risk_inputs = _reb.exposure_runtime_inputs(call_type)
        if risk_exposure_service.risk_reserve_active(
                _mapped, _risk_payload, _risk_inputs):
            reserve += _risk_cfg.RISK_CONTEXT_RESERVE

    _rel_shadow_tel.emit()  # P0-B4 계측(PII 없음) — 노출 필터 반영 후 단일 지점
    try:
        prompt_text, tokens = serialize_with_guard(payload, call_type, reserve_tokens=reserve)
    except TokenBudgetExceeded as exc:
        return ChatResponse(
            status="too_broad",
            answer=(
                f"질문 범위가 넓어 분석량이 한도를 초과했어요. 기간이나 분야를 좁혀주세요. ({exc})"
            ),
            intents=parsed.intents,
        )

    prompt_text = prompt_text + "".join("\n" + part for part in trailing)

    # R5-b(감수 46차): 위험 노출 배선 — **EXPOSE 계열 모드에서만** 실행.
    # OFF/SHADOW에서는 아래 분기가 실행되지 않아 prompt·system byte 불변
    # (회귀 fixture). 현 단계는 expose_pipeline.reviewed=false + tokenizer
    # adapter 부재라 게이트가 전부 비주입하고 suppressed guard만 부착된다 —
    # 질문 매핑·adapter·canary allowlist는 canary 개시 차수에서 감수 후 공급.
    _risk_flow_result: dict | None = None
    if risk_exposure_service.exposure_mode_active():
        # 실값 공급(감수 61차 §13-①): 매핑·payload·adapter는 직렬화 전
        # 사전 계산분(reserve 판정과 동일 값)을 재사용한다 — 어느 하나라도
        # 미해소면 게이트가 해당 사유로 BYPASS(fail-closed).
        from . import risk_exposure_bootstrap as _reb
        assert _risk_inputs is not None  # exposure 모드에서 사전 계산 보장
        _baseline_prompt = prompt_text  # 주입 전 원문(REGENERATE 재조립)
        prompt_text, system, _risk_obs = (
            risk_exposure_service.apply_risk_exposure(
                prompt_text, system,
                intent=intent,  # 파서 SSOT 매핑(감수 50차 — fail-closed)
                stored_episode_keys=_stored_risk_keys,
                payload=_risk_payload,
                subject_id=owner_id,
                counter=_risk_inputs["counter"],
                counter_model_id=_risk_inputs["counter_model_id"],
                resolved_model_id=_risk_inputs["resolved_model_id"],
                model_context_limit=_risk_inputs["context_limit"],
                base_prompt_tokens=tokens,
                user_input_tokens=0,  # prompt_text에 포함(중복 가산 금지)
                existing_context_tokens=estimate_tokens(sys_for_budget),
                response_reserve=_risk_inputs["response_reserve"],
            ))
        _logger.info("risk_exposure_gate %s", _risk_obs)
        # fail-loud 관측(감수 62차 7단계) — EXPOSE에서 조용한 BYPASS 감지.
        from .risk_exposure_monitor import observe_disposition
        observe_disposition(_risk_obs, surface="chat")
        if _risk_obs.get("disposition") == "INJECTED" and _risk_payload:
            # INJECTED 실호출(감수 60·61차): 구조화 생성→감사→REVISE/
            # REGENERATE→renderer 후 최종 감사. BYPASS/SUPPRESSED는 아래
            # 기존 generate_reading 경로 그대로(byte-equivalent 계약).
            try:
                _risk_flow_result = _reb.run_exposed_reading(
                    baseline_prompt=_baseline_prompt,
                    injected_prompt=prompt_text,
                    system=system or llm_client._SYSTEM_PROMPT,
                    observability=_risk_obs, payload=_risk_payload,
                    call_type=call_type,
                    request_context_id=f"{thread_id or 'oneshot'}:"
                                       f"{state.turn_no if state else 0}",
                    renderer=_normalize_ganji_gloss)
            except Exception:  # noqa: BLE001 — flow 인프라 장애 방어
                # 위험 요소(instruction·block·schema)가 감사 없이 나가는
                # 경로 차단: baseline+guard로 복원해 기존 경로 폴백.
                _logger.exception("risk_flow 실패 — baseline+guard 폴백")
                _risk_flow_result = None
                prompt_text = (_baseline_prompt + "\n"
                               + risk_exposure_service
                               .RISK_EXPOSURE_SUPPRESSED_GUARD)

    if state is not None:
        # T4.5 — 시스템이 제시한 상위 이벤트를 claim/event 엔티티로 등록(이의 재검산 대비).
        summaries = [
            ResultSummaryRef(
                kind="event",
                label=f"{c.event_key}@{c.period}",
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

    if _risk_flow_result is not None:
        # INJECTED 경로(감수 60차 §8): DELIVER_*만 전달 — renderer·최종
        # 감사는 flow 내부에서 이미 완료(재가공 금지). BLOCK=전달 금지 →
        # 위험 무관 일반 실패 문구(내부 상태 설명 금지).
        if _risk_flow_result["outcome"] in ("DELIVER_GENERATED",
                                            "DELIVER_SAFE_FALLBACK"):
            answer = _risk_flow_result["final_text"]
            # episode_followup 저장(감수 62차): **DELIVER_GENERATED만**
            # (SAFE_FALLBACK/BLOCK/BYPASS 등록 금지 — 전달된 위험 서술이
            # 있는 경우에만 후속 해소 대상). thread 내 최대 3건, 동일
            # turn 재시도는 register가 id로 멱등 처리.
            if (_risk_flow_result["outcome"] == "DELIVER_GENERATED"
                    and state is not None and _risk_payload):
                _summ: list[ResultSummaryRef] = []
                for _rec in (_risk_payload.get("presentationRecords")
                             or []):
                    _diag = _rec.get("diagnostics") or {}
                    _key = _diag.get("episodeKey")
                    if not _key or _rec.get("presentationLevel") == "none":
                        continue
                    _dom = (_rec.get("domains") or [""])[0]
                    _period = str(_diag.get("startPeriod", ""))[:4]
                    _summ.append(ResultSummaryRef(
                        kind="risk_episode",
                        label=f"{_key}|{_dom}|{_period}",
                        detail="위험 episode 참조(후속 질문 해소용)"))
                if _summ:
                    state = ConversationEngine.register_system_results(
                        state, _summ[:3])
        else:
            _save_thread(store, state)
            return ChatResponse(
                status="error",
                answer="답변 생성에 문제가 있었어요. 잠시 후 다시"
                       " 시도해 주세요.",
                intents=parsed.intents, thread_id=thread_id,
                turn_no=state.turn_no if state else None)
    else:
        answer = llm_client.generate_reading(
            prompt_text,
            call_type=call_type,
            system=system,
            owner_id=owner_id,
            surface="chat",
            ref_id=thread_id,
        )
        answer = _normalize_ganji_gloss(answer)  # 간지 병기 보정.
        # P4-1 출력 감사 — 실패하면 커리어 지시문을 뺀 프롬프트로 **1회만** 재생성해
        # 기존 직업운 경로로 완전 복귀한다(감사 전 원문 전달 금지, 3회 호출 금지).
        answer = _audit_career_transition_answer(
            answer, _career_prep, prompt_text, call_type, system, owner_id, thread_id
        )
        # P0 관계 의미 패치(2026-07-27) — 엔진 판정을 뒤집은 서술은 전달 금지.
        # 재호출 없이 해당 문장만 canonical claim으로 교체한다.
        answer = _audit_relation_answer(answer, payload.period_fortune, thread_id)
        # P0.5 — 내부 서술 정책이 답변에 그대로 노출되면 해당 문장만 제거한다.
        _echoes = detect_policy_echo(answer)
        if _echoes:
            answer, _removed = strip_policy_echo(answer, _echoes)
            _logger.warning(
                "policy_echo_stripped count=%d matched=%s thread=%s",
                _removed, [e.matched for e in _echoes], thread_id,
            )
    # 총운 커버리지 계측(관측 전용 — 재생성·재호출 없음, 데굴님 확정): 누락 후보를
    # 로그로 남겨 입력 구조 개선(후보 블록 후치 등)의 효과를 실측한다.
    if _overview_mode and payload.event_candidates:
        _missed = _overview_missed_candidates(answer, payload.event_candidates)
        if _missed:
            _logger.info("overview_coverage_miss missed=%s thread=%s", _missed, thread_id)
    if state is not None:
        # P3(2단계 커밋) — 답변 중심 연도가 엔진 창 밖이거나 배제 연도면 이번 턴의 시점
        # 슬롯 커밋을 직전 정상 상태로 되돌린다(오염이 다음 턴으로 퍼지지 않게, 2026-07-14).
        state = _time_commit_guard(state, _prior_time, intent, answer, _active_exclusions)
        # 이번 답변 끝의 제안(offer)을 저장 — 다음 턴의 슬롯 답변('2026년')을 제안 수락으로 연결한다
        # (비offer면 '' → 자동 만료). offer-slot 링킹·월별 승격의 근거(2026-07-01).
        state.last_offer = _extract_offer(answer)
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


# ── P4-1 커리어 전이 chat beta 훅 ──────────────────────────────────────────
# 최소 cohort(CHAT + GENERAL_CAREER + 단일 본인 + 열린 Episode 1개) 전용이며 2단 flag
# 뒤에 있다. shadow store 가 아직 대화에 영속되지 않으므로(P3 경계) production 에서는
# 자격 미달로 None 을 돌려준다 — flag OFF 와 동일하게 프롬프트·응답이 불변이다.


def _career_shadow_repository():
    """shadow 저장소 — 기본 Postgres(`CAREER_SHADOW_REPOSITORY=memory` 는 개발 전용).

    DB 오류 시 in-memory 로 **자동 fallback 하지 않는다** — worker 마다 다른 임시 상태가
    생기면 "전에 지원했다고 했는데 왜 기억 못 하냐" 류의 대화 단절이 발생한다.
    호출자가 이번 turn 노출을 억제하고 기존 경로를 유지한다.
    """
    global _CAREER_SHADOW_REPO
    if _CAREER_SHADOW_REPO is None:
        from saju_engines.career_shadow_repository import build_career_shadow_repository

        _CAREER_SHADOW_REPO = build_career_shadow_repository()
    return _CAREER_SHADOW_REPO


def _dual_run_audit_context(
    *, thread_id, subject_id, question, turn, intent, prepared
):
    """dual-run 감사 맥락 — **질문 원문·프로필을 담지 않는다**(P2-3b).

    `request_id`는 thread 식별자를 그대로 쓰지 않고 HMAC으로 치환한 뒤 턴 번호와
    발화 해시를 붙여 만든다. 같은 요청이 재시도돼도 같은 값이라 집계에서 중복 제거된다.

    Args:
        thread_id: 서버가 확정한 thread.
        subject_id: 서버가 확정한 주체.
        question: 이번 턴 발화 — **해시로만 쓰고 저장하지 않는다.**
        turn: 턴 번호.
        intent: 파싱된 intent.
        prepared: `PreparedCareerTurn`(저장소 4상태 출처).

    Returns:
        `DualRunAuditContext` 또는 실패 시 None(감사만 건너뛴다).
    """
    try:
        from saju_engines.process_dual_run_audit import (
            DualRunAuditContext,
            pseudonymize,
        )

        return DualRunAuditContext(
            request_id=(
                f"{pseudonymize(thread_id, prefix='thr')}:{turn or 0}"
                f":{_stable_turn_id(question)}"
            ),
            surface="chat",
            intent=str(intent.event_key or intent.domain or ""),
            subject_id=subject_id,
            process_source_status=(
                prepared.source_status.value if prepared is not None else ""
            ),
        )
    except Exception:  # pragma: no cover - 감사 맥락 실패가 응답을 막지 않는다
        _logger.exception("dual_run_audit_context_failed")
        return None


def _build_request_process_context(question, *, thread_id, subject_id, turn=None):
    """요청 스코프 진행 사실 컨텍스트 — **저장소 1회 조회 · 발화 1회 파싱**(P2-3a).

    `CAREER_TRANSITION_CHAT_ENABLED`와 **독립**이다. 그 플래그는 커리어 전용 지시문
    블록의 노출 여부를 정할 뿐이고, 저장소에 hard fact Episode가 있으면 P2는 그것을
    쓴다. 플래그 OFF를 "진행 사실 없음"으로 읽으면 사용자가 말한 현실이 무시된다.

    조회 실패·계약 불일치는 예외로 흘리지 않고 상태로 전달한다 — 하류에서
    `BYPASS_PROCESS_SOURCE_UNAVAILABLE` / `BYPASS_PROCESS_CONTRACT_MISMATCH`로 갈린다.

    Args:
        question: 이번 턴 발화.
        thread_id: 서버가 확정한 thread.
        subject_id: 서버가 확정한 주체.
        turn: 현재 턴 번호.

    Returns:
        `(PreparedCareerTurn | None, RequestProcessContext | None)`. 실패해도 기존
        경로를 막지 않는다(둘 다 None → 게이트 미적용).
    """
    try:
        from saju_engines.career_process_adapter import build_career_process_snapshots
        from saju_engines.career_state_shadow import prepare_career_turn
        from saju_engines.process_fact_resolver import build_request_process_context

        prepared = prepare_career_turn(
            _career_shadow_repository(), thread_id=thread_id or "",
            subject_id=subject_id or "", conversation_text=question,
        )
        snapshots = (
            []
            if prepared.blocked
            else list(
                build_career_process_snapshots(
                    prepared.store, subject_id=subject_id, source_turn=turn
                )
            )
        )
        # 4상태를 그대로 전달한다 — bool 하나로 접으면 계약 불일치가 장애로 보인다.
        context = build_request_process_context(
            subject_id=subject_id,
            current_turn_text=question,
            career_snapshots=snapshots,
            career_source_unavailable=prepared.blocked,
            source_status=prepared.source_status,
            turn=turn,
        )
        return prepared, context
    except Exception:  # pragma: no cover - P2 배선이 기존 응답을 깨지 않게
        _logger.exception("process_context_build_failed")
        return None, None


def _prepare_career_transition_block(
    question, *, thread_id, subject_id, candidates=(), prepared=None
):
    """turn 처리 + 소비 준비. flag OFF·scope 미확정·억제 시 None.

    `chat_service`는 repository 세부를 알지 않고 orchestration 결과만 본다.

    Args:
        prepared: 요청 앞단에서 만든 `PreparedCareerTurn`. 실제 chat 경로는 반드시
            넘긴다 — 넘기지 않으면 저장소를 다시 읽어 요청 내 상태가 갈린다(P2-3a).
    """
    from saju_engines import career_chat_consumer

    if not career_chat_consumer.CAREER_TRANSITION_CHAT_ENABLED:
        return None
    # 서버가 확정한 식별자만 scope 로 쓴다 — 발화에서 추출한 이름·표시명 금지.
    if not thread_id or not subject_id:
        return None
    try:
        from saju_engines.career_state_shadow import process_career_turn

        turn = process_career_turn(
            _career_shadow_repository(),
            thread_id=thread_id, subject_id=subject_id,
            conversation_text=question,
            command_id=f"{thread_id}:{subject_id}:{_stable_turn_id(question)}",
            source_fact_id=f"{thread_id}:{_stable_turn_id(question)}",
            recorded_at=datetime.now(UTC).isoformat(),
            prepared=prepared,   # 요청 앞단의 조회·파싱 결과 재사용(P2-3a)
        )
        if turn.telemetry:
            _logger.info(
                "career_shadow_turn status=%s telemetry=%s thread=%s",
                turn.persistence_status.value, list(turn.telemetry), thread_id,
            )
        if turn.suppress_exposure:
            # 저장되지 않은 사실을 노출하지 않는다(다음 turn 에 사라져 모순이 된다).
            return None
        _vector = _career_effect_vector_for(candidates)
        prep = career_chat_consumer.prepare_career_chat_block(
            turn.store,
            query_resolution=CareerQueryResolution.GENERAL_CAREER,
            subject_count=1,
            kind=CareerTransitionKind.EXTERNAL_MOVE,
            vector=_vector,
        )
        if prep.eligible:
            _log_career_vector_telemetry(prep, _vector, thread_id)
        return prep if prep.eligible else None
    except Exception:  # pragma: no cover - beta 경로가 기존 응답을 깨지 않게
        _logger.exception("career_transition_prepare_failed")
        return None


def _stable_turn_id(question: str) -> str:
    """발화 기반 안정 id — 동일 요청 재시도 시 journal·revision 중복 증가를 막는다."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]


def _career_effect_vector_for(candidates):
    """단계 효과 벡터 — 이미 계산된 이벤트 후보를 축 기여로 변환한다.

    새 점수를 만들지 않는다(어댑터 변환만). 감사가 깨끗하지 않으면 벡터를 만들지 않고
    빈 벡터를 돌려준다 — 이중 가산된 값을 조용히 노출하느니 "근거 부족"이 낫다.
    """
    from saju_engines.career_effect_adapter import build_career_contributions
    from saju_engines.career_effect_vector import build_effect_vector
    from saju_shared_types.career_effect_vector import CareerEffectVector

    contributions = build_career_contributions(candidates or ())
    if not contributions:
        return CareerEffectVector()
    vector, audit = build_effect_vector(contributions)
    if vector is None:
        _logger.warning(
            "career_effect_vector_audit_failed dup=%s derived=%s legacy=%s",
            audit.duplicates, audit.derived_as_primary, audit.legacy_mixed,
        )
        return CareerEffectVector()
    return vector


def _log_career_vector_telemetry(prep, vector, thread_id) -> None:
    """효과 벡터 품질 관측 — 축 값이 캘리브레이션되기 전의 유일한 경보다.

    `axis_saturation_rate` 가 지속적으로 높거나 `same_bottleneck` 이 한쪽으로 쏠리면
    adapter 매핑이나 표시 점수 압축을 의심해야 한다. 값이 아니라 **분포**를 본다.
    """
    from saju_engines.career_effect_vector import axis_saturation_rate

    payload = getattr(prep, "payload", None)
    if payload is None:
        return
    from saju_shared_types.career_effect_vector import EffectAxis

    top = max(vector.contributions, key=lambda c: abs(c.value), default=None)
    _logger.info(
        "career_vector_telemetry saturation=%.2f margin=%s sharpness=%s bottleneck=%s "
        "not_evaluable=%s axis_coverage=%d/%d top_source=%s scope=%s thread=%s",
        axis_saturation_rate(vector),
        payload.bottleneck_margin,
        payload.bottleneck_sharpness,
        payload.bottleneck,
        payload.bottleneck_not_evaluable,
        len(vector.axes), len(EffectAxis),
        top.signal_ref if top is not None else None,
        payload.scope.value,
        thread_id,
    )


def _audit_career_transition_answer(
    answer, preparation, prompt_text, call_type, system, owner_id, thread_id
):
    """출력 감사 — 위반 시 커리어 지시문을 뺀 프롬프트로 1회만 재생성한다."""
    if preparation is None or not preparation.eligible:
        return answer
    from saju_engines import career_chat_consumer

    audit = career_chat_consumer.audit_career_chat_response(answer, preparation)
    if audit.delivered:
        return answer
    _logger.info(
        "career_transition_output_audit_fallback violations=%s thread=%s",
        [v.value for v in audit.violations], thread_id,
    )
    legacy_prompt = prompt_text.replace(preparation.directive or "", "").strip()
    retried = llm_client.generate_reading(
        legacy_prompt, call_type=call_type, system=system,
        owner_id=owner_id, surface="chat", ref_id=thread_id,
    )
    return _normalize_ganji_gloss(retried)


def _audit_relation_answer(answer, period_fortune, thread_id):
    """P0 관계 의미 패치 — 엔진 판정 역전 서술을 결정론적으로 교정한다.

    **LLM 재호출은 하지 않는다**(2026-07-27 데굴님 확정 — 재생성 철회). 이 문제는
    창작이 아니라 엔진 확정값 반영으로 풀리며, 유료 Q&A에서 재생성을 기본 안전장치로
    두면 사용자 비용과 서버 원가가 함께 늘어난다. 복구 우선순위는
    ① 결정론적 국소 교정 → ② 엔진 안전 템플릿 조립 순이고, **원문 유지(fail-open)는
    금지**다(엔진 판정을 뒤집은 답변을 알고도 전달 = 절대원칙 1 위반).

    Args:
        answer: 정규화까지 마친 답변.
        period_fortune: 이번 턴 총운 블록(관계 구조화 의미 보유). None이면 통과.
        thread_id: 스레드 식별자(로깅·참조).

    Returns:
        패치를 통과했거나 교정된 답변.
    """
    if not period_v2_config.RELATION_SEMANTIC_PATCH_ENABLED or period_fortune is None:
        return answer
    semantics = period_fortune.relation_semantics
    if not semantics:
        return answer
    violations = audit_relation_claims(answer, semantics)
    if not violations:
        _logger.info(
            "relation_claim_audit result=pass relations=%d thread=%s",
            len(semantics), thread_id,
        )
        return answer

    patched = patch_relation_claims(answer, violations, semantics)
    _logger.warning(
        "relation_claim_audit result=violation outcome=%s kinds=%s labels=%s "
        "patched=%d ambiguous=%d unpatched=%d thread=%s",
        patched.outcome.value,
        [v.kind.value for v in violations],
        sorted({v.relation_label for v in violations}),
        patched.patched_count, len(patched.ambiguous_sentences),
        len(patched.unpatched), thread_id,
    )
    if patched.fully_repaired:
        return patched.text
    # 미교정 위반이 남음(모호하거나 문장 특정 실패) — 추가 LLM 호출 대신 엔진 데이터로
    # 답변을 조립한다. 어느 관계를 말하는지 확정 못 한 채 임의 문장으로 바꾸지 않는다.
    if period_v2_config.SAFE_TEMPLATE_FALLBACK_ENABLED:
        _logger.error("relation_claim_audit result=safe_template outcome=%s thread=%s",
                      patched.outcome.value, thread_id)
        return build_safe_period_answer(period_fortune)
    _logger.error(
        "relation_claim_audit result=unpatched_delivered thread=%s — "
        "SAFE_TEMPLATE_FALLBACK이 꺼져 있어 미교정 모순이 전달된다", thread_id,
    )
    return patched.text


#: shadow 저장소 단일 인스턴스(지연 생성).
_CAREER_SHADOW_REPO = None
