"""LLM 입력 계약 schema (v2.2 Phase 3 T3.5, docs/06 — 표준 스키마 전체).

LLM에 전달되는 데이터의 표준 포맷 — **이 계약을 벗어난 정보는 LLM에 넣지 않는다.**
4요소 필수: ① 압축 간지달력(LLM은 간지 계산 불가) ② 이벤트 후보+점수 ③ 근거 경로
④ 해석 제한 규칙. 전체 간지달력/전체 사전/원시 그래프 투입 금지.

persona(docs/11 5장)는 Phase 8.5 전까지 기본 빈 블록으로 둔다(문체 전용 — 사실 불변).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .events import EventKey
from .intent import IntentJson
from .sinsal import LlmSinsalModifier
from .structure_patterns import DetectedPattern


class UsefulGods(BaseModel):
    """용희기구한 요약(LLM 판정 금지 — 확정값 전달). v2.2.1: 5역할 전부 제공.

    희신/구신/한신까지 제공해야 사용자가 물었을 때 환각·'모름' 없이 답한다(항목 8).
    """

    yongsin: list[str] = Field(default_factory=list)
    heesin: list[str] = Field(default_factory=list)  # 용신을 돕는 기운
    gisin: list[str] = Field(default_factory=list)
    gusin: list[str] = Field(default_factory=list)  # 기신을 돕는 기운
    hansin: list[str] = Field(default_factory=list)  # 조건부 작용


class BirthChartSummary(BaseModel):
    """원국 요약 (docs/06 birthChartSummary)."""

    day_master: str
    pillars: dict[str, str]  # {'year': '庚申', ...} — 시주 미상이면 hour 생략
    void_branches: list[str] = Field(default_factory=list)
    strength: str = ""  # '중화신강'
    useful_gods: UsefulGods = Field(default_factory=UsefulGods)
    geokguk: str = ""  # '정재격 · 중성 · 반성반패'(항목 9 — 격국 정보)


class PillarDetail(BaseModel):
    """주(柱) 1개의 구조 — 엔진 계산값(LLM 재판정 금지). v2.2.1 ⑤."""

    palace: str  # 'year' | 'month' | 'day' | 'hour'
    palace_ko: str = ""  # '연주' 등
    ganji: str
    stem_ten_god: str  # 일간 주는 '일원'
    branch_ten_god: str
    twelve_stage: str
    sinsal: list[str] = Field(default_factory=list)  # 보조 자료 — 단독 결론 금지
    palace_role: str = ""  # 궁성 자리역할(항목 14): '천간 부친 · 지지 모친' 등


class InterpretationExcerpt(BaseModel):
    """해석 사전 발췌 1건 — Planner dictionaryScope 선별 결과만(전체 투입 금지)."""

    kind: str  # 'ten_god' | 'relation' | 'sinsal' | 'twelve_stage' | 'ilju'
    key: str  # '정관' | '갑기합' | ...
    text: str


class YongsinOperationalSummary(BaseModel):
    """원국(natal) 기준 작동 역할 요약 — 정적 用喜忌仇閑과 다를 수 있는 실제 작동성/조건부 해석.

    YONGSIN_OPERATIONAL_ROLE_SPEC §10. **원국 전용**(운·세운·월운 무관 → 캐시 고정 prefix 적격).
    LLM 입력용 compact 요약(operational_roles 전체 dump 아님). 점수·이벤트 판정은 불변 — 이 요약은
    '실제 작동성·조건부 해석 우선 참고' 자료일 뿐 길흉 점수를 바꾸지 않는다.
    """

    primary_yongsin: str  # 용신 오행(한자)
    operability: float | None = None  # 용신 작동성 0~1
    operability_level: str = ""  # 표시용 작동성 밴드(높음/보통/낮음) — 확정 등급 아님
    operability_factors: list[str] = Field(default_factory=list)  # stable key(내부)
    operability_factors_ko: list[str] = Field(default_factory=list)  # 프리픽스용 한국어 압축
    main_support: list[str] = Field(default_factory=list)  # 조후보조신 등 보조약
    conditional: list[str] = Field(default_factory=list)  # 조건부 라벨(mapper=conditional)
    warnings: list[str] = Field(default_factory=list)  # 핵심 경고(≤3, deterministic 우선순위)


class ChartInterpretation(BaseModel):
    """⑤ 명식 구조 + 해석 자료 (docs/06 v2.2.1 — 캐시되는 고정 prefix에 직렬화).

    사용자별로 멀티턴·전 섹션에서 동일해야 한다(가변 값 금지 — 캐시 무효화 방지).
    """

    pillar_details: list[PillarDetail] = Field(default_factory=list)
    natal_relations: list[str] = Field(default_factory=list)  # 원국 내 합충·병존·간여지동
    # 원국 천간합의 작용 모드(합화/합반/합거/본신지합)+신뢰도 — 엔진 판정(HAP_INTERACTION_SPEC).
    hap_modes: list[str] = Field(default_factory=list)
    ilju_text: str = ""  # interpretations/ilju.json 해당 엔트리 직렬화
    excerpts: list[InterpretationExcerpt] = Field(default_factory=list)
    # 원국 기준 작동 역할 요약(Phase 5a) — 없으면 None(구형/부분 결과 안전 fallback).
    yongsin_operational_summary: YongsinOperationalSummary | None = None


class DaewoonEntry(BaseModel):
    """대운 한 줄 — 장기 질문이면 전체 제공."""

    period: str  # '2025~2035'
    ganji: str
    age_range: str  # '45~54세'
    jiao_date: str = ""  # 교운일(대운 시작) — 교운기 영향 판단용(항목 1)


class SelectedYear(BaseModel):
    """선택된 세운 — 이벤트 점수 상위만(전체 투입 금지)."""

    year: int
    ganji: str
    daewoon: str  # 대운 맥락
    reason_selected: str  # 'career_change 100점' 등 선별 사유


class SelectedMonth(BaseModel):
    """선택 세운 안의 월운만."""

    period: str  # '2026-06'
    ganji: str
    year: str


class SelectedDay(BaseModel):
    """택일 질의에서만 제공."""

    date: str
    ganji: str


class LlmCalendarContext(BaseModel):
    """압축 간지달력 (docs/06 calendarContext — 계층형 압축 규칙의 산출)."""

    daewoon: list[DaewoonEntry] = Field(default_factory=list)
    selected_years: list[SelectedYear] = Field(default_factory=list)
    selected_months: list[SelectedMonth] = Field(default_factory=list)
    selected_days: list[SelectedDay] = Field(default_factory=list)


class LlmEventCandidate(BaseModel):
    """이벤트 후보 — 간지·대운 맥락 **반드시 포함**(LLM 간지 계산 불가 보완)."""

    event_key: EventKey
    event_ko: str = ""  # 한글 라벨(taxonomy) — 답변 노출용, 내부 키 노출 방지
    period: str
    ganji: str
    daewoon_context: str
    score: int = Field(ge=0, le=100)
    signal_count: int = 0  # 동점 변별용(점수 포화 완화)
    confidence: str
    polarity: str
    # 사건 방향(길흉)+타이밍 라벨('기회·유입 · 지연' 등) — 모호한 polarity 4값 대신 또렷한 방향.
    direction: str = ""
    # v2.2.1 — 동반 신호 매트릭스: 사건명은 단일 합·십성이 아니라 신호 구성이 결정
    # (regression_2025_08: 갑기합만 보고 취업 단정 금지 — 역마+식상이면 이동 우세).
    signals_ko: list[str] = Field(default_factory=list)
    # v2.2.1 — 운 유입 글자의 일간 기준 십성 해석(해석 사전 발췌, 엔진 계산).
    incoming_note: str = ""
    # 운 암합(보조 자료) — 점수 미반영, 물밑·비공식 뉘앙스 참고용(2026-06-12 자료).
    amhap_notes: list[str] = Field(default_factory=list)
    # 유불리 주의(후보별 사실) — 천간 흉신 시기: 발생해도 계약·결실 불리(우호 단정 방지).
    caution_note: str = ""
    # 결과 유불리 밴드(유리/불리, 중립이면 빈 문자열) — 발생 가능성(score)과 분리된 길흉 채널.
    # 시험 합·불, 특수직군 길화, 퇴직 리스크, 이직 압박/기회 등이 합산된 net 유불리.
    favorability_ko: str = ""
    timeline: dict | None = None  # EventTimeline (Phase 5 E4)
    realization_score: int | None = None  # Manifestation (Phase 5 E6)
    likely_forms: list[str] = Field(default_factory=list)
    # 신살 보조 태그(SINSAL_MODIFIER_SPEC §9-2, Phase A-1) — 점수 미반영, 보조 해석 전용.
    # 후보당 ≤3(pruning). 숫자 weight 미노출(한글 강도어만). 단독 사건 근거 금지.
    sinsal_modifiers: list[LlmSinsalModifier] = Field(default_factory=list)
    # 신살 기간 채널 색채(§10-2, Phase B-2) — 숫자 없는 한글(완충/리스크/색채/질감). 발생 가능성
    # 미반영. 토큰 초과 시 캐시 prefix보다 먼저 트림되는 보조 텍스트(serialize_with_guard Tier0).
    sinsal_channel_note: str = ""
    # 관계 단계(MARRIAGE_TIMING_ENHANCEMENT — Production Readiness v1 Step 2). MT 신호 기반.
    # 빈값이면 MT 미발동(비-관계 후보·default 프로파일) — 렌더 시 미노출(출력 불변).
    marriage_stage: str = ""           # awareness | relationship | ""
    marriage_base_stage: str = ""      # base E4 환원
    marriage_stage_reason: list[str] = Field(default_factory=list)  # 단계 유발 MT 코드
    marriage_stage_limit: str = ""     # 승급 상한 사유(commitment_marker_absent 등)


class LlmEvidence(BaseModel):
    """근거 묶음 — 반대 근거(contradicts) 동반(단정 방지, docs/04 Retrieval 3)."""

    event_key: EventKey
    readable_paths: list[list[str]] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    # graph rag 실효화(항목 15) — 보조 근거·해석 규칙 힌트도 프롬프트에 전달.
    supports: list[str] = Field(default_factory=list)
    interpretation_hints: list[str] = Field(default_factory=list)


class LlmStyleRules(BaseModel):
    """해석 제한 규칙 (docs/06 styleRules)."""

    prohibited: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)
    tone_guide: str = ""
    llm_instruction: str = ""


class ReferenceFrame(BaseModel):
    """기준 시점 — LLM은 오늘이 언제인지 모른다(v1 [오늘 날짜] 원칙 계승)."""

    today: str  # '2026-06-11 (목)'
    this_year: str  # '2026'
    this_year_ganji: str = ""  # '丙午'
    # 오늘이 속한 절기 월운 라벨(YYYY-MM) — 양력 달과 다를 수 있다(절기 경계 직전 구간).
    # '지남' 마커 등 시제 판정의 기준 달(기계 비교용 — 반드시 bare 'YYYY-MM' 유지).
    # 미설정 시 today[:7] 양력 폴백.
    this_luck_month: str = ""  # '2026-06'
    # 현재 절기월의 사람이 읽는 상세 — 간지·양력 절기 span·진행 상태. LLM이 절기월 라벨(YYYY-MM)을
    # 캘린더월로 오인해 진행 중인 달을 '다가오는 미래'로 서술하는 것을 차단(2026-07-02 데굴님 지적).
    this_luck_month_detail: str = ""  # '2026-06 甲午월(양력 6/6~7/6 진행 중, 오늘 7/2·남은 5일)'
    question_period: str = ""  # '2026-01-01 ~ 2026-12-31'
    question_period_note: str = ""  # "질문의 '올해'는 2026년을 의미한다"


class MonthOverviewRow(BaseModel):
    """월별 요약 한 칸 — '올해운을 월별로' 류 대응(v1 monthSummaryText 계승)."""

    period: str  # '2026-03'
    ganji: str
    top_event_ko: str = ""  # 그 달 최고 신호(없으면 빈 값)
    score: int | None = None
    polarity: str = ""
    # 사건 방향(길흉)+타이밍 사용자 라벨('기회·유입 · 지연' 등) — 모호한 polarity 4값 대체.
    direction: str = ""
    # 교운(대운 교체) 근접 라벨 — 점수 cap 포화로 사라지는 교운일 가중 차이를 표면화.
    transition: str = ""
    # 창 내 상대 강도 순위(1=최강, 클램프 전 raw 가중 합 기준) — 톤이 포화돼도
    # '진짜 중요한 달'이 변별되게(절대값보다 상대 순위 신뢰 — docs/07 리스크 1).
    strength_rank: int | None = None
    # 그 달 간지의 용기신 역할 '癸水 구신·巳火 희신' — 발생 강도와 별개로 유불리
    # (구신 천간 달=계약·결실 불리)가 표에서 변별되게(2026-06-12 사용자 도메인 지식).
    luck_roles: str = ""
    # 그 달의 운 품질 등급(luck_label: '강한 용신운'/'용신운(부분)'/'혼합'/'기신운' 등) —
    # 길흉(좋은 달/부담스러운 달)은 사건 밀도가 아니라 이 운 품질이 1차 기준(길흉=용신/기신).
    # 신약 사주에 천간·지지 모두 용신인 '강한 용신운' 달은 사건이 적어도 가장 도움되는 달.
    luck_grade: str = ""
    # 발현 분기 — 그 달 우세 사건과 같은 계열(EVENT_CATEGORY)에서 같은 시점에 점수화된
    # 형제 사건(예: 이직↔이사)을 강도순으로. 한 사건으로 단정하지 않게 한다(2026-06-14).
    branch_ko: str = ""


class PeriodFortuneSlot(BaseModel):
    """종합운 고정 슬롯 1칸 (docs/02 E9 — 엔진 확정값, LLM은 문장화만)."""

    name: str  # '돈·소비' | '재물'
    score: int = Field(ge=0, le=100)
    summary: str  # 엔진 산출 재료(수치/간지) — LLM은 이 범위로만 서술


class PeriodFortune(BaseModel):
    """특정 기간 총운 — E9 Lifestyle 슬롯 + 해당 기간 간지 grounding(엔진 확정값).

    fortune_type별로 일/월/연 총운을 담는다. 운 위계(대운>세운>월>일)에서 상위가
    형성한 기운이 하위 기간에서 사건화되며, 점수는 위계 가중 합산이다. 출력은 해당
    기간 단위 사건·조짐으로 한정하고 인생 사건의 실행·확정은 단정하지 않는다(절대원칙 3·4).
    """

    fortune_type: str  # 'daily' | 'monthly' | 'yearly'
    period_label: str  # '2026-06-12 (금)' | '2026-07' | '2026'
    ganji: str  # 해당 기간 간지(일진/월운/세운) '丁巳'
    # 절기월 안내 — 월운은 절기 경계라 양력 달과 어긋난다(예: 未월=7/7~8/6). '7월=을미월' 혼동을
    # 막으려 절기월 간지와 양력 날짜 범위를 함께 준다(2026-06-22 데굴님 제안). 비어 있으면 미표기.
    solar_month_note: str = ""
    pillar_line: str  # 십성·십이운성·용신정렬 요약 1줄(grounding)
    luck_label: str = ""  # '강한 용신운'
    luck_summary: str = ""  # 엔진 운 요약 그대로
    relation_lines: list[str] = Field(default_factory=list)  # 형충회합(운 성립 시 의미)
    sinsal_lines: list[str] = Field(default_factory=list)  # 신살 보조·양면
    gongmang: list[str] = Field(default_factory=list)  # 공망 활성
    slots: list[PeriodFortuneSlot] = Field(default_factory=list)  # 고정 슬롯(기간별)


class DateChoiceRow(BaseModel):
    """택일 추천 1행(E10 산출 — LLM은 그대로 인용만)."""

    date: str
    weekday: str  # '토'
    ganji: str
    score: int
    recommendation: str  # recommended | acceptable
    notes: list[str] = Field(default_factory=list)  # 손없는 날·공휴일·사유


class DateSelectionBlock(BaseModel):
    """택일 결과 블록 — 표가 있으면 회피성 답변 금지(v1 이사일 원칙 계승)."""

    purpose_ko: str
    period: str  # '2026-07-01 ~ 2026-07-31'
    rows: list[DateChoiceRow] = Field(default_factory=list)
    avoid: list[dict] = Field(default_factory=list)  # {'date','reason'}
    cautions: list[str] = Field(default_factory=list)
    # 방위·시진(횡재·재물 택일 — 참고용, 당첨 보장 아님). {'direction','element','fit','note'} 등.
    directions: list[dict] = Field(default_factory=list)
    hour_fits: list[dict] = Field(default_factory=list)  # {'branch','time_range','fit','note'}
    # 그룹(다인) 이사 — 구성원 이동운 충돌·경고(M10 group_summary·member_warnings). 빈 = 단일.
    group_warnings: list[str] = Field(default_factory=list)
    # 이사 — 십성 이유분류 라벨 줄(천간=명분/지지=현장, 대운=장기 배경·세운=대표·월운=발동). R2.
    relocation_reasons: list[str] = Field(default_factory=list)


class PersonaBlock(BaseModel):
    """페르소나 — 문체 전용(docs/11). Phase 8.5 전까지 빈 블록."""

    config: dict = Field(default_factory=dict)
    prompt_block: str = ""
    resolved_honorific: str = ""


class PastValidationSummary(BaseModel):
    """과거 검증 요약(신뢰 형성 — 미래 예측보다 먼저)."""

    summary: str
    calibrated_confidence: float | None = None


class OutputFormatSpec(BaseModel):
    """출력 형식 지정(B14/슬롯형)."""

    type: str  # 'report' | 'ranked_dates' | 'timeline' | 'slots'
    slots: list[str] = Field(default_factory=list)


class SectionMode(BaseModel):
    """보고서 섹션 생성 모드(docs/10 — Phase 9)."""

    product_code: str  # 'RPT_FULL' | 'RPT_FOCUS'
    section_id: str
    section_title: str
    target_chars: dict[str, int] = Field(default_factory=dict)  # {'min':, 'max':}
    fixed_facts: list[str] = Field(default_factory=list)  # 선행 섹션 확정 사실 — 모순 금지


class LlmBudget(BaseModel):
    """입출력 예산 (docs/09 8장 한도와 연동)."""

    max_input_tokens: int
    max_output_chars: int


class SubjectBlock(BaseModel):
    """동반자 공동 풀이(P2a)의 대상 1명 명식 블록 — 본인/동반자 각각 compact 요약.

    본인 기준 birth_chart_summary(단일 대상 계약)와 별개로, 여러 대상을 분리 주입할 때 쓴다.
    P2a는 pairwise만(본인+동반자 1명) — 원국 구조 요약(BirthChartSummary 재사용) + 현재 운
    한 줄. 대상별 event 후보 등 정밀 산출은 후속(companion_only/P2b)로 확장한다.
    """

    subject_id: str
    role: str  # 'self' | 'companion'
    label: str
    is_primary: bool = False
    relation_to_user: str | None = None
    chart: BirthChartSummary
    current_period: str = ""  # '대운 壬辰 · 세운 丙午(2026)' 등 compact


class RelationshipContext(BaseModel):
    """공동 풀이 관계 맥락(P2a) — 어떤 조합·관계로 함께 보는지. 실행은 pairwise 한정."""

    mode: str  # CompanionReadMode 값
    relation_type: str | None = None
    primary_subject_id: str | None = None
    companion_subject_ids: list[str] = Field(default_factory=list)
    compatibility_overlay_available: bool = False  # _compat_prompt_block 보조 존재 여부


class LlmInput(BaseModel):
    """LLM 입력 계약 전체 (docs/06 LlmInput)."""

    user_question: str
    resolved_intent: IntentJson

    birth_chart_summary: BirthChartSummary
    # ⑤ 명식 구조+해석 자료(v2.2.1) — 고정 prefix(캐시 대상)에 직렬화.
    chart_interpretation: ChartInterpretation | None = None
    calendar_context: LlmCalendarContext = Field(default_factory=LlmCalendarContext)
    event_candidates: list[LlmEventCandidate] = Field(default_factory=list)
    # 질문 기간 밖 상위 후보 — 참고 맥락 전용(메인 서술 금지 지시 동반).
    out_of_range_candidates: list[LlmEventCandidate] = Field(default_factory=list)
    no_candidates_in_period: bool = False  # 기간 내 후보 없음 → 정직한 '신호 없음' 유도
    reference: ReferenceFrame | None = None  # 기준 시점(필수 주입 — chat 경로)
    is_followup_turn: bool = False  # 멀티턴 2턴째 이상 — 인사·재인용 절제 지시(항목 19)
    # 이전 턴에서 시스템이 이미 제시한 엔진 결과(한글화) — 턴 간 모순 방지(2026-06-12:
    # 같은 기간을 1턴 '재취업 성공'↔2턴 '공백기'로 뒤집던 결함).
    prior_claims: list[str] = Field(default_factory=list)
    monthly_overview: list[MonthOverviewRow] = Field(default_factory=list)
    period_fortune: PeriodFortune | None = None  # 기간 총운(E9) — 일/월/연 경로
    date_selection: DateSelectionBlock | None = None
    # 구조 해석 블록(질문 도메인에 맞는 원국 횡재 그릇·결혼/자산·건강 취약·부귀·시대 기운 등).
    # 이미 누출 안전 한글로 직렬화된 줄들(영문 변수·점수 비노출). 도메인 관련 시에만 채운다.
    structural_context: list[str] = Field(default_factory=list)
    # 물상(2단계 프로필) 사실 맥락 — 직업·혼인·거주·자녀 중 질문 도메인 관련 항목만(사실 서술).
    # 점수·판정 불변, 페르소나 아님. LLM이 상황에 맞게 구체화하는 근거.
    profile_facts: list[str] = Field(default_factory=list)
    # 구조 패턴 압축 태그(Step ④) — 질문 가변 suffix에 직렬화, 질문 도메인 우선 선별(top-6).
    # 길흉 미확정(polarity_mode·domain_hints만). 전체 감지는 내부 보존(비직렬화).
    detected_patterns: list[DetectedPattern] = Field(default_factory=list)
    evidence: list[LlmEvidence] = Field(default_factory=list)
    past_validation: PastValidationSummary | None = None
    style_rules: LlmStyleRules = Field(default_factory=LlmStyleRules)
    output_format: OutputFormatSpec | None = None
    persona: PersonaBlock = Field(default_factory=PersonaBlock)
    user_profile_context: dict | None = None  # 해당 질문에 필요한 필드만(전체 주입 금지)
    section_mode: SectionMode | None = None
    # 동반자 공동 풀이(P2a) — 본인+동반자 대상별 명식 블록 분리 주입. 비면 단일 대상(기존).
    subject_blocks: list[SubjectBlock] = Field(default_factory=list)
    relationship_context: RelationshipContext | None = None
    budget: LlmBudget
