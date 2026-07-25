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

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_commands import (
    ApplyCareerFactCommand,
    CareerFactSource,
    RejectionCode,
    TransitionResult,
    TransitionStatus,
)
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    FactSourceRef,
)

from .career_fact_parser import CareerParsedFact, parse_career_fact
from .career_shadow_metrics import observe_career_transition
from .career_shadow_observation import ObservationContext, ShadowObservation
from .career_transition_reducer import reduce_career_command

#: shadow 전용 namespace — production 사실 원장과 섞이지 않는다.
SHADOW_NAMESPACE = "career_shadow"


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




class CareerTurnShadowResult(BaseModel):
    """한 turn의 shadow 처리 결과 — 소비 자격까지 함께 돌려준다."""

    model_config = ConfigDict(frozen=True)

    store: CareerEpisodeStore
    revision: int = 0
    run: CareerShadowRunResult | None = None
    consumable: bool = True
    suppress_reason: str | None = None


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
    loaded = repository.load(thread_id, subject_id)
    if loaded.contract_mismatch:
        # 과거 projection 을 그대로 소비하지 않는다(자동 migration 은 후속 과제).
        return CareerTurnShadowResult(
            store=loaded.store, revision=loaded.revision, consumable=False,
            suppress_reason="CONTRACT_VERSION_MISMATCH",
        )

    run = run_career_state_shadow(
        conversation_text, loaded.store, command_id=command_id,
        source_fact_id=source_fact_id, recorded_at=recorded_at,
        target_episode_id=target_episode_id, occurred_at=occurred_at,
    )
    if not run.applied or run.result is None:
        # 자격 미달·거부·롤백 — 저장하지 않고 기존 store 를 그대로 쓴다.
        return CareerTurnShadowResult(
            store=loaded.store, revision=loaded.revision, run=run
        )

    outcome = repository.save(
        thread_id, subject_id, run.result.store,
        expected_revision=loaded.revision, producer_build_sha=producer_build_sha,
    )
    if not outcome.saved:
        # 조용한 lost update 방지 — 최신 상태를 다시 읽고 이번 턴은 신규 블록 억제.
        latest = repository.load(thread_id, subject_id)
        return CareerTurnShadowResult(
            store=latest.store, revision=latest.revision, run=run,
            consumable=False, suppress_reason=outcome.reason,
        )
    return CareerTurnShadowResult(
        store=run.result.store, revision=outcome.revision, run=run
    )


__all__ = [
    "SHADOW_NAMESPACE",
    "CareerShadowRunResult",
    "CareerTurnShadowResult",
    "process_career_turn",
    "run_career_state_shadow",
]
