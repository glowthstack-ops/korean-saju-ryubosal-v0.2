"""환원 상태 전이 적용 회귀 (P1-c1a, 2026-08-01).

환원은 **사건이지 상태가 아니다.** 환원 뒤 亥의 현재 오행은 이미 水이므로 결과 상태는
`ORIGINAL` 이고, `TRANSFORMATION_REVERSED` 는 전이 기록에만 남는다. 상태 enum 에 환원을
넣으면 다음 층이 그 값을 현재 정체성으로 읽는다.

적용 범위는 직접 충을 받은 노드 하나다. 다만 그 관계 하나만을 근거로 확정돼 있던 비직접
노드를 확정으로 남겨두면 원장이 모순되므로, 근거를 지운 뒤 재평가한다 — **자동 환원은
하지 않는다.**
"""

from __future__ import annotations

import dataclasses

import pytest

from saju_engines.branch_relation_collector import collect_branch_relation_instances
from saju_engines.luck_relation_graph import (
    RelationNode,
    build_relation_dependency_graph,
    edge_from_resolution,
    edges_from_branch_relations,
)
from saju_engines.relation_reversal import detect_reversal_candidates
from saju_engines.relation_state_chain import (
    RelationFrameBuildMetrics,
    RelationStateFrame,
)
from saju_engines.relation_state_snapshot import (
    ResolutionStatus,
    build_relation_state_snapshot,
)
from saju_engines.relation_transition import (
    TransitionRejectionReason,
    TransitionType,
    apply_reversal_transitions,
)


def _n(layer: str, position: str, ch: str, element: str) -> RelationNode:
    node_id = f"{layer}.{position}.branch:{ch}" if position else f"{layer}.branch:{ch}"
    return RelationNode(node_id, layer, position, "branch", ch, element)


_MYO = _n("natal", "year", "卯", "木")
_MI = _n("natal", "month", "未", "土")
_HAI = _n("daewoon", "", "亥", "水")
_SI = _n("sewoon", "", "巳", "火")
_HARMONY_ID = "three_harmony:卯未亥@year+month+luck"


def _frame(layer, graph, snapshot) -> RelationStateFrame:
    return RelationStateFrame(
        layer=layer, period_key=snapshot.period_key, graph=graph, snapshot=snapshot,
        metrics=RelationFrameBuildMetrics(layer=layer),
    )


def _harmony(*members: str, tier: str = "confirmed", target: str = "木"):
    return edge_from_resolution(
        relation_id=_HARMONY_ID, relation_family="three_harmony:卯未亥",
        relation_type="three_harmony", member_node_ids=members,
        tier=tier, mode="transform", target_element=target,
        source_resolver="branch_hap",
    )


def _setup(*, extra_current_edges=(), harmony_members=None):
    """亥가 木으로 확정된 대운 → 巳가 들어온 세운."""
    members = harmony_members or (_MYO.node_id, _MI.node_id, _HAI.node_id)
    harmony = _harmony(*members)
    prev_nodes = (_MYO, _MI, _HAI)
    prev_graph = build_relation_dependency_graph(
        nodes=prev_nodes, resolved_relations=(harmony,))
    prev_snap = build_relation_state_snapshot(
        graph=prev_graph, layer="daewoon", period_key="2003")

    cur_nodes = (*prev_nodes, _SI)
    clash = edges_from_branch_relations(
        collect_branch_relation_instances(nodes=cur_nodes))
    cur_graph = build_relation_dependency_graph(
        nodes=cur_nodes, resolved_relations=(harmony, *extra_current_edges),
        disruptive_relations=clash)
    cur_snap = build_relation_state_snapshot(
        graph=cur_graph, layer="sewoon", period_key="2003",
        previous_snapshot=prev_snap)
    return _frame("daewoon", prev_graph, prev_snap), _frame("sewoon", cur_graph, cur_snap)


def _apply(previous, current, candidates=None):
    if candidates is None:
        candidates = detect_reversal_candidates(
            previous_frame=previous, current_frame=current).candidates
    return apply_reversal_transitions(
        previous_frame=previous, current_frame=current, candidates=candidates)


def _state(snapshot, node_id):
    return next(s for s in snapshot.element_states if s.node_id == node_id)


# ── 적용 ─────────────────────────────────────────────────────────────────


def test_direct_clash_applies_the_transition() -> None:
    result = _apply(*_setup())
    (transition,) = result.applied_transitions
    assert transition.transition_type is TransitionType.TRANSFORMATION_REVERSED
    assert transition.node_id == _HAI.node_id
    assert transition.previous_status is ResolutionStatus.TRANSFORMED
    assert transition.resulting_status is ResolutionStatus.ORIGINAL


def test_result_element_returns_to_original() -> None:
    """결과 상태는 ORIGINAL 이고 원소는 원래 오행이다 — 새로 계산하지 않는다."""
    result = _apply(*_setup())
    state = _state(result.result_snapshot, _HAI.node_id)
    assert state.original_element == "水"
    assert state.resolved_element == "水"
    assert state.resolution_status is ResolutionStatus.ORIGINAL


def test_transition_preserves_from_and_to() -> None:
    """'어떻게 지금 상태가 되었는가' 는 전이에만 남는다."""
    (transition,) = _apply(*_setup()).applied_transitions
    assert (transition.from_element, transition.to_element) == ("木", "水")
    assert transition.original_element == "水"
    assert transition.affecting_relation_ids and transition.governing_relation_ids


def test_inputs_are_not_mutated() -> None:
    previous, current = _setup()
    before = (dataclasses.asdict(previous.snapshot),
              dataclasses.asdict(current.snapshot))
    _apply(previous, current)
    assert (dataclasses.asdict(previous.snapshot),
            dataclasses.asdict(current.snapshot)) == before


# ── 계층·식별자 ──────────────────────────────────────────────────────────


def test_parent_and_fingerprint_are_unchanged() -> None:
    """같은 frame 의 다른 해석이다 — 가짜 계층을 만들지 않는다."""
    previous, current = _setup()
    result = _apply(previous, current)
    out = result.result_snapshot
    assert out.parent_snapshot_id == current.snapshot.parent_snapshot_id
    assert out.parent_snapshot_id != current.snapshot.snapshot_id
    assert out.graph_fingerprint == current.snapshot.graph_fingerprint
    assert out.layer == current.snapshot.layer
    assert out.period_key == current.snapshot.period_key


def test_snapshot_id_changes_and_base_is_recorded() -> None:
    previous, current = _setup()
    result = _apply(previous, current)
    assert result.base_snapshot_id == current.snapshot.snapshot_id
    assert result.result_snapshot.snapshot_id != current.snapshot.snapshot_id


def test_disrupted_relation_leaves_active_set() -> None:
    previous, current = _setup()
    result = _apply(previous, current)
    assert _HARMONY_ID in current.snapshot.active_relation_ids
    assert _HARMONY_ID not in result.result_snapshot.active_relation_ids
    assert _HARMONY_ID in result.result_snapshot.unresolved_relation_ids


# ── 비직접 노드 ──────────────────────────────────────────────────────────


def test_indirect_participant_is_not_reverted_to_its_original_element() -> None:
    """未를 土로 자동 환원하지 않는다 — 되돌리려면 직접 충을 받아야 한다."""
    result = _apply(*_setup())
    state = _state(result.result_snapshot, _MI.node_id)
    assert state.resolved_element != "土"
    assert state.resolution_status is not ResolutionStatus.ORIGINAL


def test_indirect_participant_without_remaining_evidence_is_unconfirmed() -> None:
    """유일한 근거가 깨졌는데 확정으로 남기면 원장이 모순된다."""
    result = _apply(*_setup())
    state = _state(result.result_snapshot, _MI.node_id)
    assert state.resolution_status is ResolutionStatus.UNCONFIRMED
    assert state.resolved_element is None
    assert _HARMONY_ID not in state.governing_relation_ids


def test_node_whose_target_equals_its_origin_needs_no_reversion() -> None:
    """卯는 원래 木이고 변환 목표도 木이다 — 되돌릴 원소가 없다."""
    result = _apply(*_setup())
    state = _state(result.result_snapshot, _MYO.node_id)
    assert state.original_element == "木"
    assert state.resolved_element == "木"


def test_indirect_participant_with_other_confirmed_evidence_keeps_its_state() -> None:
    """다른 확정 근거가 남아 있으면 상태를 유지한다."""
    other = edge_from_resolution(
        relation_id="six:卯戌@month+extra", relation_family="six:卯戌",
        relation_type="six", member_node_ids=(_MI.node_id,),
        tier="confirmed", mode="transform", target_element="木",
        source_resolver="branch_hap",
    )
    previous, current = _setup(extra_current_edges=(other,))
    state = _state(_apply(previous, current).result_snapshot, _MI.node_id)
    assert state.resolution_status is ResolutionStatus.TRANSFORMED
    assert state.resolved_element == "木"


# ── 적용 거부 ────────────────────────────────────────────────────────────


def test_current_confirmed_transform_blocks_automatic_reversal() -> None:
    """현재 층에서 다시 확정 변환 중이면 원래 오행으로 덮지 않는다."""
    previous, current = _setup()
    candidates = detect_reversal_candidates(
        previous_frame=previous, current_frame=current).candidates
    again = edge_from_resolution(
        relation_id="six:巳亥化水@luck", relation_family="six:巳亥",
        relation_type="six", member_node_ids=(_HAI.node_id,),
        tier="confirmed", mode="transform", target_element="金",
        source_resolver="branch_hap",
    )
    patched = _frame("sewoon", dataclasses.replace(
        current.graph, edges=(*current.graph.edges, again)), current.snapshot)
    result = _apply(previous, patched, candidates)
    assert result.applied_transitions == ()
    assert any(
        TransitionRejectionReason.CURRENT_CONFIRMED_TRANSFORM_CONFLICT.value
        in r.reason_codes for r in result.rejected_candidates
    )


def test_stale_candidate_is_rejected() -> None:
    previous, current = _setup()
    (candidate,) = detect_reversal_candidates(
        previous_frame=previous, current_frame=current).candidates
    stale = dataclasses.replace(candidate, current_snapshot_id="다른-스냅샷")
    result = _apply(previous, current, (stale,))
    assert result.applied_transitions == ()
    assert TransitionRejectionReason.STALE_REVERSAL_CANDIDATE.value in (
        result.rejected_candidates[0].reason_codes)


def test_graph_fingerprint_mismatch_is_rejected() -> None:
    previous, current = _setup()
    (candidate,) = detect_reversal_candidates(
        previous_frame=previous, current_frame=current).candidates
    drifted = dataclasses.replace(candidate, current_graph_fingerprint="0" * 64)
    result = _apply(previous, current, (drifted,))
    assert result.applied_transitions == ()
    assert TransitionRejectionReason.GRAPH_FINGERPRINT_MISMATCH.value in (
        result.rejected_candidates[0].reason_codes)


def test_previous_state_mismatch_is_rejected() -> None:
    previous, current = _setup()
    (candidate,) = detect_reversal_candidates(
        previous_frame=previous, current_frame=current).candidates
    wrong = dataclasses.replace(candidate, from_element="金")
    result = _apply(previous, current, (wrong,))
    assert result.applied_transitions == ()
    assert TransitionRejectionReason.PREVIOUS_STATE_MISMATCH.value in (
        result.rejected_candidates[0].reason_codes)


def test_missing_affecting_relation_is_rejected() -> None:
    previous, current = _setup()
    (candidate,) = detect_reversal_candidates(
        previous_frame=previous, current_frame=current).candidates
    ghost = dataclasses.replace(candidate, cause_relation_id="clash:없음@x+y")
    result = _apply(previous, current, (ghost,))
    assert result.applied_transitions == ()
    assert TransitionRejectionReason.AFFECTING_RELATION_MISSING.value in (
        result.rejected_candidates[0].reason_codes)


def test_multiple_candidates_for_one_node_block_application() -> None:
    """어느 충이 최종 원인인지 코드가 임의로 고르지 않는다."""
    previous, current = _setup()
    (candidate,) = detect_reversal_candidates(
        previous_frame=previous, current_frame=current).candidates
    twin = dataclasses.replace(
        candidate, candidate_id=candidate.candidate_id + "|2")
    result = _apply(previous, current, (candidate, twin))
    assert result.applied_transitions == ()
    assert all(
        TransitionRejectionReason.MULTIPLE_REVERSAL_CANDIDATES_FOR_NODE.value
        in r.reason_codes for r in result.rejected_candidates
    )
    assert len(result.rejected_candidates) == 2


# ── 결정성·멱등성 ────────────────────────────────────────────────────────


def test_candidate_order_does_not_change_the_result() -> None:
    previous, current = _setup()
    (candidate,) = detect_reversal_candidates(
        previous_frame=previous, current_frame=current).candidates
    other_node = dataclasses.replace(
        candidate, node_id=_MI.node_id,
        candidate_id="reversal:natal.month.branch:未|x")
    forward = _apply(previous, current, (candidate, other_node))
    backward = _apply(previous, current, (other_node, candidate))
    assert (forward.result_snapshot.snapshot_id
            == backward.result_snapshot.snapshot_id)
    assert forward.applied_transitions == backward.applied_transitions
    assert forward.rejected_candidates == backward.rejected_candidates


def test_reapplying_the_same_input_is_idempotent() -> None:
    previous, current = _setup()
    first = _apply(previous, current)
    second = _apply(previous, current)
    assert first.result_snapshot == second.result_snapshot
    assert first.applied_transitions == second.applied_transitions
    ids = [t.transition_id for t in first.applied_transitions]
    assert len(ids) == len(set(ids))


# ── 경계 ─────────────────────────────────────────────────────────────────


def test_non_parent_child_frames_are_rejected() -> None:
    previous, current = _setup()
    with pytest.raises(ValueError, match="부모–자식"):
        apply_reversal_transitions(
            previous_frame=current, current_frame=previous, candidates=())


def test_no_candidates_leaves_the_snapshot_equivalent() -> None:
    previous, current = _setup()
    result = _apply(previous, current, ())
    assert result.result_snapshot.snapshot_id == current.snapshot.snapshot_id
    assert result.applied_transitions == ()


def test_no_reversed_resolution_status_is_introduced() -> None:
    """상태 enum 에 환원을 넣지 않는다 — 전이로만 표현한다."""
    result = _apply(*_setup())
    assert not hasattr(ResolutionStatus, "REVERSED")
    assert all(
        s.resolution_status.value != "reversed"
        for s in result.result_snapshot.element_states
    )
