"""용신 후보 schemas (Phase 4a).

용신은 계산값이 아니라 검증 가능한 전략 모델이다. 최초 status 는 candidate 이며,
사용자 검증(calibration) 전에는 calibrated 로 만들지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 작동역할 라벨 enum(YONGSIN_OPERATIONAL_ROLE_SPEC §4-1). 정적 5역할 + 조건부/조후 합성 라벨.
# "조건부 …"·"조후보조신" 은 단순 길흉 라벨이 아니라 합성/조건부 라벨이다(해석은 mapper 경유).
OperationalRole = Literal[
    "용신", "희신", "기신", "구신", "한신",
    "조건부 희신/병", "조후보조신", "조건부 제살보조",
]


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


class ElementRole(BaseModel):
    """오행 1개의 정적(canonical)/작동(operational) 역할 이중 표현.

    canonical_role 은 현행 final 의 정적 생극 순환 결과(전통 오행표)이고,
    operational_role 은 실제 풀이·점수화가 소비할 작동 역할이다. Phase 0 에서는
    앞 3필드만 채우고, positive_when/negative_when/note 는 조건부 역할 도입(Phase 1+)에서
    채운다. operational_role 라벨 집합은 §YONGSIN_OPERATIONAL_ROLE_SPEC 4-1 enum 을 따른다.
    """

    element: str
    canonical_role: str  # 용신/희신/기신/구신/한신 (정적)
    operational_role: OperationalRole  # Phase 0: 모델맵. Phase 1~: 조건부/합성 라벨
    positive_when: list[str] = Field(default_factory=list)
    negative_when: list[str] = Field(default_factory=list)
    note: str | None = None
    # 작동성(operability, Phase 4) — 용신 원소만 채움(0~1, base 1.0 감점형). None=미산정.
    # final.confidence(모델 선택 신뢰도)와 별개의 '실제 작동성' 지표. factors 는 stable key.
    operability: float | None = Field(default=None, ge=0.0, le=1.0)
    operability_factors: list[str] = Field(default_factory=list)


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
    # 2계층 역할(YONGSIN_OPERATIONAL_ROLE_SPEC). canonical_roles 는 현행 final 5역할 미러(보존),
    # operational_roles 는 5역할 완비 모델의 자체 역할맵을 채택한 작동 역할(부분맵은 canonical
    # 폴백). Phase 0 은 생성·노출만 — 점수화(event_scoring)는 여전히 final 만 소비한다(미연결).
    canonical_roles: dict[str, str | None] = Field(default_factory=dict)
    operational_roles: list[ElementRole] = Field(default_factory=list)
    # 유통(流通) 흐름 점수(정보성):
    # {score, sheng_links, present_elements, all_five_present, smooth}.
    flow_circulation: dict | None = None
    requires_validation: bool = True
    warnings: list[str] = Field(default_factory=list)
