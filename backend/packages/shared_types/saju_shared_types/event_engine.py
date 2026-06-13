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
    """사건 품질 (사양 output_contract.quality)."""

    OPPORTUNITY = "opportunity"
    PRESSURE = "pressure"
    LOSS = "loss"
    DELAY = "delay"
    CONFLICT = "conflict"
    ACHIEVEMENT = "achievement"
    RESOLUTION = "resolution"
    MIXED = "mixed"


class ConfidenceLevel(StrEnum):
    """사건화 강도/확신도 (사양 event_materialization_levels)."""

    THEME_ONLY = "theme_only"
    WEAK_EVENT_CANDIDATE = "weak_event_candidate"
    EVENT_CANDIDATE = "event_candidate"
    STRONG_EVENT_CANDIDATE = "strong_event_candidate"
    HIGH_PROBABILITY_EVENT = "high_probability_event"


class PolarityRole(StrEnum):
    """용희기 신호 역할 (사양 polarity_rules)."""

    YONG = "YONG"
    HEE = "HEE"
    NEUTRAL = "NEUTRAL"
    GI = "GI"


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
    score: int = Field(ge=0, le=100)
    confidence_level: ConfidenceLevel = ConfidenceLevel.THEME_ONLY
    temporal_mode: TemporalMode | None = None
    quality: EventQuality | None = None
    source_layers: list[LuckLayer] = Field(default_factory=list)
    source_ten_gods: list[TenGod] = Field(default_factory=list)
    polarity_role: PolarityRole = PolarityRole.NEUTRAL
    palace: Pillar4 | None = None  # 발동된 궁성(생활 영역)
    twelve_stage: TwelveStage | None = None  # 사건 상태를 정한 12운성
    event_phase: str | None = None  # 12운성이 부여한 발현 단계(formalization/peak/cut 등)
    reason_codes: list[str] = Field(default_factory=list)  # 적용 룰 id 추적
    raw_score: float = 0.0  # 클램프 전 원점수(정렬·디버그)
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
