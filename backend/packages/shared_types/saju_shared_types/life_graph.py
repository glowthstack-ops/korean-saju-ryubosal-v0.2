"""인생 그래프 구조 데이터(총운 개편, 2026-11-07) — 대운 곡선·세운 선·주요 이벤트 마커.

LLM이 만들지 않는 엔진 확정값이다. 리포트 결과의 F-14 섹션 `data` 필드로 실려 프론트가 SVG로
그리고, 대운별 상세 페이지·인생 흐름 종합·요약 카드의 마커 목록도 같은 객체에서 나온다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MarkerKind(StrEnum):
    """주요 이벤트 마커 5종(위기는 건강·금전 두 갈래) — 2026-11-07 데굴님 확정."""

    MARRIAGE = "marriage"
    JOB = "job"
    CAREER_CHANGE = "career_change"
    RELOCATION = "relocation"
    CRISIS_HEALTH = "crisis_health"
    CRISIS_MONEY = "crisis_money"


class LifeGraphMarker(BaseModel):
    """한 해의 주요 이벤트 후보 1건(엔진 점수 그대로)."""

    year: int
    age: int
    ganji: str
    kind: MarkerKind
    kind_ko: str
    event_key: str
    score: int = Field(ge=0, le=100)
    tone: str  # 길 | 주의 | 혼합
    daewoon_index: int
    risk_backed: bool = False  # 위험 엔진(건강·금전 family) 신호 동반
    # 읽기 메모(서술 전용) — 미성년 등 나이 맥락: '가족 단위로 읽을 것' 같은 안내. 빈 문자열=없음.
    note: str = ""


class LifeGraphDaewoon(BaseModel):
    """대운 1구간 — 곡선의 한 마디."""

    index: int
    ganji: str
    stem_ten_god: str
    branch_ten_god: str
    start_age: int
    end_age: int
    start_year: int
    end_year: int
    score: float
    label: str
    status: str  # past | current | future | unknown
    markers: list[LifeGraphMarker] = Field(default_factory=list)


class LifeGraphYear(BaseModel):
    """세운 1해 — 얇은 선의 점."""

    year: int
    age: int
    ganji: str
    score: float
    label: str


class LifeGraph(BaseModel):
    """인생 그래프 전체."""

    birth_year: int
    end_year: int
    current_daewoon_index: int | None = None
    daewoons: list[LifeGraphDaewoon] = Field(default_factory=list)
    years: list[LifeGraphYear] = Field(default_factory=list)
    markers: list[LifeGraphMarker] = Field(default_factory=list)
