"""P1 shadow 관측·census 회귀 — CAREER_TRANSITION_SYSTEM §15·§16.

지표 판정이 **감사 코드가 아니라 실제 전후 상태**로 이뤄지는지, 정상 가드 작동이
위반으로 집계되지 않는지 검증한다(INV-24). census 분모는 지표별로 따로 고정한다.
"""

from __future__ import annotations

from saju_engines.career_shadow_metrics import (
    METRIC_DUPLICATE_FACT,
    METRIC_EPISODE_COLLISION,
    METRIC_PARTIAL_COMMIT,
    observe_career_transition,
    run_career_shadow_transition,
)
from saju_engines.career_shadow_observation import GuardOutcome, ObservationKind
from saju_engines.career_transition_reducer import reduce_career_command
from saju_shared_types.career_commands import (
    ApplyCareerFactCommand,
    CareerFactSource,
    CareerFactType,
    CloseEpisodeCommand,
    CreateEpisodeCommand,
    FactEvidenceClass,
    IntegrityStatus,
    RejectionCode,
    TransitionStatus,
    ViolationScope,
)
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    CareerTrack,
    CareerTransitionCloseReason,
    CareerTransitionEpisode,
    FactOperationType,
    FactSourceRef,
    TrackState,
)

UC = CareerFactSource.USER_CONFIRMED
HARD = FactEvidenceClass.OBSERVABLE_HARD_FACT


def _sref(fid: str) -> FactSourceRef:
    return FactSourceRef(source_kind="user_confirmed", source_namespace="chat", source_fact_id=fid)


def _create(cid: str, eid: str, at: str = "t0") -> CreateEpisodeCommand:
    return CreateEpisodeCommand(command_id=cid, episode_id=eid, recorded_at=at, source_kind=UC)


def _fact(cid, fid, ftype, ep=None, *, op=FactOperationType.ASSERT, target=None,
          at="t1", occurred=None, evidence=HARD) -> ApplyCareerFactCommand:
    return ApplyCareerFactCommand(
        command_id=cid, source_ref=_sref(fid), source_kind=UC, evidence_class=evidence,
        operation_type=op, fact_type=ftype, recorded_at=at, occurred_at=occurred,
        target_episode_id=ep, target_history_item_id=target,
    )


def _apply(store, *cmds):
    for c in cmds:
        r = reduce_career_command(store, c)
        assert r.status in {TransitionStatus.APPLIED, TransitionStatus.APPLIED_NO_STATE_CHANGE}, (
            f"{c.command_id} → {r.status} {r.rejection_code}"
        )
        store = r.store
    return store


# ── #1 journal 순서 vs projection 순서 ─────────────────────────────────────


def test_journal_replays_in_append_order_not_occurred_at() -> None:
    """전체 journal을 occurred_at으로 재정렬하지 않는다.

    오늘 만든 Episode에 그보다 이른 발생일 사실을 뒤늦게 기록해도 Episode 생성이 사실보다
    뒤로 밀리지 않는다. 발생일 정렬은 **사실 projection에만** 적용된다.
    """
    store = _apply(
        CareerEpisodeStore(),
        _create("c0", "ep-a", at="2027-07-10"),
        _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a",
              at="2027-07-11", occurred="2027-07-01"),
    )
    assert [type(i).__name__ for i in store.career_journal][0] == "EpisodeCreatedJournalItem"
    assert "ep-a" in store.by_id                       # Episode 유실 없음
    observed = store.by_id["ep-a"].opportunity.observed_stages
    assert [o.occurred_at for o in observed] == ["2027-07-01"]   # projection 은 과거 사실


# ── #4 JOINED rollover 가 Exit 사실을 합성하지 않음 ────────────────────────


def test_join_rollover_does_not_synthesise_exit_facts() -> None:
    """입사로 고용 맥락이 승격돼도 퇴사·통보가 확인된 것으로 기록되지 않는다."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.JOINED, "ep-a"),
    )
    assert store.current_employment is not None
    exit_state = store.current_employment.exit_state
    assert exit_state.observed_stages == ()          # EXIT 관찰 자동 생성 0
    assert exit_state.frontier_stage is None
    exit_facts = [f for f in store.fact_journal if f.track is CareerTrack.EXIT]
    assert exit_facts == []


def test_offer_accepted_only_links_and_join_preserves_history() -> None:
    """수락은 링크만, 입사는 이전 맥락을 이력으로 보존한다."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a"),
        _fact("c2", "f2", CareerFactType.OFFER_ACCEPTED, "ep-a"),
    )
    assert store.current_employment is not None
    assert store.current_employment.linked_accepted_episode_id == "ep-a"
    assert store.by_id["ep-a"].entry.observed_stages == ()   # 입사 전진 0
    joined = _apply(store, _fact("c3", "f3", CareerFactType.JOINED, "ep-a"))
    assert joined.employment_context_history  # 이전 맥락 보존


# ── #5 정정·철회 revision chain ────────────────────────────────────────────


def test_retract_after_correct_does_not_revive_original() -> None:
    """ASSERT → CORRECT → RETRACT 이면 체인 전체가 철회되고 원본이 되살아나지 않는다."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a"),
        _fact("c2", "f2", CareerFactType.INTERVIEW_COMPLETED, "ep-a",
              op=FactOperationType.CORRECT, target="c1:fact"),
        _fact("c3", "f3", CareerFactType.INTERVIEW_COMPLETED, "ep-a",
              op=FactOperationType.RETRACT, target="c2:fact"),
    )
    opp = store.by_id["ep-a"].opportunity
    assert opp.observed_stages == ()      # 원본 APPLICATION 부활 금지
    assert opp.frontier_stage is None
    assert len(store.fact_journal) == 3   # 물리 삭제 없음


# ── #3 close 와 accepted link 정합 ─────────────────────────────────────────


def test_close_with_attached_accepted_link_is_rejected() -> None:
    """수락 링크가 걸린 Episode를 근거 없이 닫으면 dangling link가 되므로 거부한다."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.OFFER_ACCEPTED, "ep-a"),
    )
    result = reduce_career_command(
        store,
        CloseEpisodeCommand(
            command_id="c2", episode_id="ep-a", recorded_at="t", source_kind=UC,
            close_reason=CareerTransitionCloseReason.CANDIDATE_WITHDRAWAL,
        ),
    )
    assert result.status is TransitionStatus.REJECTED
    assert result.rejection_code is RejectionCode.ACCEPTED_LINK_STILL_ATTACHED
    assert result.store == store
    assert store.current_employment is not None
    assert store.current_employment.linked_accepted_episode_id == "ep-a"  # dangling 0


# ── #2 무결성 위반 분류 ────────────────────────────────────────────────────


def test_store_journal_divergence_is_global_integrity_violation() -> None:
    """journal로 설명되지 않는 store는 정상 안전 차단이 아니라 전역 무결성 결함이다."""
    orphan = CareerTransitionEpisode(
        episode_id="ep-x",
        opportunity=TrackState(track=CareerTrack.OPPORTUNITY),
        entry=TrackState(track=CareerTrack.ENTRY),
    )
    store = CareerEpisodeStore(episodes=(orphan,))  # journal 없음 — 불일치
    result = reduce_career_command(store, _create("c1", "ep-a"))
    assert result.integrity_status is IntegrityStatus.VIOLATION
    assert result.violation_scope is ViolationScope.GLOBAL
    assert result.rejection_code is RejectionCode.STORE_NOT_JOURNAL_CONSISTENT
    assert result.store == store
    obs = observe_career_transition(store, _create("c1", "ep-a"), result)
    assert obs[0].guard_outcome is GuardOutcome.VIOLATION


def test_normal_safety_block_is_not_an_integrity_violation() -> None:
    """미해소 같은 정상 안전 차단은 무결성 위반이 아니다."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"))
    result = reduce_career_command(store, _fact("c2", "f1", CareerFactType.JOINED))
    assert result.integrity_status is IntegrityStatus.OK
    assert result.violation_scope is None


# ── #6 관측: 실제 전후 상태로 판정 ─────────────────────────────────────────


def test_blocked_ownership_conflict_is_telemetry_not_violation() -> None:
    """소유권 충돌이 차단되면 collision violation이 아니라 가드 텔레메트리다."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"),
        _fact("c2", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a"),
    )
    cmd = _fact("c3", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-b")
    result, obs = run_career_shadow_transition(store, cmd)
    assert result.rejection_code is RejectionCode.FACT_OWNERSHIP_CONFLICT
    assert len(obs) == 1
    assert obs[0].guard_outcome is GuardOutcome.BLOCKED
    assert obs[0].observation_kind is ObservationKind.ROLLOUT_TELEMETRY
    assert obs[0].metric_name != METRIC_EPISODE_COLLISION      # 위반 아님


def test_idempotent_noop_is_blocked_telemetry_not_duplicate_application() -> None:
    """멱등 no-op은 duplicate_fact_application 위반이 아니다."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"))
    cmd = _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a")
    store = _apply(store, cmd)
    result, obs = run_career_shadow_transition(store, cmd)
    assert result.status is TransitionStatus.IDEMPOTENT_NOOP
    assert obs[0].guard_outcome is GuardOutcome.BLOCKED
    assert obs[0].metric_name != METRIC_DUPLICATE_FACT
    assert len(result.store.career_journal) == len(store.career_journal)  # 증가 없음


def test_applied_fact_lands_only_on_target_episode() -> None:
    """정상 적용은 의도한 Episode에만 반영되며 collision violation이 없다."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"))
    result, obs = run_career_shadow_transition(
        store, _fact("c2", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a")
    )
    assert result.status is TransitionStatus.APPLIED
    collision = [o for o in obs if o.metric_name == METRIC_EPISODE_COLLISION]
    assert collision and collision[0].guard_outcome is GuardOutcome.ALLOWED
    assert result.store.by_id["ep-b"].opportunity.observed_stages == ()


# ── #7 지표별 census 분모 ──────────────────────────────────────────────────

#: 지표별 eligible case — **공통 분모를 쓰지 않는다**(지표마다 대상 시도가 다르다).
_CENSUS: dict[str, frozenset[str]] = {
    METRIC_EPISODE_COLLISION: frozenset(
        {"blocked_ownership_conflict", "applied_fact_target_only"}
    ),
    METRIC_DUPLICATE_FACT: frozenset({"idempotent_noop"}),
    METRIC_PARTIAL_COMMIT: frozenset({"close_with_attached_link"}),
}


def test_metric_census_has_per_metric_denominators() -> None:
    """지표별 eligible/measured/excluded를 따로 보존한다."""
    scenarios = {
        "blocked_ownership_conflict": test_blocked_ownership_conflict_is_telemetry_not_violation,
        "applied_fact_target_only": test_applied_fact_lands_only_on_target_episode,
        "idempotent_noop": test_idempotent_noop_is_blocked_telemetry_not_duplicate_application,
        "close_with_attached_link": test_close_with_attached_accepted_link_is_rejected,
    }
    for metric, eligible in _CENSUS.items():
        measured = eligible & set(scenarios)
        excluded: set[str] = set()
        assert eligible, f"{metric}: eligible=0 → NO_ELIGIBLE_CASES(통과 아님)"
        assert measured == eligible - excluded, f"{metric}: 불완전 계측"
        for case in measured:
            scenarios[case]()   # 실제 실행으로 violation 0 확인
