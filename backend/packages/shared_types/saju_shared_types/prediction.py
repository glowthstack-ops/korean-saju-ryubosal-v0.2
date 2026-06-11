"""예측 엔진군 출력 schemas (v2.2 Phase 5, docs/02 E3~E8·E12·E13).

모든 점수·확률은 엔진(코드)이 확정하며 LLM은 서술만 한다(절대 원칙 1·3).
Trigger Month ≠ Execution Month — Activation Window 필수(절대 원칙 4).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .events import EventKey


class ActivationWindow(BaseModel):
    """이벤트 활성 구간 (docs/01 — Trigger/Execution 분리 모델)."""

    start: str  # '2026-06'
    end: str


class TimelinePhase(BaseModel):
    """단계 한 칸 — awareness→exploration→action→decision→completion."""

    period: str
    stage: str


class TimelineScores(BaseModel):
    """단계 분리 점수 (docs/01 — interest/action/completion)."""

    interest: int = Field(ge=0, le=100)
    action: int = Field(ge=0, le=100)
    completion: int = Field(ge=0, le=100)


class EventTimeline(BaseModel):
    """E4 Timeline — progress 이벤트 전용("6월 이직운 ≠ 6월 퇴사" 오해 해소)."""

    event_key: EventKey
    activation_window: ActivationWindow
    phases: list[TimelinePhase] = Field(default_factory=list)
    scores: TimelineScores


class EventForm(BaseModel):
    """발현 형태 1종."""

    name: str
    prob: float = Field(ge=0.0, le=1.0)


class EventFormResult(BaseModel):
    """E3 Event Form — 같은 신호의 발현 형태 분포(prob 합 ≤ 1.0)."""

    event_key: EventKey
    forms: list[EventForm] = Field(default_factory=list)


class SelfProfile(BaseModel):
    """E5 Self Profile — 성향이 이벤트의 현실화 방식을 결정(성격검사화 금지)."""

    decision_style: str  # impulsive | deliberate | avoidant | consensus
    risk_tolerance: int = Field(ge=0, le=100)
    execution_power: int = Field(ge=0, le=100)
    axes: dict[str, str] = Field(default_factory=dict)  # relationship/money/work/stress
    manifestation_tendency: str = ""  # 통변 문구 재료
    evidence: list[str] = Field(default_factory=list)  # 모든 축에 근거 첨부


class ManifestationResult(BaseModel):
    """E6 Manifestation — 발생 가능성 ≠ 현실화(세 요소 결합)."""

    event_key: EventKey
    event_score: int = Field(ge=0, le=100)
    profile_modifier: int  # E5 기반(예: -15)
    context_modifier: int  # Reality Context 기반(부재 시 0 + confidence 하향)
    realization_score: int = Field(ge=0, le=100)
    likely_forms: list[str] = Field(default_factory=list)
    confidence: str = "medium"  # context 부재 시 하향


class AdviceItem(BaseModel):
    """행동 조언 1건."""

    period: str
    action: str
    rationale: str


class AdviceResult(BaseModel):
    """E8 Advice — '그래서 뭘 해야 하나'. 의료·법률·투자 단정 금지."""

    event_key: EventKey
    advice: list[AdviceItem] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)


class CompatibilityAxis(BaseModel):
    """궁합 축별 평가."""

    axis: str
    ko: str
    score: int = Field(ge=0, le=100)
    notes: list[str] = Field(default_factory=list)


class CompatibilityResult(BaseModel):
    """E13 Compatibility — 관계 유형별 축 분석."""

    relation_type: str
    overall: int = Field(ge=0, le=100)
    axes: list[CompatibilityAxis] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)  # 관계 패턴
    frictions: list[str] = Field(default_factory=list)  # 갈등 요소
    advice: list[str] = Field(default_factory=list)


class CompetitionCandidate(BaseModel):
    """E12 경쟁 후보 1명 — 판정일 운세 강도."""

    subject_label: str
    strength_score: int = Field(ge=0, le=100)
    evidence_path: list[str] = Field(default_factory=list)
    data_quality: str = "full"  # full | no_hour(공인 등 시각 미상 → 신뢰도 한계 명시)


class CompetitionResult(BaseModel):
    """E12 Competition — 상대 우열 + 근거까지만. 당락·승패 확정 표현 출력 금지."""

    anchor_date: str
    candidates: list[CompetitionCandidate] = Field(default_factory=list)
    relative_gap: str = "inconclusive"  # clear | narrow | inconclusive
    prohibitions: list[str] = Field(default_factory=list)  # templates 고정 문구
