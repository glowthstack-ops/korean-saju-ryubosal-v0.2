"""P3 사용자 사실 상속 runtime shadow — CAREER_TRANSITION_SYSTEM §7·§12·§15.

```
parse → 증거 자격 판정 → Episode 해소 → CareerCommand 생성 → P1 reducer → shadow 관측
```

**P3 경계**: 실제 대화 입력을 읽더라도 결과를 다음에 반영하지 않는다 —
`ConversationState` 권위 필드 · 기존 `user_facts` · 기존 EventCandidate 점수 ·
LLM 입력 · report 입력 · 사용자 응답. 상태는 **shadow namespace 전용 store**에만 쌓인다.

Episode 해소는 P1 계약 그대로다: 명시 대상 → 정정 대상 소유 Episode →
ASSERT 한정 유일 open → 나머지 `EPISODE_UNRESOLVED`(추측 금지).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_commands import (
    ApplyCareerFactCommand,
    CareerFactSource,
    CreateEpisodeCommand,
    RejectionCode,
    TransitionResult,
    TransitionStatus,
)
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    FactSourceRef,
    TrackLifecycleStatus,
)

from .career_fact_parser import CareerParsedFact, parse_career_fact
from .career_shadow_metrics import observe_career_transition
from .career_shadow_observation import ObservationContext, ShadowObservation
from .career_transition_reducer import reduce_career_command

#: shadow 전용 namespace — production 사실 원장과 섞이지 않는다.
SHADOW_NAMESPACE = "career_shadow"


def _has_open_episode(store: CareerEpisodeStore) -> bool:
    return any(
        e.opportunity.lifecycle_status is not TrackLifecycleStatus.CLOSED
        for e in store.episodes
    )


class CareerShadowRunResult(BaseModel):
    """shadow 실행 1건의 결과 — 권위 상태에 반영되지 않는다."""

    model_config = ConfigDict(frozen=True)

    parsed: CareerParsedFact
    applied: bool = False
    result: TransitionResult | None = None
    observations: tuple[ShadowObservation, ...] = ()
    skip_reason: str | None = None

    @property
    def blocked_as_not_authoritative(self) -> bool:
        """증거 자격 미달로 전이가 차단됐는지 — 정상 차단이며 위반이 아니다."""
        return self.skip_reason == "not_transition_eligible" or (
            self.result is not None
            and self.result.rejection_code is RejectionCode.FACT_NOT_AUTHORITATIVE
        )


def run_career_state_shadow(
    conversation_text: str,
    shadow_store: CareerEpisodeStore,
    *,
    command_id: str,
    source_fact_id: str,
    recorded_at: str,
    target_episode_id: str | None = None,
    occurred_at: str | None = None,
    context: ObservationContext = ObservationContext.SHADOW_TRAFFIC,
) -> CareerShadowRunResult:
    """대화 발화 1건을 shadow 상태 머신에 흘린다(순수 함수).

    전이 자격이 없으면 reducer를 호출하지 않고 `skip_reason`만 남긴다 — 추측·전망이
    권위 경로에 닿지 않게 하기 위함(INV-18).
    """
    parsed = parse_career_fact(conversation_text)
    if not parsed.is_transition_eligible:
        return CareerShadowRunResult(parsed=parsed, skip_reason="not_transition_eligible")

    assert parsed.fact_type is not None  # is_transition_eligible 이 보장
    command = ApplyCareerFactCommand(
        command_id=command_id,
        source_ref=FactSourceRef(
            source_kind=CareerFactSource.USER_CONFIRMED.value,
            source_namespace=SHADOW_NAMESPACE,
            source_fact_id=source_fact_id,
        ),
        source_kind=CareerFactSource.USER_CONFIRMED,
        evidence_class=parsed.evidence_class,
        operation_type=parsed.operation_type,
        fact_type=parsed.fact_type,
        recorded_at=recorded_at,
        occurred_at=occurred_at,
        target_episode_id=target_episode_id or parsed.episode_target_hint,
    )
    result = reduce_career_command(shadow_store, command)
    observations = observe_career_transition(shadow_store, command, result, context)
    return CareerShadowRunResult(
        parsed=parsed,
        applied=result.status
        in {TransitionStatus.APPLIED, TransitionStatus.APPLIED_NO_STATE_CHANGE},
        result=result,
        observations=observations,
    )




class PersistenceStatus(StrEnum):
    """영속 처리 결과 — canary telemetry 축."""

    NOT_ATTEMPTED = "not_attempted"      # 자격 미달·추측 등으로 저장 시도 없음
    SAVED = "saved"
    LOAD_FAILED = "load_failed"
    SAVE_FAILED = "save_failed"
    STALE_WRITE = "stale_write"
    CONTRACT_MISMATCH = "contract_mismatch"
    SCOPE_INCOMPLETE = "scope_incomplete"


class CareerTurnShadowResult(BaseModel):
    """한 turn의 shadow 처리 결과 — 소비 자격까지 함께 돌려준다.

    `chat_service`는 repository 세부를 알 필요 없이 이 결과만 본다.
    """

    model_config = ConfigDict(frozen=True)

    store: CareerEpisodeStore
    revision: int = 0
    persistence_status: PersistenceStatus = PersistenceStatus.NOT_ATTEMPTED
    run: CareerShadowRunResult | None = None
    suppress_exposure: bool = False
    telemetry: tuple[str, ...] = ()

    @property
    def consumable(self) -> bool:
        """신규 블록 노출 자격 — 억제 사유가 없을 때만 True."""
        return not self.suppress_exposure


def process_career_turn(
    repository,
    *,
    thread_id: str,
    subject_id: str,
    conversation_text: str,
    command_id: str,
    source_fact_id: str,
    recorded_at: str,
    target_episode_id: str | None = None,
    occurred_at: str | None = None,
    producer_build_sha: str = "",
) -> CareerTurnShadowResult:
    """turn 1건: load → parse → reducer → 성공분만 atomic save → 소비 자격 판정.

    거부·롤백·추측 차단 시에는 기존 store를 덮어쓰지 않는다. 멱등 no-op 은 revision을
    올리지 않는다. 저장 실패(stale·오류)나 계약 버전 불일치면 신규 블록을 억제하고
    기존 chat 경로를 유지한다.
    """
    if not thread_id or not subject_id:
        # 서버가 확정한 scope 가 없으면 저장·노출하지 않는다(발화에서 추측 금지).
        return CareerTurnShadowResult(
            store=CareerEpisodeStore(),
            persistence_status=PersistenceStatus.SCOPE_INCOMPLETE,
            suppress_exposure=True, telemetry=("scope_incomplete",),
        )
    try:
        loaded = repository.load(thread_id, subject_id)
    except Exception:
        # 빈 store 로 진행하면 과거 사실이 사라진 채 노출된다 — 이번 turn 을 억제한다.
        return CareerTurnShadowResult(
            store=CareerEpisodeStore(),
            persistence_status=PersistenceStatus.LOAD_FAILED,
            suppress_exposure=True, telemetry=("repository_load_failure",),
        )
    if loaded.contract_mismatch:
        # parse·reducer·save 를 모두 억제한다(과거 projection 소비 금지).
        return CareerTurnShadowResult(
            store=loaded.store, revision=loaded.revision,
            persistence_status=PersistenceStatus.CONTRACT_MISMATCH,
            suppress_exposure=True, telemetry=("contract_version_mismatch",),
        )

    working = loaded.store
    # 확정 사실이 들어왔는데 열린 Episode 가 없으면 하나를 만든다 — 사실이 해소될
    # 대상이 없어 유실되는 것을 막는다. 추측 발화로는 만들지 않는다(자격 판정 후).
    parsed_probe = parse_career_fact(conversation_text)
    if parsed_probe.is_transition_eligible and not _has_open_episode(working):
        created = reduce_career_command(
            working,
            CreateEpisodeCommand(
                command_id=f"{command_id}:mk",
                episode_id=f"{thread_id}:{subject_id}:ep1",
                recorded_at=recorded_at,
                source_kind=CareerFactSource.USER_CONFIRMED,
            ),
        )
        if created.status in {
            TransitionStatus.APPLIED, TransitionStatus.APPLIED_NO_STATE_CHANGE
        }:
            working = created.store

    run = run_career_state_shadow(
        conversation_text, working, command_id=command_id,
        source_fact_id=source_fact_id, recorded_at=recorded_at,
        target_episode_id=target_episode_id, occurred_at=occurred_at,
    )
    if not run.applied or run.result is None:
        # 자격 미달·거부·롤백 — 저장하지 않고 기존 store 를 그대로 쓴다(노출은 가능).
        tel = ("parser_downgrade",) if run.skip_reason == "not_transition_eligible" else ()
        return CareerTurnShadowResult(
            store=loaded.store, revision=loaded.revision, run=run, telemetry=tel
        )

    try:
        outcome = repository.save(
            thread_id, subject_id, run.result.store,
            expected_revision=loaded.revision, producer_build_sha=producer_build_sha,
        )
    except Exception:
        outcome = None
    if outcome is None or not outcome.saved:
        # **저장되지 않은 사실을 노출하지 않는다** — 다음 turn 에 사라져 모순이 된다.
        reason = outcome.reason if outcome is not None else "SAVE_FAILED"
        status = (
            PersistenceStatus.STALE_WRITE
            if reason == "STALE_SHADOW_WRITE"
            else PersistenceStatus.SAVE_FAILED
        )
        try:
            latest = repository.load(thread_id, subject_id)
            store, revision = latest.store, latest.revision
        except Exception:
            store, revision = loaded.store, loaded.revision
        return CareerTurnShadowResult(
            store=store, revision=revision, persistence_status=status, run=run,
            suppress_exposure=True, telemetry=(str(reason).lower(),),
        )
    return CareerTurnShadowResult(
        store=run.result.store, revision=outcome.revision,
        persistence_status=PersistenceStatus.SAVED, run=run,
    )


__all__ = [
    "SHADOW_NAMESPACE",
    "CareerShadowRunResult",
    "CareerTurnShadowResult",
    "PersistenceStatus",
    "process_career_turn",
    "run_career_state_shadow",
]
