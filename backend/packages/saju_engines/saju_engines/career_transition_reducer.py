"""커리어 전이 상태 머신 — 순수 reducer (P1-b, CAREER_TRANSITION_SYSTEM §5·§7·§13).

`reduce_career_command(store, command) -> TransitionResult`는 in-place mutation 없이
**새 aggregate**를 반환한다. 처리 순서:

1. `replay(journal)` — 통합 journal에서 전체 store를 재구성
2. 명령 멱등·충돌 검사(`command_id` + payload digest)
3. Episode 해소(전이 실행보다 **먼저**)
4. 명령 검증(증거 자격·연산별 필수 참조·소유권)
5. canonical `fact_type → stage` 투영
6. `TransitionPlan` 작성
7. plan 전체 불변식 검증
8. immutable aggregate **단일 commit**
9. 증분 결과 == replay 결과 대조
10. 감사 이벤트 생성

**결정론**: `datetime.now()`·`uuid4()`·`random`·프로세스별 `hash()`를 쓰지 않는다. 모든
ID·시각은 명령에서 오고, digest는 안정 정렬 JSON + sha256으로 파생한다.

**P1 경계**: forecast·`PredictionSnapshot`은 입력 자격이 없고, 사용자용 LLM·report 입력과
기존 점수·랭킹은 변하지 않으며 DB·`ConversationState` 영속 배선도 없다(shadow 전용).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from saju_shared_types.career_commands import (
    REOPENABLE_CLOSE_REASONS,
    ApplyCareerFactCommand,
    CareerAuditEvent,
    CareerCommand,
    CareerFactType,
    CloseEpisodeCommand,
    CreateEpisodeCommand,
    EpisodeResolutionOutcome,
    FactEvidenceClass,
    ProjectionMode,
    RejectionCode,
    ReopenEpisodeCommand,
    TransitionResult,
    TransitionStatus,
    canonical_stage_for,
)
from saju_shared_types.career_transition import (
    AcceptedEpisodeSwitchedJournalItem,
    CareerEpisodeStore,
    CareerJournalItem,
    CareerStageRef,
    CareerTrack,
    CareerTransitionEpisode,
    CurrentEmploymentContext,
    EmploymentContextRolledJournalItem,
    EmploymentContextSnapshot,
    EpisodeClosedJournalItem,
    EpisodeCreatedJournalItem,
    EpisodeReopenedJournalItem,
    FactOperationType,
    ObservedStageState,
    OpportunityStage,
    RealizationStatus,
    StageHistoryItem,
    TrackLifecycleStatus,
    TrackState,
    stage_rank,
)

#: 수락 사실 — 링크만 만들고 Exit·Entry를 자동 전진시키지 않는다.
_ACCEPT_FACTS = frozenset({CareerFactType.OFFER_ACCEPTED})
#: 고용 맥락을 승격(rollover)시키는 사실.
_JOIN_FACTS = frozenset({CareerFactType.JOINED})
#: 고용 맥락을 종료시키는 사실.
_EXIT_FACTS = frozenset({CareerFactType.EXIT_COMPLETED})
#: 고용 관계를 끝내지 않고 역할 revision만 남기는 사실.
_TRANSFER_FACTS = frozenset({CareerFactType.TRANSFER_COMPLETED})


def command_digest(command: CareerCommand) -> str:
    """명령 payload의 안정 다이제스트 — 같은 `command_id` 재수신이 멱등인지 충돌인지 가른다.

    `hash()`는 프로세스마다 달라지므로 쓰지 않고 정렬된 JSON + sha256으로 파생한다.
    """
    payload = command.model_dump(mode="json", exclude={"command_id"})
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ── 1. replay ──────────────────────────────────────────────────────────────


def _effective_facts(facts: tuple[StageHistoryItem, ...]) -> tuple[StageHistoryItem, ...]:
    """supersede/retract를 해소한 유효 사실만 남긴다(물리 삭제 없음).

    정렬은 `occurred_at → recorded_at → item id`로 결정적이다. 늦게 도착한 과거 사실도
    발생 시점 기준으로 재생되므로 현재 상태를 뒤로 되돌리지 않는다.
    """
    superseded = {f.supersedes_history_item_id for f in facts if f.supersedes_history_item_id}
    retracted = {
        f.supersedes_history_item_id
        for f in facts
        if f.operation_type is FactOperationType.RETRACT and f.supersedes_history_item_id
    }
    alive = [
        f
        for f in facts
        if f.history_item_id not in superseded
        and f.operation_type is not FactOperationType.RETRACT
        and f.history_item_id not in retracted
    ]
    return tuple(sorted(alive, key=lambda f: f.sort_key))


def _project_track(track: CareerTrack, facts: tuple[StageHistoryItem, ...]) -> TrackState:
    """유효 사실을 트랙 상태로 투영한다.

    `frontier_stage`는 진행 위치(최고 순위 단계)이고 `observed_stages`는 **실제 확인된
    단계만**이다. 관찰되지 않은 중간 단계를 만들지 않는다(sparse forward).
    """
    effective = _effective_facts(tuple(f for f in facts if f.track is track))
    observed = tuple(
        ObservedStageState(
            stage=CareerStageRef(track=f.track, stage=f.stage),
            source_history_item_id=f.history_item_id,
            occurred_at=f.occurred_at,
        )
        for f in effective
    )
    frontier: CareerStageRef | None = None
    if observed:
        best = max(observed, key=lambda o: stage_rank(o.stage.stage))
        frontier = best.stage
    realization = RealizationStatus.NOT_STARTED
    if effective:
        realization = RealizationStatus.IN_PROGRESS
    return TrackState(
        track=track,
        frontier_stage=frontier,
        observed_stages=observed,
        stage_history=effective,
        last_updated_at=effective[-1].recorded_at if effective else None,
        realization_status=realization,
    )


def replay(journal: tuple[CareerJournalItem, ...]) -> CareerEpisodeStore:
    """통합 journal에서 전체 store를 재구성한다 — 증분 결과의 대조 기준.

    사실만으로는 Episode 생성·재개·수락 링크·고용 rollover를 복원할 수 없으므로 생명주기
    항목까지 순서대로 재생한다.
    """
    episodes: dict[str, dict[str, object]] = {}
    current: CurrentEmploymentContext | None = None
    archived: list[EmploymentContextSnapshot] = []
    facts_by_episode: dict[str, list[StageHistoryItem]] = {}
    exit_facts: list[StageHistoryItem] = []

    for item in journal:
        if isinstance(item, EpisodeCreatedJournalItem):
            episodes[item.episode_id] = {
                "target_company": item.target_company,
                "target_role": item.target_role,
                "closed": False,
                "close_reason": None,
            }
        elif isinstance(item, EpisodeClosedJournalItem):
            if item.episode_id in episodes:
                episodes[item.episode_id]["closed"] = True
                episodes[item.episode_id]["close_reason"] = item.close_reason
        elif isinstance(item, EpisodeReopenedJournalItem):
            if item.episode_id in episodes:
                episodes[item.episode_id]["closed"] = False
                episodes[item.episode_id]["close_reason"] = None
        elif isinstance(item, StageHistoryItem):
            if item.track is CareerTrack.EXIT:
                exit_facts.append(item)
            elif item.target_episode_id:
                facts_by_episode.setdefault(item.target_episode_id, []).append(item)
        elif isinstance(item, AcceptedEpisodeSwitchedJournalItem):
            base = current or CurrentEmploymentContext(
                employment_context_id="emp-implicit",
                exit_state=TrackState(track=CareerTrack.EXIT),
            )
            history = base.linked_episode_history
            if base.linked_accepted_episode_id:
                history = (*history, base.linked_accepted_episode_id)
            current = base.model_copy(
                update={
                    "linked_accepted_episode_id": item.to_episode_id,
                    "linked_episode_history": history,
                }
            )
        elif isinstance(item, EmploymentContextRolledJournalItem):
            if current is not None and item.archived_context_id:
                archived.append(
                    EmploymentContextSnapshot(context=current, archived_at=item.recorded_at)
                )
            current = (
                CurrentEmploymentContext(
                    employment_context_id=item.new_context_id,
                    exit_state=TrackState(track=CareerTrack.EXIT),
                )
                if item.new_context_id
                else None
            )

    if exit_facts and current is not None:
        current = current.model_copy(
            update={"exit_state": _project_track(CareerTrack.EXIT, tuple(exit_facts))}
        )

    built = tuple(
        CareerTransitionEpisode(
            episode_id=eid,
            target_company=str(meta["target_company"]) if meta["target_company"] else None,
            target_role=str(meta["target_role"]) if meta["target_role"] else None,
            opportunity=_project_track(
                CareerTrack.OPPORTUNITY, tuple(facts_by_episode.get(eid, ()))
            ),
            entry=_project_track(CareerTrack.ENTRY, tuple(facts_by_episode.get(eid, ()))),
            outcome=None,
        ).model_copy(
            update={
                "opportunity": _project_track(
                    CareerTrack.OPPORTUNITY, tuple(facts_by_episode.get(eid, ()))
                ).model_copy(
                    update={
                        "lifecycle_status": TrackLifecycleStatus.CLOSED
                        if meta["closed"]
                        else TrackLifecycleStatus.OPEN,
                        "close_reason": meta["close_reason"],
                    }
                )
            }
        )
        for eid, meta in episodes.items()
    )
    return CareerEpisodeStore(
        episodes=built,
        current_employment=current,
        employment_context_history=tuple(archived),
        career_journal=journal,
    )


# ── 6. TransitionPlan ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransitionPlan:
    """commit 전 계획 — 전체가 검증을 통과해야 한 번에 반영된다(부분 commit 금지)."""

    journal_delta: tuple[CareerJournalItem, ...] = ()
    projection_mode: ProjectionMode = ProjectionMode.NORMAL_TRANSITION
    resolution: EpisodeResolutionOutcome | None = None
    audit_events: tuple[CareerAuditEvent, ...] = field(default=())


def _reject(
    store: CareerEpisodeStore,
    command: CareerCommand,
    code: RejectionCode,
    *,
    resolution: EpisodeResolutionOutcome | None = None,
) -> TransitionResult:
    """입력 거부 — 권위 상태 변화 0, 감사 이벤트만 남는다(롤백과 구분)."""
    return TransitionResult(
        status=TransitionStatus.REJECTED,
        store=store,
        rejection_code=code,
        resolution=resolution,
        audit_events=(
            CareerAuditEvent(event=code.value.upper(), command_id=command.command_id),
        ),
    )


def _rolled_back(
    store: CareerEpisodeStore, command: CareerCommand, code: RejectionCode
) -> TransitionResult:
    """원자 plan 검증 실패 — 반쪽 상태를 남기지 않는다(INV-17)."""
    return TransitionResult(
        status=TransitionStatus.ROLLED_BACK,
        store=store,
        rejection_code=code,
        audit_events=(
            CareerAuditEvent(
                event="TRANSACTION_ROLLED_BACK", command_id=command.command_id, detail=code.value
            ),
        ),
    )


# ── 2. 멱등 · 충돌 ─────────────────────────────────────────────────────────


def _prior_digest(store: CareerEpisodeStore, command_id: str) -> str | None:
    for item in store.career_journal:
        if getattr(item, "command_id", None) == command_id:
            return getattr(item, "command_digest", "") or ""
    return None


# ── 3. Episode 해소 ────────────────────────────────────────────────────────


def _open_episodes(store: CareerEpisodeStore) -> tuple[CareerTransitionEpisode, ...]:
    return tuple(
        e for e in store.episodes
        if e.opportunity.lifecycle_status is not TrackLifecycleStatus.CLOSED
    )


def _is_sparse_forward(
    store: CareerEpisodeStore, episode_id: str | None, stage: CareerStageRef
) -> bool:
    """확인된 사실이 **관찰되지 않은 중간 단계를 건너뛰는지** 판정한다.

    두 경우를 sparse로 본다("이미 최종 합격했고 다음 주 입사해요" 류):
    - Entry 사실인데 같은 Episode의 Opportunity 합의(`AGREEMENT`)가 관찰되지 않음
    - 같은 트랙 안에서 기존 frontier보다 2단계 이상 앞서감

    첫 사실 자체는 sparse가 아니다(`CONTACT` 없이 `APPLICATION`으로 시작하는 것은 정상).
    어느 경우든 **중간 단계를 만들어내지 않는다** — 표시만 남긴다.
    """
    episode_facts = tuple(f for f in store.fact_journal if f.target_episode_id == episode_id)
    if stage.track is CareerTrack.ENTRY:
        opportunity = _project_track(CareerTrack.OPPORTUNITY, episode_facts)
        observed = {o.stage.stage for o in opportunity.observed_stages}
        return OpportunityStage.AGREEMENT not in observed
    prior = _project_track(stage.track, episode_facts)
    if prior.frontier_stage is None:
        return False
    return stage_rank(stage.stage) > stage_rank(prior.frontier_stage.stage) + 1


def _resolve_episode(
    store: CareerEpisodeStore, command: ApplyCareerFactCommand
) -> tuple[str | None, EpisodeResolutionOutcome]:
    """전이 실행 **전에** 대상 Episode를 확정한다.

    정정·철회는 대상 사실의 소유 Episode로 해소하며 unique-open 자동해소를 쓰지 않는다.
    """
    if command.target_episode_id:
        return command.target_episode_id, EpisodeResolutionOutcome.EXPLICIT_TARGET
    if command.operation_type is not FactOperationType.ASSERT:
        for f in store.fact_journal:
            if f.history_item_id == command.target_history_item_id:
                return f.target_episode_id, EpisodeResolutionOutcome.CORRECTION_TARGET_OWNER
        return None, EpisodeResolutionOutcome.UNRESOLVED
    open_eps = _open_episodes(store)
    if len(open_eps) == 1:
        return open_eps[0].episode_id, EpisodeResolutionOutcome.UNIQUE_OPEN
    return None, EpisodeResolutionOutcome.UNRESOLVED


# ── 명령별 처리 ────────────────────────────────────────────────────────────


def _plan_create(
    store: CareerEpisodeStore, command: CreateEpisodeCommand
) -> TransitionPlan | TransitionResult:
    if any(e.episode_id == command.episode_id for e in store.episodes):
        return _reject(store, command, RejectionCode.EPISODE_ID_COLLISION)
    return TransitionPlan(
        journal_delta=(
            EpisodeCreatedJournalItem(
                journal_item_id=f"{command.command_id}:created",
                command_id=command.command_id,
                command_digest=command_digest(command),
                episode_id=command.episode_id,
                recorded_at=command.recorded_at,
                target_company=command.target_company,
                target_role=command.target_role,
                requisition_id=command.requisition_id,
            ),
        )
    )


def _plan_close(
    store: CareerEpisodeStore, command: CloseEpisodeCommand
) -> TransitionPlan | TransitionResult:
    if command.episode_id not in store.by_id:
        return _reject(store, command, RejectionCode.EPISODE_NOT_FOUND)
    return TransitionPlan(
        journal_delta=(
            EpisodeClosedJournalItem(
                journal_item_id=f"{command.command_id}:closed",
                command_id=command.command_id,
                command_digest=command_digest(command),
                episode_id=command.episode_id,
                recorded_at=command.recorded_at,
                close_reason=command.close_reason,
            ),
        )
    )


def _plan_reopen(
    store: CareerEpisodeStore, command: ReopenEpisodeCommand
) -> TransitionPlan | TransitionResult:
    episode = store.by_id.get(command.episode_id)
    if episode is None:
        return _reject(store, command, RejectionCode.EPISODE_NOT_FOUND)
    close_reason = episode.opportunity.close_reason
    if close_reason is not None and close_reason not in REOPENABLE_CLOSE_REASONS:
        return _reject(store, command, RejectionCode.EPISODE_NOT_REOPENABLE)
    return TransitionPlan(
        journal_delta=(
            EpisodeReopenedJournalItem(
                journal_item_id=f"{command.command_id}:reopened",
                command_id=command.command_id,
                command_digest=command_digest(command),
                episode_id=command.episode_id,
                recorded_at=command.recorded_at,
                reopen_reason=command.reopen_reason.value,
                requisition_id=command.requisition_id,
            ),
        )
    )


def _plan_fact(
    store: CareerEpisodeStore, command: ApplyCareerFactCommand
) -> TransitionPlan | TransitionResult:
    # 4-a. 증거 자격 — 사용자가 말했어도 인상·추측은 전이 자격이 없다.
    if command.evidence_class is not FactEvidenceClass.OBSERVABLE_HARD_FACT:
        return _reject(store, command, RejectionCode.FACT_NOT_AUTHORITATIVE)

    # 4-b. 연산별 필수 참조.
    if command.operation_type is FactOperationType.ASSERT:
        if command.target_history_item_id is not None:
            return _reject(store, command, RejectionCode.UNEXPECTED_TARGET_HISTORY_ITEM)
    elif command.target_history_item_id is None:
        return _reject(store, command, RejectionCode.MISSING_TARGET_HISTORY_ITEM)

    # 3. Episode 해소(실행 전).
    episode_id, resolution = _resolve_episode(store, command)
    if resolution is EpisodeResolutionOutcome.UNRESOLVED:
        code = (
            RejectionCode.CORRECTION_TARGET_MISSING
            if command.operation_type is not FactOperationType.ASSERT
            else RejectionCode.EPISODE_UNRESOLVED
        )
        return _reject(store, command, code, resolution=resolution)

    stage = canonical_stage_for(command.fact_type)
    is_exit = stage.track is CareerTrack.EXIT

    if not is_exit:
        episode = store.by_id.get(episode_id or "")
        if episode is None:
            return _reject(store, command, RejectionCode.EPISODE_NOT_FOUND, resolution=resolution)
        if (
            command.operation_type is FactOperationType.ASSERT
            and episode.opportunity.lifecycle_status is TrackLifecycleStatus.CLOSED
        ):
            return _reject(store, command, RejectionCode.EPISODE_CLOSED, resolution=resolution)

    # 4-c. 정정 대상이 같은 Episode 소유인지.
    if command.operation_type is not FactOperationType.ASSERT:
        target = next(
            (f for f in store.fact_journal if f.history_item_id == command.target_history_item_id),
            None,
        )
        if target is None:
            return _reject(
                store, command, RejectionCode.CORRECTION_TARGET_MISSING, resolution=resolution
            )
        if target.target_episode_id != episode_id:
            return _reject(
                store,
                command,
                RejectionCode.CORRECTION_TARGET_OTHER_EPISODE,
                resolution=resolution,
            )

    # 4-d. 사실 소유권 충돌 — 멱등과 별개 검사(A사 사실이 B사 Episode로 가는 것).
    owner = store.source_fact_ownership.get(command.source_ref.identity)
    if owner is not None:
        owner_episode, owner_track, owner_type = owner
        if (owner_episode, owner_track, owner_type) != (
            episode_id,
            stage.track,
            command.fact_type.value,
        ):
            return _reject(
                store, command, RejectionCode.FACT_OWNERSHIP_CONFLICT, resolution=resolution
            )

    # 5. canonical 투영 + 6. plan 작성.
    item = StageHistoryItem(
        history_item_id=f"{command.command_id}:fact",
        command_id=command.command_id,
        command_digest=command_digest(command),
        track=stage.track,
        stage=stage.stage,
        source_ref=command.source_ref,
        target_episode_id=episode_id,
        fact_type=command.fact_type.value,
        operation_type=command.operation_type,
        recorded_at=command.recorded_at,
        occurred_at=command.occurred_at,
        supersedes_history_item_id=command.target_history_item_id,
    )
    delta: list[CareerJournalItem] = [item]
    mode = ProjectionMode.NORMAL_TRANSITION
    if command.operation_type is not FactOperationType.ASSERT:
        mode = ProjectionMode.CORRECTION_REPROJECTION
    elif _is_sparse_forward(store, episode_id, stage):
        # 확인된 하위 단계 사실은 전진시키되 **중간 단계를 합성하지 않는다.**
        mode = ProjectionMode.SPARSE_FORWARD_RECONCILIATION

    # Kind별 고용 전환 — 한 사실이 다른 트랙 사실을 자동 생성하지 않는다.
    if command.operation_type is FactOperationType.ASSERT:
        if command.fact_type in _ACCEPT_FACTS:
            # 수락은 링크만. Exit·JOINED 자동 전진 없음.
            delta.append(
                AcceptedEpisodeSwitchedJournalItem(
                    journal_item_id=f"{command.command_id}:accepted",
                    command_id=command.command_id,
                    command_digest=command_digest(command),
                    recorded_at=command.recorded_at,
                    occurred_at=command.occurred_at,
                    from_episode_id=(
                        store.current_employment.linked_accepted_episode_id
                        if store.current_employment
                        else None
                    ),
                    to_episode_id=episode_id or "",
                    supporting_history_item_id=item.history_item_id,
                )
            )
        elif command.fact_type in _JOIN_FACTS:
            delta.append(
                EmploymentContextRolledJournalItem(
                    journal_item_id=f"{command.command_id}:rolled",
                    command_id=command.command_id,
                    command_digest=command_digest(command),
                    recorded_at=command.recorded_at,
                    occurred_at=command.occurred_at,
                    archived_context_id=(
                        store.current_employment.employment_context_id
                        if store.current_employment
                        else None
                    ),
                    new_context_id=f"emp:{episode_id}",
                )
            )
        elif command.fact_type in _EXIT_FACTS:
            delta.append(
                EmploymentContextRolledJournalItem(
                    journal_item_id=f"{command.command_id}:exited",
                    command_id=command.command_id,
                    command_digest=command_digest(command),
                    recorded_at=command.recorded_at,
                    occurred_at=command.occurred_at,
                    archived_context_id=(
                        store.current_employment.employment_context_id
                        if store.current_employment
                        else None
                    ),
                    new_context_id=None,  # 퇴사 단독 — current 없음
                )
            )
        elif command.fact_type in _TRANSFER_FACTS and store.current_employment is None:
            # 내부 전보는 고용 관계가 있어야 성립한다.
            return _rolled_back(store, command, RejectionCode.EMPLOYMENT_CONTEXT_CONFLICT)

    return TransitionPlan(
        journal_delta=tuple(delta), projection_mode=mode, resolution=resolution
    )


# ── 7~9. plan 검증 · 단일 commit · replay 대조 ─────────────────────────────


def _validate_plan(store: CareerEpisodeStore, plan: TransitionPlan) -> RejectionCode | None:
    """commit 전 전체 plan 불변식 검증."""
    def _jid(item: CareerJournalItem) -> str:
        # 사실 항목은 history_item_id, 생명주기 항목은 journal_item_id 를 쓴다.
        found: object = getattr(item, "journal_item_id", None) or getattr(
            item, "history_item_id", ""
        )
        return str(found)

    ids = [_jid(i) for i in plan.journal_delta]
    if len(ids) != len(set(ids)):
        return RejectionCode.EMPLOYMENT_CONTEXT_CONFLICT  # journal id 중복
    existing = {_jid(i) for i in store.career_journal}
    if existing & set(ids):
        return RejectionCode.EMPLOYMENT_CONTEXT_CONFLICT
    rolls = [i for i in plan.journal_delta if isinstance(i, EmploymentContextRolledJournalItem)]
    if len(rolls) > 1:
        return RejectionCode.EMPLOYMENT_CONTEXT_CONFLICT  # current employment 결과는 최대 1개
    switches = [
        i for i in plan.journal_delta if isinstance(i, AcceptedEpisodeSwitchedJournalItem)
    ]
    if len(switches) > 1:
        return RejectionCode.EMPLOYMENT_CONTEXT_CONFLICT  # accepted link 최대 1개
    return None


def reduce_career_command(
    store: CareerEpisodeStore, command: CareerCommand
) -> TransitionResult:
    """명령 1건을 적용해 새 aggregate를 반환한다(순수 함수).

    실패 시 `store`는 입력 그대로이며 `journal_delta`가 비고 감사 이벤트만 남는다.
    """
    # 0. 입력 store 가 자신의 journal 로 설명되는지 — commit 이 전체 replay 이므로,
    #    journal 로 재현되지 않는 상태는 조용히 유실된다. 유실 대신 거부한다.
    if replay(store.career_journal) != store:
        return _reject(store, command, RejectionCode.STORE_NOT_JOURNAL_CONSISTENT)

    # 2. 멱등 · command_id 충돌.
    digest = command_digest(command)
    prior = _prior_digest(store, command.command_id)
    if prior is not None:
        if prior == digest:
            return TransitionResult(
                status=TransitionStatus.IDEMPOTENT_NOOP,
                store=store,
                resolution=None,
                audit_events=(
                    CareerAuditEvent(event="IDEMPOTENT_NOOP", command_id=command.command_id),
                ),
            )
        return _reject(store, command, RejectionCode.COMMAND_ID_CONFLICT)

    # 3~6. 명령별 plan.
    if isinstance(command, CreateEpisodeCommand):
        outcome = _plan_create(store, command)
    elif isinstance(command, CloseEpisodeCommand):
        outcome = _plan_close(store, command)
    elif isinstance(command, ReopenEpisodeCommand):
        outcome = _plan_reopen(store, command)
    else:
        outcome = _plan_fact(store, command)
    if isinstance(outcome, TransitionResult):
        return outcome
    plan = outcome

    # 7. plan 전체 검증 — 실패는 롤백(입력 거부와 구분).
    invalid = _validate_plan(store, plan)
    if invalid is not None:
        return _rolled_back(store, command, invalid)

    # 8. 단일 commit — journal에 append 후 전체 replay로 투영한다.
    new_journal = (*store.career_journal, *plan.journal_delta)
    new_store = replay(new_journal)

    facts = tuple(i for i in plan.journal_delta if isinstance(i, StageHistoryItem))
    changed = new_store.episodes != store.episodes or (
        new_store.current_employment != store.current_employment
    )
    status = TransitionStatus.APPLIED if changed else TransitionStatus.APPLIED_NO_STATE_CHANGE
    return TransitionResult(
        status=status,
        store=new_store,
        journal_delta=plan.journal_delta,
        history_delta=facts,
        resolution=plan.resolution,
        projection_mode=plan.projection_mode,
        audit_events=(CareerAuditEvent(event=status.value.upper(), command_id=command.command_id),),
    )


__all__ = ["TransitionPlan", "command_digest", "reduce_career_command", "replay"]
