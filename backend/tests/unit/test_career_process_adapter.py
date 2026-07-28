"""커리어 Episode → 중립 스냅샷 변환 (P2-3a).

실제 DTO로 검증한다 — 덕타이핑 스텁은 배선 단절을 잡지 못한다(감사에서 3회 재발).
"""

from __future__ import annotations

import pytest

from saju_engines.career_process_adapter import build_career_process_snapshots
from saju_shared_types.career_transition import (
    CareerEpisodeOutcome,
    CareerEpisodeStore,
    CareerStageRef,
    CareerTrack,
    CareerTransitionCloseReason,
    CareerTransitionEpisode,
    CurrentEmploymentContext,
    EntryScope,
    EntryStage,
    ExitStage,
    ObservedStageState,
    OpportunityStage,
    TrackLifecycleStatus,
    TrackState,
)
from saju_shared_types.process_fact import (
    TERMINAL_STAGES,
    CareerEntryScope,
    ProcessFamily,
    ProcessStage,
)


def _track(
    track: CareerTrack,
    stage=None,
    *,
    frontier=None,
    lifecycle: TrackLifecycleStatus = TrackLifecycleStatus.OPEN,
    close_reason: CareerTransitionCloseReason | None = None,
) -> TrackState:
    """관찰 단계·frontier·lifecycle을 따로 지정할 수 있는 트랙 상태."""
    observed = ()
    if stage is not None:
        observed = (
            ObservedStageState(
                stage=CareerStageRef(track=track, stage=stage),
                source_history_item_id="h1",
            ),
        )
    return TrackState(
        track=track,
        frontier_stage=(
            CareerStageRef(track=track, stage=frontier) if frontier else None
        ),
        observed_stages=observed,
        lifecycle_status=lifecycle,
        close_reason=close_reason,
    )


def _episode(
    *,
    episode_id: str = "ep1",
    opportunity: TrackState | None = None,
    entry: TrackState | None = None,
    entry_scope: EntryScope | None = None,
    outcome: CareerEpisodeOutcome | None = None,
) -> CareerTransitionEpisode:
    return CareerTransitionEpisode(
        episode_id=episode_id,
        opportunity=opportunity or _track(CareerTrack.OPPORTUNITY),
        entry=entry or _track(CareerTrack.ENTRY),
        entry_scope=entry_scope,
        outcome=outcome,
    )


# ── 단계 매핑 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("track", "stage", "expected"),
    [
        (CareerTrack.OPPORTUNITY, OpportunityStage.APPLICATION, ProcessStage.APPLIED),
        (
            CareerTrack.OPPORTUNITY,
            OpportunityStage.INTERVIEW,
            ProcessStage.RESULT_PENDING,
        ),
        (
            CareerTrack.OPPORTUNITY,
            OpportunityStage.OFFER_RECEIVED,
            ProcessStage.IN_REVIEW,
        ),
        (CareerTrack.OPPORTUNITY, OpportunityStage.AGREEMENT, ProcessStage.APPROVED),
        (CareerTrack.ENTRY, EntryStage.JOINED, ProcessStage.COMPLETED),
    ],
)
def test_confirmed_stage_maps_to_neutral_stage(track, stage, expected) -> None:
    """확정된 변환표대로 매핑된다."""
    kwargs = {"opportunity" if track is CareerTrack.OPPORTUNITY else "entry": _track(
        track, stage
    )}
    store = CareerEpisodeStore(episodes=(_episode(**kwargs),))

    snapshots = build_career_process_snapshots(store, subject_id="self")

    assert [s.stage for s in snapshots] == [expected]


def test_interview_completed_is_result_pending_not_interviewing() -> None:
    """면접 **완료** 사실이므로 진행 중(INTERVIEWING)이 아니다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(CareerTrack.OPPORTUNITY, OpportunityStage.INTERVIEW)
            ),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.stage is ProcessStage.RESULT_PENDING
    assert snapshot.stage is not ProcessStage.INTERVIEWING


def test_joined_does_not_become_onboarding() -> None:
    """입사 완료에서 온보딩 진행을 추정하지 않는다 — 별도 관찰 사실이 필요하다."""
    store = CareerEpisodeStore(
        episodes=(_episode(entry=_track(CareerTrack.ENTRY, EntryStage.JOINED)),)
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.stage is ProcessStage.COMPLETED
    assert snapshot.current is False


def test_unreachable_stage_is_fail_closed() -> None:
    """producer가 없는 예약 단계는 추측 매핑하지 않는다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(CareerTrack.OPPORTUNITY, OpportunityStage.SCREENING)
            ),
        )
    )

    assert build_career_process_snapshots(store, subject_id="self") == ()


# ── frontier 금지 ──────────────────────────────────────────────────────────


def test_frontier_stage_alone_produces_no_snapshot() -> None:
    """`frontier_stage`만 있고 관찰 사실이 없으면 진행 사실이 아니다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(
                    CareerTrack.OPPORTUNITY, None, frontier=OpportunityStage.AGREEMENT
                )
            ),
        )
    )

    assert build_career_process_snapshots(store, subject_id="self") == ()


def test_frontier_ahead_of_observed_uses_observed() -> None:
    """frontier가 앞서 있어도 확인된 단계만 쓴다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(
                    CareerTrack.OPPORTUNITY,
                    OpportunityStage.APPLICATION,
                    frontier=OpportunityStage.AGREEMENT,
                )
            ),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.stage is ProcessStage.APPLIED


# ── lifecycle terminal override ────────────────────────────────────────────


def test_closed_episode_does_not_stay_active() -> None:
    """단계 이름이 active여도 lifecycle이 닫혔으면 terminal이다(감사 핵심 불변식)."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(
                    CareerTrack.OPPORTUNITY,
                    OpportunityStage.OFFER_RECEIVED,
                    lifecycle=TrackLifecycleStatus.CLOSED,
                    close_reason=CareerTransitionCloseReason.OTHER_OFFER_CHOSEN,
                )
            ),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.stage is ProcessStage.ABANDONED
    assert snapshot.stage in TERMINAL_STAGES
    assert snapshot.current is False


def test_closed_without_reason_still_closes() -> None:
    """해석할 수 없는 종료도 active로 남기지 않는다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(
                    CareerTrack.OPPORTUNITY,
                    OpportunityStage.INTERVIEW,
                    lifecycle=TrackLifecycleStatus.CLOSED,
                )
            ),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.stage in TERMINAL_STAGES


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (CareerTransitionCloseReason.INTERVIEW_REJECTED, ProcessStage.REJECTED),
        (CareerTransitionCloseReason.SCREENING_REJECTED, ProcessStage.REJECTED),
        (CareerTransitionCloseReason.CANDIDATE_WITHDRAWAL, ProcessStage.ABANDONED),
        (CareerTransitionCloseReason.POSITION_CLOSED, ProcessStage.CANCELLED),
        (CareerTransitionCloseReason.VOLUNTARY_EXIT, ProcessStage.COMPLETED),
    ],
)
def test_close_reason_maps_to_distinct_terminal(reason, expected) -> None:
    """거절·철회·소멸·정상 종료를 하나로 뭉개지 않는다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(
                    CareerTrack.OPPORTUNITY,
                    OpportunityStage.INTERVIEW,
                    lifecycle=TrackLifecycleStatus.CLOSED,
                    close_reason=reason,
                )
            ),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.stage is expected


def test_every_close_reason_is_mapped() -> None:
    """종료 사유가 늘어나면 이 테스트가 먼저 깨진다(누락 = active 오귀속)."""
    from saju_engines.career_process_adapter import _CLOSE_REASON_STAGE

    missing = set(CareerTransitionCloseReason) - set(_CLOSE_REASON_STAGE)
    assert not missing, f"미매핑 종료 사유: {sorted(m.value for m in missing)}"


# ── F2: Exit 트랙 ──────────────────────────────────────────────────────────


def test_exit_state_is_included_from_employment_context() -> None:
    """Episode는 Exit 트랙을 갖지 않는다 — 고용 맥락에서 가져와야 한다(F2)."""
    store = CareerEpisodeStore(
        current_employment=CurrentEmploymentContext(
            employment_context_id="emp1",
            exit_state=_track(CareerTrack.EXIT, ExitStage.NOTICE_GIVEN),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.process_family is ProcessFamily.CAREER_EXIT
    assert snapshot.stage is ProcessStage.NOTICE_GIVEN
    assert snapshot.episode_id == "emp1"  # employment_context_id 를 인스턴스 키로
    assert snapshot.current is True


def test_exit_completed_is_terminal() -> None:
    store = CareerEpisodeStore(
        current_employment=CurrentEmploymentContext(
            employment_context_id="emp1",
            exit_state=_track(CareerTrack.EXIT, ExitStage.EXITED),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.stage is ProcessStage.COMPLETED
    assert snapshot.current is False


def test_employment_history_is_excluded() -> None:
    """보관된 과거 고용 맥락은 초기 게이트 입력에 넣지 않는다."""
    from saju_shared_types.career_transition import EmploymentContextSnapshot

    store = CareerEpisodeStore(
        employment_context_history=(
            EmploymentContextSnapshot(
                context=CurrentEmploymentContext(
                    employment_context_id="old",
                    exit_state=_track(CareerTrack.EXIT, ExitStage.NOTICE_GIVEN),
                ),
                archived_at="2026-01-01T00:00:00Z",
            ),
        )
    )

    assert build_career_process_snapshots(store, subject_id="self") == ()


# ── entry_scope (F1) ───────────────────────────────────────────────────────


def test_entry_scope_is_preserved_losslessly() -> None:
    """4개 값을 합치지 않는다 — 승진과 전보가 섞이면 오귀속이다."""
    for scope in EntryScope:
        store = CareerEpisodeStore(
            episodes=(
                _episode(
                    opportunity=_track(
                        CareerTrack.OPPORTUNITY, OpportunityStage.INTERVIEW
                    ),
                    entry_scope=scope,
                ),
            )
        )

        (snapshot,) = build_career_process_snapshots(store, subject_id="self")

        assert snapshot.entry_scope is CareerEntryScope(scope.value)


def test_missing_entry_scope_is_none_not_defaulted() -> None:
    """producer 부재를 '외부 이직'으로 기본값 처리하지 않는다(F1)."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(CareerTrack.OPPORTUNITY, OpportunityStage.INTERVIEW)
            ),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="self")

    assert snapshot.entry_scope is None


# ── 인스턴스 분리·결정성 ────────────────────────────────────────────────────


def test_multiple_episodes_keep_distinct_instance_keys() -> None:
    """복수 지원이 하나로 합쳐지지 않는다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                episode_id="epA",
                opportunity=_track(CareerTrack.OPPORTUNITY, OpportunityStage.INTERVIEW),
            ),
            _episode(
                episode_id="epB",
                opportunity=_track(
                    CareerTrack.OPPORTUNITY, OpportunityStage.APPLICATION
                ),
            ),
        )
    )

    snapshots = build_career_process_snapshots(store, subject_id="self")

    assert [s.episode_id for s in snapshots] == ["epA", "epB"]
    assert [s.stage for s in snapshots] == [
        ProcessStage.RESULT_PENDING,
        ProcessStage.APPLIED,
    ]


def test_order_is_deterministic() -> None:
    """같은 입력은 항상 같은 순서 — 감사 비교의 전제."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                episode_id="epA",
                opportunity=_track(CareerTrack.OPPORTUNITY, OpportunityStage.INTERVIEW),
                entry=_track(CareerTrack.ENTRY, EntryStage.JOINED),
            ),
        ),
        current_employment=CurrentEmploymentContext(
            employment_context_id="emp1",
            exit_state=_track(CareerTrack.EXIT, ExitStage.NOTICE_GIVEN),
        ),
    )

    first = build_career_process_snapshots(store, subject_id="self")
    second = build_career_process_snapshots(store, subject_id="self")

    assert first == second
    assert [s.process_family for s in first] == [
        ProcessFamily.CAREER_OPPORTUNITY,
        ProcessFamily.CAREER_ENTRY,
        ProcessFamily.CAREER_EXIT,
    ]


def test_subject_id_is_propagated_not_guessed() -> None:
    """주체는 서버가 확정한 값만 들어간다."""
    store = CareerEpisodeStore(
        episodes=(
            _episode(
                opportunity=_track(CareerTrack.OPPORTUNITY, OpportunityStage.INTERVIEW)
            ),
        )
    )

    (snapshot,) = build_career_process_snapshots(store, subject_id="companion-3")

    assert snapshot.subject_id == "companion-3"


def test_empty_store_yields_no_snapshots() -> None:
    """빈 저장소는 빈 목록 — 예외를 던지지 않는다."""
    assert build_career_process_snapshots(CareerEpisodeStore(), subject_id="self") == ()
