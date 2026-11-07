"""인생 그래프 구조 데이터(총운 개편, 2026-11-07) — 대운 곡선·세운 선·주요 이벤트 마커.

LLM이 만들지 않는 엔진 확정값이다. 리포트 결과의 F-14 섹션 `data` 필드로 실려 프론트가 SVG로
그리고, 대운별 상세 페이지·인생 흐름 종합·요약 카드의 마커 목록도 같은 객체에서 나온다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MarkerKind(StrEnum):
    """주요 이벤트 마커 — 결혼·취업·이직·이사·재물 유입·위기(건강/금전) — 2026-11-07 데굴님 확정.

    재물 유입(wealth_gain)은 같은 날 "돈 들어오는 시기도 표시되어야" 요청으로 추가(재물 변화 길
    방향).
    """

    MARRIAGE = "marriage"
    JOB = "job"
    CAREER_CHANGE = "career_change"
    RELOCATION = "relocation"
    WEALTH_GAIN = "wealth_gain"
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


class LifeGraphWindow(BaseModel):
    """앞으로의 긍정 창 1건 — 오늘 이후 길·혼합 방향 후보(게이트 이상)를 연속 연도로 묶은 것.

    마커 선별(대운당 상한)과 무관하게 **모든** 게이트 통과 연도를 담는다 — "76세에나 결혼"처럼
    늦은 마커만 남아 희망을 빼앗는 문제의 보완(2026-11-07 데굴님). 가장 가까운 창이 먼저 온다.
    """

    kind: MarkerKind
    kind_ko: str
    start_year: int
    end_year: int
    start_age: int
    end_age: int
    peak_year: int
    peak_score: int = Field(ge=0, le=100)
    years_count: int


class LifeGraph(BaseModel):
    """인생 그래프 전체."""

    birth_year: int
    end_year: int
    # 오늘 연도 — 마커·세운 행의 [지남]/[올해]/[예정] 표식과 프론트 '오늘' 선의 원천
    # (2026-11-07 실답: 오늘이 2026-11인데 2025년 취업 마커를 "내년"으로 쓴 산출 교정).
    # None이면 표식 생략.
    today_year: int | None = None
    current_daewoon_index: int | None = None
    daewoons: list[LifeGraphDaewoon] = Field(default_factory=list)
    years: list[LifeGraphYear] = Field(default_factory=list)
    markers: list[LifeGraphMarker] = Field(default_factory=list)
    # 앞으로의 긍정 창(오늘 이후) — F-14 해설·F-14b 종합·F-21 요약 카드·프론트 표 공용.
    positive_windows: list[LifeGraphWindow] = Field(default_factory=list)
