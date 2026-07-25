"""커리어 전이 명령·결과 계약 — P1 (CAREER_TRANSITION_SYSTEM §5·§7·§13-3·§13-4).

상태 머신은 in-place mutation이 아니라 **순수 reducer**가 새 aggregate를 반환한다.
명령은 의미별로 분리한다 — 단계 사실 하나가 암묵적으로 Episode를 만들거나 닫힌 Episode를
다시 여는 일을 막기 위함이다.

```
CareerCommand = CreateEpisodeCommand | ReopenEpisodeCommand
              | ApplyCareerFactCommand | SwitchAcceptedEpisodeCommand
```

**결정론**: reducer와 명령은 `datetime.now()`·`uuid4()`·`random`·프로세스별 `hash()`를
쓰지 않는다. 모든 ID와 시각은 명령에서 받거나 입력에서 안정적으로 파생한다 — 그래야
replay와 fixture가 byte-stable하다.

**P1 경계**: forecast·`PredictionSnapshot`은 **reducer 입력 자격이 없다**. 사용자용
LLM·report 입력과 기존 점수·랭킹은 변하지 않으며 DB·`ConversationState` 영속 배선도 없다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .career_transition import (
    CareerEpisodeStore,
    CareerStageRef,
    CareerTrack,
    CareerTransitionCloseReason,
    FactOperationType,
    OpportunitySource,
    StageHistoryItem,
)


class CareerFactSource(StrEnum):
    """사실 출처 — 여기 없는 출처(예측·추론)는 **타입 자체가 존재하지 않는다**.

    `SAJU_FORECAST`·`LLM_INFERENCE`·`SUBJECTIVE_COUNTERPARTY_GUESS`를 값으로 두지 않아
    reducer 입력이 될 수 없게 한다(INV-18).
    """

    USER_CONFIRMED = "user_confirmed"
    EXTERNAL_CONFIRMED = "external_confirmed"
    SYSTEM_MIGRATION = "system_migration"


class FactEvidenceClass(StrEnum):
    """증거 등급 — 사용자가 말했다고 모두 현실 사실은 아니다.

    "면접관이 나를 좋아한 것 같아요"는 `SUBJECTIVE_IMPRESSION`, "회사에서 뽑으려는 것
    같아요"는 `COUNTERPARTY_SPECULATION`이며 **단계 전이에 쓸 수 없다**(§8·INV-7).
    """

    OBSERVABLE_HARD_FACT = "observable_hard_fact"      # reducer 허용은 이것뿐
    SUBJECTIVE_IMPRESSION = "subjective_impression"
    COUNTERPARTY_SPECULATION = "counterparty_speculation"


class CareerFactType(StrEnum):
    """관찰 가능한 사건만 사실 유형으로 둔다.

    `EMPLOYER_INTERESTED` 같이 상대 의향을 뜻하는 유형은 만들지 않는다 — 회사의 숨은
    의향은 계산하지도 저장하지도 않는다(§8).
    """

    APPLICATION_SUBMITTED = "application_submitted"
    INTERVIEW_COMPLETED = "interview_completed"
    WRITTEN_OFFER_RECEIVED = "written_offer_received"
    OFFER_ACCEPTED = "offer_accepted"
    NOTICE_GIVEN = "notice_given"
    EXIT_COMPLETED = "exit_completed"
    JOINED = "joined"
    TRANSFER_COMPLETED = "transfer_completed"


class ReopenReason(StrEnum):
    """재개 허용 근거 — 회사명·유사 직무·추론만으로는 재개하지 않는다(§13-4e).

    금지 근거(`SAME_COMPANY_NAME_ONLY`·`SIMILAR_ROLE_ONLY`·`LLM_INFERENCE`·
    `SAJU_FORECAST`)는 값으로 두지 않아 표현 자체가 불가능하다.
    """

    SAME_REQUISITION_ID = "same_requisition_id"
    EXPLICIT_SAME_PROCESS = "explicit_same_process"
    EXPLICIT_RESUMED_PROCESS = "explicit_resumed_process"


class TransitionStatus(StrEnum):
    """전이 결과 상태 — `rejection=None`만으로는 구분되지 않는 경우를 나눈다."""

    APPLIED = "applied"
    APPLIED_NO_STATE_CHANGE = "applied_no_state_change"  # journal 추가, 현재 단계 불변
    IDEMPOTENT_NOOP = "idempotent_noop"                  # 동일 멱등 키 재수신
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"                          # 원자 transaction 검증 실패


class RejectionCode(StrEnum):
    """거부 사유 — 안전 분기(정상)와 위반을 구분해 계측한다(§15)."""

    EPISODE_UNRESOLVED = "episode_unresolved"                    # 정상 안전 분기
    FACT_OWNERSHIP_CONFLICT = "fact_ownership_conflict"          # episode_collision 후보
    EPISODE_CLOSED = "episode_closed"
    EPISODE_NOT_FOUND = "episode_not_found"
    DUPLICATE_EPISODE_ID = "duplicate_episode_id"
    INVALID_EVIDENCE_CLASS = "invalid_evidence_class"
    MISSING_STAGE_REF = "missing_stage_ref"
    UNEXPECTED_STAGE_REF = "unexpected_stage_ref"
    MISSING_TARGET_HISTORY_ITEM = "missing_target_history_item"
    CORRECTION_TARGET_MISSING = "correction_target_missing"
    CORRECTION_TARGET_OTHER_EPISODE = "correction_target_other_episode"
    REOPEN_REASON_REQUIRED = "reopen_reason_required"
    EMPLOYMENT_CONTEXT_CONFLICT = "employment_context_conflict"


class ProjectionMode(StrEnum):
    """상태 투영 방식 — 결과에 남겨 무엇이 일어났는지 구분한다."""

    NORMAL_TRANSITION = "normal_transition"
    #: 확인된 하위 단계 사실이 중간 기록 없이 들어옴. **중간 단계를 합성하지 않는다.**
    SPARSE_FORWARD_RECONCILIATION = "sparse_forward_reconciliation"
    CORRECTION_REPROJECTION = "correction_reprojection"
    MIGRATION_REPLAY = "migration_replay"


class EpisodeResolutionOutcome(StrEnum):
    """Episode 해소 결과 — 전이 실행보다 **먼저** 확정된다."""

    EXPLICIT_TARGET = "explicit_target"
    CORRECTION_TARGET_OWNER = "correction_target_owner"  # 정정·철회는 대상 사실의 소유 Episode
    UNIQUE_OPEN = "unique_open"                          # ASSERT 에만 허용
    UNRESOLVED = "unresolved"


# ── 명령 ───────────────────────────────────────────────────────────────────


class CreateEpisodeCommand(BaseModel):
    """Episode 생성 — 기본 동작은 **항상 NEW_EPISODE**.

    employer·role이 같아도 기존 Episode를 자동 재사용하지 않는다(§13-4e).
    """

    model_config = ConfigDict(frozen=True)

    command_id: str
    episode_id: str
    recorded_at: str
    source_kind: CareerFactSource
    target_company: str | None = None
    target_role: str | None = None
    requisition_id: str | None = None
    opportunity_source: OpportunitySource | None = None
    creation_reason: str | None = None


class ReopenEpisodeCommand(BaseModel):
    """닫힌 Episode 재개 — 구조화된 근거가 있을 때만 허용된다."""

    model_config = ConfigDict(frozen=True)

    command_id: str
    episode_id: str
    recorded_at: str
    source_kind: CareerFactSource
    reopen_reason: ReopenReason
    requisition_id: str | None = None


class ApplyCareerFactCommand(BaseModel):
    """단계 사실 적용 — 주장/정정/철회만 담당한다(Episode 생성·재개 불가).

    검증 규칙(operation_type 별):

    | operation | target_history_item_id | stage_ref |
    |---|---|---|
    | ASSERT  | 금지 | 필수 |
    | CORRECT | 필수 | 교정값 필수 |
    | RETRACT | 필수 | 원칙적으로 없음 |
    """

    model_config = ConfigDict(frozen=True)

    command_id: str
    source_fact_id: str
    source_kind: CareerFactSource
    evidence_class: FactEvidenceClass
    operation_type: FactOperationType
    fact_type: CareerFactType
    track: CareerTrack
    recorded_at: str
    occurred_at: str | None = None
    target_episode_id: str | None = None
    target_history_item_id: str | None = None
    stage_ref: CareerStageRef | None = None


class SwitchAcceptedEpisodeCommand(BaseModel):
    """수락 대상 Episode 변경(B사 → C사).

    현재 링크는 정확히 하나이며 기존 링크는 이력으로 보존한다 — 단순 덮어쓰기 금지.
    """

    model_config = ConfigDict(frozen=True)

    command_id: str
    new_episode_id: str
    recorded_at: str
    source_kind: CareerFactSource
    previous_episode_close_reason: CareerTransitionCloseReason | None = None


CareerCommand = (
    CreateEpisodeCommand
    | ReopenEpisodeCommand
    | ApplyCareerFactCommand
    | SwitchAcceptedEpisodeCommand
)


# ── 결과 ───────────────────────────────────────────────────────────────────


class CareerAuditEvent(BaseModel):
    """감사 이벤트 — 롤백·거부에도 **추가는 허용**되나 권위 상태를 바꾸지 않는다."""

    model_config = ConfigDict(frozen=True)

    event: str
    command_id: str
    detail: str | None = None


class TransitionResult(BaseModel):
    """reducer 출력.

    실패 시 `store`는 **입력 aggregate 그대로**이고 `history_delta`는 비어 있으며
    감사 이벤트만 남는다(부분 commit 금지 — INV-17).
    """

    model_config = ConfigDict(frozen=True)

    status: TransitionStatus
    store: CareerEpisodeStore
    history_delta: tuple[StageHistoryItem, ...] = ()
    audit_events: tuple[CareerAuditEvent, ...] = ()
    rejection_code: RejectionCode | None = None
    resolution: EpisodeResolutionOutcome | None = None
    projection_mode: ProjectionMode | None = None

    @property
    def state_changed(self) -> bool:
        """권위 상태가 실제로 바뀌었는지 — 감사 이벤트만 추가된 경우는 False."""
        return self.status in {TransitionStatus.APPLIED, TransitionStatus.APPLIED_NO_STATE_CHANGE}


__all__ = [
    "ApplyCareerFactCommand",
    "CareerAuditEvent",
    "CareerCommand",
    "CareerFactSource",
    "CareerFactType",
    "CreateEpisodeCommand",
    "EpisodeResolutionOutcome",
    "FactEvidenceClass",
    "ProjectionMode",
    "RejectionCode",
    "ReopenEpisodeCommand",
    "ReopenReason",
    "SwitchAcceptedEpisodeCommand",
    "TransitionResult",
    "TransitionStatus",
]
