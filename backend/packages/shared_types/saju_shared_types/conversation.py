"""대화 계층 schemas (v2.2 Phase 4, docs/03 A0~A3).

서비스 품질을 실제로 결정하는 계층 — 사용자는 "내 질문을 이해하고 맥락을 이어
답했는가"로 평가한다(docs/03). 대상(Subject) 해석 오류가 실측 최다 치명 오류이므로
모든 메시지는 intent 파싱 전에 대상부터 확정한다(절대 원칙 7).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .events import EventKey
from .intent import Domain, IntentJson, SubjectMode, SubjectRef


class EntityType(StrEnum):
    """추적 엔티티 종류 (docs/03 A2 — claim 포함 7종)."""

    PERSON = "person"
    EVENT = "event"
    PERIOD = "period"
    PLACE = "place"
    DAEWOON = "daewoon"
    ANCHOR_DATE = "anchor_date"
    CLAIM = "claim"  # 시스템 명리 판정 — 수 턴 뒤 이의 제기 재검산용(T4.5)


class TrackedEntity(BaseModel):
    """참조어 해석 대상 1건 (docs/03 A2 TrackedEntity)."""

    id: str  # 'partner_1', 'temp_19980723_f', 'claim_yongsin_1'
    type: EntityType
    label: str  # '현재 연애 상대', '1998.07.23 여자'
    source_turn: int
    source_role: str  # 'user' | 'assistant' — 시스템 답변 발 엔티티 구분
    attributes: dict = Field(default_factory=dict)


class LinkKind(StrEnum):
    """연속성 종류 (docs/03 A3 LinkResult.linkKind)."""

    TIME_SHIFT = "time_shift"  # "5월은 어때?" — 시점만 교체(F2)
    DOMAIN_SHIFT = "domain_shift"  # "그럼 이직은 어때?" — 도메인만 교체(F1)
    SUBJECT_SHIFT = "subject_shift"  # "남편은?" — 대상만 교체
    CONSTRAINT_ADD = "constraint_add"  # "남동쪽으로 간다면" — 조건 누적(F3)
    DRILL_DOWN = "drill_down"  # "세부적으로 시기별로" — granularity 상향(F8)
    CHALLENGE = "challenge"  # 이의/정정(B9/B10) → Q12 라우팅
    NEW = "new"


class LinkResult(BaseModel):
    """새 질문 vs 이전 질문 판별 결과 (docs/03 A3)."""

    is_follow_up: bool
    parent_intent_id: str | None = None
    link_kind: LinkKind = LinkKind.NEW
    confidence: float = 1.0
    # 상속된 슬롯 요약(전체 intent 병합은 엔진이 수행).
    inherited_domain: Domain | None = None
    inherited_subjects: list[SubjectRef] = Field(default_factory=list)


class SubjectResolution(BaseModel):
    """대상 확정 결과 (docs/03 A0)."""

    subjects: list[SubjectRef] = Field(default_factory=list)
    subject_mode: SubjectMode = SubjectMode.SINGLE
    unresolved: list[str] = Field(default_factory=list)  # 매핑 실패 호칭 → 확인 질문
    alias_updates: dict[str, str] = Field(default_factory=dict)  # 별칭 → companion_id 학습
    correction: bool = False  # A10 대상 혼동 정정 → 동일 intent 재실행 신호
    time_unknown: bool = False  # A13 생시 미상 → 3주 모드 + 신뢰도 하향


class ResultSummaryRef(BaseModel):
    """직전 답변에서 제시한 이벤트/시기/판정 요약(F5 인용 이의 대응)."""

    kind: str  # 'event' | 'claim' | 'period'
    label: str
    detail: str = ""


class ConversationState(BaseModel):
    """현재 대화가 무엇을 다루는지 (docs/03 A1 ConversationState)."""

    thread_id: str
    turn_no: int = 0
    active_subjects: list[SubjectRef] = Field(default_factory=list)
    active_topic: Domain | None = None
    active_time_scope: str | None = None  # '2027' / '2026-06' 등 기간 키
    active_event: EventKey | None = None
    active_constraints: dict = Field(default_factory=dict)  # 누적 조건(F3)
    anchor_dates: list[dict] = Field(default_factory=list)  # {'label','date'}(C11)
    last_intent: IntentJson | None = None
    last_results: list[ResultSummaryRef] = Field(default_factory=list)
    repeat_count: int = 0  # 동일 질문 반복(F7) — 2회 이상이면 다른 각도 제시
    last_question_norm: str = ""  # 반복 감지용 정규화 질문
    entities: list[TrackedEntity] = Field(default_factory=list)
    # 궁합 상대 첨부(크로스 디바이스 재개 복원용) — 프론트 ChatPartner 형태
    # {'mode','label', 'subjectId'|'birth'}. 매 턴 현재 첨부로 미러링(없으면 None).
    partner: dict | None = None
