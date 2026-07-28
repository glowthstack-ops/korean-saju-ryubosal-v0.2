"""커리어 Episode → 중립 진행사실 스냅샷 변환기 (P2-3a).

```
CareerEpisodeStore (커리어 도메인)
  → build_career_process_snapshots()      ← 이 모듈
  → CareerProcessSnapshot (중립 DTO)
  → adapt_career_snapshot()               ← process_fact_resolver
  → ProcessFact
```

**이 모듈만 커리어 타입을 본다.** 엔진 점수 경로가 커리어 모듈을 import하지 못하게
막는 `test_career_shadow_drift` 규약을 유지하기 위해, 변환은 여기서 끝내고 이후 계층에는
중립 모델만 흘린다. 소비 배선 지점은 `chat_service`·`report_service`뿐이다.

감사에서 확정된 원칙 세 가지(REVIEW_P2_WIRING_AUDIT §5·§6):

1. **`frontier_stage`를 쓰지 않는다.** 진행 위치는 미관찰 단계까지 전진할 수 있어
   현실 근거가 아니다. `observed_stages[-1]`(= `current_confirmed_stage`)만 쓴다.
2. **`evidence_class` 필드를 찾지 않는다.** 그 게이트는 command 레벨(reducer 진입부)에서
   적용되고 저장되지 않는다 — `observed_stages`에 있다는 것 자체가 통과 증거다.
3. **단계 이름만으로 active를 판단하지 않는다.** lifecycle·close_reason·outcome·
   realization이 종료를 말하면 terminal 단계로 덮어쓴다.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from saju_shared_types.career_transition import (
    CareerEpisodeOutcome,
    CareerEpisodeStore,
    CareerStageRef,
    CareerTrack,
    CareerTransitionCloseReason,
    CareerTransitionEpisode,
    EntryStage,
    ExitStage,
    OpportunityStage,
    RealizationStatus,
    TrackLifecycleStatus,
    TrackState,
)
from saju_shared_types.process_fact import (
    TERMINAL_STAGES,
    CareerEntryScope,
    CareerProcessSnapshot,
    ProcessFamily,
    ProcessStage,
)

#: 트랙 → 중립 family. 3트랙이 그대로 3 family에 대응한다.
_TRACK_FAMILY: Mapping[CareerTrack, ProcessFamily] = MappingProxyType({
    CareerTrack.OPPORTUNITY: ProcessFamily.CAREER_OPPORTUNITY,
    CareerTrack.EXIT: ProcessFamily.CAREER_EXIT,
    CareerTrack.ENTRY: ProcessFamily.CAREER_ENTRY,
})

#: 관찰 단계 → 중립 단계. **`FACT_STAGE_MAPPING`이 실제로 만들어 낼 수 있는 7개만**
#: 담는다(fact type 8종 → JOINED/TRANSFER_COMPLETED가 같은 단계로 합류).
#:
#: 나머지 13개 단계는 타입 레이어 예약값이며 producer가 없다. 여기 넣으면 "언젠가
#: 생길 값"에 대한 추측 매핑이 되므로 **의도적으로 비운다**(미지 단계는 fail-closed).
#:
#: | 커리어 단계 | 중립 단계 | 근거 |
#: |---|---|---|
#: | OPPORTUNITY.APPLICATION | APPLIED | 지원 제출 |
#: | OPPORTUNITY.INTERVIEW | RESULT_PENDING | `INTERVIEW_COMPLETED`는 면접 **완료** 사실 |
#: | OPPORTUNITY.OFFER_RECEIVED | IN_REVIEW | 회사 제안 존재·본인 수락 미확인 |
#: | OPPORTUNITY.AGREEMENT | APPROVED | 합의 성립(입사 전이라 terminal 아님) |
#: | EXIT.NOTICE_GIVEN | NOTICE_GIVEN | 사직 통보 |
#: | EXIT.EXITED | COMPLETED | 퇴사 완료 |
#: | ENTRY.JOINED | COMPLETED | 입사·전보 완료(온보딩 진행은 추정하지 않음) |
_OBSERVED_STAGE_MAP: Mapping[tuple[CareerTrack, str], ProcessStage] = MappingProxyType({
    (CareerTrack.OPPORTUNITY, OpportunityStage.APPLICATION.value): ProcessStage.APPLIED,
    (CareerTrack.OPPORTUNITY, OpportunityStage.INTERVIEW.value):
        ProcessStage.RESULT_PENDING,
    (CareerTrack.OPPORTUNITY, OpportunityStage.OFFER_RECEIVED.value):
        ProcessStage.IN_REVIEW,
    (CareerTrack.OPPORTUNITY, OpportunityStage.AGREEMENT.value): ProcessStage.APPROVED,
    (CareerTrack.EXIT, ExitStage.NOTICE_GIVEN.value): ProcessStage.NOTICE_GIVEN,
    (CareerTrack.EXIT, ExitStage.EXITED.value): ProcessStage.COMPLETED,
    (CareerTrack.ENTRY, EntryStage.JOINED.value): ProcessStage.COMPLETED,
})

#: 종료 사유 → terminal 단계. **모든 사유를 명시한다** — 빠진 사유가 active로 남으면
#: 닫힌 Episode가 예외를 여는 오귀속이 된다.
_CLOSE_REASON_STAGE: Mapping[CareerTransitionCloseReason, ProcessStage] = (
    MappingProxyType({
        # 상대가 거절 — 사건이 성립하지 않았다.
        CareerTransitionCloseReason.SCREENING_REJECTED: ProcessStage.REJECTED,
        CareerTransitionCloseReason.INTERVIEW_REJECTED: ProcessStage.REJECTED,
        CareerTransitionCloseReason.PROBATION_FAILED: ProcessStage.REJECTED,
        # 상대가 거둬들임 — 본인 의사와 무관하게 기회가 사라졌다.
        CareerTransitionCloseReason.POSITION_CLOSED: ProcessStage.CANCELLED,
        CareerTransitionCloseReason.OFFER_WITHDRAWN: ProcessStage.CANCELLED,
        CareerTransitionCloseReason.AGREEMENT_FAILED: ProcessStage.CANCELLED,
        # 본인이 다른 선택 — 기회를 포기했다.
        CareerTransitionCloseReason.CANDIDATE_WITHDRAWAL: ProcessStage.ABANDONED,
        CareerTransitionCloseReason.OTHER_OFFER_CHOSEN: ProcessStage.ABANDONED,
        CareerTransitionCloseReason.COUNTEROFFER_ACCEPTED: ProcessStage.ABANDONED,
        # 정상 종료 — 사건이 실제로 일어났다.
        CareerTransitionCloseReason.VOLUNTARY_EXIT: ProcessStage.COMPLETED,
        CareerTransitionCloseReason.EMPLOYER_INITIATED_EXIT: ProcessStage.COMPLETED,
        CareerTransitionCloseReason.EARLY_EXIT: ProcessStage.COMPLETED,
    })
)

#: 해석할 수 없는 종료(사유 없음·신규 enum 값)의 안전 착지점. 세부는 잃더라도
#: **active로 남기지 않는다** — 열려 있는 것으로 오독하는 쪽이 훨씬 위험하다.
_UNINTERPRETED_TERMINAL: ProcessStage = ProcessStage.CANCELLED


def _neutral_entry_scope(episode: CareerTransitionEpisode) -> CareerEntryScope | None:
    """Episode의 진입 범위를 중립 enum으로 옮긴다(값 동일 — 무손실).

    Args:
        episode: 대상 Episode.

    Returns:
        `entry_scope`가 없으면 None. **None은 "외부 이직"이 아니라 "판정 자료 없음"**
        이며, 하류에서 `ENTRY_SCOPE_UNAVAILABLE` → coverage bypass로 처리된다(F1).
    """
    if episode.entry_scope is None:
        return None
    return CareerEntryScope(episode.entry_scope.value)


def _terminal_override(
    track_state: TrackState, outcome: CareerEpisodeOutcome | None
) -> ProcessStage | None:
    """lifecycle·사유·결과·실현 상태가 종료를 말하는가 — 말하면 terminal 단계.

    단계 이름만 보면 `OFFER_RECEIVED`(=IN_REVIEW)인 Episode가 이미 닫혀 있어도 active로
    남는다. 그 오귀속을 막는 것이 이 함수의 유일한 목적이다.

    Args:
        track_state: 대상 트랙 상태.
        outcome: Episode lifecycle 결말(Exit 트랙은 None).

    Returns:
        종료면 terminal `ProcessStage`, 진행 중이면 None.
    """
    if track_state.lifecycle_status is TrackLifecycleStatus.CLOSED:
        if track_state.close_reason is None:
            return _UNINTERPRETED_TERMINAL
        return _CLOSE_REASON_STAGE.get(track_state.close_reason, _UNINTERPRETED_TERMINAL)
    if track_state.realization_status is RealizationStatus.COMPLETED:
        return ProcessStage.COMPLETED
    if track_state.realization_status is RealizationStatus.CLOSED_UNREALIZED:
        return _UNINTERPRETED_TERMINAL
    if outcome is CareerEpisodeOutcome.REALIZED:
        return ProcessStage.COMPLETED
    if outcome is CareerEpisodeOutcome.CLOSED_UNREALIZED:
        return _UNINTERPRETED_TERMINAL
    if outcome is CareerEpisodeOutcome.SUPERSEDED:
        return ProcessStage.ABANDONED
    return None


def _confirmed_stage(track_state: TrackState) -> CareerStageRef | None:
    """확인된 최고 단계 — `frontier_stage`가 아니라 관찰 사실만.

    Args:
        track_state: 대상 트랙 상태.

    Returns:
        관찰된 단계가 없으면 None(스냅샷을 만들지 않는다).
    """
    return track_state.current_confirmed_stage


def _snapshot_for_track(
    track_state: TrackState,
    *,
    instance_key: str,
    subject_id: str | None,
    entry_scope: CareerEntryScope | None,
    outcome: CareerEpisodeOutcome | None,
    source_turn: int | None,
    source_order: int,
) -> CareerProcessSnapshot | None:
    """트랙 하나 → 스냅샷 하나. 관찰 단계가 없거나 매핑이 없으면 None.

    Args:
        track_state: 대상 트랙 상태.
        instance_key: 인스턴스 식별자(Episode는 `episode_id`, Exit는
            `employment_context_id`) — 서로 다른 건이 섞이지 않게 하는 축이다.
        subject_id: 확정된 주체.
        entry_scope: 진입 범위(Exit 트랙은 None — 규칙이 scope를 요구하지 않는다).
        outcome: Episode lifecycle 결말.
        source_turn: 사실이 관찰된 턴.
        source_order: 같은 턴 내 결정적 정렬용 순번.

    Returns:
        변환된 스냅샷 또는 None.
    """
    ref = _confirmed_stage(track_state)
    if ref is None:
        return None
    base = _OBSERVED_STAGE_MAP.get((ref.track, str(ref.stage.value)))
    if base is None:
        # producer가 없는 예약 단계 — 추측 매핑하지 않는다(fail-closed).
        return None
    stage = _terminal_override(track_state, outcome) or base
    return CareerProcessSnapshot(
        episode_id=instance_key,
        subject_id=subject_id,
        process_family=_TRACK_FAMILY[ref.track],
        stage=stage,
        entry_scope=entry_scope,
        # `observed_stages`에 있다 = reducer의 OBSERVABLE_HARD_FACT 게이트를 통과했다.
        observable_hard_fact=True,
        current=stage not in TERMINAL_STAGES,
        source_turn=source_turn,
        source_order=source_order,
        original_text=f"{ref.track.value}:{ref.stage.value}",
    )


def build_career_process_snapshots(
    store: CareerEpisodeStore,
    *,
    subject_id: str | None,
    source_turn: int | None = None,
) -> tuple[CareerProcessSnapshot, ...]:
    """저장소 aggregate → 중립 스냅샷 목록.

    **두 원천을 합친다** — Episode는 Exit 트랙을 갖지 않기 때문이다(D4). Episode만
    순회하면 "퇴사 통보"가 통째로 사라진다(감사 F2).

    ```
    episodes[]  ├─ opportunity  → CAREER_OPPORTUNITY
                └─ entry        → CAREER_ENTRY
    current_employment.exit_state → CAREER_EXIT
    ```

    `employment_context_history`(보관된 과거 고용 맥락)는 **포함하지 않는다.** 현재 사건의
    예외를 여는 데 필요하지 않고, 과거 맥락이 현재 진행과 섞이면 supersession 범위가
    불필요하게 넓어진다. 필요해지면 `current=False`인 감사 전용 스냅샷으로 따로 넣는다.

    Args:
        store: replay된 커리어 저장소 aggregate.
        subject_id: 서버가 확정한 주체 — 발화에서 추측한 이름을 넣지 않는다.
        source_turn: 사실이 관찰된 턴 번호.

    Returns:
        결정적 순서(Episode 순 → opportunity·entry → Exit)의 스냅샷 목록.
    """
    snapshots: list[CareerProcessSnapshot] = []
    order = 0
    for episode in store.episodes:
        scope = _neutral_entry_scope(episode)
        for track_state in (episode.opportunity, episode.entry):
            snapshot = _snapshot_for_track(
                track_state,
                instance_key=episode.episode_id,
                subject_id=subject_id,
                entry_scope=scope,
                outcome=episode.outcome,
                source_turn=source_turn,
                source_order=order,
            )
            order += 1
            if snapshot is not None:
                snapshots.append(snapshot)
    employment = store.current_employment
    if employment is not None:
        snapshot = _snapshot_for_track(
            employment.exit_state,
            # Exit의 인스턴스는 Episode가 아니라 고용 맥락이다.
            instance_key=employment.employment_context_id,
            subject_id=subject_id,
            entry_scope=None,
            outcome=None,
            source_turn=source_turn,
            source_order=order,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)


__all__ = [
    "build_career_process_snapshots",
]
