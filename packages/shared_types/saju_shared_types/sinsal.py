"""신살 schemas (Phase 5).

정책: 계산 가능한 신살을 모두 표시하되, 신강약·용신·격국 결정의 핵심 근거로 직접 쓰지 않는다
(use_for_yongsin_decision=False). 해석 태그·사건 분야 힌트로만 활용.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SinsalItem(BaseModel):
    name: str
    category: str
    position: str  # year / month / day / hour
    basis: str
    palace: str | None = None
    ten_god_context: str | None = None
    element_context: str | None = None
    intensity: str = "low"  # low / medium / high / very_high
    repeated: bool = False
    activated_by_relations: list[str] = Field(default_factory=list)
    interpretation_tags: list[str] = Field(default_factory=list)
    caution_tags: list[str] = Field(default_factory=list)
    use_for_yongsin_decision: bool = False


class SinsalSummary(BaseModel):
    repeated: list[str] = Field(default_factory=list)
    major_positive: list[str] = Field(default_factory=list)
    major_caution: list[str] = Field(default_factory=list)
    palace_sensitive: list[str] = Field(default_factory=list)
    structure_overlapped: list[str] = Field(default_factory=list)


class SinsalAnalysis(BaseModel):
    scope: str = "natal_chart_only"
    display_policy: str = "show_all"
    summary: SinsalSummary = Field(default_factory=SinsalSummary)
    by_pillar: dict[str, list[str]] = Field(default_factory=dict)
    by_category: dict[str, list[str]] = Field(default_factory=dict)
    full_list: list[SinsalItem] = Field(default_factory=list)
    hour_unknown: bool = False
    catalog_version: str = "default-2024.1"
    warnings: list[str] = Field(default_factory=list)


class TraditionalExtras(BaseModel):
    sinsal: SinsalAnalysis | None = None
    naeum: dict[str, str | None] = Field(default_factory=dict)  # position -> 납음
