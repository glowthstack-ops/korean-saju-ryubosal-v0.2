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
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    EntryScopeDeclaredJournalItem,
)

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

# CARR-SCOPE — 범위 채움·충돌·부재. 부재는 결함이 아니라 자료 부재이며, dual-run에서
# "active process가 없었다"와 절대 섞지 않는다.
METRIC_ENTRY_SCOPE_FILLED = "entry_scope_filled"
METRIC_ENTRY_SCOPE_CONFLICT = "entry_scope_conflict"
METRIC_ENTRY_SCOPE_UNAVAILABLE = "entry_scope_unavailable"


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
        out.extend(_observe_entry_scope(before_store, command, result, context))
    return tuple(out)


def _observe_entry_scope(
    before_store: CareerEpisodeStore,
    command: ApplyCareerFactCommand,
    result: TransitionResult,
    context: ObservationContext,
) -> list[ShadowObservation]:
    """진입 범위 선언의 채움·충돌·부재를 감사에 남긴다 (CARR-SCOPE).

    충돌은 **위반이 아니라 정상 차단**이다(INV-24) — 자동 변경을 막았다는 뜻이므로
    `BLOCKED`으로 기록한다. 범위 부재도 결함이 아니라 자료 부재이며, dual-run에서
    "active가 없다"와 섞이지 않도록 별도 지표로 센다.

    Args:
        before_store: 명령 적용 전 store.
        command: 적용된 사실 명령.
        result: 전이 결과.
        context: 관측 맥락.

    Returns:
        관측 목록(해당 없으면 빈 목록).
    """
    if command.entry_scope is None:
        return [
            _obs(
                METRIC_ENTRY_SCOPE_UNAVAILABLE, MetricClass.MODEL_QUALITY,
                ObservationKind.ROLLOUT_TELEMETRY, GuardOutcome.NOT_APPLICABLE,
                command, context,
            )
        ]
    # 대상 Episode 는 명령이 아니라 **reducer 가 해소**한다(`target_episode_id`는 보통
    # None). 그래서 이번 명령이 남긴 선언 항목에서 실제 귀속 Episode 를 읽는다 —
    # 명령 필드를 그대로 믿으면 충돌이 조용히 '채움'으로 집계된다.
    declared = next(
        (
            i
            for i in result.store.career_journal
            if isinstance(i, EntryScopeDeclaredJournalItem)
            and i.command_id == command.command_id
        ),
        None,
    )
    if declared is None:
        return []
    episode_id = declared.target_episode_id or ""
    existing = before_store.by_id.get(episode_id)
    prior = existing.entry_scope if existing is not None else None
    if prior is not None and prior is not command.entry_scope:
        # 기존 A + 새 B — 자동 변경을 막았다. 사실을 지우지도 않는다.
        return [
            _obs(
                METRIC_ENTRY_SCOPE_CONFLICT, MetricClass.STATE_INTEGRITY,
                ObservationKind.AUDIT_EVENT, GuardOutcome.BLOCKED, command, context,
                audit_event="ENTRY_SCOPE_CONFLICT_EXISTING_VALUE",
            )
        ]
    if prior is None:
        return [
            _obs(
                METRIC_ENTRY_SCOPE_FILLED, MetricClass.MODEL_QUALITY,
                ObservationKind.AUDIT_EVENT, GuardOutcome.ALLOWED, command, context,
                audit_event="ENTRY_SCOPE_FILLED_FROM_EXPLICIT_FACT",
            )
        ]
    return []


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
    "METRIC_ENTRY_SCOPE_CONFLICT",
    "METRIC_ENTRY_SCOPE_FILLED",
    "METRIC_ENTRY_SCOPE_UNAVAILABLE",
    "METRIC_EPISODE_COLLISION",
    "METRIC_PARTIAL_COMMIT",
    "observe_career_transition",
    "run_career_shadow_transition",
]
