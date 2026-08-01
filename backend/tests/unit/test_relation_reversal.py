"""합화 환원 후보 탐지 골든 회귀 (P1-c0, 2026-08-01).

여기서 지키는 구분 하나가 이 슬라이스의 전부다.

    변환 미완성   卯酉冲이 있어 亥卯未가 애초에 木으로 완성되지 못함
    변환 후 환원  이미 木으로 작동하던 亥가 巳亥冲으로 다시 水로 돌아옴

둘은 다른 사건이고 다른 서술을 낳는다. 전자에 환원을 붙이면 "木이었다가 돌아왔다" 는 없던
이력을 만들어낸다.

P1-c0 는 후보와 기각 사유만 낸다 — snapshot 을 바꾸지 않고 `TRANSFORMATION_REVERSED` 도
생성하지 않는다(P1-c1).
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
from saju_engines.relation_reversal import (
    EvidencePath,
    ReversalReason,
    detect_reversal_candidates,
)
from saju_engines.relation_state_chain import (
    RelationFrameBuildMetrics,
    RelationStateFrame,
    assemble_relation_state_chain,
)
from saju_engines.relation_state_snapshot import (
    ElementResolutionState,
    ResolutionStatus,
    build_relation_state_snapshot,
)

_PERIODS = {"natal": "natal", "daewoon": "2003", "sewoon": "2003"}


def _n(layer: str, position: str, ch: str, element: str) -> RelationNode:
    node_id = f"{layer}.{position}.branch:{ch}" if position else f"{layer}.branch:{ch}"
    return RelationNode(node_id, layer, position, "branch", ch, element)


_MYO = _n("natal", "year", "卯", "木")
_MI = _n("natal", "month", "未", "土")


class _Hap:
    def __init__(self, kind, members, positions, tier, mode, target):
        self.kind, self.members, self.positions = kind, members, positions
        self.transform_tier, self.hap_mode, self.transform_element = tier, mode, target


def _harmony_chain(daewoon: str, sewoon: str, *, tier: str, mode: str):
    """亥卯未 삼합이 대운에서 성립한 뒤 세운 글자가 들어오는 체인."""
    def call(luck_branches=None):
        lb = list(luck_branches or [])
        if "亥" in lb:
            return [_Hap("three_harmony", ("卯", "未", "亥"),
                         ("year", "month", "luck"), tier, mode, "木")]
        return []

    return assemble_relation_state_chain(
        natal_nodes=(_MYO, _MI),
        daewoon_nodes=(_n("daewoon", "", daewoon, "水"),),
        sewoon_nodes=(_n("sewoon", "", sewoon, "火"),),
        resolve_branch_hap=call, period_keys=_PERIODS,
    )


def _detect(chain):
    prev, cur = chain.frames[1], chain.frames[2]
    return detect_reversal_candidates(
        previous_snapshot=prev.snapshot, previous_graph=prev.graph,
        current_snapshot=cur.snapshot, current_graph=cur.graph,
    )


# ── 확정 변환 후 직접 충 ─────────────────────────────────────────────────


def test_confirmed_transform_hit_by_new_clash_becomes_a_candidate() -> None:
    """亥가 木으로 확정 변환된 뒤 巳亥冲 — 환원 후보가 된다."""
    detection = _detect(_harmony_chain("亥", "巳", tier="confirmed", mode="transform"))
    (candidate,) = detection.candidates
    assert candidate.node_id == "daewoon.branch:亥"
    assert candidate.from_element == "木"
    assert candidate.to_element == "水"          # 원래 오행으로 — 새로 계산하지 않는다
    assert candidate.original_element == "水"
    assert candidate.evidence_path is EvidencePath.DEPENDENCY_LINK
    assert candidate.reason_codes == (
        ReversalReason.REVERSAL_BY_DEPENDENCY_LINK.value,
    )
    assert candidate.governing_relation_ids


def test_other_participants_are_not_reverted_automatically() -> None:
    """亥卯未가 깨져도 卯·未 를 함께 되돌리지 않는다.

    영상에서 확인되는 것은 '亥가 木이었다가 水로 돌아간다' 까지다. 참여 지지 전체가 함께
    환원된다고 일반화하지 않는다.
    """
    detection = _detect(_harmony_chain("亥", "巳", tier="confirmed", mode="transform"))
    assert {c.node_id for c in detection.candidates} == {"daewoon.branch:亥"}
    rejected = {r.node_id for r in detection.rejections}
    assert "natal.year.branch:卯" in rejected
    assert "natal.month.branch:未" in rejected


def test_detection_does_not_mutate_snapshots() -> None:
    """P1-c0 는 상태를 바꾸지 않는다."""
    chain = _harmony_chain("亥", "巳", tier="confirmed", mode="transform")
    before = [dataclasses.asdict(f.snapshot) for f in chain.frames]
    _detect(chain)
    assert [dataclasses.asdict(f.snapshot) for f in chain.frames] == before
    assert all(
        s.resolution_status.value != "reversed"
        for f in chain.frames for s in f.snapshot.element_states
    )


# ── 미완성 변환 ──────────────────────────────────────────────────────────


def test_incomplete_transform_is_prevented_not_reversed() -> None:
    """tier=none·mode=transform 에 충이 와도 환원이 아니다 — 애초에 木인 적이 없다."""
    detection = _detect(_harmony_chain("亥", "巳", tier="none", mode="transform"))
    assert detection.candidates == ()
    prevented = [
        r for r in detection.rejections
        if ReversalReason.TRANSFORMATION_PREVENTED.value in r.reason_codes
    ]
    assert prevented and prevented[0].node_id == "daewoon.branch:亥"


def test_bound_state_is_not_reversed() -> None:
    """묶였을 뿐 변한 적이 없으면 되돌릴 것도 없다."""
    detection = _detect(_harmony_chain("亥", "巳", tier="conditional", mode="bind"))
    assert detection.candidates == ()


# ── 자리 정합 ────────────────────────────────────────────────────────────


def test_same_character_at_a_different_position_does_not_revert() -> None:
    """글자 亥가 같은 것으로는 부족하다 — 같은 node_id 여야 한다."""
    hai_month = _n("natal", "month", "亥", "水")
    hai_day = _n("natal", "day", "亥", "水")
    harmony = edge_from_resolution(
        relation_id="three_harmony:卯未亥@month", relation_family="three_harmony:卯未亥",
        relation_type="three_harmony", member_node_ids=(hai_month.node_id,),
        tier="confirmed", mode="transform", target_element="木",
        source_resolver="branch_hap",
    )
    nodes = (_MYO, hai_month, hai_day)
    prev_graph = build_relation_dependency_graph(
        nodes=nodes, resolved_relations=(harmony,))
    prev_snap = build_relation_state_snapshot(
        graph=prev_graph, layer="daewoon", period_key="2003")

    si = _n("sewoon", "", "巳", "火")
    cur_nodes = (*nodes, si)
    # collector 는 巳亥冲을 **자리별로 두 건** 만든다(월지·일지). 자리 정합만 격리해 보려고
    # 일지 인스턴스만 넣는다 — 손으로 만든 충이 아니라 collector 가 낸 실제 인스턴스다.
    instances = [
        i for i in collect_branch_relation_instances(nodes=cur_nodes)
        if hai_day.node_id in i.member_node_ids
    ]
    assert instances, "collector 가 일지 巳亥冲을 내지 않았다"
    clash = edges_from_branch_relations(instances)
    cur_graph = build_relation_dependency_graph(
        nodes=cur_nodes, resolved_relations=(harmony,), disruptive_relations=clash)
    cur_snap = build_relation_state_snapshot(
        graph=cur_graph, layer="sewoon", period_key="2003",
        previous_snapshot=prev_snap)

    detection = detect_reversal_candidates(
        previous_snapshot=prev_snap, previous_graph=prev_graph,
        current_snapshot=cur_snap, current_graph=cur_graph,
    )
    # 巳는 일지 亥와 충하지만 변환된 것은 월지 亥다.
    assert all(c.node_id != hai_month.node_id for c in detection.candidates)


def _frame(layer, graph, snapshot) -> RelationStateFrame:
    return RelationStateFrame(
        layer=layer, period_key=snapshot.period_key, graph=graph, snapshot=snapshot,
        metrics=RelationFrameBuildMetrics(layer=layer),
    )


# ── 이전부터 있던 충 ─────────────────────────────────────────────────────


def test_preexisting_clash_is_diagnosed_not_reverted() -> None:
    """이미 충이 있었는데 TRANSFORMED 였다면 환원 사건이 아니라 확정 규칙의 모순일 수 있다."""
    hai, si = _n("daewoon", "", "亥", "水"), _n("daewoon", "", "巳", "火")
    harmony = edge_from_resolution(
        relation_id="three_harmony:卯未亥@year+month+luck",
        relation_family="three_harmony:卯未亥", relation_type="three_harmony",
        member_node_ids=(_MYO.node_id, _MI.node_id, hai.node_id),
        tier="confirmed", mode="transform", target_element="木",
        source_resolver="branch_hap",
    )
    nodes = (_MYO, _MI, hai, si)
    clash = edges_from_branch_relations(collect_branch_relation_instances(nodes=nodes))
    graph = build_relation_dependency_graph(
        nodes=nodes, resolved_relations=(harmony,), disruptive_relations=clash)
    prev = build_relation_state_snapshot(
        graph=graph, layer="daewoon", period_key="2003")
    cur = build_relation_state_snapshot(
        graph=graph, layer="sewoon", period_key="2003", previous_snapshot=prev)

    detection = detect_reversal_candidates(
        previous_snapshot=prev, previous_graph=graph,
        current_snapshot=cur, current_graph=graph,
    )
    assert detection.candidates == ()
    assert any(
        ReversalReason.PREEXISTING_CONFLICT_WITH_CONFIRMED_TRANSFORM.value
        in r.reason_codes
        for r in detection.rejections
    )


# ── 형·파·해 ─────────────────────────────────────────────────────────────


def test_harm_is_not_a_reversal_cause() -> None:
    """형·파·해는 첫 버전에서 환원 원인이 아니다 — 구조 근거만 남는다."""
    detection = _detect(_harmony_chain("亥", "申", tier="confirmed", mode="transform"))
    assert detection.candidates == ()


# ── 근거 경로 ────────────────────────────────────────────────────────────


def _reversal_frames(*, include_harmony_in_current: bool, clash_target: str = "亥"):
    """대운에서 확정된 삼합 + 세운 巳. 현재 그래프에 삼합 엣지를 넣을지 고른다."""
    hai, si = _n("daewoon", "", "亥", "水"), _n("sewoon", "", "巳", "火")
    harmony = edge_from_resolution(
        relation_id="three_harmony:卯未亥@year+month+luck",
        relation_family="three_harmony:卯未亥", relation_type="three_harmony",
        member_node_ids=(_MYO.node_id, _MI.node_id, hai.node_id),
        tier="confirmed", mode="transform", target_element="木",
        source_resolver="branch_hap",
    )
    prev_nodes = (_MYO, _MI, hai)
    prev_graph = build_relation_dependency_graph(
        nodes=prev_nodes, resolved_relations=(harmony,))
    prev = build_relation_state_snapshot(
        graph=prev_graph, layer="daewoon", period_key="2003")

    cur_nodes = (*prev_nodes, si)
    clash = edges_from_branch_relations(
        collect_branch_relation_instances(nodes=cur_nodes))
    cur_graph = build_relation_dependency_graph(
        nodes=cur_nodes,
        resolved_relations=(harmony,) if include_harmony_in_current else (),
        disruptive_relations=clash,
    )
    cur = build_relation_state_snapshot(
        graph=cur_graph, layer="sewoon", period_key="2003", previous_snapshot=prev)
    return (_frame("daewoon", prev_graph, prev), _frame("sewoon", cur_graph, cur))


def test_dependency_path_is_preferred() -> None:
    prev, cur = _reversal_frames(include_harmony_in_current=True)
    (candidate,) = detect_reversal_candidates(
        previous_snapshot=prev.snapshot, previous_graph=prev.graph,
        current_snapshot=cur.snapshot, current_graph=cur.graph).candidates
    assert candidate.evidence_path is EvidencePath.DEPENDENCY_LINK


def test_node_intersection_fallback_when_dependency_is_missing() -> None:
    """현재 그래프에 기존 합 엣지가 없으면 dependency 가 생기지 않는다(P1-b1.5 실측).

    그래도 node 교집합으로 후보를 만들 수 있어야 한다.
    """
    prev, cur = _reversal_frames(include_harmony_in_current=False)
    assert not cur.graph.relation_dependencies
    (candidate,) = detect_reversal_candidates(
        previous_snapshot=prev.snapshot, previous_graph=prev.graph,
        current_snapshot=cur.snapshot, current_graph=cur.graph).candidates
    assert candidate.evidence_path is EvidencePath.NODE_INTERSECTION_FALLBACK
    assert candidate.reason_codes == (
        ReversalReason.REVERSAL_BY_NODE_INTERSECTION_FALLBACK.value,
    )


def test_two_clashes_on_one_relation_are_not_a_conflict() -> None:
    """卯酉冲도 같은 삼합을 교란하지만 亥를 치지 않는다 — 亥의 환원 원인이 아니다.

    dependency 가 여럿이어도 그중 하나가 node 를 직접 치면 그것이 원인이다. 이 경우를
    충돌로 오인하면 정상 환원이 전부 막힌다.
    """
    hai, si = _n("daewoon", "", "亥", "水"), _n("sewoon", "", "巳", "火")
    yu = _n("sewoon", "", "酉", "金")
    harmony = edge_from_resolution(
        relation_id="three_harmony:卯未亥@year+month+luck",
        relation_family="three_harmony:卯未亥", relation_type="three_harmony",
        member_node_ids=(_MYO.node_id, _MI.node_id, hai.node_id),
        tier="confirmed", mode="transform", target_element="木",
        source_resolver="branch_hap",
    )
    prev_nodes = (_MYO, _MI, hai)
    prev_graph = build_relation_dependency_graph(
        nodes=prev_nodes, resolved_relations=(harmony,))
    prev = build_relation_state_snapshot(
        graph=prev_graph, layer="daewoon", period_key="2003")

    cur_nodes = (*prev_nodes, si, yu)
    clash = edges_from_branch_relations(
        collect_branch_relation_instances(nodes=cur_nodes))
    cur_graph = build_relation_dependency_graph(
        nodes=cur_nodes, resolved_relations=(harmony,), disruptive_relations=clash)
    cur = build_relation_state_snapshot(
        graph=cur_graph, layer="sewoon", period_key="2003", previous_snapshot=prev)

    (candidate,) = detect_reversal_candidates(
        previous_snapshot=prev, previous_graph=prev_graph,
        current_snapshot=cur, current_graph=cur_graph,
    ).candidates
    assert candidate.evidence_path is EvidencePath.DEPENDENCY_LINK
    assert "亥巳" in candidate.cause_relation_id      # 卯酉가 아니다


def test_conflicting_evidence_blocks_automatic_reversal() -> None:
    """우선 경로와 백업 경로가 서로 다른 관계를 가리키면 자동 적용하지 않는다.

    현재 층에서 근거 관계의 구성이 달라져 亥가 빠지면, dependency 는 卯酉冲을 가리키고
    node 교집합은 巳亥冲을 가리킨다. 어느 쪽이 환원 원인인지 코드가 정할 문제가 아니다.
    """
    hai, si = _n("daewoon", "", "亥", "水"), _n("sewoon", "", "巳", "火")
    yu = _n("sewoon", "", "酉", "金")
    relation_id = "three_harmony:卯未亥@year+month+luck"
    prev_harmony = edge_from_resolution(
        relation_id=relation_id, relation_family="three_harmony:卯未亥",
        relation_type="three_harmony",
        member_node_ids=(_MYO.node_id, _MI.node_id, hai.node_id),
        tier="confirmed", mode="transform", target_element="木",
        source_resolver="branch_hap",
    )
    prev_nodes = (_MYO, _MI, hai)
    prev_graph = build_relation_dependency_graph(
        nodes=prev_nodes, resolved_relations=(prev_harmony,))
    prev = build_relation_state_snapshot(
        graph=prev_graph, layer="daewoon", period_key="2003")

    # 같은 relation_id 인데 현재 층에서는 亥가 구성에서 빠졌다.
    current_harmony = dataclasses.replace(
        prev_harmony, member_node_ids=(_MYO.node_id, _MI.node_id))
    cur_nodes = (*prev_nodes, si, yu)
    clash = edges_from_branch_relations(
        collect_branch_relation_instances(nodes=cur_nodes))
    cur_graph = build_relation_dependency_graph(
        nodes=cur_nodes, resolved_relations=(current_harmony,),
        disruptive_relations=clash)
    cur = build_relation_state_snapshot(
        graph=cur_graph, layer="sewoon", period_key="2003", previous_snapshot=prev)

    detection = detect_reversal_candidates(
        previous_snapshot=prev, previous_graph=prev_graph,
        current_snapshot=cur, current_graph=cur_graph,
    )
    assert detection.candidates == ()
    conflict = [
        r for r in detection.rejections
        if ReversalReason.REVERSAL_EVIDENCE_CONFLICT.value in r.reason_codes
    ]
    assert conflict and conflict[0].node_id == hai.node_id


def test_multiple_governing_targets_stay_unconfirmed() -> None:
    """서로 다른 target 이 한 노드를 지배하면 무엇이 환원되는지 정할 수 없다.

    snapshot 빌더는 이 상태를 만들지 않는다(경쟁이면 UNCONFIRMED). 방어적 가드다.
    """
    prev, cur = _reversal_frames(include_harmony_in_current=True)
    extra = edge_from_resolution(
        relation_id="six:卯戌@year+luck", relation_family="six:卯戌",
        relation_type="six", member_node_ids=("daewoon.branch:亥",),
        tier="confirmed", mode="transform", target_element="火",
        source_resolver="branch_hap",
    )
    prev_graph = dataclasses.replace(
        prev.graph, edges=(*prev.graph.edges, extra))
    states = tuple(
        dataclasses.replace(s, governing_relation_ids=(
            *s.governing_relation_ids, extra.relation_id))
        if s.node_id == "daewoon.branch:亥" else s
        for s in prev.snapshot.element_states
    )
    prev_snap = dataclasses.replace(
        prev.snapshot, element_states=states,
        active_relation_ids=(*prev.snapshot.active_relation_ids, extra.relation_id))

    detection = detect_reversal_candidates(
        previous_snapshot=prev_snap, previous_graph=prev_graph,
        current_snapshot=cur.snapshot, current_graph=cur.graph)
    assert detection.candidates == ()
    assert any(
        ReversalReason.REVERSAL_UNCONFIRMED.value in r.reason_codes
        for r in detection.rejections
    )


# ── 계약 ─────────────────────────────────────────────────────────────────


def test_non_parent_child_frames_are_rejected() -> None:
    """엉뚱한 층을 비교하면 '새로 들어온 충' 판정이 통째로 무의미해진다."""
    chain = _harmony_chain("亥", "巳", tier="confirmed", mode="transform")
    with pytest.raises(ValueError, match="부모–자식"):
        detect_reversal_candidates(
            previous_snapshot=chain.frames[0].snapshot,
            previous_graph=chain.frames[0].graph,
            current_snapshot=chain.frames[2].snapshot,
            current_graph=chain.frames[2].graph)


def test_metrics_are_low_cardinality() -> None:
    detection = _detect(_harmony_chain("亥", "巳", tier="confirmed", mode="transform"))
    metrics = detection.metrics()
    assert metrics["reversal_candidate_count"] == 1
    assert all(isinstance(v, int) for v in metrics.values())
    assert not any("亥" in k or "巳" in k for k in metrics)


def test_no_reversed_status_is_created() -> None:
    """상태 적용은 P1-c1 이다."""
    assert not hasattr(ResolutionStatus, "REVERSED")
    assert ElementResolutionState(
        "n", "水", "水", ResolutionStatus.ORIGINAL, ()
    ).resolution_status is ResolutionStatus.ORIGINAL
