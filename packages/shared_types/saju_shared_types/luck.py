"""대운·세운·월운·일운 schemas (Phase 4b).

운은 원국 오행분포를 직접 바꾸지 않는다(별도 luck_effect 레이어). raw/transformed
오행을 분리하고, 용신 후보와의 관계를 함께 제공한다.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LuckPillar(BaseModel):
    """세운/월운/일운 공통 항목."""

    label: str  # "2015" / "2015-03" / "2015-03-21"
    period_type: str  # year / month / day
    ganji: str
    stem: str
    branch: str
    stem_ten_god: str
    branch_ten_god: str
    raw_elements: list[str] = Field(default_factory=list)
    relations_to_chart: list[str] = Field(default_factory=list)
    yongsin_alignment: str = "평운"  # 용신운 / 기신운 / 혼합 / 평운
    solar_term_range: str | None = None


class DaewoonItem(BaseModel):
    index: int
    start_age: int
    start_date: date
    end_date: date
    ganji: str
    stem: str
    branch: str
    stem_ten_god: str
    branch_ten_god: str
    twelve_unseong: str
    first_half_focus: str = "stem"  # 0-4년 천간 주도
    second_half_focus: str = "branch"  # 5-9년 지지 주도
    relations_to_chart: list[str] = Field(default_factory=list)
    raw_elements: list[str] = Field(default_factory=list)
    transformed_elements: list[str] = Field(default_factory=list)
    yongsin_relation: str = "평운"
    volatility_score: float = 0.0


class LuckCycles(BaseModel):
    direction: str  # forward / backward
    start_age: int
    start_age_exact: float
    daewoon_table: list[DaewoonItem] = Field(default_factory=list)
    current_age: int | None = None
    current_daewoon_index: int | None = None
    yearly_luck: list[LuckPillar] = Field(default_factory=list)
    monthly_luck: list[LuckPillar] = Field(default_factory=list)
    daily_luck: list[LuckPillar] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)
