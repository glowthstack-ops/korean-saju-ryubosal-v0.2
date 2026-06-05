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


class GeokgukResult(BaseModel):
    main_structure: str | None
    basis: dict
    exposure: dict
    formation_level: str  # 성 / 중성 / 패 / 불명확
    stability: dict
    auxiliary_structures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
