"""Force-analysis schemas (Phase 2): distributions, rooting, strength."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FiveElementAnalysis(BaseModel):
    raw_visible: dict[str, float]
    hidden_base: dict[str, float]
    effective_force: dict[str, float]
    effective_percent: dict[str, float]
    strongest_element: str
    weakest_element: str
    excessive_elements: list[str] = Field(default_factory=list)
    deficient_elements: list[str] = Field(default_factory=list)


class TenGodAnalysis(BaseModel):
    raw_visible: dict[str, float]
    effective: dict[str, float]
    effective_percent: dict[str, float]
    groups: dict[str, float]  # peer/resource/output/wealth/officer powers
    strongest_ten_god: str
    missing_ten_gods: list[str] = Field(default_factory=list)
    hidden_only_ten_gods: list[str] = Field(default_factory=list)


class RootItem(BaseModel):
    position: str  # year/month/day/hour
    branch: str
    hidden_stem: str
    root_type: str  # peer_root / resource_root
    strength: str  # weak/medium/strong
    score: float


class RootingAnalysis(BaseModel):
    roots: list[RootItem]
    root_score: float
    deukryeong: bool
    deukji: bool
    deukse: bool
    tonggeun: bool
    rootedness_label: str  # 무근/약근/보통/신왕
    rootedness_score: float


class StrengthResult(BaseModel):
    score: float
    band: str
    borderline: bool
    confidence: float
    requires_validation: bool
    components: dict[str, float]
    basis: dict[str, bool]
    rootedness: dict[str, object]
    strong_chart_gate: dict[str, bool]
    explanation: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ForceAnalysis(BaseModel):
    five_elements: FiveElementAnalysis
    ten_gods: TenGodAnalysis
    rooting: RootingAnalysis
    strength: StrengthResult
