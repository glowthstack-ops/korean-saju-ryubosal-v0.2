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


class UsefulGods(BaseModel):
    """용·기신 요약(LLM 판정 금지 — 확정값 전달)."""

    yongsin: list[str] = Field(default_factory=list)
    gisin: list[str] = Field(default_factory=list)


class BirthChartSummary(BaseModel):
    """원국 요약 (docs/06 birthChartSummary)."""

    day_master: str
    pillars: dict[str, str]  # {'year': '庚申', ...} — 시주 미상이면 hour 생략
    void_branches: list[str] = Field(default_factory=list)
    strength: str = ""  # '중화신강'
    useful_gods: UsefulGods = Field(default_factory=UsefulGods)


class DaewoonEntry(BaseModel):
    """대운 한 줄 — 장기 질문이면 전체 제공."""

    period: str  # '2025~2035'
    ganji: str
    age_range: str  # '45~54세'


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
    period: str
    ganji: str
    daewoon_context: str
    score: int = Field(ge=0, le=100)
    confidence: str
    polarity: str
    timeline: dict | None = None  # EventTimeline (Phase 5 E4)
    realization_score: int | None = None  # Manifestation (Phase 5 E6)
    likely_forms: list[str] = Field(default_factory=list)


class LlmEvidence(BaseModel):
    """근거 묶음 — 반대 근거(contradicts) 동반(단정 방지, docs/04 Retrieval 3)."""

    event_key: EventKey
    readable_paths: list[list[str]] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)


class LlmStyleRules(BaseModel):
    """해석 제한 규칙 (docs/06 styleRules)."""

    prohibited: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)
    tone_guide: str = ""
    llm_instruction: str = ""


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


class LlmInput(BaseModel):
    """LLM 입력 계약 전체 (docs/06 LlmInput)."""

    user_question: str
    resolved_intent: IntentJson

    birth_chart_summary: BirthChartSummary
    calendar_context: LlmCalendarContext = Field(default_factory=LlmCalendarContext)
    event_candidates: list[LlmEventCandidate] = Field(default_factory=list)
    evidence: list[LlmEvidence] = Field(default_factory=list)
    past_validation: PastValidationSummary | None = None
    style_rules: LlmStyleRules = Field(default_factory=LlmStyleRules)
    output_format: OutputFormatSpec | None = None
    persona: PersonaBlock = Field(default_factory=PersonaBlock)
    user_profile_context: dict | None = None  # 해당 질문에 필요한 필드만(전체 주입 금지)
    section_mode: SectionMode | None = None
    budget: LlmBudget
