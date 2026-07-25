"""이직·커리어 전이 도메인 타입 — P0-B 계약 전용 (CAREER_TRANSITION_SYSTEM §3·§5~§9).

이직은 하나의 운이 아니라 **Opportunity·Exit·Entry 3트랙이 병렬로 움직이는 사건
그래프**다(INV-1). 세 트랙은 순서가 교차할 수 있으므로(오퍼 전 퇴사·수락 후 통보
지연·퇴사 후 입사 취소) 단일 `completion` 값을 두지 않는다.

**P0-B 범위 — 계약 전용**:
- DB·`ConversationState` 접근 없음, 전역 singleton 없음, production 생성 없음.
- authoritative write 메서드 없음(권위 상태 변경 0 — P0-B 종료 조건).
- 실제 전이 로직은 P1, 사용자 사실 상속은 P3에서 구현한다. 본 모듈은 그 타입이
  **표현 가능**하다는 것만 보장한다.

신규 canonical `event_key`를 만들지 않는다(D1) — 단계·결과·종료사유는 `career_change`
/`job_gain`/`promotion` 위의 타입 레이어다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

#: 커리어 전이 계약 버전 — 타입·불변식이 바뀌면 올린다.
CAREER_CONTRACT_VERSION = "career-transition.v1"


# ── 트랙과 단계 (D5 — 트랙별 enum으로 트랙 교차 전이를 타입 수준에서 차단) ──


class CareerTrack(StrEnum):
    """3 병렬 트랙."""

    OPPORTUNITY = "opportunity"  # 새 기회
    EXIT = "exit"                # 현 직장 종료 — current_employment_context 소유
    ENTRY = "entry"              # 목적지 진입(외부 입사 또는 내부 역할·부서 실행)


class OpportunityStage(StrEnum):
    """기회 트랙 단계 — 오퍼 검토·협상은 **단계가 소유**한다(태도 enum에 넣지 않음)."""

    CONTACT = "contact"
    APPLICATION = "application"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER_RECEIVED = "offer_received"
    OFFER_REVIEW = "offer_review"
    NEGOTIATING = "negotiating"
    AGREEMENT = "agreement"


class ExitStage(StrEnum):
    """현 직장 종료 트랙 단계."""

    UNDECIDED = "undecided"
    NOTICE_PLANNED = "notice_planned"
    NOTICE_GIVEN = "notice_given"
    COUNTEROFFER = "counteroffer"
    HANDOVER = "handover"
    EXITED = "exited"


class EntryStage(StrEnum):
    """목적지 진입 트랙 단계 — '새 회사 입사'로 좁게 보지 않는다(D18)."""

    START_DATE_PENDING = "start_date_pending"
    START_DATE_FIXED = "start_date_fixed"
    CONTRACT_APPROVED = "contract_approved"
    JOINED = "joined"
    PROBATION = "probation"
    STABILIZED = "stabilized"


class EntryScope(StrEnum):
    """진입 목적지 범위 — 내부 전보를 Entry 트랙에 담기 위한 구분(D18)."""

    EXTERNAL_EMPLOYER = "external_employer"
    INTERNAL_ROLE = "internal_role"
    INTERNAL_DEPARTMENT = "internal_department"
    INTERNAL_LOCATION = "internal_location"


class CareerStageRef(BaseModel):
    """트랙 + 단계 쌍. `INTERVIEW → HANDOVER` 같은 트랙 교차 전이를 타입으로 막는다."""

    model_config = ConfigDict(frozen=True)

    track: CareerTrack
    stage: OpportunityStage | ExitStage | EntryStage


# ── 전환 유형 · 태도 · 질의 (D20 — 세 축을 서로 다른 필드가 소유) ──


class CareerTransitionKind(StrEnum):
    """전환 **결과유형**. 재직 중 탐색 여부 같은 진행 상태는 `CareerProcessMode`가 소유."""

    EXTERNAL_MOVE = "external_move"
    JOB_GAIN_FROM_UNEMPLOYED = "job_gain_from_unemployed"
    RESIGNATION_ONLY = "resignation_only"
    INTERNAL_TRANSFER = "internal_transfer"


class CareerProcessMode(StrEnum):
    """사용자 구직 **태도**만 소유. 오퍼 검토·협상은 `OpportunityStage`가 소유한다."""

    NOT_SEARCHING = "not_searching"
    PASSIVE_EXPLORATION = "passive_exploration"
    ACTIVE_JOB_SEARCH = "active_job_search"
    EXIT_ONLY = "exit_only"


class CareerQueryResolution(StrEnum):
    """현재 턴의 질의 해소 결과 — **저장 권위 상태가 아니라 라우팅값**(§12-3)."""

    GENERAL_CAREER = "general_career"                          # Episode 비특정(해소 오류 아님)
    EPISODE_SPECIFIC_RESOLVED = "episode_specific_resolved"
    EPISODE_SPECIFIC_UNRESOLVED = "episode_specific_unresolved"  # 항상 안전 분기


class OpportunitySource(StrEnum):
    """기회 유입 경로 — legacy `event_forms`의 '스카우트 제의'가 여기로 재분류된다."""

    RECRUITER_OR_SCOUT = "recruiter_or_scout"
    REFERRAL = "referral"
    DIRECT_APPLICATION = "direct_application"
    INTERNAL_CONTACT = "internal_contact"


# ── lifecycle · 종료사유 · 결과 (명문화 B — 단계/lifecycle/사유/결과 4분할) ──


class TrackLifecycleStatus(StrEnum):
    """트랙 진행 상태. 종료 **사유**는 `CareerTransitionCloseReason`이 따로 소유한다."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class CareerTransitionCloseReason(StrEnum):
    """종료 사유 — 단계·lifecycle·결과와 분리한다(`NEGOTIATION_FAILED` 단일값 금지)."""

    SCREENING_REJECTED = "screening_rejected"
    INTERVIEW_REJECTED = "interview_rejected"
    POSITION_CLOSED = "position_closed"
    OFFER_WITHDRAWN = "offer_withdrawn"
    CANDIDATE_WITHDRAWAL = "candidate_withdrawal"
    AGREEMENT_FAILED = "agreement_failed"
    COUNTEROFFER_ACCEPTED = "counteroffer_accepted"
    OTHER_OFFER_CHOSEN = "other_offer_chosen"
    EMPLOYER_INITIATED_EXIT = "employer_initiated_exit"
    VOLUNTARY_EXIT = "voluntary_exit"
    EARLY_EXIT = "early_exit"          # 조기 이탈 — 사건 소유자는 lifecycle/Exit 트랙
    PROBATION_FAILED = "probation_failed"


class CareerEpisodeOutcome(StrEnum):
    """**Episode lifecycle 결말**만 뜻한다.

    §14 캘리브레이션의 `outcome`(사용자 확인 현실 결말)이나 사용자 체감과는 다른 축이며
    서로 대체하지 않는다(INV-22). 캘리브레이션 축은 별도 타입이 소유한다.
    """

    REALIZED = "realized"
    CLOSED_UNREALIZED = "closed_unrealized"
    SUPERSEDED = "superseded"


class RealizationStatus(StrEnum):
    """사실 완료 — **사용자 확인 사실만으로** 결정한다(INV-15).

    점수·명식·forecast는 이 값을 생성하거나 취소하지 않는다. 예측 여건은
    `forecast_completion_readiness`(별도)가 표현한다.
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED_UNREALIZED = "closed_unrealized"


# ── 사실 이력 (§13-4 — 멱등·정정·역순 입력을 타입이 표현할 수 있어야 한다) ──


class FactOperationType(StrEnum):
    """사실 적용 연산 — 멱등 키의 구성 요소이자 정정·철회의 보상 이벤트 종류."""

    ASSERT = "assert"      # 사실 주장
    CORRECT = "correct"    # 정정(기존 사실 supersede)
    RETRACT = "retract"    # 철회(물리 삭제 아님 — 보상 이벤트로 남긴다)


class TimePrecision(StrEnum):
    """발생 시점 정밀도 — 시점 오차는 관찰 시점이 아니라 발생 시점으로 계산한다(INV-23)."""

    EXACT = "exact"
    DAY = "day"
    MONTH = "month"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class StageHistoryItem(BaseModel):
    """사용자 확인 진행 이력 1건.

    `stage + timestamp`만으로는 정정·멱등·역순 사실을 표현할 수 없으므로 멱등 키와
    보상 이벤트 메타데이터를 함께 보존한다. 정정·철회는 **물리 삭제가 아니라**
    `supersedes_history_item_id`로 연결된 새 항목이다.
    """

    model_config = ConfigDict(frozen=True)

    history_item_id: str
    track: CareerTrack
    stage: OpportunityStage | ExitStage | EntryStage
    source_fact_id: str
    #: 멱등 키의 대상 Episode 성분. 소유 트랙 상태가 자신의 Episode를 알고 채운다.
    target_episode_id: str | None = None
    fact_type: str
    operation_type: FactOperationType
    recorded_at: str                      # 시스템이 받은 시점(≠ 발생 시점)
    occurred_at: str | None = None        # 실제 발생 시점(역순 입력은 이 값으로 정렬)
    time_precision: TimePrecision = TimePrecision.UNKNOWN
    supersedes_history_item_id: str | None = None
    evidence_id: str | None = None

    @property
    def idempotency_key(self) -> tuple[str, str | None, str, FactOperationType]:
        """멱등 키 — 문장 텍스트가 아니다(§13-4a).

        같은 문장이라도 대상 Episode가 다르면 별개 사실이다("오퍼를 받았다"—A사 / B사).
        동일 `source_fact_id` 재전달만 중복 적용하지 않는다.
        """
        return (self.source_fact_id, self.target_episode_id, self.fact_type, self.operation_type)


# ── 트랙 상태 (D16 — 단일 completed_stage 금지, 이력·lifecycle·사유 분리) ──


class TrackState(BaseModel):
    """트랙 1개의 상태.

    `resolved_stage`(발화 해석)는 여기 저장하지 않는다 — resolver의 **턴 단위 출력**이며
    적용 게이트를 통과한 뒤에만 `current_confirmed_stage`·`stage_history`가 갱신된다(§7).
    """

    model_config = ConfigDict(frozen=True)

    track: CareerTrack
    current_confirmed_stage: CareerStageRef | None = None
    lifecycle_status: TrackLifecycleStatus = TrackLifecycleStatus.OPEN
    close_reason: CareerTransitionCloseReason | None = None
    stage_history: tuple[StageHistoryItem, ...] = ()
    last_updated_at: str | None = None
    source_fact_id: str | None = None
    realization_status: RealizationStatus = RealizationStatus.NOT_STARTED


# ── Episode · 현재 고용 맥락 · 저장소 aggregate ──


class CareerTransitionEpisode(BaseModel):
    """회사(기회)별 Episode.

    **Exit 트랙을 갖지 않는다** — 현 직장 종료는 `CurrentEmploymentContext`가 단독
    소유하며 Episode에 복제하지 않는다(D4). 복제하면 복수 지원 시 충돌한다.

    `transition_kind`/`intended_kind`는 **nullable**이며 `UNKNOWN` enum을 두지 않는다
    (미확정과 실제 유형을 섞지 않기 위함). 사주 신호는 두 값을 확정하지 않는다.
    """

    model_config = ConfigDict(frozen=True)

    episode_id: str
    target_company: str | None = None
    target_role: str | None = None
    source: OpportunitySource | None = None
    transition_kind: CareerTransitionKind | None = None   # 현실 증거로 해소된 유형
    intended_kind: CareerTransitionKind | None = None     # 사용자가 밝힌 목표
    process_mode: CareerProcessMode | None = None
    entry_scope: EntryScope | None = None
    opportunity: TrackState
    entry: TrackState
    outcome: CareerEpisodeOutcome | None = None


class CurrentEmploymentContext(BaseModel):
    """현 직장 맥락 — **Exit 트랙의 단독 소유자**(D4).

    오퍼 수락 시 선택된 Episode와 링크하며, 링크 변경은 단순 덮어쓰기가 아니라 이력을
    남긴다(§5 교차 트랙 게이트). 퇴사 단독은 링크 없이 성립한다.
    """

    model_config = ConfigDict(frozen=True)

    employment_context_id: str
    exit_state: TrackState
    linked_accepted_episode_id: str | None = None   # RESIGNATION_ONLY 는 None 허용
    linked_episode_history: tuple[str, ...] = ()     # 대상 변경 이력(덮어쓰기 금지)


class CareerEpisodeStore(BaseModel):
    """P0-B 계약 전용 aggregate(스냅샷).

    영속되지 않고 `ConversationState`에 배선되지 않으며, 승인된 후속 Phase 전에는
    권위 상태가 아니다. 실제 영속은 후속 `CareerEpisodeRepository`(미구현)가 맡고
    본 타입은 도메인 aggregate/스냅샷으로 남는다.

    **P0 범위**: 한 시점에 primary employment는 **하나**만 관리한다(D19). 겸업·복수
    고용·법인+개인사업 병행은 확장 범위이며, 감지돼도 단일 Exit로 임의 병합하지 않는다.
    """

    model_config = ConfigDict(frozen=True)

    episodes: dict[str, CareerTransitionEpisode] = Field(default_factory=dict)
    current_employment: CurrentEmploymentContext | None = None
    contract_version: str = CAREER_CONTRACT_VERSION
