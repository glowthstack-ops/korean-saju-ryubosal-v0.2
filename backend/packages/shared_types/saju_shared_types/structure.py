"""구조작용(합충형파해 등) and 격국 schemas (Phase 3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StructuralInteraction(BaseModel):
    relation_type: str  # 합/충/형/파/해/삼합/반합/방합/병존/간여지동 …
    scope: str  # stem / branch / pillar
    positions: list[str]
    members: list[str]
    palaces: list[str] = Field(default_factory=list)
    affected_elements: list[str] = Field(default_factory=list)
    affected_ten_gods: list[str] = Field(default_factory=list)
    transform_element: str | None = None
    severity: str = "low"  # low/medium/high
    stability_effect: float = 0.0
    notes: list[str] = Field(default_factory=list)


class TransformationCheck(BaseModel):
    members: list[str]
    target_element: str
    exists: bool = True
    possible: bool = False
    confirmed: bool = False
    confidence: float = 0.0
    blockers: list[str] = Field(default_factory=list)


class StabilityScores(BaseModel):
    yongsin_stability: float
    geokguk_stability: float
    root_stability: float


class GongmangAnalysis(BaseModel):
    """공망 분석 (신살과 별개 레이어). 일공망(日 기준)을 중심으로, 년공망(年 기준)은 참조."""

    day_basis_empty_branches: list[str] = Field(default_factory=list)  # 일공망 (중심)
    day_affected_positions: list[str] = Field(default_factory=list)
    day_affected_palaces: list[str] = Field(default_factory=list)
    year_basis_empty_branches: list[str] = Field(default_factory=list)  # 년공망 (참조)
    year_affected_positions: list[str] = Field(default_factory=list)
    primary_basis: str = "day"  # 일공망 중심
    activation_note: str = ""


class StructureAnalysis(BaseModel):
    interactions: list[StructuralInteraction]
    transformed_candidates: list[TransformationCheck] = Field(default_factory=list)
    palace_interactions: list[dict] = Field(default_factory=list)
    amplifiers: list[StructuralInteraction] = Field(default_factory=list)  # 병존/간여지동
    stability: StabilityScores
    volatility_score: float
    gongmang: GongmangAnalysis | None = None
    structure_modifier: float
    structure_modifier_breakdown: list[str] = Field(default_factory=list)
    calculation_trace: dict = Field(default_factory=dict)


class GeokgukEvaluation(BaseModel):
    """격국 평가 — 용신 후보 우선순위 보정 레이어(단독 확정자 아님)."""

    confidence_score: int = 0  # 0~100 (geokguk_master_v2 7요소)
    pattern_confidence: float  # 0~1 (= confidence_score/100, 용신 가중 계산용)
    confidence_grade: str  # A~E
    confidence_factors: list[dict] = Field(default_factory=list)
    success_failure_score: float  # -100~100 (성격 ↔ 패격)
    success_failure_grade: str
    success_failure_label: str
    damage_types: list[str] = Field(default_factory=list)  # 파격 원인(병)
    failures: list[dict] = Field(default_factory=list)  # 파격 + 구제 상세
    total_active: int = 0
    total_rescued: int = 0
    clarity_level: str
    clarity_policy: str
    final_weight: float  # 0.10~0.60 — 격국 axis 가중치
    final_weight_interpretation: str
    # 격국 신뢰도는 '성공 크기'가 아니라 '삶의 무대(직업성·역할)의 선명도'.
    social_expression: str


class GeokgukResult(BaseModel):
    main_structure: str | None
    basis: dict
    exposure: dict
    formation_level: str  # 성 / 중성 / 패 / 불명확
    stability: dict
    auxiliary_structures: list[str] = Field(default_factory=list)
    # 월지 지장간(정기/중기/여기) 전체에서 산출한 격 후보 랭킹(주격=[0]).
    candidates: list[dict] = Field(default_factory=list)
    # 종격/전왕 등 특수격 신호(있으면 정격과 병행 검토). 없으면 None.
    special_pattern: dict | None = None
    evaluation: GeokgukEvaluation | None = None
    warnings: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
