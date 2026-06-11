"""신규 엔진군이 소비하는 정규화 만세 차트 schema (v2.2 Phase 0, docs/02 E0).

설계 문서의 `ManseResult` 인터페이스(신규 엔진 입력 계약)를 Python으로 옮긴 것.
만세력 엔진의 풍부한 출력(`ManseV2Result`)을 신규 엔진이 안정적으로 소비하도록 **최소
계약**만 노출한다. 변환은 `saju_engines.adapter`가 담당하며 만세력 엔진은 수정하지 않는다
(절대 원칙: 기존 엔진 수정 금지, 어댑터만 추가).

리포의 기존 `ManseV2Result`/프론트 `ManseResult`와 이름이 겹치지 않도록 정규화 차트는
`ManseChart`로 명명한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChartPillar(BaseModel):
    """정규화 원국 기둥 (docs/02 E0 Pillar). 표시 상세는 생략한 신규 엔진 소비용 최소형."""

    stem: str
    branch: str
    hidden_stems: list[str] = Field(default_factory=list)  # 지장간(천간 한자)
    ten_god: str  # 천간 십성
    twelve_stage: str  # 12운성
    shinsal: list[str] = Field(default_factory=list)  # 이 자리 신살 이름


class FourPillarsChart(BaseModel):
    """원국 4기둥. 시주 미상이면 hour=None."""

    year: ChartPillar
    month: ChartPillar
    day: ChartPillar
    hour: ChartPillar | None = None


class DaewoonPeriod(BaseModel):
    """대운 한 주기 (docs/02 E0 DaewoonPeriod). 10년 단위 배경."""

    index: int
    start_age: int
    period: str  # '2026~2035'
    stem: str
    branch: str
    ganji: str
    stem_ten_god: str
    branch_ten_god: str


class BirthMeta(BaseModel):
    """차트 산출 입력 요약 (docs/02 E0 birthInfo). gender는 'M'/'F'/'U'로 정규화."""

    datetime: str  # ISO8601 (출생 민간력 일시; 시각 미상이면 날짜만)
    calendar_type: str  # 'solar' / 'lunar'
    gender: str  # 'M' / 'F' / 'U'
    birth_time_unknown: bool = False


class ManseChart(BaseModel):
    """신규 엔진 입력 계약 (docs/02 E0 ManseResult).

    chart_variant/twin_shift는 쌍둥이 시주 조정(docs/11 2-2)용이며, 해당 기능 미구현
    상태에서는 'original'/0 고정으로 내보낸다(절대 원칙 11: 미구현으로 차단/오류 금지).
    """

    chart_id: str
    birth_info: BirthMeta
    chart_variant: str = "original"  # 'original' / 'twin_adjusted'
    twin_shift: int = 0  # 0=조정 없음
    chart: FourPillarsChart
    day_master: str
    void_branches: list[str] = Field(default_factory=list)  # 공망 지지
    daewoon_list: list[DaewoonPeriod] = Field(default_factory=list)
