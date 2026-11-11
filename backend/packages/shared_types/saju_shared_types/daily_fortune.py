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
# v1.14(2026-09-18): 사건 카탈로그 64→82종 3차 확장(docs/17 §22-7, 사용자 승인 — 전문가 참고
#   기준 사건 목록 대조). good 9(회복·해소·부담 경감·손실 방지·자율·확대)·caution 9(배분 이견·
#   결정 보류·부탁 얽힘·반복 실수·평가 누락·지급 지연·가족 일정·민원·기기 말썽) 추가, 동의어 그룹
#   6건 재배정,
#   문구 템플릿 18종 추가. 날짜 경계(CATALOG_EXPANSION_3_EFFECTIVE_FROM)로 계약을 고른다.
# v1.15(2026-11-01): 12운성 끝 문장 폐지(docs/17 §23-7, 데굴님 지적·승인) — 사건을 보지 않는
#   풀이라 카드 맥락을 흐트렸다. 헤드라인·연애 줄이 사건+행동 2문장이 되고, 사건 문장·행동
#   문장의 마침표 누락 102건을 보정했다. 날짜 경계(HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM)로
#   계약을 고른다.
# v1.16(2026-11-01): 이번 달 흐름·조언 층(docs/17 §24) + 헤드라인 행동을 사건 전용 풀로 교체
#   (데굴님 지적 — 십성 행동 문장이 앞 사건과 어긋나 뭘 하라는 건지 알 수 없었다). v1.15 는
#   11/2 선생성에만 쓰였고 사용자 노출 전에 대체됐다 — 경계는 같은 11/2 를 그대로 쓴다.
# v1.17(2026-11-01): 오늘의 운세 전체 문구 교정(docs/17 §24-6, 데굴님 지시 — 비유·직역투 제거,
#   어미는 문장별 선택) + 일주별 흐름을 12운성 기본으로 60일주 전부 채움. 문장만 바뀌고 판정은
#   같다. 11/2 보드는 이미 생성·export 돼 v1.16 을 유지하고 11/3 보드부터 쓴다.
# v1.18(2026-11-03): 12운성 방향 교정(docs/17 §25, 데굴님 "전체 로직 점검" → "그래 진행해") —
#   이번 달 흐름의 12운성 문장을 '월운 천간→일지'(일주별)에서 통설·만세력 엔진과 같은
#   '일간→월운 지지'(천간 공통)로 옮기고(`ilju_stage` → `stem_stage`), 일주별 흐름은 일지↔월운
#   지지·내년 세운 지지 관계만 남긴다. 패널에 월 이름·기간, 입절 전 7일은 다음 달 미리보기.
#   같은 경계(STAGE_DIRECTION_EFFECTIVE_FROM)로 v2 채점 채널의 12운성 방향도 바뀐다(model.v2.3).
# v1.19(2026-11-08): 단식(單式) 결 층(docs/17 §26, 데굴님 "세운뿐 아니라 월운·일운 공통") —
#   `simple_layer`: 올해의 결 패널(일간별 쌍 결·같은 결 강조·체감 포인트 3·절정 달), 이번 달
#   천간 공통 흐름의 같은 결 강조 1문장, 오늘 조언 줄 앞 같은 결 강조 1문장. 판정 불변.
#   경계 SIMPLE_LAYER_EFFECTIVE_FROM(11/8, 데굴님 "오늘 것부터 적용") — 11/8·11/9 보드는 새
#   content_version 으로 재생성·재교정된다(판정·사건 불변, 패널·조언 접두만 추가).
# v1.20(2026-11-08, 같은 날 2차): 단식 십성별 정의(docs/17 §27, 데굴님 "비견과 겁재를 묶어 같은
#   내용으로 풀이해도 되나 — 두 달씩 같은 내용이 나온다 → 십성별 각각 풀이 방식을 정의").
#   `god_scene`(10십성×5영역)·`god_axes`·`ilju_seat`(일지 십성군 5×월운 천간 십성 10). 이번 달 흐름
#   공통 줄은 십성 장면 + 12운성 + 행동(다음 달/내년 연결 문장 삭제), 일주별 흐름은 60일주 전부(관계
#   문장 또는 자리 문장, 내년 세운 지지 관계 삭제, 왕지 없는 반합 포함). 같은 경계(11/8) — v1.19 는
#   11/8 선생성에만 쓰였고 서비스 중 대체된다.
# v1.21(2026-11-11): 단식 연 지평 확장(docs/17 §31, 데굴님 "내년 단식 글을 바탕으로 추가 개선" →
#   "A 를 진행 · B 는 한번 추가 · D 는 가능 여부 판단 후 반영 · 조건이 있을 경우의 간단한 설명").
#   올해의 흐름 패널에 ① 연내 구간(가장 강한 때 + 전환 뒤 흐름) ② 여러 해 흐름(세운 지지 계절 3년
#   묶음) ③ 일주별 올해 한 줄 ④ 조건 줄(신강약·필요한 기운·지지 충형 글자·과다 기운). 채팅·테마 연
#   문단에도 ①②가 붙고, ④는 엔진이 확인한 항목만 따로 싣는다. 판정·사건·점수 불변(문체 전용).
#   경계 YEAR_PHASE_EFFECTIVE_FROM(11/12 — 11/11 보드는 이미 생성·교정돼 v1.20 유지).
DICT_VERSION = "dict.v1.21"
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
#: 사건 카탈로그 3차 확장(v1.14, docs/17 §22-7 3차) 활성화 기준일 — 승인(9/18) 다음 날 21시
#: 선생성분부터 = 9/20 보드(2026-09-18 데굴님 승인). 9/19 보드까지는 v1.13(64종).
CATALOG_EXPANSION_3_EFFECTIVE_FROM = date(2026, 9, 20)
#: 그 기준일 이전(9/12~9/19)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_CATALOG_EXPANSION_3 = "dict.v1.13"
#: 12운성 끝 문장 폐지(v1.15, docs/17 §23-7) 활성화 기준일 — 11/1 보드는 이미 생성·교정돼
#: v1.14 를 유지하고 11/2 보드(11/1 20시 선생성)부터 2문장 카드를 쓴다. 문장만 바뀌고
#: 사건 배정은 그대로지만, 당일 보드 재생성·재교정을 막으려고 날짜로 계약을 고른다.
HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM = date(2026, 11, 2)
#: 그 기준일 이전(9/20~11/1)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_HEADLINE_CLOSING_REMOVAL = "dict.v1.14"
#: 전체 문구 교정(v1.17, docs/17 §24-6) 활성화 기준일 — 11/2 보드(11/1 20시 선생성·재생성)는
#: v1.16 을 유지하고 11/3 보드(11/2 20시 선생성)부터 새 문구를 쓴다.
WORDING_REVISION_EFFECTIVE_FROM = date(2026, 11, 3)
#: 그 기준일 이전(11/2)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_WORDING_REVISION = "dict.v1.16"
#: 12운성 방향 교정(v1.18·model.v2.3, docs/17 §25) 활성화 기준일 — 11/4 보드는 11/3 20시
#: 선생성으로 이미 만들어지므로 v1.17·v2.2 를 유지하고, 11/5 보드(11/4 20시 선생성)부터 쓴다.
#: 채점 채널(오늘 카드)·이번 달 층 둘 다 이 날짜로 방향을 고른다 — 사전 키와 코드 분기가
#: 같은 경계를 보게 해 과거 날짜 재생이 그날 계약 그대로 나오게 한다.
STAGE_DIRECTION_EFFECTIVE_FROM = date(2026, 11, 5)
#: 그 기준일 이전(11/3~11/4)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_STAGE_DIRECTION = "dict.v1.17"

#: 단식 결 층(docs/17 §26) 활성화 기준일 — 11/8 보드부터(데굴님 "오늘 것부터 적용", 2026-11-08).
SIMPLE_LAYER_EFFECTIVE_FROM = date(2026, 11, 8)
#: 그 기준일 이전(11/5~11/7)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_SIMPLE_LAYER = "dict.v1.18"
#: 단식 연 지평 확장(v1.21, docs/17 §31) 활성화 기준일 — 11/11 보드는 이미 생성·교정돼 v1.20 을
#: 유지하고 11/12 보드(11/11 20시 선생성)부터 쓴다. 판정·사건은 그대로고 올해의 흐름 패널 필드만
#: 늘지만, 당일 보드 재생성·재교정을 막으려고 날짜로 계약을 고른다.
YEAR_PHASE_EFFECTIVE_FROM = date(2026, 11, 12)
#: 그 기준일 이전(11/8~11/11)에 적용되는 사전 버전.
DICT_VERSION_BEFORE_YEAR_PHASE = "dict.v1.20"


def stage_direction_forward(target_date: date) -> bool:
    """그 날짜의 12운성 방향 — True 면 일간→운 지지(통설·만세력 엔진과 동일), False 면 종전
    '오늘(월운) 천간→일지'.

    과거 날짜는 그날 계약으로 재생돼야 하므로 날짜가 방향을 고른다(docs/17 §25).

    Args:
        target_date: 운세 대상 날짜(KST 기준).
    """
    return target_date >= STAGE_DIRECTION_EFFECTIVE_FROM


def active_dict_version(target_date: date) -> str:
    """그 날짜에 적용할 사전 버전.

    Args:
        target_date: 운세 대상 날짜(KST 기준).

    Returns:
        7/30 이전 v1.10 → 9/3 이전 v1.11 → 9/12 이전 v1.12 → 9/20 이전 v1.13 → 11/2 이전
        v1.14 → 11/3 이전 v1.16 → 11/5 이전 v1.17 → 11/8 이전 v1.18 → 11/12 이전 v1.20
        (v1.19 는 11/8 경계에서 당일 대체) → 이후 현재 `DICT_VERSION`(v1.21).
    """
    if target_date < SMALL_FIND_HEADLINE_REVERT_EFFECTIVE_FROM:
        return PREVIOUS_DICT_VERSION
    if target_date < LUCKY_PLACES_REVISION_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_LUCKY_PLACES_REVISION
    if target_date < CATALOG_EXPANSION_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_CATALOG_EXPANSION
    if target_date < CATALOG_EXPANSION_3_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_CATALOG_EXPANSION_3
    if target_date < HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_HEADLINE_CLOSING_REMOVAL
    if target_date < WORDING_REVISION_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_WORDING_REVISION
    if target_date < STAGE_DIRECTION_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_STAGE_DIRECTION
    if target_date < SIMPLE_LAYER_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_SIMPLE_LAYER
    if target_date < YEAR_PHASE_EFFECTIVE_FROM:
        return DICT_VERSION_BEFORE_YEAR_PHASE
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
    # 조언 줄(docs/17 §24) — 사전 원문, LLM 교정 대상 아님. 과거 계약·베타 풀은 None.
    advice: str | None = None
    polished: bool = False  # LLM 교정 반영 여부(단건)


class DailyMonthIljuFlow(BaseModel):
    """일주별 흐름 한 줄 — 일지↔월운 지지(연말 구간은 내년 세운 지지) 관계 문장.

    dict.v1.17 계약(11/3~11/4)에서는 '월운 천간→일지 12운성' 문장이 앞에 붙었다(§25 교정 전).
    """

    ilju: str  # 한자 2자
    ilju_ko: str  # 한글 2자
    note: str


class DailyMonthStemFlow(BaseModel):
    """일간 하나의 이번 달 흐름 — /daily 일간 탭과 카드 사이 고정 패널(docs/17 §24)."""

    day_stem_ko: str  # 일간 한글 1자 — 탭 그룹핑 키와 같다
    common: str  # 천간 공통 흐름
    ilju_notes: list[DailyMonthIljuFlow] = Field(default_factory=list)
    # 다음 달 미리보기(docs/17 §25-3) — 월운 전환 7일 전부터 다음 달의 천간 공통 흐름.
    # 그 밖의 날과 과거 계약(dict.v1.17 이하)은 None.
    next_preview: str | None = None
    # 단식 같은 결 강조(docs/17 §26) — 월운 천간·지지 십성군이 같은 달에만. 과거 계약은 None.
    same_group_note: str | None = None


class DailyYearStemFlow(BaseModel):
    """올해의 결(단식, docs/17 §26) — 일간 1개. 세운이 바뀔 때까지 고정, 길흉 없음(양면 어휘)."""

    day_stem_ko: str  # 일간 한글 1자 — 탭 그룹핑 키와 같다
    tone: str  # 쌍 결 문장(사전 year_tone)
    emphasis: str | None = None  # 천간·지지 십성군이 같은 해에만
    points: list[str] = Field(default_factory=list)  # 체감 포인트 3줄(일·돈·사람·몸·연애 중)
    peak_months: str | None = None  # 2026-11-10 패널에서 제거(§30) — 계약 호환 필드, 항상 None
    # 단식 연 지평 확장(docs/17 §31, dict.v1.21) — 과거 계약 보드는 전부 기본값(None·빈 목록).
    # 연내 구간: 가장 강한 때 1문장(지났으면 과거형) + 전환 뒤 흐름·조언. 土 세운 해는 None.
    phase: list[str] | None = None
    # 여러 해 흐름: 세운 지지 계절 3년 묶음(직전 3년 → 지금 3년 중 몇 번째 해 → 다음 3년).
    span: str | None = None
    # 일주별 올해 한 줄: 일지↔세운 지지(충·육합·삼합·형·같은 글자·없음) — 그 일간의 6일주 전부.
    ilju_notes: list[DailyMonthIljuFlow] = Field(default_factory=list)
    # 조건 줄: 신강약 / 필요한 기운 / 지지 충·형 글자 / 과다 기운 — 조건 보유는 사용자 판단.
    conditions: list[str] = Field(default_factory=list)


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
    # 이번 달 층(docs/17 §24) — 오늘 카드 바깥 영역. 과거 계약·베타 풀은 None.
    season_band: str | None = None  # 12절기 입절일에만
    month_flow: list[DailyMonthStemFlow] | None = None  # 10일간, 월운 간지가 바뀔 때까지 고정
    # 패널 라벨(docs/17 §25-3) — "기해월(己亥) 11월 8일~12월 6일". 과거 계약(v1.17 이하)은 None.
    month_label: str | None = None
    # 다음 달 미리보기 라벨 — 월운 전환 7일 전부터("기해월(己亥) 11월 8일부터"). 그 밖은 None.
    next_month_label: str | None = None
    # 단식 결 층(docs/17 §26, dict.v1.19) — 10일간 올해의 결. 과거 계약 보드는 null.
    year_flow: list[DailyYearStemFlow] | None = None
    year_label: str | None = None  # "병오년(丙午) 2026년 2월 4일~2027년 2월 3일"
    # 방향 기준 줄(docs/17 §26-5, 2026-11-08) — 같은 결이 발판이 되는지 소모가 되는지는 내 명식
    # (용기신) 기준이라 일주 버킷은 판정하지 않고 안내만 한다. 사전 `simple_layer.direction_note`.
    year_direction_note: str | None = None
