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
# v1.8: runtime_status(ACTIVE)·review_status(PENDING) 분리 — 미감수 ≠ 계산 미사용
# v1.7: 사전 3종 검수 상태(reviewed·review_note) 명시 + 컴파일 스냅샷 파이프라인 도입
# v1.6: 연애 Top5가 good 오늘의연애 신호 일주 우선 정렬(love_line과 정합, beta·감수 대상)
# v1.5: love_line 강한 신호 게이트(sg≥3)·reunion 문구 여운 중심 수정
# v1.12(2026-09-01): 행운의 장소 UX 점검 — 예약·티켓·회원권이 필요한 13곳을 "지나가다
#   머물러도 이상하지 않은 곳"으로 교체(우체국·생활용품점·버스 정류장·분식집 등), 3곳 표현
#   손질, place_phrases 조사 오류("편의점를") 제거. 키·이름만 바뀌고 순서·도메인·오행은 유지.
# v1.13(2026-09-10): 사건 카탈로그 48→64종 확장(docs/17 §22-7, 사용자 승인). good 11·caution 5
#   추가, small_find/lend_money 동의어 그룹 재배정, 문구 템플릿 16종 추가. 사건 후보가 늘어
#   선발 결과가 바뀌므로 날짜 경계(CATALOG_EXPANSION_EFFECTIVE_FROM)로 계약을 고른다.
DICT_VERSION = "dict.v1.13"
PROMPT_VERSION = "polish.v1"
#: 서사 family 회전 계약(OA-8b). 값이 바뀌면 새 epoch 이 시작되며 **캐시만** 무효화된다
#: — 선택 seed 에는 들어가지 않으므로 사건 배정은 흔들리지 않는다(OA-6d1).
NARRATIVE_ROTATION_VERSION = "narrative-rotation.v1"
CONTENT_VERSION = (
    f"{ENGINE_VERSION}|{DICT_VERSION}|{PROMPT_VERSION}|{NARRATIVE_ROTATION_VERSION}"
)

#: `small_find` 헤드라인 자격 철회(OA-6a2) 활성화 기준일 — KST 날짜 경계.
#: 일부 사용자의 **event_key 가 바뀌므로** 같은 날 결과 불변성을 지키려면 날짜로 계약을
#: 고른다. 재기동·캐시 유실이 있어도 7/29 는 이전 계약, 7/30 부터 새 계약으로 재생된다.
SMALL_FIND_HEADLINE_REVERT_EFFECTIVE_FROM = date(2026, 7, 30)
#: 활성화 이전 계약(스냅샷이 함께 커밋돼 있어야 재현 가능하다).
PREVIOUS_DICT_VERSION = "dict.v1.10"
#: 행운의 장소 개정(v1.12) 활성화 기준일 — 이미 생성·export 된 9/2 보드는 v1.11 을 유지하고
#: 9/3 보드(9/2 21시 선생성)부터 새 사전을 쓴다. 캐시 namespace 가 날짜별로 갈리므로
#: 승격 시점에 당일 보드가 재생성·재교정되지 않는다(2026-09-01 데굴님 승인).
LUCKY_PLACES_REVISION_EFFECTIVE_FROM = date(2026, 9, 3)
#: 그 기준일 이전(7/30~9/2)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_LUCKY_PLACES_REVISION = "dict.v1.11"
#: 사건 카탈로그 확장(v1.13, docs/17 §22-7) 활성화 기준일 — 9/11 보드(9/10 21시 선생성)는
#: v1.12 를 유지하고 9/12 보드(9/11 21시 선생성)부터 64종 카탈로그를 쓴다. 사건 후보가
#: 늘어 **event_key 가 바뀌므로** 같은 날 결과 불변성을 지키려면 날짜로 계약을 골라야
#: 한다(2026-09-10 데굴님 승인 — "승인 다음 날 21시 선생성분부터").
CATALOG_EXPANSION_EFFECTIVE_FROM = date(2026, 9, 12)
#: 그 기준일 이전(9/3~9/11)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_CATALOG_EXPANSION = "dict.v1.12"


def active_dict_version(target_date: date) -> str:
    """그 날짜에 적용할 사전 버전.

    Args:
        target_date: 운세 대상 날짜(KST 기준).

    Returns:
        7/30 이전 v1.10 → 9/3 이전 v1.11 → 9/12 이전 v1.12 → 이후 현재
        `DICT_VERSION`(v1.13).
    """
    if target_date < SMALL_FIND_HEADLINE_REVERT_EFFECTIVE_FROM:
        return PREVIOUS_DICT_VERSION
    if target_date < LUCKY_PLACES_REVISION_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_LUCKY_PLACES_REVISION
    if target_date < CATALOG_EXPANSION_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_CATALOG_EXPANSION
    return DICT_VERSION


def content_version_for(target_date: date) -> str:
    """그 날짜의 캐시 namespace — 계약이 다르면 키도 달라야 한다."""
    return (
        f"{ENGINE_VERSION}|{active_dict_version(target_date)}"
        f"|{PROMPT_VERSION}|{NARRATIVE_ROTATION_VERSION}"
    )

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
