"""대운·세운·월운·일운 schemas (Phase 4b).

운은 원국 오행분포를 직접 바꾸지 않는다(별도 luck_effect 레이어). raw/transformed
오행을 분리하고, 용신 후보와의 관계를 함께 제공한다.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from saju_shared_types.sinsal import LuckSinsal


class LuckPolarity(BaseModel):
    """운 천간/지지 한쪽의 용신 관계(드러남=천간, 기반=지지)."""

    element: str  # 대표 오행(지지는 정기 기준)
    type: str  # 용신 / 기신 / 한신
    score: float  # +용신 ~ -기신 (지지는 지장간 가중, 공망/충 반영 후)
    detail: str = ""  # 지장간 구성 등 부가 설명
    # 지지 동태(공망=실속·작동력, 충=사건화·변동성) — 천간엔 미적용.
    base_score: float | None = None  # 공망/충 반영 전 방향 점수
    is_void: bool = False
    has_clash: bool = False
    branch_label: str = ""  # 공망 용신운 / 충발 용신운 / 공망 기신운 / 충동 기신운
    event_trigger: float = 0.0  # 사건화 가능성(충↑)
    volatility: float = 0.0  # 변동성(충·공망↑)
    reliability: float = 1.0  # 실현 신뢰도(공망↓)


class LuckPillar(BaseModel):
    """세운/월운/일운 공통 항목."""

    label: str  # "2015" / "2015-03" / "2015-03-21"
    period_type: str  # year / month / day
    ganji: str
    stem: str
    branch: str
    stem_ten_god: str
    branch_ten_god: str
    twelve_unseong: str = ""  # 운성(십이운성) — 카드 표시용
    raw_elements: list[str] = Field(default_factory=list)
    relations_to_chart: list[str] = Field(default_factory=list)
    gongmang_activation: list[str] = Field(default_factory=list)  # 운이 원국 공망을 자극
    yongsin_alignment: str = "평운"  # 용신운 / 기신운 / 혼합 / 평운 (coarse 호환)
    # 천간(드러남)·지지(기반) 분리 평가 + 세분 라벨.
    stem_effect: LuckPolarity | None = None
    branch_effect: LuckPolarity | None = None
    luck_score: float = 0.0
    luck_label: str = ""  # 한글 세분 라벨
    luck_label_code: str = ""  # pure_yongsin_luck / mixed_yongsin_surface / ...
    luck_summary: str = ""
    solar_term_range: str | None = None
    # 이 운이 불러오는 신살/길신/흉성 — 카드 하단(십이운성 아래) 표시용.
    luck_sinsal: list[LuckSinsal] = Field(default_factory=list)


class DaewoonItem(BaseModel):
    index: int
    start_age: int
    # 정수 나이 기반 근사 교운일(생일 기준). 정밀 교운일시는 LuckCycles.trace 참조.
    approx_start_date: date
    approx_end_date: date
    ganji: str
    stem: str
    branch: str
    stem_ten_god: str
    branch_ten_god: str
    twelve_unseong: str
    first_half_focus: str = "stem"  # 0-4년 천간 주도
    second_half_focus: str = "branch"  # 5-9년 지지 주도
    relations_to_chart: list[str] = Field(default_factory=list)
    gongmang_activation: list[str] = Field(default_factory=list)  # 운이 원국 공망을 자극
    raw_elements: list[str] = Field(default_factory=list)
    transformed_elements: list[str] = Field(default_factory=list)
    yongsin_relation: str = "평운"  # coarse 호환(용신운/기신운/혼합/평운)
    # 천간(드러남)·지지(기반) 분리 평가 + 세분 라벨.
    stem_effect: LuckPolarity | None = None
    branch_effect: LuckPolarity | None = None
    luck_score: float = 0.0
    luck_label: str = ""
    luck_label_code: str = ""
    luck_summary: str = ""
    volatility_score: float = 0.0
    # 이 대운이 불러오는 신살/길신/흉성 — 카드 하단(십이운성 아래) 표시용.
    luck_sinsal: list[LuckSinsal] = Field(default_factory=list)
    # 이 대운에 속한 10개 세운(연동 표시용) — 대운 선택 시 노출.
    sewoon: list[LuckPillar] = Field(default_factory=list)


class LuckCycles(BaseModel):
    direction: str  # forward / backward
    start_age: int
    start_age_exact: float
    daewoon_table: list[DaewoonItem] = Field(default_factory=list)
    current_age: int | None = None
    current_daewoon_index: int | None = None
    current_year: int | None = None  # 세운 카드 현재 강조용
    current_month: int | None = None  # 월운 카드 현재 강조용
    yearly_luck: list[LuckPillar] = Field(default_factory=list)
    monthly_luck: list[LuckPillar] = Field(default_factory=list)
    daily_luck: list[LuckPillar] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)
