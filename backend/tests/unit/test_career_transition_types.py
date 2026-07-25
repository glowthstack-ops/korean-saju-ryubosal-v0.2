"""커리어 전이 타입 불변식 — CAREER_TRANSITION_SYSTEM §3·§5~§9.

P0-B는 전이 로직을 구현하지 않는다. **타입이 계약을 표현할 수 있는지**와 금지된 표현이
타입 수준에서 막히는지만 검증한다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    CareerProcessMode,
    CareerStageRef,
    CareerTrack,
    CareerTransitionEpisode,
    CareerTransitionKind,
    CurrentEmploymentContext,
    EntryScope,
    EntryStage,
    ExitStage,
    FactOperationType,
    FactSourceRef,
    OpportunityStage,
    RealizationStatus,
    StageHistoryItem,
    TrackState,
)


def _track(track: CareerTrack) -> TrackState:
    return TrackState(track=track)


def _episode(episode_id: str = "ep-a") -> CareerTransitionEpisode:
    return CareerTransitionEpisode(
        episode_id=episode_id,
        opportunity=_track(CareerTrack.OPPORTUNITY),
        entry=_track(CareerTrack.ENTRY),
    )


# ── 유형·태도·질의 축 분리 (D20) ────────────────────────────────────────────


def test_transition_kind_and_intended_kind_are_nullable() -> None:
    """미확정과 실제 유형을 섞지 않기 위해 nullable이며 UNKNOWN enum이 없다."""
    ep = _episode()
    assert ep.transition_kind is None
    assert ep.intended_kind is None
    assert "UNKNOWN" not in {m.name for m in CareerTransitionKind}


def test_process_mode_does_not_own_procedure_stages() -> None:
    """오퍼 검토·협상은 OpportunityStage 소유 — 태도 enum에 중복 소유시키지 않는다."""
    modes = {m.name for m in CareerProcessMode}
    assert "OFFER_REVIEW" not in modes
    assert "NEGOTIATING" not in modes
    stages = {s.name for s in OpportunityStage}
    assert {"OFFER_REVIEW", "NEGOTIATING"} <= stages


def test_employed_job_search_is_not_a_transition_kind() -> None:
    """재직 중 탐색은 결과유형이 아니라 진행 모드다."""
    assert "EMPLOYED_JOB_SEARCH" not in {m.name for m in CareerTransitionKind}


# ── 트랙 교차 차단 (D5) ────────────────────────────────────────────────────


def test_stage_ref_rejects_cross_track_stage() -> None:
    """INTERVIEW → HANDOVER 류 트랙 교차 전이를 타입 수준에서 막는다."""
    ok = CareerStageRef(track=CareerTrack.OPPORTUNITY, stage=OpportunityStage.INTERVIEW)
    assert ok.stage is OpportunityStage.INTERVIEW
    with pytest.raises(ValidationError):
        CareerStageRef(track=CareerTrack.EXIT, stage="handover_typo")  # type: ignore[arg-type]


def test_all_three_track_stage_enums_are_disjoint() -> None:
    """세 트랙 단계 값이 겹치지 않는다 — 값만 보고 트랙을 오인할 수 없다."""
    opp = {s.value for s in OpportunityStage}
    exit_ = {s.value for s in ExitStage}
    entry = {s.value for s in EntryStage}
    assert opp & exit_ == set()
    assert opp & entry == set()
    assert exit_ & entry == set()


# ── Exit 소유권 (D4) ───────────────────────────────────────────────────────


def test_episode_has_no_exit_track() -> None:
    """Exit는 Episode에 복제하지 않는다 — 복수 지원 시 충돌하기 때문."""
    assert "exit" not in CareerTransitionEpisode.model_fields
    assert "exit_state" not in CareerTransitionEpisode.model_fields


def test_current_employment_owns_exit_and_may_link_episode() -> None:
    """Exit는 현재 고용 맥락 소유이며 수락된 Episode를 링크할 수 있다."""
    ctx = CurrentEmploymentContext(
        employment_context_id="emp-1",
        exit_state=_track(CareerTrack.EXIT),
        linked_accepted_episode_id="ep-b",
    )
    assert ctx.exit_state.track is CareerTrack.EXIT
    assert ctx.linked_accepted_episode_id == "ep-b"


def test_resignation_only_allows_no_linked_episode() -> None:
    """퇴사 단독은 연결 Episode 없이 성립한다."""
    ctx = CurrentEmploymentContext(
        employment_context_id="emp-1",
        exit_state=_track(CareerTrack.EXIT),
    )
    assert ctx.linked_accepted_episode_id is None


def test_link_change_keeps_history_instead_of_overwrite() -> None:
    """대상 변경(B사→C사)은 덮어쓰기가 아니라 이력을 남길 수 있어야 한다."""
    ctx = CurrentEmploymentContext(
        employment_context_id="emp-1",
        exit_state=_track(CareerTrack.EXIT),
        linked_accepted_episode_id="ep-c",
        linked_episode_history=("ep-b",),
    )
    assert ctx.linked_accepted_episode_id == "ep-c"
    assert "ep-b" in ctx.linked_episode_history


def test_store_holds_single_primary_employment() -> None:
    """P0는 primary employment를 하나만 관리한다(D19) — 리스트 형태가 아니다."""
    assert "current_employments" not in CareerEpisodeStore.model_fields
    store = CareerEpisodeStore(
        episodes=(_episode("ep-a"), _episode("ep-b")),
        current_employment=CurrentEmploymentContext(
            employment_context_id="emp-1",
            exit_state=_track(CareerTrack.EXIT),
        ),
    )
    assert len(store.episodes) == 2
    assert set(store.by_id) == {"ep-a", "ep-b"}
    assert store.current_employment is not None


# ── 상태 구조 (D16 · INV-15) ───────────────────────────────────────────────


def test_no_global_completed_stage_field() -> None:
    """단일 completed_stage는 재개·후퇴·반복을 표현하지 못하므로 두지 않는다."""
    for model in (TrackState, CareerTransitionEpisode, CareerEpisodeStore):
        assert "completed_stage" not in model.model_fields


def test_track_state_separates_lifecycle_reason_history() -> None:
    """단계 / lifecycle / 종료사유 / 이력이 각각 별도 필드다."""
    fields = TrackState.model_fields
    for name in (
        "frontier_stage",
        "observed_stages",
        "lifecycle_status",
        "close_reason",
        "stage_history",
        "realization_status",
    ):
        assert name in fields


def test_resolved_stage_is_not_stored_on_track_state() -> None:
    """resolved_stage는 resolver의 턴 단위 출력이지 저장 상태가 아니다(§7)."""
    assert "resolved_stage" not in TrackState.model_fields


def test_realization_status_defaults_to_not_started() -> None:
    """사실 완료는 사용자 확인으로만 올라간다 — 기본은 미시작(INV-15)."""
    assert _track(CareerTrack.ENTRY).realization_status is RealizationStatus.NOT_STARTED


# ── 사실 이력 · 멱등 (§13-4) ───────────────────────────────────────────────


def _history_item(**kw: object) -> StageHistoryItem:
    base: dict[str, object] = {
        "history_item_id": "h1",
        "track": CareerTrack.OPPORTUNITY,
        "stage": OpportunityStage.OFFER_RECEIVED,
        "source_ref": FactSourceRef(
            source_kind="user_confirmed", source_namespace="chat", source_fact_id="f1"),
        "fact_type": "offer_received",
        "operation_type": FactOperationType.ASSERT,
        "recorded_at": "2027-04-10T00:00:00Z",
    }
    base.update(kw)
    return StageHistoryItem(**base)  # type: ignore[arg-type]


def test_idempotency_key_is_not_text_based() -> None:
    """같은 문장이라도 대상 Episode가 다르면 별개 사실이다."""
    a = _history_item(target_episode_id="ep-a")
    b = _history_item(target_episode_id="ep-b")
    assert a.idempotency_key != b.idempotency_key
    assert a.idempotency_key == _history_item(target_episode_id="ep-a").idempotency_key


def test_history_supports_correction_and_retraction_as_compensating_events() -> None:
    """정정·철회는 물리 삭제가 아니라 supersede 링크를 가진 새 항목이다."""
    corrected = _history_item(
        history_item_id="h2",
        operation_type=FactOperationType.CORRECT,
        supersedes_history_item_id="h1",
    )
    assert corrected.operation_type is FactOperationType.CORRECT
    assert corrected.supersedes_history_item_id == "h1"
    assert FactOperationType.RETRACT in set(FactOperationType)


def test_occurred_at_is_separate_from_recorded_at() -> None:
    """역순 입력 정렬을 위해 발생 시점과 수신 시점을 분리한다(INV-23)."""
    item = _history_item(occurred_at="2027-03-28T00:00:00Z")
    assert item.occurred_at != item.recorded_at


# ── 불변성 ─────────────────────────────────────────────────────────────────


def test_contract_models_are_frozen() -> None:
    """계약 스냅샷은 변경 불가 — 권위 상태를 우회 수정할 수 없다."""
    store = CareerEpisodeStore()
    with pytest.raises(ValidationError):
        store.contract_version = "tampered"  # type: ignore[misc]
    ep = _episode()
    with pytest.raises(ValidationError):
        ep.episode_id = "other"  # type: ignore[misc]


def test_internal_collections_are_deeply_immutable() -> None:
    """`frozen=True`는 필드 재할당만 막는다 — 내부 컬렉션 변경도 차단해야 한다.

    Episode 목록·이력·링크 이력이 mutable이면 권위 상태를 우회 수정할 수 있다.
    """
    ep = _episode()
    store = CareerEpisodeStore(
        episodes=(ep,),
        current_employment=CurrentEmploymentContext(
            employment_context_id="emp-1",
            exit_state=_track(CareerTrack.EXIT),
            linked_episode_history=("ep-b",),
        ),
    )
    assert isinstance(store.episodes, tuple)
    assert isinstance(ep.opportunity.stage_history, tuple)
    assert store.current_employment is not None
    assert isinstance(store.current_employment.linked_episode_history, tuple)
    with pytest.raises(TypeError):
        store.episodes[0] = ep  # type: ignore[index]
    with pytest.raises(AttributeError):
        store.episodes.append(ep)  # type: ignore[attr-defined]


def test_by_id_view_is_read_only() -> None:
    """`by_id`는 읽기 전용 파생 뷰 — 여기에 써서 store를 바꿀 수 없다."""
    store = CareerEpisodeStore(episodes=(_episode("ep-a"),))
    with pytest.raises(TypeError):
        store.by_id["ep-b"] = _episode("ep-b")  # type: ignore[index]


def test_entry_scope_covers_internal_transfer() -> None:
    """내부 전보는 Exit·외부 합의 없이 Entry 트랙에 담긴다(D18)."""
    scopes = {s.name for s in EntryScope}
    assert "EXTERNAL_EMPLOYER" in scopes
    assert {"INTERNAL_ROLE", "INTERNAL_DEPARTMENT", "INTERNAL_LOCATION"} <= scopes
