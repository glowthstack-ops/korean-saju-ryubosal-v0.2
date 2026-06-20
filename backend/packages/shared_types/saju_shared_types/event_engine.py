"""이벤트 엔진 재설계 v2 타입 (십성 분기 + 12운성 + 관계·궁성 + 용신 품질).

사용자 제공 사양(transit_ten_god_event_branching.v1 외 3종)을 코드 타입으로 옮긴다. 기존
EventKey/EventCandidate(events.py)는 Phase 7 스위치 전까지 병행 유지하므로 본 모듈은 별도다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class EventKeyV2(StrEnum):
    """재설계 이벤트 키 (사양 event_keys, 21종)."""

    CAREER_CHANGE = "career_change"
    JOB_GAIN = "job_gain"
    PROMOTION = "promotion"
    BUSINESS_START = "business_start"
    BUSINESS_EXPANSION = "business_expansion"
    WEALTH_CHANGE = "wealth_change"
    WINDFALL = "windfall"
    CONTRACT_DOCUMENT = "contract_document"
    EDUCATION_ADMISSION = "education_admission"
    EDUCATION_COMPLETION = "education_completion"
    RELATIONSHIP_CHANGE = "relationship_change"
    NEW_RELATIONSHIP = "new_relationship"
    MARRIAGE_SIGNAL = "marriage_signal"
    CHILDBIRTH = "childbirth"
    RELOCATION = "relocation"
    LEGAL_CONFLICT = "legal_conflict"
    HEALTH_ATTENTION = "health_attention"
    SOCIAL_CONFLICT = "social_conflict"
    PREPARATION_DELAY = "preparation_delay"
    CREATIVE_OUTPUT = "creative_output"
    PUBLIC_EXPOSURE = "public_exposure"


class TenGod(StrEnum):
    """십성(로마자 키 — 사양 ten_god_keys)."""

    BIJIAN = "BIJIAN"
    JIECAI = "JIECAI"
    SHISHEN = "SHISHEN"
    SHANGGUAN = "SHANGGUAN"
    ZHENGCAI = "ZHENGCAI"
    PIANCAI = "PIANCAI"
    ZHENGGUAN = "ZHENGGUAN"
    QISHA = "QISHA"
    ZHENGYIN = "ZHENGYIN"
    PIANYIN = "PIANYIN"


class TenGodGroup(StrEnum):
    """십성 그룹 (사양 ten_god_groups)."""

    PEER = "peer"
    OUTPUT = "output"
    WEALTH = "wealth"
    AUTHORITY = "authority"
    RESOURCE = "resource"


class LuckLayer(StrEnum):
    """운 층위."""

    DAEWOON = "daewoon"
    SEWOON = "sewoon"
    WOLWOON = "wolwoon"
    ILWOON = "ilwoon"


class TemporalMode(StrEnum):
    """사건 시간 성격 (사양 temporal_modes)."""

    LONG_TERM = "long_term"
    MEDIUM_TERM = "medium_term"
    IMMEDIATE = "immediate"


class EventQuality(StrEnum):
    """사건 '방향'(길흉) 품질 (사양 output_contract.quality).

    방향 전용이다 — 시간 작동 방식(지연·보류)은 길흉이 아니므로 EventTiming으로 분리한다.
    DELAY는 더 이상 생산하지 않는다(deprecated, 하위호환 위해 멤버만 유지).
    """

    OPPORTUNITY = "opportunity"
    PRESSURE = "pressure"
    LOSS = "loss"
    DELAY = "delay"  # deprecated — EventTiming.DELAY로 이관(방향이 아니라 타이밍)
    CONFLICT = "conflict"
    ACHIEVEMENT = "achievement"
    RESOLUTION = "resolution"
    MIXED = "mixed"


class EventTiming(StrEnum):
    """사건의 시간 작동 방식 (길흉과 독립 축). 방향(quality)은 그대로 두고 발현 시점만 수식한다.

    ACTIVE: 해당 기간에 바로 발현. DELAY: 공망·게이트로 지연·보류(좋고 나쁨과 무관하게 늦어짐).
    반복·재점화 등은 후속 작업에서 확장한다.
    """

    ACTIVE = "active"
    DELAY = "delay"


class ConfidenceLevel(StrEnum):
    """사건화 강도/확신도 (사양 event_materialization_levels)."""

    THEME_ONLY = "theme_only"
    WEAK_EVENT_CANDIDATE = "weak_event_candidate"
    EVENT_CANDIDATE = "event_candidate"
    STRONG_EVENT_CANDIDATE = "strong_event_candidate"
    HIGH_PROBABILITY_EVENT = "high_probability_event"


class PolarityRole(StrEnum):
    """용희기 신호 역할 (사양 polarity_rules).

    HAN_GOOD/HAN_BAD: 한신 오행의 간접(생, 生) 길흉 — 직접 역할(용·희·기·구)이 없을 때만,
    한신이 생하는 오행이 용신·희신이면 약한 길(HAN_GOOD), 기신·구신이면 약한 흉(HAN_BAD).
    """

    YONG = "YONG"
    HEE = "HEE"
    NEUTRAL = "NEUTRAL"
    GI = "GI"
    HAN_GOOD = "HAN_GOOD"
    HAN_BAD = "HAN_BAD"
    # 천간·지지가 같은 방향으로 겹친 강한 신호 — 모두 용신(강한 용신운)/모두 기신·구신(강한 흉운).
    # 신약 사주에 용신이 천간·지지로 보강되면 가장 이로운 운이라는 판정을 점수에 반영.
    YONG_STRONG = "YONG_STRONG"
    GI_STRONG = "GI_STRONG"


class TwelveStage(StrEnum):
    """십이운성 (사양 twelve_life_stages, 로마자 키)."""

    JANGSAENG = "JANGSAENG"
    MOKYOK = "MOKYOK"
    GWANDAE = "GWANDAE"
    GEONROK = "GEONROK"
    JEWANG = "JEWANG"
    SOE = "SOE"
    BYEONG = "BYEONG"
    SA = "SA"
    MYO = "MYO"
    JEOL = "JEOL"
    TAE = "TAE"
    YANG = "YANG"


class RelationKind(StrEnum):
    """관계(합충형파해) 종류 (사양 relation_types)."""

    HAP = "HAP"
    CHUNG = "CHUNG"
    HYEONG = "HYEONG"
    PA = "PA"
    HAE = "HAE"


class Pillar4(StrEnum):
    """궁성(사주 기둥)."""

    YEAR = "year_pillar"
    MONTH = "month_pillar"
    DAY = "day_pillar"
    HOUR = "hour_pillar"


# ── 엔진(한글) 출력 → enum 매핑 ───────────────────────────────────
# 만세 엔진의 ten_god은 한글("정관" 등), 십이운성도 한글("장생" 등)으로 산출된다.
TEN_GOD_KO_TO_KEY: dict[str, TenGod] = {
    "비견": TenGod.BIJIAN, "겁재": TenGod.JIECAI, "식신": TenGod.SHISHEN,
    "상관": TenGod.SHANGGUAN, "정재": TenGod.ZHENGCAI, "편재": TenGod.PIANCAI,
    "정관": TenGod.ZHENGGUAN, "편관": TenGod.QISHA, "정인": TenGod.ZHENGYIN,
    "편인": TenGod.PIANYIN,
}

TEN_GOD_GROUP: dict[TenGod, TenGodGroup] = {
    TenGod.BIJIAN: TenGodGroup.PEER, TenGod.JIECAI: TenGodGroup.PEER,
    TenGod.SHISHEN: TenGodGroup.OUTPUT, TenGod.SHANGGUAN: TenGodGroup.OUTPUT,
    TenGod.ZHENGCAI: TenGodGroup.WEALTH, TenGod.PIANCAI: TenGodGroup.WEALTH,
    TenGod.ZHENGGUAN: TenGodGroup.AUTHORITY, TenGod.QISHA: TenGodGroup.AUTHORITY,
    TenGod.ZHENGYIN: TenGodGroup.RESOURCE, TenGod.PIANYIN: TenGodGroup.RESOURCE,
}

TWELVE_STAGE_KO_TO_KEY: dict[str, TwelveStage] = {
    "장생": TwelveStage.JANGSAENG, "목욕": TwelveStage.MOKYOK, "관대": TwelveStage.GWANDAE,
    "건록": TwelveStage.GEONROK, "제왕": TwelveStage.JEWANG, "쇠": TwelveStage.SOE,
    "병": TwelveStage.BYEONG, "사": TwelveStage.SA, "묘": TwelveStage.MYO,
    "절": TwelveStage.JEOL, "태": TwelveStage.TAE, "양": TwelveStage.YANG,
}


class EventCandidateV2(BaseModel):
    """재설계 이벤트 후보 (사양 output_contract.event_candidate).

    십성=종류 / 12운성=상태 / 관계=발동 / 궁성=생활영역 / 용신=품질의 결과를 한 후보로 담는다.
    """

    event_key: EventKeyV2
    period: str  # '2026' / '2026-06' 등 운 기간 라벨
    # 모디파이어 누적 중에는 상한 없이 raw를 보존하고(중간 하드 클램프 제거), 최종 단계에서만
    # soft_cap을 걸어 표시용 점수(≤100)로 만든다. 그래서 le=100 제약을 두지 않는다.
    score: int = Field(ge=0)
    confidence_level: ConfidenceLevel = ConfidenceLevel.THEME_ONLY
    temporal_mode: TemporalMode | None = None
    quality: EventQuality | None = None  # 방향(길흉)만 — 타이밍은 timing으로 분리
    timing: EventTiming = EventTiming.ACTIVE  # 시간 작동 방식(공망·게이트 지연·보류)
    source_layers: list[LuckLayer] = Field(default_factory=list)
    source_ten_gods: list[TenGod] = Field(default_factory=list)
    polarity_role: PolarityRole = PolarityRole.NEUTRAL
    palace: Pillar4 | None = None  # 발동된 궁성(생활 영역)
    twelve_stage: TwelveStage | None = None  # 사건 상태를 정한 12운성
    event_phase: str | None = None  # 12운성이 부여한 발현 단계(formalization/peak/cut 등)
    reason_codes: list[str] = Field(default_factory=list)  # 적용 룰 id 추적
    raw_score: float = 0.0  # soft_cap 전 누적 raw(정렬·디버그) — 최종 단계에서 채움
    # 단계별 점수 기여(base/stage/flow/gate/relation/yongi/wealth_act) — 포화 진단·2차
    # 계열 인지 감쇠 전환용 계측. 표시·판정엔 쓰지 않는다(내부 로그).
    contributions: dict[str, float] = Field(default_factory=dict)
    # ── 활성/길흉 이중 채널 (career_mobility 자료 0·15장: "사건 형성도 ≠ 길흉") ──
    # 사건이 일어나는가(activation)와 결과가 유리한가(favorability)를 독립 출력한다. 절대원칙
    # 3·4(이벤트≠결과, 단정 금지)의 코드 표현 — 점수 재계산이 아니라 contributions/극성 집계.
    activation: float = 0.0      # 사건 형성도(길흉 제외 누적, display 스케일) — "일어나는가"
    favorability: float = 0.0    # 결과 길흉 −1.0~+1.0 (양수=유리·음수=불리·0=중립) — "유리한가"
    # ── Life Event Inference 정렬축 (LIFE_EVENT_INFERENCE.md §1) ──
    life_fit: float = 0.0       # 현실 적합도(reality_gate) — 최상위 정렬축
    personal_match: float = 0.0  # 과거 검증 유사도(개인 시그니처 + 코호트, 음수=실패예측 페널티)
    # score는 '표시용 내부값(display_score)'으로 격하됐다 — 절대값 신뢰 금지, 정렬은 아래 축이 우선.


# ── 공식 정렬축 (LIFE_EVENT_INFERENCE.md §1) — 엔진·랭커 공용 단일 함수 ──
_LEI_CONF_RANK: dict[ConfidenceLevel, int] = {
    ConfidenceLevel.THEME_ONLY: 0,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE: 1,
    ConfidenceLevel.EVENT_CANDIDATE: 2,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE: 3,
    ConfidenceLevel.HIGH_PROBABILITY_EVENT: 4,
}


def lei_rank_key(c: EventCandidateV2) -> tuple:
    """공식 정렬축 — 현실적합 > 사건화증거 > 과거유사 > 잠재(score=display) > 시점·키.

    life_fit·personal_match가 0이면(개인/맥락 미배선) (사건화강도, score) 순서로 자연 환원된다.
    score는 최하위 보조축(표시용)이며 절대값 신뢰 대상이 아니다.
    """
    return (
        -c.life_fit,
        -_LEI_CONF_RANK.get(c.confidence_level, 0),
        -c.personal_match,
        -c.score,
        c.period,
        str(c.event_key),
    )
