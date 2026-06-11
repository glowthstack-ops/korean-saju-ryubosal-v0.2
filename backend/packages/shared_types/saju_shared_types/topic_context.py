"""Topic Context 표준 schema (v2.2 Phase 2.5 T2.5.6, docs/09 5장).

Topic Builder 모듈(M01~M15)의 공통 출력. findings·ranked_results의 모든 수치는
Topic Builder에서 확정되며 LLM 입력 이후 어떤 수치도 변하지 않는다(docs/09 5장,
정합성 검사 — docs/10 7장).

Finding/RankedItem/GroupAggReport의 세부 필드는 문서에 미정의라 최소형으로 시작한다
(검수 대상). calendar_context는 docs/06 LLM 입력 계약의 압축 간지달력과 동일 구조를
지향하되, Phase 3(T3.5 직렬화기)에서 확정한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .graph import EvidenceBundle
from .intent import SubjectRef


class PeriodSpec(BaseModel):
    """분석 기간."""

    start: str
    end: str
    granularity: str  # 'daewoon'|'year'|'month'|'day'|'hour'


class CalendarContextEntry(BaseModel):
    """압축 간지달력 한 항목 — LLM은 간지를 계산할 수 없으므로 항상 동반(절대 원칙 2)."""

    period_key: str
    ganji: str
    parent_daewoon: str | None = None
    parent_year: str | None = None


class Finding(BaseModel):
    """모듈 핵심 산출 1건(점수 확정 완료) — 최소형(문서 미정의, 검수 대상)."""

    key: str  # 'career_change@2026' 등 안정 식별자
    summary: str  # 한글 요약(LLM 서술 재료)
    score: int = Field(ge=0, le=100)
    event_key: str | None = None
    period_key: str | None = None
    signals: list[str] = Field(default_factory=list)


class TimeSeriesPoint(BaseModel):
    """시계열 한 점 (docs/09 5장 timeSeries)."""

    period_key: str
    ganji: str
    score: int = Field(ge=0, le=100)
    signals: list[str] = Field(default_factory=list)


class RankedItem(BaseModel):
    """택일/랭킹형 결과 1건 — 최소형(M10/E10에서 부분점수 확장)."""

    label: str  # 날짜/선택지
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class TraitShift(BaseModel):
    """시기별 성향 변화 (docs/09 6장 — M03 전용)."""

    period_key: str  # 'DW:壬辰' | '2026'
    dominant_ten_gods: list[str] = Field(default_factory=list)  # 상위 2~3
    rising_traits: list[str] = Field(default_factory=list)
    fading_traits: list[str] = Field(default_factory=list)
    quality_flag: str = "favorable"  # favorable | pressured | mixed
    evidence: list[str] = Field(default_factory=list)


class GroupAggReport(BaseModel):
    """다중 대상 집계 — 최소형(M10 S2에서 확장)."""

    rule: str  # householder_primary | balanced | protect_weakest
    member_scores: dict[str, float] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)


class StyleRules(BaseModel):
    """표현 제한 — 금기/톤/단정금지 (절대 원칙 3·8)."""

    prohibited_expressions: list[str] = Field(default_factory=list)
    tone_notes: list[str] = Field(default_factory=list)


class TokenBudget(BaseModel):
    """LLM 입출력 예산 (docs/09 8장 거버넌스와 연동)."""

    max_input_tokens: int
    max_output_chars: int


class TopicContext(BaseModel):
    """Topic Builder 모듈 공통 출력 (docs/09 5장)."""

    module_id: str  # 'M07'
    subjects: list[SubjectRef] = Field(default_factory=list)
    period: PeriodSpec
    calendar_context: list[CalendarContextEntry] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    time_series: list[TimeSeriesPoint] = Field(default_factory=list)
    ranked_results: list[RankedItem] = Field(default_factory=list)
    trait_shifts: list[TraitShift] = Field(default_factory=list)
    group_aggregation: GroupAggReport | None = None
    evidence: list[EvidenceBundle] = Field(default_factory=list)
    style_rules: StyleRules = Field(default_factory=StyleRules)
    budget: TokenBudget
