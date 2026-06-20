"""이벤트 분류·후보 schemas (v2.2 Phase 0, docs/02 E2 + Event Taxonomy).

설계 문서(`doc/v2_2/docs/02_ENGINES_SPEC.md`)는 TypeScript/zod 기준이나 본 리포는
Python/pydantic으로 통합 구현한다. 문서의 camelCase 필드명은 snake_case로 번역하되
의미·열거 항목은 그대로 유지한다(절대 원칙 10: 전체 규격 문서 준수).

이 모듈은 타입 정의(Phase 0 T0.1)만 담당한다. 점수 산출 로직은 Event Scoring
Engine(Phase 2)에서 구현하며, LLM은 이 점수를 계산하지 않는다(절대 원칙 1).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# v2.2 Phase 7 하드 스위치(2026-06-13 사용자 확정): 표준 이벤트 키를 21키 EventKeyV2로 일원화한다.
# 구 25키는 폐기하고 EventKey는 EventKeyV2 별칭으로 둔다(타입 주석 호환). 구→신 매핑·한글·카테고리·
# 금기룰은 event_taxonomy_v2 참조. EventType/EventPolarity/Confidence/Signal/EventCandidate는 DTO로
# 유지(EventEngineV2가 어댑터로 산출). 점수 산출은 EventEngineV2가 담당하고 구 EventScorer는 제거됨.
from .event_engine import EventKeyV2 as EventKey  # noqa: F401  (canonical 21-key alias)


class EventType(StrEnum):
    """이벤트 시간 성격 (docs/01 §2, docs/02 E11).

    progress=장기 진행형(Timeline/Manifestation 적용), instant=즉효성 실행일
    (Date Selection 적용), hybrid=둘 다(이사: 준비 progress + 당일 instant).
    """

    PROGRESS = "progress"
    INSTANT = "instant"
    HYBRID = "hybrid"


class EventPolarity(StrEnum):
    """이벤트 길흉/강제성 방향 (docs/02 E2)."""

    POSITIVE = "positive"
    NEGATIVE_OR_FORCED = "negative_or_forced"
    CONDITIONAL = "conditional"
    NEUTRAL = "neutral"


class Confidence(StrEnum):
    """판정 신뢰도 5단계 (docs/02 E2). 낮을수록 LLM 표현을 보수화한다."""

    LOW = "low"
    MEDIUM_LOW = "medium_low"
    MEDIUM = "medium"
    MEDIUM_HIGH = "medium_high"
    HIGH = "high"


class Signal(BaseModel):
    """이벤트 점수에 기여하는 단일 신호 (docs/02 E2).

    type는 합충형파해·공망활성·십성활성·신살·대운교체 등 신호 종류이며, 신규 종류가
    필요하면 임의 추가하지 않고 사전/문서에 먼저 정의한다(절대 원칙 10).
    """

    type: str  # 'heavenly_stem_combine' / 'branch_clash' / 'void_activation' / ...
    name: str  # '甲己合' — 한자 간지 표기
    effect: str  # '직업/책임/환경 변화 자극'
    weight: float  # 양/음수 가능 (예: 공망 활성 -8)


class EventCandidate(BaseModel):
    """특정 시점의 이벤트 발생 가능성 후보 (docs/02 E2).

    score는 0~100 정수 범위로 클램프된 룰 기반 점수다(LLM 산출 금지). evidence_path는
    Graph RAG 근거 경로의 노드 ID 순서다(Phase 2에서 채움).
    """

    event_key: EventKey
    event_type: EventType
    period: str  # '2026-06' — 간지달력 기간 라벨
    score: int = Field(ge=0, le=100)
    confidence: Confidence
    polarity: EventPolarity
    # 사건 '방향'(길흉) + '타이밍'(즉시/지연) — polarity 4값 축소로 묻히는 길흉을 또렷이 전달.
    # quality: opportunity/achievement/resolution(길)·loss/pressure/conflict(흉)·mixed(혼합).
    # timing: active/delay(공망·게이트 보류). 표시 계층이 한글 방향 라벨로 노출한다.
    quality: str | None = None
    timing: str = "active"
    signals: list[Signal] = Field(default_factory=list)
    evidence_path: list[str] = Field(default_factory=list)
    # 클램프(0~100) 전 raw 가중 합 — 동점 후보의 우위 변별용(내부 정렬).
    raw_total: float = 0.0
    # Life Event Inference 정렬축 전달(EventCandidateV2→어댑터) — 0이면 기존 score 정렬과 동치.
    life_fit: float = 0.0
    personal_match: float = 0.0
    # 결과 길흉(−1.0~+1.0) — "사건 형성도(score) ≠ 유불리(favorability)"의 길흉 채널을
    # 다운스트림(LLM 입력)까지 전달. 양수=유리·음수=불리·0=중립/미정(EventCandidateV2에서 옮김).
    favorability: float = 0.0
