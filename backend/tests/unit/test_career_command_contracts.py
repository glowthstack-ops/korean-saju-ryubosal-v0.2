"""P1-a 명령·결과 계약 회귀 — CAREER_TRANSITION_SYSTEM §5·§7·§13-3·§13-4.

reducer 구현 전에 **타입이 계약을 강제하는지**를 고정한다. 여기서 막지 못하는 것은
reducer가 런타임으로 막아야 하므로, 무엇이 타입 수준에서 이미 불가능한지 명확히 한다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from saju_shared_types.career_commands import (
    FACT_STAGE_MAPPING,
    REOPENABLE_CLOSE_REASONS,
    ApplyCareerFactCommand,
    CareerAuditEvent,
    CareerFactSource,
    CareerFactType,
    CreateEpisodeCommand,
    EpisodeResolutionOutcome,
    FactEvidenceClass,
    ProjectionMode,
    RejectionCode,
    ReopenEpisodeCommand,
    ReopenReason,
    TransitionResult,
    TransitionStatus,
    canonical_stage_for,
)
from saju_shared_types.career_transition import (
    AcceptedEpisodeSwitchedJournalItem,
    CareerEpisodeStore,
    CareerStageRef,
    CareerTrack,
    CareerTransitionEpisode,
    CurrentEmploymentContext,
    EmploymentContextSnapshot,
    EntryStage,
    EpisodeCreatedJournalItem,
    FactOperationType,
    FactSourceRef,
    JournalItemKind,
    ObservedStageState,
    OpportunityStage,
    StageHistoryItem,
    TrackState,
)


def _episode(episode_id: str = "ep-a") -> CareerTransitionEpisode:
    return CareerTransitionEpisode(
        episode_id=episode_id,
        opportunity=TrackState(track=CareerTrack.OPPORTUNITY),
        entry=TrackState(track=CareerTrack.ENTRY),
    )


def _fact(**kw: object) -> StageHistoryItem:
    base: dict[str, object] = {
        "history_item_id": "h1",
        "track": CareerTrack.OPPORTUNITY,
        "stage": OpportunityStage.OFFER_RECEIVED,
        "source_ref": FactSourceRef(
            source_kind="user_confirmed", source_namespace="chat", source_fact_id="f1"),
        "target_episode_id": "ep-a",
        "fact_type": CareerFactType.WRITTEN_OFFER_RECEIVED.value,
        "operation_type": FactOperationType.ASSERT,
        "recorded_at": "2027-04-10T00:00:00Z",
    }
    base.update(kw)
    return StageHistoryItem(**base)  # type: ignore[arg-type]


# ── 1. 명령 분리 (Episode 생명주기 ≠ 사실 적용) ─────────────────────────────


def test_fact_command_cannot_create_or_reopen_episode() -> None:
    """단계 사실 명령에는 Episode 생성·재개 수단이 없다."""
    fields = set(ApplyCareerFactCommand.model_fields)
    assert not ({"reopen_reason", "creation_reason", "target_company"} & fields)


def test_create_episode_requires_explicit_id() -> None:
    """생성은 항상 명시 id — 회사·직무가 같아도 자동 재사용하지 않는다."""
    with pytest.raises(ValidationError):
        CreateEpisodeCommand(  # type: ignore[call-arg]
            command_id="c1", recorded_at="t", source_kind=CareerFactSource.USER_CONFIRMED
        )


def test_reopen_requires_structured_reason() -> None:
    """재개는 구조화된 근거 필수 — 회사명만으로는 표현 자체가 불가능하다."""
    with pytest.raises(ValidationError):
        ReopenEpisodeCommand(  # type: ignore[call-arg]
            command_id="c1", episode_id="ep-a", recorded_at="t",
            source_kind=CareerFactSource.USER_CONFIRMED,
        )
    reasons = {r.name for r in ReopenReason}
    assert reasons == {
        "SAME_REQUISITION_ID", "EXPLICIT_SAME_PROCESS", "EXPLICIT_RESUMED_PROCESS"
    }
    assert "SAME_COMPANY_NAME_ONLY" not in reasons
    assert "LLM_INFERENCE" not in reasons


# ── 2. journal / projection 2층 ────────────────────────────────────────────


def test_store_separates_append_only_journal_from_projection() -> None:
    """저장 필드는 통합 journal 하나이고 사실 목록·투영은 파생이다.

    사실만 담는 journal로는 Episode 생성·재개·수락 링크 변경·고용 rollover를 replay할 수
    없으므로 생명주기 항목까지 하나의 순서 있는 journal에 담는다.
    """
    assert "career_journal" in CareerEpisodeStore.model_fields
    assert "fact_journal" not in CareerEpisodeStore.model_fields  # 파생 뷰
    assert "stage_history" in TrackState.model_fields
    store = CareerEpisodeStore(career_journal=(_fact(),))
    assert isinstance(store.fact_journal, tuple)
    with pytest.raises(AttributeError):
        store.career_journal.append(_fact())  # type: ignore[attr-defined]


def test_journal_can_replay_episode_lifecycle_not_only_facts() -> None:
    """생명주기 항목이 journal에 들어가 전체 store replay가 가능해야 한다."""
    created = EpisodeCreatedJournalItem(
        journal_item_id="j1", command_id="c1", episode_id="ep-a", recorded_at="t1"
    )
    switched = AcceptedEpisodeSwitchedJournalItem(
        journal_item_id="j2", command_id="c2", recorded_at="t2",
        to_episode_id="ep-c", supporting_history_item_id="h9",
    )
    store = CareerEpisodeStore(career_journal=(created, _fact(), switched))
    kinds = {i.kind for i in store.career_journal}
    assert JournalItemKind.EPISODE_CREATED in kinds
    assert JournalItemKind.ACCEPTED_EPISODE_SWITCHED in kinds
    assert len(store.fact_journal) == 1  # 사실 뷰는 사실만


def test_journal_entry_carries_occurred_and_recorded_time() -> None:
    """역순 입력 재생을 위해 발생 시점과 수신 시점을 모두 보존한다."""
    item = _fact(occurred_at="2027-03-01T00:00:00Z")
    assert item.occurred_at is not None
    assert item.recorded_at != item.occurred_at


# ── 3. 멱등 ≠ 사실 소유권 충돌 ─────────────────────────────────────────────


def test_same_fact_in_other_episode_is_not_idempotent_but_conflicting() -> None:
    """동일 source_fact_id를 다른 Episode에 넣으면 멱등 키는 달라진다.

    따라서 멱등 검사만으로는 A사 사실이 B사 Episode에 들어가는 것을 막지 못하며,
    소유권 인덱스 검사가 별도로 필요하다.
    """
    a = _fact(target_episode_id="ep-a")
    b = _fact(target_episode_id="ep-b")
    assert a.idempotency_key != b.idempotency_key          # 멱등으로는 안 걸림
    store = CareerEpisodeStore(career_journal=(a,))
    identity = ("user_confirmed", "chat", "f1")
    owner_episode, owner_track, owner_type = store.source_fact_ownership[identity]
    assert owner_episode == "ep-a"                          # 소유권 인덱스가 잡는다
    assert (owner_track, owner_type) == (CareerTrack.OPPORTUNITY, a.fact_type)


def test_ownership_index_is_read_only_derived_view() -> None:
    """소유권 인덱스는 journal 파생 읽기 전용 뷰 — 별도 mutable 상태가 아니다."""
    store = CareerEpisodeStore(career_journal=(_fact(),))
    assert "source_fact_ownership" not in CareerEpisodeStore.model_fields
    with pytest.raises(TypeError):
        store.source_fact_ownership[("k", "n", "f2")] = (  # type: ignore[index]
            "ep-b", CareerTrack.EXIT, "x")


def test_same_text_different_fact_id_stays_distinct() -> None:
    """같은 문장이라도 source_fact_id가 다르면 별개 사실이다(§13-4a)."""
    a = _fact()
    b = _fact(history_item_id="h2", source_ref=FactSourceRef(
        source_kind="user_confirmed", source_namespace="chat", source_fact_id="f2"))
    assert a.idempotency_key != b.idempotency_key


# ── 4. CORRECT · RETRACT 대상 참조 ─────────────────────────────────────────


def test_correction_and_retraction_reference_a_target_item() -> None:
    """정정·철회는 무엇을 대상으로 하는지 참조를 가질 수 있어야 한다."""
    corrected = ApplyCareerFactCommand(
        command_id="c2",
        source_ref=FactSourceRef(
            source_kind="user_confirmed", source_namespace="chat", source_fact_id="f2"),
        source_kind=CareerFactSource.USER_CONFIRMED,
        evidence_class=FactEvidenceClass.OBSERVABLE_HARD_FACT,
        operation_type=FactOperationType.CORRECT,
        fact_type=CareerFactType.WRITTEN_OFFER_RECEIVED,
        recorded_at="t", target_history_item_id="h1",
    )
    assert corrected.target_history_item_id == "h1"
    assert FactOperationType.RETRACT in set(FactOperationType)


def test_resolution_outcomes_separate_correction_owner_from_unique_open() -> None:
    """정정·철회는 대상 사실의 소유 Episode로 해소하며 unique-open 자동해소를 쓰지 않는다."""
    outcomes = {o.name for o in EpisodeResolutionOutcome}
    assert {"EXPLICIT_TARGET", "CORRECTION_TARGET_OWNER", "UNIQUE_OPEN", "UNRESOLVED"} == outcomes


# ── 5. 입력 자격 (source · evidence class · fact type) ─────────────────────


def test_forecast_and_inference_sources_do_not_exist() -> None:
    """예측·추론 출처는 값 자체가 없어 reducer 입력이 될 수 없다(INV-18)."""
    sources = {s.name for s in CareerFactSource}
    assert sources == {"USER_CONFIRMED", "EXTERNAL_CONFIRMED", "SYSTEM_MIGRATION"}
    for forbidden in ("SAJU_FORECAST", "LLM_INFERENCE", "SUBJECTIVE_COUNTERPARTY_GUESS"):
        assert forbidden not in sources


def test_evidence_class_separates_impression_from_hard_fact() -> None:
    """사용자가 말했어도 인상·추측은 단계 전이 자격이 없다."""
    classes = {c.name for c in FactEvidenceClass}
    assert {"OBSERVABLE_HARD_FACT", "SUBJECTIVE_IMPRESSION", "COUNTERPARTY_SPECULATION"} == classes


def test_fact_types_are_observable_events_only() -> None:
    """상대 의향을 뜻하는 fact type을 만들지 않는다(§8)."""
    types_ = {t.name for t in CareerFactType}
    assert "EMPLOYER_INTERESTED" not in types_
    assert {"WRITTEN_OFFER_RECEIVED", "OFFER_ACCEPTED", "JOINED", "EXIT_COMPLETED"} <= types_


def test_offer_accepted_is_distinct_from_exit_and_join() -> None:
    """한 사실이 다른 트랙의 사실 단계를 자동 생성하지 않도록 유형을 분리한다."""
    for name in ("OFFER_ACCEPTED", "NOTICE_GIVEN", "EXIT_COMPLETED", "JOINED"):
        assert name in {t.name for t in CareerFactType}


# ── 6. 고용 컨텍스트 보존 ──────────────────────────────────────────────────


def test_previous_employment_context_is_preserved() -> None:
    """새 context로 교체해도 과거 context를 잃지 않는다(단일 current는 유지)."""
    ctx = CurrentEmploymentContext(
        employment_context_id="emp-1", exit_state=TrackState(track=CareerTrack.EXIT)
    )
    store = CareerEpisodeStore(
        current_employment=CurrentEmploymentContext(
            employment_context_id="emp-2", exit_state=TrackState(track=CareerTrack.EXIT)
        ),
        employment_context_history=(
            EmploymentContextSnapshot(context=ctx, archived_at="2027-05-01T00:00:00Z"),
        ),
    )
    assert store.current_employment is not None
    assert store.current_employment.employment_context_id == "emp-2"
    assert store.employment_context_history[0].context.employment_context_id == "emp-1"


def test_internal_transfer_keeps_employment_and_adds_role_revision() -> None:
    """내부 전보는 고용 관계 종료가 아니라 역할 revision이다."""
    ctx = CurrentEmploymentContext(
        employment_context_id="emp-1",
        exit_state=TrackState(track=CareerTrack.EXIT),
        role_revisions=("team-b-lead",),
    )
    assert ctx.role_revisions == ("team-b-lead",)
    assert ctx.exit_state.current_confirmed_stage is None  # 종료로 기록되지 않음


# ── 결과 계약 ──────────────────────────────────────────────────────────────


def test_transition_status_distinguishes_noop_from_rejection() -> None:
    """적용·무변화 적용·멱등 no-op·거부·롤백을 구분한다."""
    assert {s.name for s in TransitionStatus} == {
        "APPLIED", "APPLIED_NO_STATE_CHANGE", "IDEMPOTENT_NOOP", "REJECTED", "ROLLED_BACK"
    }


def test_rollback_result_keeps_store_unchanged_but_allows_audit() -> None:
    """롤백은 권위 상태 변화 0 + 감사 이벤트만 남긴다(INV-17·INV-24)."""
    store = CareerEpisodeStore(episodes=(_episode(),))
    result = TransitionResult(
        status=TransitionStatus.ROLLED_BACK,
        store=store,
        audit_events=(CareerAuditEvent(event="TRANSACTION_ROLLED_BACK", command_id="c1"),),
        rejection_code=RejectionCode.EMPLOYMENT_CONTEXT_CONFLICT,
    )
    assert result.store == store
    assert result.history_delta == ()
    assert result.audit_events[0].event == "TRANSACTION_ROLLED_BACK"
    assert result.state_changed is False


def test_projection_mode_marks_sparse_forward_reconciliation() -> None:
    """확인된 하위 단계 사실은 허용하되 중간 단계 합성과 구분해 표시한다."""
    modes = {m.name for m in ProjectionMode}
    assert {
        "NORMAL_TRANSITION", "SPARSE_FORWARD_RECONCILIATION",
        "CORRECTION_REPROJECTION", "MIGRATION_REPLAY",
    } == modes


def test_episode_unresolved_is_a_rejection_not_a_violation_code() -> None:
    """미해소는 정상 안전 분기다 — 위반 코드와 같은 층위로 두지 않는다."""
    assert RejectionCode.EPISODE_UNRESOLVED.value == "episode_unresolved"
    assert RejectionCode.FACT_OWNERSHIP_CONFLICT.value == "fact_ownership_conflict"


# ── 3. fact_type → stage 파생 (단일 SSOT) ──────────────────────────────────


def test_stage_is_derived_from_fact_type_not_input() -> None:
    """호출자가 stage를 넣지 못하므로 유형·단계 불일치가 구조적으로 불가능하다."""
    assert "stage_ref" not in ApplyCareerFactCommand.model_fields
    cmd = ApplyCareerFactCommand(
        command_id="c1",
        source_ref=FactSourceRef(
            source_kind="user_confirmed", source_namespace="chat", source_fact_id="f1"),
        source_kind=CareerFactSource.USER_CONFIRMED,
        evidence_class=FactEvidenceClass.OBSERVABLE_HARD_FACT,
        operation_type=FactOperationType.ASSERT,
        fact_type=CareerFactType.WRITTEN_OFFER_RECEIVED,
        recorded_at="t",
    )
    assert cmd.stage_ref == canonical_stage_for(CareerFactType.WRITTEN_OFFER_RECEIVED)
    assert cmd.track is CareerTrack.OPPORTUNITY  # track 도 파생


def test_fact_stage_mapping_is_single_ssot_and_total() -> None:
    """모든 사실 유형이 canonical 단계를 가지며 매핑은 한 곳에만 있다."""
    assert set(FACT_STAGE_MAPPING) == set(CareerFactType)
    with pytest.raises(TypeError):
        FACT_STAGE_MAPPING[CareerFactType.JOINED] = None  # type: ignore[index]


def test_join_and_exit_facts_map_to_different_tracks() -> None:
    """한 사실이 다른 트랙 단계를 만들지 않도록 매핑이 트랙을 분리한다."""
    assert canonical_stage_for(CareerFactType.JOINED).track is CareerTrack.ENTRY
    assert canonical_stage_for(CareerFactType.EXIT_COMPLETED).track is CareerTrack.EXIT
    assert canonical_stage_for(CareerFactType.OFFER_ACCEPTED).track is CareerTrack.OPPORTUNITY


# ── 6. frontier ≠ observed (sparse forward) ────────────────────────────────


def test_frontier_stage_is_separate_from_observed_stages() -> None:
    """JOINED 직접 입력이 이전 단계 확인을 의미하지 않는다."""
    joined = CareerStageRef(track=CareerTrack.ENTRY, stage=EntryStage.JOINED)
    entry = TrackState(
        track=CareerTrack.ENTRY,
        frontier_stage=joined,
        observed_stages=(ObservedStageState(stage=joined, source_history_item_id="h1"),),
    )
    assert entry.frontier_stage == joined
    assert [o.stage for o in entry.observed_stages] == [joined]
    # 중간 단계는 관찰되지 않았다 — 합성 금지
    assert all(o.stage.stage is EntryStage.JOINED for o in entry.observed_stages)
    assert entry.current_confirmed_stage == joined


def test_sparse_forward_does_not_synthesise_intermediate_history() -> None:
    """중간 StageHistoryItem을 만들지 않는다(§13 필수 사례 4)."""
    joined = CareerStageRef(track=CareerTrack.ENTRY, stage=EntryStage.JOINED)
    entry = TrackState(
        track=CareerTrack.ENTRY,
        frontier_stage=joined,
        observed_stages=(ObservedStageState(stage=joined, source_history_item_id="h1"),),
        stage_history=(),
    )
    assert entry.stage_history == ()
    assert len(entry.observed_stages) == 1


# ── 재개 가능 종료 사유 · 결정적 정렬 ───────────────────────────────────────


def test_completed_join_episode_is_not_reopenable() -> None:
    """완결된 입사 Episode는 구조화 근거가 있어도 재개 대상이 아니다."""
    from saju_shared_types.career_transition import CareerTransitionCloseReason

    assert CareerTransitionCloseReason.POSITION_CLOSED in REOPENABLE_CLOSE_REASONS
    for blocked in (
        CareerTransitionCloseReason.PROBATION_FAILED,
        CareerTransitionCloseReason.OTHER_OFFER_CHOSEN,
        CareerTransitionCloseReason.EARLY_EXIT,
    ):
        assert blocked not in REOPENABLE_CLOSE_REASONS


def test_journal_sort_key_is_deterministic() -> None:
    """정렬 tie-break는 occurred_at → recorded_at → journal item id로 고정한다."""
    a = _fact(history_item_id="h1", occurred_at="2027-01-01T00:00:00Z")
    b = _fact(history_item_id="h2", occurred_at="2027-01-01T00:00:00Z")
    assert a.sort_key < b.sort_key
    assert a.sort_key[0] == "2027-01-01T00:00:00Z"


def test_rejection_codes_separate_input_refusal_from_rollback() -> None:
    """일반 거부와 원자 transaction 롤백을 다른 코드로 구분한다."""
    codes = {c.name for c in RejectionCode}
    assert {"EPISODE_UNRESOLVED", "FACT_NOT_AUTHORITATIVE", "FACT_OWNERSHIP_CONFLICT"} <= codes
    assert {"COMMAND_ID_CONFLICT", "EPISODE_ID_COLLISION", "EPISODE_NOT_REOPENABLE"} <= codes
    assert "EMPLOYMENT_CONTEXT_CONFLICT" in codes  # ROLLED_BACK 후보
