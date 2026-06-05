"""Force-analysis schemas (Phase 2): distributions, rooting, strength."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FiveElementAnalysis(BaseModel):
    raw_visible: dict[str, float]
    hidden_base: dict[str, float]
    effective_force: dict[str, float]
    effective_percent: dict[str, float]  # 판정용(내부/고급 실세력)
    visible_percent: dict[str, float] = Field(default_factory=dict)  # 표시용(단순 표면, 일간 포함)
    visible_percent_without_day_master: dict[str, float] = Field(default_factory=dict)
    # 오행별 지장간 출처(표면 유무 무관) — 예: 土 → [申여戊, 巳여戊]. 표면 %에는 섞지 않음.
    hidden_support: dict[str, list[str]] = Field(default_factory=dict)
    strongest_element: str
    weakest_element: str
    excessive_elements: list[str] = Field(default_factory=list)
    deficient_elements: list[str] = Field(default_factory=list)
    # 표면(visible)엔 없고 지장간에만 있는 오행(암장). 강한 오행으로 표기하지 않는다.
    hidden_only_elements: list[dict] = Field(default_factory=list)
    # 사용자 표시용 요약(visible 우선). effective는 고급/내부 분석용.
    display_summary: dict = Field(default_factory=dict)
    calculation_trace: dict = Field(default_factory=dict)


class TenGodAnalysis(BaseModel):
    raw_visible: dict[str, float]
    effective: dict[str, float]
    effective_percent: dict[str, float]  # 판정용(내부/고급)
    visible_percent: dict[str, float] = Field(default_factory=dict)  # 표시용(암장 제외)
    visible_absent: list[str] = Field(default_factory=list)  # 표면에 없는 십성(화면에서 '-')
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
