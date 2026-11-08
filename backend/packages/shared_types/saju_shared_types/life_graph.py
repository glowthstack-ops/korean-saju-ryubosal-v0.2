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
    ROMANCE = "romance"  # 인연(새 만남·관계 형성, 길·혼합 방향) — 2026-11-07 "26~28년 결혼운" 대조
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
    # 추세선(docs/10 §3-1, 2026-11-08 데굴님 "대운별 운세와 조후 운세를 합쳐서 하나의 추세선으로")
    # — trend_score = 억부(용신) 점수와 조후 점수의 평균(조후 축 없는 명식은 억부 점수 그대로),
    # 직전 구간(첫 대운은 대운 전 유년) 대비 차이·추세 라벨(상승/하강/보합/시작). 설명용 산술.
    trend_score: float = 0.0
    trend_delta: float | None = None
    trend: str = ""
    # 흐름 두 패턴(2026-11-08 데굴님 "띠 색상·설명이 어려워 — 좋은 흐름/힘든 흐름으로") — 추세 점수
    # ≥ 0 이면 good(좋은 흐름), < 0 이면 hard(힘든 흐름). 띠 채움과 라벨의 유일한 기준.
    flow: str = ""
    flow_ko: str = ""
    # 배우자성 대운(남=재성·여=관성이 대운 천간/지지에) — 결혼·이성 인연이 본격 거론되는 10년이라는
    # 통설의 서술 라벨(점수 무관, 2026-11-07).
    partner_star_daewoon: bool = False
    # 조후 흐름선(2026-11-08 데굴님 "겨울생이라 바닥에서 서서히 쌓인다") — 대운 지지의 조후 점수
    # (−1~+1, 월지 필요 온도 기준). 중립 월(卯申酉) 명식은 None. 설명용 층.
    climate: float | None = None
    markers: list[LifeGraphMarker] = Field(default_factory=list)


class LifeGraphYear(BaseModel):
    """세운 1해 — 얇은 선의 점."""

    year: int
    age: int
    ganji: str
    score: float
    label: str
    # 조후(2026-11-08) — 0.7×소속 대운 조후 + 0.3×세운 지지 조후. 축 없는 명식은 None(설명용).
    climate: float | None = None


class LifeGraphPreDaewoon(BaseModel):
    """첫 대운 전 유년 구간(2026-11-08 데굴님 "0세부터 5세까지는 대운도 없는 거잖아").

    통설대로 **월주 간지를 운처럼** 본다 — 억부 점수는 월주를 운 기둥으로 채점한 값, 조후는 월지
    온도. 첫 대운 페이지(띠)는 그대로 출생부터 그리되, 추세선의 첫 마디는 이 구간이 맡는다.
    """

    ganji: str
    start_age: int = 0
    end_age: int
    start_year: int
    end_year: int
    score: float
    label: str
    climate: float | None = None
    trend_score: float = 0.0
    flow: str = ""
    flow_ko: str = ""


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
    # 추세선 요약(2026-11-08) — 대운 전 유년 구간, 추세 최고·최저 구간, 추세가 처음 보통선(0) 이상이
    # 되는 구간(간지 라벨). 설명용 산술.
    pre_daewoon: LifeGraphPreDaewoon | None = None
    trend_peak: str | None = None
    trend_low: str | None = None
    trend_baseline: str | None = None
    # 조후 흐름선(docs/10 §3-1, 2026-11-08) — 월지 조후 축(cold/heat/damp/dry, 중립이면 "")·필요
    # 온도 한글·조후가 처음 0 이상이 되는 대운·조후 정점 대운. 억부 점수와 별도의 설명용 층.
    climate_axis: str = ""
    climate_need_ko: str = ""
    climate_baseline_daewoon: str | None = None
    climate_peak_daewoon: str | None = None
