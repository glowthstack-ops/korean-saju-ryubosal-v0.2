"""환원 상태 전이 적용기 (P1-c1a, 2026-08-01).

**환원은 사건이지 상태가 아니다.** 환원이 일어난 뒤 亥의 현재 오행은 이미 水다.
`TRANSFORMATION_REVERSED` 는 "지금 무엇인가" 가 아니라 "어떻게 지금 상태가 되었는가" 를
가리키므로, 결과 상태(`ORIGINAL` + 원래 오행)와 전이 기록을 분리한다. 상태 enum 에 환원을
새로 넣지 않는 이유가 이것이다 — 넣으면 다음 층이 그 값을 현재 정체성으로 읽는다.

    transition     TRANSFORMATION_REVERSED  木 → 水
    결과 상태       ORIGINAL                 resolved = original = 水

**후보를 그대로 믿지 않는다.** 후보는 다른 snapshot 에 잘못 적용될 수 있으므로 적용 시점에
출처와 전제를 다시 검증한다. 불일치는 조용히 넘기지 않고 분류된 사유로 기각한다.

적용 범위는 **직접 충을 받은 노드 하나**다. 관계가 교란됐다고 참여 지지 전부를 원래 오행으로
돌리지 않는다. 다만 그 관계 하나만을 근거로 확정돼 있던 비직접 노드를 계속 확정으로 두면
원장 내부가 모순되므로, 근거를 지운 뒤 남은 근거로 재평가한다(자동 환원은 하지 않는다).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .relation_reversal import EvidencePath, ReversalCandidate
from .relation_state_chain import RelationStateFrame
from .relation_state_snapshot import (
    ElementResolutionState,
    RelationStateSnapshot,
    ResolutionStatus,
    compute_snapshot_id,
)


class TransitionType(StrEnum):
    """무슨 일이 일어났는가 — 현재 상태가 아니라 전이다."""

    TRANSFORMATION_REVERSED = "transformation_reversed"
    RELATION_DISRUPTED = "relation_disrupted"


class TransitionRejectionReason(StrEnum):
    """적용 기각 사유. 후보 생성 실패와 적용 거부를 구분한다."""

    STALE_REVERSAL_CANDIDATE = "STALE_REVERSAL_CANDIDATE"
    SOURCE_SNAPSHOT_MISMATCH = "SOURCE_SNAPSHOT_MISMATCH"
    GRAPH_FINGERPRINT_MISMATCH = "GRAPH_FINGERPRINT_MISMATCH"
    PREVIOUS_STATE_MISMATCH = "PREVIOUS_STATE_MISMATCH"
    AFFECTING_RELATION_MISSING = "AFFECTING_RELATION_MISSING"
    CURRENT_CONFIRMED_TRANSFORM_CONFLICT = "CURRENT_CONFIRMED_TRANSFORM_CONFLICT"
    MULTIPLE_REVERSAL_CANDIDATES_FOR_NODE = "MULTIPLE_REVERSAL_CANDIDATES_FOR_NODE"


@dataclass(frozen=True)
class RelationStateTransition:
    """전이 1건. 결과 상태와 별도로 보존한다."""

    transition_id: str
    transition_type: TransitionType
    node_id: str
    previous_status: ResolutionStatus
    resulting_status: ResolutionStatus
    original_element: str
    from_element: str
    to_element: str
    governing_relation_ids: tuple[str, ...]
    affecting_relation_ids: tuple[str, ...]
    evidence_path: EvidencePath
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class TransitionApplicationRejection:
    """적용 기각 1건."""

    candidate_id: str
    node_id: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class TransitionApplicationResult:
    """적용 결과. 입력 snapshot 은 건드리지 않는다."""

    base_snapshot_id: str
    result_snapshot: RelationStateSnapshot
    applied_transitions: tuple[RelationStateTransition, ...]
    rejected_candidates: tuple[TransitionApplicationRejection, ...]


def _sort_key(candidate: ReversalCandidate) -> tuple[str, str, str]:
    """결정적 정렬 — 입력 순서가 결과를 바꾸면 안 된다."""
    return (candidate.node_id, candidate.candidate_id, candidate.cause_relation_id)


def _confirmed_targets_now(
    frame: RelationStateFrame, node_id: str, exclude: frozenset[str] = frozenset(),
) -> set[str]:
    """현재 그래프에서 이 노드를 확정 변환시키는 target 들.

    `exclude` 에는 **지금 깨지는 관계**를 넣는다. 그걸 빼지 않으면 교란 대상인 삼합 자신이
    "현재도 확정 변환 중" 으로 잡혀 모든 정상 환원이 막힌다(실측). 충돌은 어디까지나 **다른**
    관계가 같은 노드를 다시 변환시킬 때의 이야기다.
    """
    return {
        e.target_element for e in frame.graph.edges
        if e.relation_id not in exclude
        and node_id in e.member_node_ids
        and e.existing_tier == "confirmed"
        and e.existing_mode == "transform"
        and e.target_element
        and e.normalized_observation.get("position_binding") != "unconfirmed"
    }


def _validate(
    candidate: ReversalCandidate,
    previous_frame: RelationStateFrame,
    current_frame: RelationStateFrame,
) -> tuple[str, ...]:
    """적용 전제 재검증. 사유 목록이 비어 있으면 적용 가능하다."""
    reasons: list[str] = []
    if candidate.previous_snapshot_id != previous_frame.snapshot.snapshot_id:
        reasons.append(TransitionRejectionReason.SOURCE_SNAPSHOT_MISMATCH.value)
    if candidate.current_snapshot_id != current_frame.snapshot.snapshot_id:
        reasons.append(TransitionRejectionReason.STALE_REVERSAL_CANDIDATE.value)
    if candidate.current_graph_fingerprint != current_frame.snapshot.graph_fingerprint:
        reasons.append(TransitionRejectionReason.GRAPH_FINGERPRINT_MISMATCH.value)
    prev = next(
        (s for s in previous_frame.snapshot.element_states
         if s.node_id == candidate.node_id), None,
    )
    if prev is None:
        reasons.append(TransitionRejectionReason.SOURCE_SNAPSHOT_MISMATCH.value)
    else:
        if prev.resolution_status is not ResolutionStatus.TRANSFORMED:
            reasons.append(TransitionRejectionReason.PREVIOUS_STATE_MISMATCH.value)
        if prev.resolved_element != candidate.from_element:
            reasons.append(TransitionRejectionReason.PREVIOUS_STATE_MISMATCH.value)
        if prev.original_element != candidate.to_element:
            reasons.append(TransitionRejectionReason.PREVIOUS_STATE_MISMATCH.value)
    if not any(
        e.relation_id == candidate.cause_relation_id for e in current_frame.graph.edges
    ):
        reasons.append(TransitionRejectionReason.AFFECTING_RELATION_MISSING.value)
    if _confirmed_targets_now(
        current_frame, candidate.node_id,
        frozenset(candidate.disrupted_relation_ids) | frozenset(
            candidate.governing_relation_ids),
    ):
        # 현재 층에서 **다른** 관계가 다시 확정 변환 중이라면 원래 오행으로 덮지 않는다.
        reasons.append(
            TransitionRejectionReason.CURRENT_CONFIRMED_TRANSFORM_CONFLICT.value)
    return tuple(dict.fromkeys(reasons))


def _reevaluate_indirect(
    state: ElementResolutionState,
    disrupted: set[str],
    current_frame: RelationStateFrame,
) -> ElementResolutionState:
    """비직접 참여 노드 재평가. **자동 환원하지 않는다.**

    깨진 관계를 근거에서 빼고, 남은 확정 근거가 있으면 상태를 유지한다. 근거가 없어졌는데
    변환 상태로 남아 있으면 원장이 모순되므로 `UNCONFIRMED` 로 낮춘다 — 원래 오행으로
    되돌리는 것과는 다르다. 되돌리려면 그 노드가 직접 충을 받아야 한다.
    """
    remaining = tuple(r for r in state.governing_relation_ids if r not in disrupted)
    if remaining == state.governing_relation_ids:
        return state
    if state.resolution_status is not ResolutionStatus.TRANSFORMED:
        return dataclasses.replace(state, governing_relation_ids=remaining)
    if state.resolved_element == state.original_element:
        # 원래 오행과 변환 목표가 같다 — 되돌릴 원소가 없다.
        return dataclasses.replace(state, governing_relation_ids=remaining)
    if _confirmed_targets_now(current_frame, state.node_id, frozenset(disrupted)):
        return dataclasses.replace(state, governing_relation_ids=remaining)
    return dataclasses.replace(
        state, governing_relation_ids=remaining,
        resolution_status=ResolutionStatus.UNCONFIRMED, resolved_element=None,
    )


def apply_reversal_transitions(
    *,
    previous_frame: RelationStateFrame,
    current_frame: RelationStateFrame,
    candidates: Sequence[ReversalCandidate],
) -> TransitionApplicationResult:
    """환원 후보를 현재 snapshot 에 적용한다.

    결과 snapshot 은 **같은 층·같은 기간·같은 그래프**에 대한 다른 해석이다. 그래서
    `graph_fingerprint`·`layer`·`period_key`·`parent_snapshot_id` 는 그대로 두고
    `snapshot_id` 만 바뀐다. 현재 snapshot 을 결과의 부모로 삼으면 같은 세운 안에 가짜 계층이
    하나 더 생긴다.

    Args:
        previous_frame: 이전 층 frame.
        current_frame: 현재 층 frame. 여기 snapshot 이 적용 대상이다.
        candidates: `detect_reversal_candidates` 산출 후보.

    Returns:
        적용 결과. 입력 frame·snapshot 은 변경하지 않는다.

    Raises:
        ValueError: 두 frame 이 부모–자식이 아닌 경우.
    """
    if current_frame.snapshot.parent_snapshot_id != previous_frame.snapshot.snapshot_id:
        raise ValueError(
            "부모–자식 frame 이 아니다: "
            f"{previous_frame.layer!r} → {current_frame.layer!r}"
        )

    by_node: dict[str, list[ReversalCandidate]] = {}
    for cand in sorted(candidates, key=_sort_key):
        by_node.setdefault(cand.node_id, []).append(cand)

    applied: list[RelationStateTransition] = []
    rejected: list[TransitionApplicationRejection] = []
    reverted: dict[str, ReversalCandidate] = {}

    for node_id, cands in sorted(by_node.items()):
        if len(cands) > 1:
            # 어느 충이 최종 원인인지 코드가 임의로 고르지 않는다.
            for cand in cands:
                rejected.append(TransitionApplicationRejection(
                    cand.candidate_id, node_id,
                    (TransitionRejectionReason
                     .MULTIPLE_REVERSAL_CANDIDATES_FOR_NODE.value,),
                ))
            continue
        cand = cands[0]
        reasons = _validate(cand, previous_frame, current_frame)
        if reasons:
            rejected.append(TransitionApplicationRejection(
                cand.candidate_id, node_id, reasons))
            continue
        reverted[node_id] = cand

    disrupted: set[str] = set()
    for cand in reverted.values():
        disrupted.update(cand.disrupted_relation_ids)

    states: list[ElementResolutionState] = []
    for state in current_frame.snapshot.element_states:
        applied_here = reverted.get(state.node_id)
        if applied_here is not None:
            cand = applied_here
            previous_status = next(
                s.resolution_status for s in previous_frame.snapshot.element_states
                if s.node_id == state.node_id
            )
            states.append(dataclasses.replace(
                state, resolved_element=cand.to_element,
                resolution_status=ResolutionStatus.ORIGINAL,
                governing_relation_ids=tuple(
                    r for r in state.governing_relation_ids if r not in disrupted),
            ))
            applied.append(RelationStateTransition(
                transition_id=f"transition:{cand.candidate_id}",
                transition_type=TransitionType.TRANSFORMATION_REVERSED,
                node_id=state.node_id, previous_status=previous_status,
                resulting_status=ResolutionStatus.ORIGINAL,
                original_element=cand.original_element,
                from_element=cand.from_element, to_element=cand.to_element,
                governing_relation_ids=cand.governing_relation_ids,
                affecting_relation_ids=(cand.cause_relation_id,),
                evidence_path=cand.evidence_path, reason_codes=cand.reason_codes,
            ))
            continue
        states.append(_reevaluate_indirect(state, disrupted, current_frame))

    active = tuple(
        r for r in current_frame.snapshot.active_relation_ids if r not in disrupted
    )
    unresolved = tuple(sorted(
        set(current_frame.snapshot.unresolved_relation_ids) | disrupted
    ))
    result = dataclasses.replace(
        current_frame.snapshot,
        snapshot_id=compute_snapshot_id(
            layer=current_frame.snapshot.layer,
            period_key=current_frame.snapshot.period_key,
            parent_id=current_frame.snapshot.parent_snapshot_id,
            graph_fp=current_frame.snapshot.graph_fingerprint,
            states=states, active=active, unresolved=unresolved,
        ),
        element_states=tuple(states), active_relation_ids=active,
        unresolved_relation_ids=unresolved,
    )
    return TransitionApplicationResult(
        base_snapshot_id=current_frame.snapshot.snapshot_id,
        result_snapshot=result,
        applied_transitions=tuple(
            sorted(applied, key=lambda t: t.transition_id)),
        rejected_candidates=tuple(
            sorted(rejected, key=lambda r: (r.node_id, r.candidate_id))),
    )
