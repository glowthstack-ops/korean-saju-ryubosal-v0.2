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


# 신뢰도 한글 라벨 — 사용자 노출 시 내부 키(medium_high 등)를 그대로 쓰지 않는다(2026-06-23).
CONFIDENCE_KO: dict[Confidence, str] = {
    Confidence.LOW: "낮음",
    Confidence.MEDIUM_LOW: "다소 낮음",
    Confidence.MEDIUM: "보통",
    Confidence.MEDIUM_HIGH: "다소 높음",
    Confidence.HIGH: "높음",
}


def confidence_ko(value: object) -> str:
    """신뢰도 값(enum/문자열)을 한글 라벨로 순화. 미상이면 '보통'."""
    try:
        return CONFIDENCE_KO[Confidence(str(value))]
    except (ValueError, KeyError):
        return "보통"


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
    # ⚠ quality는 '성사 여부(outcome)'가 아니다(2026-07-22 데굴님 확정) — 활성 강도·경험
    # 품질이 섞인 값이라, 성사/불성사 판정으로 읽지 말 것. 표시 파생은 result_direction 사용.
    quality: str | None = None
    timing: str = "active"
    # 사건 의미축 분리 예약 필드(2026-07-22 스키마 예약 — 판정 엔진은 후속 개발).
    # outcome: 'success'|'failure'|'delayed'|None(미판정 — 억지로 채우지 않는다).
    # experience: 'stable'|'burden'|'conflict'|'drain'|None(미판정).
    # 결과 명사(합격·취업 성사 등)는 outcome이 확인된 경우에만 표시 계층이 노출한다.
    outcome: str | None = None
    experience: str | None = None
    signals: list[Signal] = Field(default_factory=list)
    evidence_path: list[str] = Field(default_factory=list)
    # ── 층위 정보는 두 개다. 섞으면 안 된다(2026-07-27 실측으로 확정) ──
    # stack_layers: 이 시점에 엔진이 **평가한 전체 signal stack**의 층위. 같은 시점의
    #   모든 후보가 동일 값을 갖는다(EventCandidateV2.source_layers의 실제 의미).
    #   ⚠ 이 값으로 "이 후보를 대운·세운이 지지했다"를 판정하면 안 된다 —
    #   stack_for()가 관할 상위 운을 항상 붙이므로 전 후보가 상위 지지로 보인다.
    # candidate_source_layers: **이 후보에 실제로 기여한** 층위. 현재 엔진은 기여 시점에
    #   층위를 기록하지 않아 항상 비어 있다(P2-PROV에서 수집 예정). 빈 값은 "월·일운만"이
    #   아니라 **판정 불가**이며, 소비 측은 기존 동작을 유지해야 한다.
    stack_layers: list[str] = Field(default_factory=list)
    candidate_source_layers: list[str] = Field(default_factory=list)
    # 클램프(0~100) 전 raw 가중 합 — 동점 후보의 우위 변별용(내부 정렬).
    raw_total: float = 0.0
    # Life Event Inference 정렬축 전달(EventCandidateV2→어댑터) — 0이면 기존 score 정렬과 동치.
    life_fit: float = 0.0
    personal_match: float = 0.0
    # 결과 길흉(−1.0~+1.0) — "사건 형성도(score) ≠ 유불리(favorability)"의 길흉 채널을
    # 다운스트림(LLM 입력)까지 전달. 양수=유리·음수=불리·0=중립/미정(EventCandidateV2에서 옮김).
    favorability: float = 0.0
    # 사건 형성도(길흉 기여 제외, display 스케일) — favorability와 독립인 활성 채널.
    # V2의 이중 채널 중 activation이 legacy 변환에서 드롭되던 것을 복구(P0-1, 2026-08-21).
    # ⚠ INV-C: 이 값과 favorability를 단일 good/bad 축으로 재합성하지 말 것.
    activation: float = 0.0
    # 시점 유입 글자의 천간/지지 역할 라벨('용신'~'한신'|'') — 독립 evidence 전용(INV-E:
    # "천간=결과, 지지=과정" 일괄 해석 금지, 단계 연결은 사건별 SSOT 매핑이 있을 때만).
    stem_role: str = ""
    branch_role: str = ""
