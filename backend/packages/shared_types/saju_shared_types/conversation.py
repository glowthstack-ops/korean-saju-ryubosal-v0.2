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


class TimeExclusion(BaseModel):
    """사용자가 배제한 연 단위 기간 + 스코프 (2026-07-14 시점 정합 P2).

    "2026·27년은 의미없고"처럼 배제된 기간을 스레드 전체 영구 금지가 아니라
    출처·스코프가 있는 제약으로 저장한다 — 이후 "이번에는 2026년만 다시 봐줘"
    같은 명시적 재요청이 오면 해제하고, 주제 전환 시 topic 스코프는 만료한다.
    """

    start_year: int
    end_year: int
    scope: str = "current_topic"  # 'current_turn' | 'current_topic' | 'thread'
    source_turn: int = 0
    explicit: bool = True
    reason: str = ""  # 배제 판정 근거 술어 원문('의미없고' 등)
    confidence: float = 1.0


class UserFact(BaseModel):
    """사용자가 대화에서 직접 밝힌 사실 1건 (2026-07-22 사실 원장 P0).

    쓰기 정책: 출처는 항상 사용자 명시 발화(user_explicit)다 — 엔진 계산 결과·LLM 해석·
    추론을 이 모델에 기록하는 것은 금지(대화 오염 차단, GPT 검토안 §8 승인). 상속은
    질문 원문이 아니라 이 슬롯 단위로만 하며, LLM 입력에는 [사용자 제공 정보] 블록으로
    주입돼 이미 밝힌 사실과 모순되는 서술·되묻기를 차단한다.
    """

    key: str  # 'completed' | 'remaining' | 'fixed_schedule' | 'unchangeable' | 'folk_condition'
    quote: str  # 발화 원문 절(정규화 값 대신 인용 보존 — 오해석 방지, 80자 컷)
    scope: str = "topic"  # 'topic'(주제 전환 시 만료) | 'global'(스레드 지속)
    status: str = "confirmed"  # 'confirmed' | 'corrected'(supersede로 대체됨)
    source_turn: int = 0
    superseded_quote: str | None = None  # 같은 key 단수 슬롯이 정정된 경우 이전 인용(이력)


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
    # 직전 턴의 시간 방향(과거 회고면 True). open_when 후속('월단위로')처럼 자체 신호가 없는
    # 턴이 직전 방향을 상속해 미래/과거 창을 일관 유지하게 한다(2026-06-30 시점 정합).
    last_retro: bool = False
    # 직전 답변 끝의 제안(offer) 문장 — '어느 해의 월별 흐름을 볼까요?'. 다음 턴의 슬롯 답변
    # ('2026년')을 제안 수락(offer-slot)으로 연결하고, '월별' 함의면 granularity를 월로 승격한다
    # (2026-07-01). 답변 확정 시 _extract_offer로 채우고 비offer면 ''로 만료.
    last_offer: str = ""
    # 사용자가 배제한 기간 목록(2026-07-14 P2) — 시점 승계·엔진 창·LLM 서술에서 제외.
    # 명시적 재요청 시 해제, 주제 전환 시 current_topic 스코프 만료(병합 규칙은 엔진).
    time_exclusions: list[TimeExclusion] = Field(default_factory=list)
    # 사용자 제공 사실 원장(2026-07-22 P0) — 완료·잔여·확정 일정 등 명시 사실만 축적해
    # 후속 턴 LLM 입력에 주입한다(원문 전체 상속 없이 연속성 보존). 규칙은 user_facts 모듈.
    user_facts: list[UserFact] = Field(default_factory=list)
    # 활성 시점의 출처 메타(2026-07-14 P7 lite) — {'value','source_turn','resolution_type',
    # 'confidence'}. 낮은 신뢰 파싱이 기존 상태를 덮어쓰는 것을 막는 근거 기록.
    active_time_meta: dict = Field(default_factory=dict)
