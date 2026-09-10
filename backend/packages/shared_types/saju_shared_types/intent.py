"""질문 분류·의도 schemas (v2.2 Phase 0, docs/03 B1·B2).

설계 문서의 Question Taxonomy(Q1~Q14)와 IntentJson/ParsedMessage/SubjectRef 등 오케스트
레이터 입력 계약을 Python으로 옮긴 것. 본 모듈은 타입 정의(T0.1)만 담당하며, 파싱·플래닝
로직은 Phase 3에서 구현한다.

대상(Subject) 확정은 intent보다 우선한다(절대 원칙 7). 그래서 SubjectRef/SubjectMode를
IntentJson과 함께 정의해 모든 의도가 대상을 명시적으로 들고 다니게 한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .events import EventKey


class QueryType(StrEnum):
    """질문 유형 14종 (docs/03 B1). 한 메시지는 복수 intent를 가질 수 있다."""

    FORTUNE_OVERVIEW = "fortune_overview"  # Q1
    DOMAIN_ANALYSIS = "domain_analysis"  # Q2
    TIMING_SEARCH = "timing_search"  # Q3
    DATE_RECOMMENDATION = "date_recommendation"  # Q4
    EVENT_EXPLANATION = "event_explanation"  # Q5
    COMPARISON = "comparison"  # Q6 (compatibility/competition/ranking)
    DECISION_SUPPORT = "decision_support"  # Q7
    CHART_ANALYSIS = "chart_analysis"  # Q8
    RELATIONSHIP_ANALYSIS = "relationship_analysis"  # Q9
    REMEDY = "remedy"  # Q10
    TERMINOLOGY_EDUCATION = "terminology_education"  # Q11
    FEEDBACK_CORRECTION = "feedback_correction"  # Q12
    EMOTIONAL_SUPPORT = "emotional_support"  # Q13
    OUT_OF_SCOPE = "out_of_scope"  # Q14


class Domain(StrEnum):
    """분야 (docs/03 C graphScope 기준). 결합 질문은 domains[]로 표현."""

    CAREER = "career"
    RELATIONSHIP = "relationship"
    RELOCATION = "relocation"
    WEALTH = "wealth"
    EDUCATION = "education"
    HEALTH = "health"
    GENERAL = "general"


class SubjectKind(StrEnum):
    """대상 종류 (docs/03 B2 SubjectRef.kind)."""

    SELF = "self"
    COMPANION = "companion"  # 등록 동반자
    INLINE_TEMP = "inline_temp"  # 인라인 임시 인물
    PARTIAL_INFO = "partial_info"


class SubjectMode(StrEnum):
    """대상 모드 (docs/03 A0·B2)."""

    SINGLE = "single"
    PAIRWISE = "pairwise"  # 궁합(본인↔동반자)
    GROUP_AGGREGATE = "group_aggregate"  # 가구 합산
    COMPARE_EXCLUDE_SELF = "compare_exclude_self"  # 본인 제외 비교
    RANKING = "ranking"  # 다자 순위


class CompanionRelationType(StrEnum):
    """대상 간 인간관계 유형 (docs/02 E13 Compatibility 축 분기).

    간지 관계(`ganji_calendar.RelationType`, 합충형파해)와 이름이 겹치지 않도록
    'Companion' 접두를 붙인다.
    """

    SPOUSE = "spouse"
    LOVER = "lover"
    PARENT_CHILD = "parent_child"
    SIBLING = "sibling"
    FRIEND = "friend"
    COLLEAGUE = "colleague"
    BOSS = "boss"
    BUSINESS_PARTNER = "business_partner"
    RIVAL = "rival"
    UNKNOWN = "unknown"


class TimeScope(StrEnum):
    """시간 범위 성격 (docs/03 B2)."""

    LONG_TERM = "long_term"
    MID_TERM = "mid_term"
    SHORT_TERM = "short_term"
    DATE_LEVEL = "date_level"
    HOUR_LEVEL = "hour_level"
    PAST = "past"
    LIFE_STAGE = "life_stage"
    DAEWOON_UNIT = "daewoon_unit"
    TIMELESS = "timeless"


class Granularity(StrEnum):
    """분석 단위 (docs/03 B2 timeRange.granularity)."""

    DAEWOON = "daewoon"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"


class OutputFormat(StrEnum):
    """출력 형식 (docs/03 B2 OutputStyle.format)."""

    RANKED_DATES = "ranked_dates"
    TIMELINE = "timeline"
    REPORT = "report"
    COMPARISON = "comparison"
    SLOTS = "slots"
    NARRATIVE = "narrative"


class InlineBirth(BaseModel):
    """미등록 제3자 출생정보 (docs/03 B2). 시각 없으면 3주(시주 제외) 모드.

    좌표·timezone(선택): FE 지역 피커가 선택 지명의 좌표를 함께 보내면 백엔드 지명
    시드(소수)와 무관하게 경도 보정이 정확해진다(2026-07-03 즉석입력 지역 미동작 수정).
    """

    date: str
    time: str | None = None
    calendar_type: str = "solar"  # 'solar' / 'lunar'
    gender: str | None = None  # 'M' / 'F'
    birthplace: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None  # IANA tz, 예: 'Asia/Seoul'


class SubjectRef(BaseModel):
    """분석 대상 한 명 (docs/03 B2 SubjectRef).

    별칭('1호'/'신랑'/'아가')은 Subject Manager(E14)에서 companion_id로 매핑된다.
    entity_id는 Entity Tracking 등록 ID로, 후속 턴 누적 참조에 쓰인다.
    """

    kind: SubjectKind
    label: str  # 대화 표시명 ('1998.07.23 여자')
    companion_id: str | None = None
    inline_birth: InlineBirth | None = None
    entity_id: str | None = None
    # 기준(SELF) 대상과의 관계 — relationship_hints.RELATION_TYPES 값(사용자 명시 선택).
    # 테마 애정·관계운 궁합(RP)의 풀이 방향에 쓰인다(2026-07-03). 미지정=중립 궁합 톤.
    relation_type: str | None = None


class AnchorDate(BaseModel):
    """외부 일정 앵커 (docs/03 B2 — '투표일 6/3')."""

    label: str
    date: str


class LabeledRange(BaseModel):
    """사용자 지정 기간 구간 (docs/03 B2 — '26-27 / 28-30년')."""

    label: str
    start: str
    end: str


class AgeRange(BaseModel):
    """나이 기반 기간 (docs/03 B2 — '20살 전까지')."""

    from_age: int | None = None
    to_age: int | None = None


class ChainedStep(BaseModel):
    """역산 체인 한 단계 (docs/03 B2 — '계약 후 2~3개월 안에 이사')."""

    step: str
    offset_from: str | None = None
    window: str | None = None


class TimeConstraintRole(StrEnum):
    """발화 속 시간 표현의 담화 역할 (2026-07-14 시점 정합 P1).

    '처음/마지막 연도 기계 선택'을 금지하고, 각 시간 표현에 역할을 부여한 뒤
    담화상 중심 시점을 결정하기 위한 분류다. 우선순위:
    명시적 정정 > 명시적 요청 대상 > 긍정 절 중심 > 승계 > 단순 언급.
    """

    TARGET = "target"  # 실제 분석 대상
    EXCLUDED = "excluded"  # 이번 요청에서 제외한 시점
    COMPARISON = "comparison"  # 비교용 시점
    REFERENCE = "reference"  # 과거 답변·사건을 가리키는 시점
    HYPOTHETICAL = "hypothetical"  # 가정으로 언급한 시점
    CORRECTION = "correction"  # 이전 시점을 정정하며 새로 제시한 시점
    MENTION = "mention"  # 술어 없이 단순 언급(역할 미확정)


class TimeConstraintItem(BaseModel):
    """연 단위 시간 표현 1건 + 역할 (2026-07-14 시점 정합 P1).

    실측 결함: "2026년 27년은 의미없고 2033년이 중요해"에서 첫 연도(2026)가
    시점으로 저장돼 후속 턴까지 오염. 모든 연도 표현을 추출해 역할을 부여하고,
    배제 연도는 절대 target으로 승격하지 않는다.
    """

    role: TimeConstraintRole
    start_year: int
    end_year: int
    source_span: str = ""  # 원문 근거 조각(출처 추적 — P7)
    reason: str = ""  # 역할 판정 근거 술어('의미없고' 등)
    explicit: bool = True
    confidence: float = 1.0


class TimeRange(BaseModel):
    """시점 상세 (docs/03 B2 timeRange — C차원 18패턴 수용)."""

    # 'relative'|'absolute'|'deadline'|'age_based'|'anchor_based'|'user_ranges'|'open_when'
    type: str
    granularity: Granularity
    start: str | None = None
    end: str | None = None
    end_offset_days: int | None = None
    deadline: str | None = None
    age: AgeRange | None = None
    anchor_dates: list[AnchorDate] = Field(default_factory=list)
    ranges: list[LabeledRange] = Field(default_factory=list)
    life_stage: str | None = None  # '초년'|'청년'|'중년'|'말년'|'평생'
    urgency: str | None = None  # 'asap'
    granularity_override: bool = False


class Constraints(BaseModel):
    """조건/제약 (docs/03 B2 constraints). 방위 기준점은 거주지 또는 발화 명시."""

    direction: str | None = None  # 8방위 또는 'unknown'
    location_base: str | None = None  # 현재 거주지(방위 기준점)
    target_region: str | None = None  # 이사 목적지 지역 — region_fit(지역 오행×용신)용
    son_eomneun_nal: bool | None = None
    conditional: str | None = None  # 가정형 원문
    branch_scenario: bool = False  # 결과 조건부('당선되면 이후 운까지')
    chained_schedule: list[ChainedStep] = Field(default_factory=list)
    reality_constraints: list[str] = Field(default_factory=list)
    exclude_options: list[str] = Field(default_factory=list)


class OutputStyle(BaseModel):
    """출력 스타일 (docs/03 B2 OutputStyle)."""

    format: OutputFormat = OutputFormat.NARRATIVE
    max_results: int | None = None
    score_display: str | None = None  # 'hundred_scale'|'grade'|'none'
    rank_range: int | None = None
    tone_override: str | None = None
    detail_level: str | None = None  # 'summary'|'detailed'


class IntentJson(BaseModel):
    """단일 의도 (docs/03 B2 IntentJson). subjects는 1명 이상, 기본 [self]."""

    intent_id: str
    query_type: QueryType

    subjects: list[SubjectRef] = Field(default_factory=list)
    subject_mode: SubjectMode = SubjectMode.SINGLE
    relation_type: CompanionRelationType | None = None

    domain: Domain = Domain.GENERAL
    domains: list[Domain] = Field(default_factory=list)
    event_key: EventKey | None = None
    event_keys: list[EventKey] = Field(default_factory=list)

    time_scope: TimeScope = TimeScope.TIMELESS
    time_range: TimeRange | None = None
    # 이번 턴에서 사용자가 배제·비교·정정한 연 단위 시간 제약(2026-07-14 P1).
    # excluded 역할은 엔진 창·서술에서 제외 대상이며 절대 target으로 승격하지 않는다.
    time_exclusions: list[TimeConstraintItem] = Field(default_factory=list)
    # 대화 행위(도메인 intent보다 상위) — 'conclusion_summary'(결론 재확인) 등.
    # 결론 요구형은 새 월별 분석 대신 직전 분석의 압축 결론을 계약한다(2026-07-14 P4).
    dialogue_act: str | None = None

    # R4 — 이사 종류(집=일지 중심 / 사무실=월주 중심). 기본 home(선택, 원칙 11).
    relocation_kind: str = "home"  # home|office
    # 직업 분야·직종·적성 질문(docs/08 career_field, 2026-09-10): '어떤 분야/직종/일이 맞나·
    # 제안이 온다면 어떤 분야' — 시점이 아니라 원국 십성 기능이 답의 축. 시점 승계 대상 아님.
    career_field: bool = False

    constraints: Constraints = Field(default_factory=Constraints)
    output: OutputStyle = Field(default_factory=OutputStyle)


class ParsedMessage(BaseModel):
    """한 메시지 파싱 결과 (docs/03 B2 ParsedMessage).

    intents는 1개 이상(다중 질문 실측 7.5%). 답변도 intent 수만큼 섹션을 보장해 부분
    질문 누락을 구조적으로 차단한다(docs/03 B4).
    """

    intents: list[IntentJson] = Field(default_factory=list)
    is_follow_up: bool = False
    inherited_from: str | None = None
    output_style: OutputStyle | None = None
    reality_context_updates: list[str] = Field(default_factory=list)
    # 턴별 시점 해소 추적(2026-07-14 P0) — extracted_times/resolved_target/excluded/
    # inherited_time 등. 파싱→상속→커밋 경로의 회귀 진단·E2E 검증용(운영 로직 미사용).
    trace: dict = Field(default_factory=dict)
