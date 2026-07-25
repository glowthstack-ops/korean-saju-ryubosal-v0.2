"""일주별 오늘의 운세 (Daily Ilju Fortune) 공유 타입.

60갑자 일주 × 오늘 일진(챠트리스)으로 산출되는 휘발성 콘텐츠의 스키마.
docs/17_DAILY_ILJU_FORTUNE.md 규격. 과거 본문은 저장하지 않는다(TTL 캐시 전용).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# 버전 3분리 — content_version 은 캐시 namespace·ETag·락 키·LLM 감사 전용
# (과거 결과의 버전별 보존 용도가 아님. 이전 키는 TTL 로 소멸한다.)
ENGINE_VERSION = "engine.v1"
# 사전을 고치면 반드시 이 버전을 올린다 — 캐시 키의 일부라, 올리지 않으면 이미 생성된
# 보드가 옛 문구를 계속 서비스한다. compiled/daily_fortune_{DICT_VERSION}.json 스냅샷이
# 버전별로 존재하므로, 누락하면 회귀(test_daily_fortune_snapshot)가 잡는다.
# v1.7: 사전 3종 검수 상태(reviewed·review_note) 명시 + 컴파일 스냅샷 파이프라인 도입
# v1.6: 연애 Top5가 good 오늘의연애 신호 일주 우선 정렬(love_line과 정합, beta·감수 대상)
# v1.5: love_line 강한 신호 게이트(sg≥3)·reunion 문구 여운 중심 수정
DICT_VERSION = "dict.v1.7"
PROMPT_VERSION = "polish.v1"
CONTENT_VERSION = f"{ENGINE_VERSION}|{DICT_VERSION}|{PROMPT_VERSION}"

#: 사건 영역 — daily_event_catalog.json 의 domain 과 1:1
DailyDomain = Literal[
    "money", "love", "work", "social", "news", "document", "move", "health", "leisure"
]

#: 슬롯 — 좋은 사건 / 주의 사건 / 보조 생활 사건 (PRD §8)
DailySlot = Literal["good", "caution", "support"]

#: 보드 교정 상태(외부 노출 축약형)
PolishStatus = Literal["RAW", "PARTIAL", "POLISHED", "FAILED"]


class DayGanjiContext(BaseModel):
    """엔진 입력 — 특정 날짜의 일진·월운·세운 간지(개인 명식 무관).

    build_month() 산출값에서 추출하므로 입춘·절기 경계가 반영되어 있다.
    """

    the_date: date
    day_stem: str  # 오늘 일진 천간 (한자 1자, 예 "甲")
    day_branch: str  # 오늘 일진 지지 (한자 1자, 예 "子")
    month_stem: str  # 절기 기준 월운 천간
    month_branch: str  # 절기 기준 월운 지지
    year_stem: str  # 입춘 기준 세운 천간
    year_branch: str  # 입춘 기준 세운 지지


class DailyEventForecast(BaseModel):
    """생활 사건 확률 항목 1개 (화면의 '~할 확률 NN%')."""

    slot: DailySlot
    event_key: str  # daily_event_catalog.json 의 사건 키
    domain: DailyDomain
    probability: int = Field(ge=5, le=95)  # 0%/100% 구조적 금지 (PRD §11)
    phrase: str  # 화면 문장(밝은 단정 톤, 명리 용어 금지)


class LuckyPlace(BaseModel):
    """행운의 장소 (PRD §13 — 정확성보다 기억성·재미 우선)."""

    place_key: str  # daily_lucky_places.json 의 장소 키
    name: str  # 사용자 노출명 (예 "동네 서점")
    phrase: str


class DailyIljuFortune(BaseModel):
    """일주 1개의 오늘 운세 (보드의 단위 레코드)."""

    ilju: str  # 한자 2자 (예 "甲子")
    ilju_ko: str  # 한글 (예 "갑자")
    day_stem_ko: str  # 일간 한글 1자 — /daily 페이지 일간 탭 그룹핑용 (예 "갑")
    headline: str  # 오늘의 한마디 (2~3 짧은 문장)
    headline_event_key: str  # 헤드라인의 근거 사건 키 (LLM 불변 필드)
    events: list[DailyEventForecast] = Field(min_length=3, max_length=3)
    lucky_place: LuckyPlace
    lotto_phrase: str | None = None  # 조건부 희소 노출 (PRD §12)
    # 일일 연애운 한 줄(확장·beta) — 그 일주의 love 도메인 대표 신호를 사건 서술형으로.
    # 없으면 None(love 신호 미미). 미평가·판정 없음(오늘의 연애 흐름 서술만).
    love_line: str | None = None
    polished: bool = False  # LLM 교정 반영 여부(단건)


class DailyTop5(BaseModel):
    """분야별 운 좋은 일주 Top5 — 값은 한자 일주 5개씩."""

    money: list[str] = Field(min_length=5, max_length=5)
    love: list[str] = Field(min_length=5, max_length=5)
    news: list[str] = Field(min_length=5, max_length=5)


class DailyFortuneSingle(BaseModel):
    """일주 단건 응답(메인 카드용) — 보드에서 해당 일주만 추출."""

    fortune_date: date
    weekday: int = Field(ge=0, le=6)
    weekday_ko: str
    fortune: DailyIljuFortune


class DailyFortuneBoard(BaseModel):
    """하루치 전체 보드(60일주) — 캐시·API 응답의 단위.

    표시 날짜·요일은 이 값을 그대로 쓴다(클라이언트 재계산 금지).
    """

    fortune_date: date
    weekday: int = Field(ge=0, le=6)  # 0=월요일 (date.weekday())
    weekday_ko: str  # "수요일" 등 표시용
    content_version: str
    polish_status: PolishStatus = "RAW"
    top5: DailyTop5
    fortunes: list[DailyIljuFortune] = Field(min_length=60, max_length=60)
