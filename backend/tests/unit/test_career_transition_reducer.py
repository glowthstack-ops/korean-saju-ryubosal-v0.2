"""P1-b reducer 회귀 — CAREER_TRANSITION_SYSTEM §5·§13-3·§13-4.

§13 계약대로 **scenario**(다단계 정상 흐름)와 **atomic fixture**(단일 명령 거부·롤백·멱등)를
분리한다. 수치·명리 매핑이 아니라 상태·의미·소유권 불변식이 대상이다.
"""

from __future__ import annotations

import ast
from pathlib import Path

from saju_engines.career_transition_reducer import (
    command_digest,
    reduce_career_command,
    replay,
)
from saju_shared_types.career_commands import (
    ApplyCareerFactCommand,
    CareerFactSource,
    CareerFactType,
    CloseEpisodeCommand,
    CreateEpisodeCommand,
    EpisodeResolutionOutcome,
    FactEvidenceClass,
    ProjectionMode,
    RejectionCode,
    ReopenEpisodeCommand,
    ReopenReason,
    TransitionStatus,
)
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    CareerTrack,
    CareerTransitionCloseReason,
    EntryStage,
    FactOperationType,
    FactSourceRef,
    OpportunityStage,
)


def _sref(fid: str, ns: str = "chat") -> FactSourceRef:
    return FactSourceRef(source_kind="user_confirmed", source_namespace=ns, source_fact_id=fid)


def _create(cid: str, eid: str, at: str = "t0") -> CreateEpisodeCommand:
    return CreateEpisodeCommand(
        command_id=cid, episode_id=eid, recorded_at=at,
        source_kind=CareerFactSource.USER_CONFIRMED,
    )


def _fact(
    cid: str,
    fid: str,
    ftype: CareerFactType,
    episode: str | None = None,
    *,
    op: FactOperationType = FactOperationType.ASSERT,
    target_item: str | None = None,
    at: str = "t1",
    occurred: str | None = None,
    evidence: FactEvidenceClass = FactEvidenceClass.OBSERVABLE_HARD_FACT,
    ns: str = "chat",
) -> ApplyCareerFactCommand:
    return ApplyCareerFactCommand(
        command_id=cid, source_ref=_sref(fid, ns),
        source_kind=CareerFactSource.USER_CONFIRMED, evidence_class=evidence,
        operation_type=op, fact_type=ftype, recorded_at=at, occurred_at=occurred,
        target_episode_id=episode, target_history_item_id=target_item,
    )


def _apply(store: CareerEpisodeStore, *commands) -> CareerEpisodeStore:
    for c in commands:
        result = reduce_career_command(store, c)
        assert result.status in {
            TransitionStatus.APPLIED, TransitionStatus.APPLIED_NO_STATE_CHANGE
        }, f"{c.command_id} → {result.status} {result.rejection_code}"
        store = result.store
    return store


# ── Scenario: Kind별 정상 흐름 ─────────────────────────────────────────────


def test_scenario_external_move() -> None:
    """외부 이직: 지원 → 면접 → 오퍼 → 수락 → 퇴사 → 입사."""
    store = _apply(
        CareerEpisodeStore(),
        _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a"),
        _fact("c2", "f2", CareerFactType.INTERVIEW_COMPLETED, "ep-a"),
        _fact("c3", "f3", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a"),
        _fact("c4", "f4", CareerFactType.OFFER_ACCEPTED, "ep-a"),
        _fact("c5", "f5", CareerFactType.EXIT_COMPLETED, "ep-a"),
        _fact("c6", "f6", CareerFactType.JOINED, "ep-a"),
    )
    ep = store.by_id["ep-a"]
    assert ep.opportunity.frontier_stage is not None
    assert ep.opportunity.frontier_stage.stage is OpportunityStage.AGREEMENT
    assert ep.entry.frontier_stage is not None
    assert ep.entry.frontier_stage.stage is EntryStage.JOINED
    assert store.current_employment is not None  # 입사로 고용 맥락 승격
    assert replay(store.career_journal) == store


def test_scenario_job_gain_from_unemployed() -> None:
    """무직 취업: 지원 → 오퍼 → 입사. Exit 사실이 없어도 성립한다."""
    store = _apply(
        CareerEpisodeStore(),
        _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a"),
        _fact("c2", "f2", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a"),
        _fact("c3", "f3", CareerFactType.JOINED, "ep-a"),
    )
    assert store.current_employment is not None
    exit_facts = [f for f in store.fact_journal if f.track is CareerTrack.EXIT]
    assert exit_facts == []  # Exit 트랙은 관여하지 않음
    assert replay(store.career_journal) == store


def test_scenario_resignation_only() -> None:
    """퇴사 단독: 통보 → 퇴사. accepted Episode 링크 없이 고용 맥락이 종료된다."""
    store = _apply(
        CareerEpisodeStore(),
        _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.NOTICE_GIVEN, "ep-a"),
        _fact("c2", "f2", CareerFactType.EXIT_COMPLETED, "ep-a"),
    )
    assert store.current_employment is None  # 종료 — 새 고용 없음
    assert replay(store.career_journal) == store


def test_scenario_internal_transfer_does_not_end_employment() -> None:
    """내부 전보: 고용 관계를 종료로 기록하지 않는다."""
    store = _apply(
        CareerEpisodeStore(),
        _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.JOINED, "ep-a"),          # 재직 성립
        _fact("c2", "f2", CareerFactType.TRANSFER_COMPLETED, "ep-a"),
    )
    assert store.current_employment is not None  # 여전히 재직
    exit_observed = [
        f for f in store.fact_journal
        if f.track is CareerTrack.EXIT and f.fact_type == CareerFactType.EXIT_COMPLETED.value
    ]
    assert exit_observed == []


# ── Atomic: Episode lifecycle ──────────────────────────────────────────────


def test_same_source_fact_in_other_episode_is_ownership_conflict() -> None:
    """A사 사실을 B사 Episode에 넣으면 소유권 충돌 — 상태 변화 0(§13 필수 1)."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"),
        _fact("c2", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a"),
    )
    result = reduce_career_command(
        store, _fact("c3", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-b")
    )
    assert result.status is TransitionStatus.REJECTED
    assert result.rejection_code is RejectionCode.FACT_OWNERSHIP_CONFLICT
    assert result.store == store          # mutation 0
    assert result.history_delta == ()


def _closed_store(reason: CareerTransitionCloseReason) -> CareerEpisodeStore:
    """journal을 통해 닫힌 Episode 상태를 만든다(직접 구성은 journal 불일치로 거부된다)."""
    return _apply(
        CareerEpisodeStore(),
        _create("c0", "ep-a"),
        CloseEpisodeCommand(
            command_id="c-close", episode_id="ep-a", recorded_at="t",
            source_kind=CareerFactSource.USER_CONFIRMED, close_reason=reason,
        ),
    )


def test_assert_on_closed_episode_is_rejected() -> None:
    """닫힌 Episode에 일반 ASSERT는 거부한다(§13 필수 2)."""
    store = _closed_store(CareerTransitionCloseReason.POSITION_CLOSED)
    result = reduce_career_command(
        store, _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a")
    )
    assert result.status is TransitionStatus.REJECTED
    assert result.rejection_code is RejectionCode.EPISODE_CLOSED
    assert result.store == store


def test_completed_episode_is_not_reopenable() -> None:
    """완결 Episode는 구조화 근거가 있어도 재개할 수 없다(§13 추가 4)."""
    store = _closed_store(CareerTransitionCloseReason.PROBATION_FAILED)
    result = reduce_career_command(
        store,
        ReopenEpisodeCommand(
            command_id="c1", episode_id="ep-a", recorded_at="t",
            source_kind=CareerFactSource.USER_CONFIRMED,
            reopen_reason=ReopenReason.EXPLICIT_SAME_PROCESS,
        ),
    )
    assert result.status is TransitionStatus.REJECTED
    assert result.rejection_code is RejectionCode.EPISODE_NOT_REOPENABLE


def test_reopen_then_fact_is_allowed() -> None:
    """재개 가능한 사유로 명시 REOPEN한 뒤에는 사실을 적용할 수 있다(§13 필수 3)."""
    store = _closed_store(CareerTransitionCloseReason.POSITION_CLOSED)
    reopened = reduce_career_command(
        store,
        ReopenEpisodeCommand(
            command_id="c1", episode_id="ep-a", recorded_at="t",
            source_kind=CareerFactSource.USER_CONFIRMED,
            reopen_reason=ReopenReason.SAME_REQUISITION_ID, requisition_id="REQ-1",
        ),
    )
    assert reopened.status is TransitionStatus.APPLIED
    after = reduce_career_command(
        reopened.store, _fact("c2", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a")
    )
    assert after.status is TransitionStatus.APPLIED


def test_duplicate_episode_id_from_other_command_collides() -> None:
    """다른 명령이 기존 episode_id를 쓰면 충돌이다(§13 추가 3)."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"))
    result = reduce_career_command(store, _create("c1", "ep-a"))
    assert result.rejection_code is RejectionCode.EPISODE_ID_COLLISION
    assert result.store == store


def test_unresolved_episode_blocks_mutation() -> None:
    """복수 open Episode + 대상 불명 → 안전 분기, 상태 변화 0."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"))
    result = reduce_career_command(
        store, _fact("c2", "f1", CareerFactType.APPLICATION_SUBMITTED)
    )
    assert result.status is TransitionStatus.REJECTED
    assert result.rejection_code is RejectionCode.EPISODE_UNRESOLVED
    assert result.resolution is EpisodeResolutionOutcome.UNRESOLVED
    assert result.store == store


def test_unique_open_episode_auto_resolves() -> None:
    """열린 Episode가 하나뿐이면 자동 해소한다(ASSERT 한정)."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"))
    result = reduce_career_command(
        store, _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED)
    )
    assert result.status is TransitionStatus.APPLIED
    assert result.resolution is EpisodeResolutionOutcome.UNIQUE_OPEN


# ── Atomic: 사실 처리(멱등·정정·역순) ──────────────────────────────────────


def test_same_command_is_idempotent() -> None:
    """동일 명령 재수신 → no-op, journal·상태 불변."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"))
    cmd = _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a")
    first = reduce_career_command(store, cmd)
    second = reduce_career_command(first.store, cmd)
    assert second.status is TransitionStatus.IDEMPOTENT_NOOP
    assert second.store == first.store
    assert second.history_delta == ()


def test_same_command_id_different_payload_conflicts() -> None:
    """같은 command_id에 다른 payload → 충돌, 상태 변화 0(§13 추가 2)."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a"),
    )
    result = reduce_career_command(
        store, _fact("c1", "f1", CareerFactType.JOINED, "ep-a")
    )
    assert result.rejection_code is RejectionCode.COMMAND_ID_CONFLICT
    assert result.store == store


def test_late_past_fact_does_not_regress_current_state() -> None:
    """뒤늦게 도착한 과거 사실은 journal에 남되 현재 상태를 되돌리지 않는다(§13 필수 5)."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.JOINED, "ep-a", occurred="2027-05-01"),
    )
    before = store.by_id["ep-a"].entry.frontier_stage
    result = reduce_career_command(
        store,
        _fact("c2", "f2", CareerFactType.APPLICATION_SUBMITTED, "ep-a",
              at="t9", occurred="2027-01-01"),
    )
    assert result.status in {TransitionStatus.APPLIED, TransitionStatus.APPLIED_NO_STATE_CHANGE}
    assert len(result.store.fact_journal) == 2               # journal 에는 추가
    assert result.store.by_id["ep-a"].entry.frontier_stage == before  # JOINED 유지


def test_correction_target_in_other_episode_is_rejected() -> None:
    """정정 대상이 다른 Episode면 거부한다(§13 필수 6)."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"),
        _fact("c2", "f1", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a"),
    )
    result = reduce_career_command(
        store,
        _fact("c3", "f2", CareerFactType.APPLICATION_SUBMITTED, "ep-b",
              op=FactOperationType.CORRECT, target_item="c2:fact"),
    )
    assert result.status is TransitionStatus.REJECTED
    assert result.rejection_code is RejectionCode.CORRECTION_TARGET_OTHER_EPISODE
    assert result.store == store


def test_retraction_keeps_later_valid_join() -> None:
    """철회 이후에도 더 늦은 유효 JOINED가 있으면 현재 상태는 JOINED다(§13 필수 7)."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a"),
        _fact("c2", "f2", CareerFactType.JOINED, "ep-a"),
        _fact("c3", "f1", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a",
              op=FactOperationType.RETRACT, target_item="c1:fact"),
    )
    ep = store.by_id["ep-a"]
    assert ep.entry.frontier_stage is not None
    assert ep.entry.frontier_stage.stage is EntryStage.JOINED
    # 철회는 물리 삭제가 아니라 보상 이벤트로 journal에 남는다.
    assert any(f.operation_type is FactOperationType.RETRACT for f in store.fact_journal)


def test_subjective_impression_is_not_authoritative() -> None:
    """사용자가 말했어도 인상·추측은 단계 전이 자격이 없다."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"))
    result = reduce_career_command(
        store,
        _fact("c1", "f1", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a",
              evidence=FactEvidenceClass.COUNTERPARTY_SPECULATION),
    )
    assert result.rejection_code is RejectionCode.FACT_NOT_AUTHORITATIVE
    assert result.store == store


# ── Atomic: 교차 트랙·sparse ───────────────────────────────────────────────


def test_offer_accepted_does_not_advance_exit_or_entry() -> None:
    """수락은 링크만 만들고 퇴사·입사를 자동 전진시키지 않는다(§13 필수 8)."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"),
        _fact("c1", "f1", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-a"),
        _fact("c2", "f2", CareerFactType.OFFER_ACCEPTED, "ep-a"),
    )
    ep = store.by_id["ep-a"]
    assert ep.entry.frontier_stage is None                 # 입사 자동 전진 없음
    assert ep.entry.observed_stages == ()
    assert store.current_employment is not None
    assert store.current_employment.linked_accepted_episode_id == "ep-a"
    assert store.current_employment.exit_state.frontier_stage is None  # 퇴사 전진 없음


def test_direct_join_is_sparse_without_synthesised_history() -> None:
    """JOINED 직접 입력 → frontier만 전진, 중간 단계 관찰·이력 합성 0(§13 필수 4·추가 5)."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"))
    result = reduce_career_command(
        store, _fact("c1", "f1", CareerFactType.JOINED, "ep-a")
    )
    assert result.projection_mode is ProjectionMode.SPARSE_FORWARD_RECONCILIATION
    ep = result.store.by_id["ep-a"]
    assert ep.entry.frontier_stage is not None
    assert ep.entry.frontier_stage.stage is EntryStage.JOINED
    assert [o.stage.stage for o in ep.entry.observed_stages] == [EntryStage.JOINED]
    assert ep.opportunity.observed_stages == ()   # 지원·면접·오퍼는 확인된 바 없음
    assert ep.opportunity.stage_history == ()     # 중간 이력 합성 0


# ── replay · 결정론 ────────────────────────────────────────────────────────


def test_incremental_result_equals_full_replay() -> None:
    """증분 reducer 결과와 전체 replay 결과가 같아야 한다(drift 방지)."""
    store = _apply(
        CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"),
        _fact("c2", "f1", CareerFactType.APPLICATION_SUBMITTED, "ep-a"),
        _fact("c3", "f2", CareerFactType.WRITTEN_OFFER_RECEIVED, "ep-b"),
        _fact("c4", "f3", CareerFactType.JOINED, "ep-a"),
    )
    assert replay(store.career_journal) == store


def test_command_digest_is_stable_across_calls() -> None:
    """digest는 프로세스 해시가 아니라 안정 정렬 JSON에서 파생한다."""
    cmd = _fact("c1", "f1", CareerFactType.JOINED, "ep-a")
    assert command_digest(cmd) == command_digest(cmd)
    assert command_digest(cmd) != command_digest(
        _fact("c1", "f1", CareerFactType.EXIT_COMPLETED, "ep-a")
    )


def test_reducer_uses_no_nondeterministic_sources() -> None:
    """reducer가 now()·uuid4()·random·hash()를 쓰지 않는다(replay·fixture 안정성)."""
    src = (
        Path(__file__).resolve().parents[2]
        / "packages/saju_engines/saju_engines/career_transition_reducer.py"
    )
    tree = ast.parse(src.read_text(encoding="utf-8"))
    forbidden = {"now", "utcnow", "uuid4", "uuid1", "random", "shuffle", "hash"}
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in forbidden:
                hits.append(name)
    assert not hits, f"비결정 소스 사용: {sorted(set(hits))}"


def test_rejections_never_emit_journal_delta() -> None:
    """모든 거부 경로에서 journal·history delta가 비어 있다(부분 commit 금지)."""
    store = _apply(CareerEpisodeStore(), _create("c0", "ep-a"), _create("c1", "ep-b"))
    rejected = [
        reduce_career_command(store, _fact("cx", "f1", CareerFactType.JOINED)),
        reduce_career_command(store, _create("cy", "ep-a")),
        reduce_career_command(
            store,
            _fact("cz", "f1", CareerFactType.JOINED, "ep-a",
                  evidence=FactEvidenceClass.SUBJECTIVE_IMPRESSION),
        ),
    ]
    for r in rejected:
        assert r.status in {TransitionStatus.REJECTED, TransitionStatus.ROLLED_BACK}
        assert r.journal_delta == ()
        assert r.history_delta == ()
        assert r.store == store
        assert r.audit_events  # 감사 이벤트 추가는 허용
