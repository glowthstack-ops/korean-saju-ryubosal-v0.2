"""이사 Composite Resolver(M10) 입출력 schemas (v2.2 Phase 2.5 T2.5.7, docs/09 7장).

LLM에는 `RelocationResult` + 압축 간지만 전달한다 — LLM이 받는 것은 "계산할 문제"가
아니라 "설명할 결론"이다(docs/09 7장).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .graph import EvidenceBundle
from .intent import ChainedStep, SubjectRef


class RelocationPeriod(BaseModel):
    """이사 가능 기간(데드라인 역산 결과 반영)."""

    start: str  # 'YYYY-MM'
    end: str


class RelocationQuery(BaseModel):
    """이사 질의 전체 필드 (docs/09 7장 RelocationQuery)."""

    group_subjects: list[SubjectRef] = Field(min_length=1)
    aggregation_rule: str = "householder_primary"  # |balanced|protect_weakest
    weights: dict[str, float] | None = None  # subject entity/label → 가중
    period: RelocationPeriod
    current_location: str  # 방위 기준점(필수 — 없으면 확인 질문)
    candidate_directions: list[str] | None = None  # 미지정 시 8방위 전부
    candidate_regions: list[str] | None = None
    housing_type: str | None = None  # buy|jeonse|monthly|new_build|old_build
    # R4 — 집 이사(일지 중심) vs 사무실 이전(월주 중심). 기본 home, 선택 입력(원칙 11).
    relocation_kind: str = "home"  # home|office
    reality_constraints: list[str] = Field(default_factory=list)
    chained_schedule: list[ChainedStep] = Field(default_factory=list)


class MoveDateScores(BaseModel):
    """부분점수 5종 + 최종 (docs/09 7장 S10)."""

    macro_flow: int = Field(ge=0, le=100)
    month_fit: int = Field(ge=0, le=100)
    day_execution: int = Field(ge=0, le=100)
    calendar_rule: int = Field(ge=0, le=100)
    reality_fit: int = Field(ge=0, le=100)
    final: int = Field(ge=0, le=100)


class MemberWarning(BaseModel):
    """구성원별 이동운 충돌 경고 (S2)."""

    subject_label: str
    signal: str


class MoveDateCandidate(BaseModel):
    """이사일 후보 1건."""

    date: str
    ganji: str
    final_score: int = Field(ge=0, le=100)
    scores: MoveDateScores
    direction_fit: dict[str, float] = Field(default_factory=dict)  # 방위별 분리 산출
    member_warnings: list[MemberWarning] = Field(default_factory=list)
    son_eomneun_nal: bool = False
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class RelocationReasonProfile(BaseModel):
    """십성 기반 이사 이유·집성격·리스크 분류 (R2, docs/02·09 — relocation_ten_gods.json).

    이사 '발생'은 합·충·역마·재관 자극이 보고(events/relocation.json), 십성은 '왜 이사하고
    어떤 집으로 가는가'를 분류한다. 점수·날짜·랭킹에 일절 개입하지 않는 해석 라벨 전용
    (절대원칙 1·12). source는 신호 출처(천간=명분 / 지지=현장, 사용자 스펙 5장).
    """

    ten_god: str
    source: str  # '세운 천간(명분)' | '월운 지지(현장)' 등
    type: str
    move_reason: list[str]
    property_tendency: list[str]
    risk: list[str]
    required_checks: list[str]
    risk_level: str
    main_question: str


class GroupSummary(BaseModel):
    """그룹 월별 집계 + 충돌 (docs/09 7장 groupSummary)."""

    monthly_scores: dict[str, float] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)


class AvoidDate(BaseModel):
    """회피일 + 사유."""

    date: str
    reason: str


class RelocationResult(BaseModel):
    """이사 Resolver 최종 산출 (docs/09 7장 RelocationResult)."""

    contract_window: list[MoveDateCandidate] = Field(default_factory=list)  # 체인 모드
    move_dates: list[MoveDateCandidate] = Field(default_factory=list)
    reason_profiles: list[RelocationReasonProfile] = Field(default_factory=list)  # R2
    group_summary: GroupSummary = Field(default_factory=GroupSummary)
    avoid_dates: list[AvoidDate] = Field(default_factory=list)
    evidence: list[EvidenceBundle] = Field(default_factory=list)
