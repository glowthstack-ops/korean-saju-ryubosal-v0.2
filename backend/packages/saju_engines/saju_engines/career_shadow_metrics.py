"""P1 shadow 관측 빌더 — 전이 결과를 §15 지표 관측으로 변환한다.

reducer는 **도메인 순수 함수로 유지**하고, 관측 생성은 여기서 한다(관측 코드가 상태
전이에 섞이지 않도록).

```
observe_career_transition(before_store, command, result, context) -> tuple[ShadowObservation, ...]
```

**판정은 감사 코드가 아니라 실제 전후 상태로 한다**(INV-24). 정상 가드 작동과 결함을
합산하지 않는다:

- 소유권 충돌이 **차단**되면 violation 0 + `fact_ownership_conflict_blocked` 텔레메트리
- 다른 Episode에 **실제 적용**되면 `episode_collision` violation
- 멱등 no-op은 violation 0 + `duplicate_fact_blocked` 텔레메트리
- journal·투영이 **실제 증가**하면 `duplicate_fact_application` violation
- `ROLLED_BACK` + store 불변은 violation 0, store가 바뀌었으면 partial commit violation
"""

from __future__ import annotations

from saju_shared_types.career_commands import (
    ApplyCareerFactCommand,
    CareerCommand,
    IntegrityStatus,
    RejectionCode,
    TransitionResult,
    TransitionStatus,
)
from saju_shared_types.career_transition import CareerEpisodeStore

from .career_shadow_observation import (
    GuardOutcome,
    MetricClass,
    ObservationContext,
    ObservationKind,
    ShadowObservation,
)

#: 0 허용 무결성 지표.
METRIC_EPISODE_COLLISION = "episode_collision"
METRIC_DUPLICATE_FACT = "duplicate_fact_application"
METRIC_PARTIAL_COMMIT = "employment_context_partial_commit"
METRIC_STORE_DIVERGENCE = "store_journal_divergence"
METRIC_REPLAY_DIVERGENCE = "replay_divergence"
#: 정상 가드 작동 텔레메트리(위반 아님).
METRIC_OWNERSHIP_BLOCKED = "fact_ownership_conflict_blocked"
METRIC_DUPLICATE_BLOCKED = "duplicate_fact_blocked"
METRIC_EPISODE_UNRESOLVED = "episode_unresolved"


def _obs(
    name: str,
    metric_class: MetricClass,
    kind: ObservationKind,
    guard: GuardOutcome,
    command: CareerCommand,
    context: ObservationContext,
    *,
    audit_event: str | None = None,
) -> ShadowObservation:
    return ShadowObservation(
        observation_id=f"{command.command_id}:{name}",
        metric_name=name,
        metric_class=metric_class,
        observation_kind=kind,
        guard_outcome=guard,
        observation_context=context,
        audit_event=audit_event,
    )


def _applied_episode_ids(before: CareerEpisodeStore, after: CareerEpisodeStore) -> set[str]:
    """새로 추가된 사실이 실제로 적용된 Episode id 집합."""
    before_ids = {f.history_item_id for f in before.fact_journal}
    return {
        f.target_episode_id
        for f in after.fact_journal
        if f.history_item_id not in before_ids and f.target_episode_id
    }


def observe_career_transition(
    before_store: CareerEpisodeStore,
    command: CareerCommand,
    result: TransitionResult,
    context: ObservationContext = ObservationContext.FIXTURE,
) -> tuple[ShadowObservation, ...]:
    """전이 1건의 shadow 관측을 만든다(순수 함수 — 권위 상태를 바꾸지 않는다)."""
    out: list[ShadowObservation] = []
    store_changed = result.store != before_store

    # ── 무결성 결함(전역) ──
    if result.integrity_status is IntegrityStatus.VIOLATION:
        name = (
            METRIC_REPLAY_DIVERGENCE
            if result.status is TransitionStatus.ROLLED_BACK
            else METRIC_STORE_DIVERGENCE
        )
        out.append(
            _obs(
                name, MetricClass.STATE_INTEGRITY, ObservationKind.METRIC_MEASUREMENT,
                GuardOutcome.VIOLATION, command, context, audit_event=name.upper(),
            )
        )
        return tuple(out)

    # ── 원자성: ROLLED_BACK 인데 store 가 바뀌면 위반 ──
    if result.status is TransitionStatus.ROLLED_BACK:
        out.append(
            _obs(
                METRIC_PARTIAL_COMMIT, MetricClass.STATE_INTEGRITY,
                ObservationKind.METRIC_MEASUREMENT,
                GuardOutcome.VIOLATION if store_changed else GuardOutcome.ROLLED_BACK,
                command, context, audit_event="TRANSACTION_ROLLED_BACK",
            )
        )
        return tuple(out)

    # ── 멱등: no-op 인데 journal 이 늘면 위반 ──
    if result.status is TransitionStatus.IDEMPOTENT_NOOP:
        grew = len(result.store.career_journal) > len(before_store.career_journal)
        out.append(
            _obs(
                METRIC_DUPLICATE_FACT if grew else METRIC_DUPLICATE_BLOCKED,
                MetricClass.STATE_INTEGRITY,
                ObservationKind.METRIC_MEASUREMENT if grew else ObservationKind.ROLLOUT_TELEMETRY,
                GuardOutcome.VIOLATION if grew else GuardOutcome.BLOCKED,
                command, context,
            )
        )
        return tuple(out)

    # ── 거부: 정상 안전 차단은 텔레메트리 ──
    if result.status is TransitionStatus.REJECTED:
        if result.rejection_code is RejectionCode.FACT_OWNERSHIP_CONFLICT:
            # 차단됐고 상태가 안 바뀌었으면 collision violation 이 아니다.
            out.append(
                _obs(
                    METRIC_EPISODE_COLLISION if store_changed else METRIC_OWNERSHIP_BLOCKED,
                    MetricClass.STATE_INTEGRITY,
                    ObservationKind.METRIC_MEASUREMENT
                    if store_changed
                    else ObservationKind.ROLLOUT_TELEMETRY,
                    GuardOutcome.VIOLATION if store_changed else GuardOutcome.BLOCKED,
                    command, context,
                )
            )
        elif result.rejection_code is RejectionCode.EPISODE_UNRESOLVED:
            out.append(
                _obs(
                    METRIC_EPISODE_UNRESOLVED, MetricClass.STATE_INTEGRITY,
                    ObservationKind.ROLLOUT_TELEMETRY, GuardOutcome.BLOCKED, command, context,
                )
            )
        return tuple(out)

    # ── 적용: 사실이 의도한 Episode 에만 들어갔는지 ──
    if isinstance(command, ApplyCareerFactCommand):
        applied = _applied_episode_ids(before_store, result.store)
        expected = command.target_episode_id
        leaked = bool(expected) and any(e != expected for e in applied)
        out.append(
            _obs(
                METRIC_EPISODE_COLLISION, MetricClass.STATE_INTEGRITY,
                ObservationKind.METRIC_MEASUREMENT,
                GuardOutcome.VIOLATION if leaked else GuardOutcome.ALLOWED,
                command, context,
            )
        )
    return tuple(out)


def run_career_shadow_transition(
    store: CareerEpisodeStore,
    command: CareerCommand,
    context: ObservationContext = ObservationContext.FIXTURE,
) -> tuple[TransitionResult, tuple[ShadowObservation, ...]]:
    """전이 + 관측을 묶는 shadow 전용 runner(reducer 자체는 순수 유지)."""
    from .career_transition_reducer import reduce_career_command

    result = reduce_career_command(store, command)
    return result, observe_career_transition(store, command, result, context)


__all__ = [
    "METRIC_DUPLICATE_FACT",
    "METRIC_EPISODE_COLLISION",
    "METRIC_PARTIAL_COMMIT",
    "observe_career_transition",
    "run_career_shadow_transition",
]
