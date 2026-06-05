"""용신 후보 schemas (Phase 4a).

용신은 계산값이 아니라 검증 가능한 전략 모델이다. 최초 status 는 candidate 이며,
사용자 검증(calibration) 전에는 calibrated 로 만들지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ElementCandidate(BaseModel):
    element: str
    score: float
    model: str | None = None
    reason: str | None = None


class YongsinCandidateModel(BaseModel):
    model_type: str
    label: str
    yongsin: str | None = None
    heesin: str | None = None
    gisin: str | None = None
    gusin: str | None = None
    hansin: str | None = None
    confidence: float
    reasons: list[str] = Field(default_factory=list)
    requires_validation: bool = True
    # 조후·고립/건강 등 보조 모델은 단독으로 용신을 확정할 수 없다.
    is_auxiliary: bool = False


class SpecialCaseCheck(BaseModel):
    detected: bool
    confidence: float = 0.0
    detail: str | None = None


class AggregatedYongsinResult(BaseModel):
    status: str  # candidate / probable / calibrated / uncertain
    special_case_checks: dict[str, SpecialCaseCheck] = Field(default_factory=dict)
    candidate_models: list[YongsinCandidateModel] = Field(default_factory=list)
    useful_candidates: list[ElementCandidate] = Field(default_factory=list)
    unfavorable_candidates: list[ElementCandidate] = Field(default_factory=list)
    # 다축(억부/조후/격국/병약/특수격) 동적 가중치 + 축별 기여(보정 레이어).
    axis_weights: dict[str, float] = Field(default_factory=dict)
    axes: list[dict] = Field(default_factory=list)  # [{axis, weight, top_element, score}]
    final: dict = Field(default_factory=dict)
    requires_validation: bool = True
    warnings: list[str] = Field(default_factory=list)
