"""환원 전제정보 보존 검증 (P1-b1.5, 2026-08-01).

P1-c(`TRANSFORMATION_REVERSED`)를 구현하기 **전에** 확인한다: 상태 원장이 환원 판정에 필요한
사실을 잃지 않는가?

여기서 판정하지 않는 것 — 巳亥冲이 실제로 합화를 해제했는지, 亥가 水로 환원됐는지,
`TRANSFORMATION_REVERSED`가 성립했는지. 그건 P1-c 범위다. 이 파일은 **정보가 남아 있는지만**
본다.

계층 조립(P1-b2)을 먼저 만들었다가 snapshot 에 필요한 정보가 없다는 사실이 드러나면 조립기와
플래그 배선을 다시 뜯어야 한다. 지금 확인하는 비용이 훨씬 작다.

시나리오: 亥卯未 삼합으로 亥(水)가 木으로 변환된 뒤, 다음 층에 巳가 들어와 亥와 충한다.

    조건 1  test_node_identity_is_stable_across_layers
            test_same_character_in_two_luck_layers_is_rejected
    조건 2  test_previous_state_retains_element_before_and_after
    조건 3  test_previous_state_retains_governing_relation
            test_relation_id_is_stable_across_luck_combinations
    조건 4  test_clash_instance_comes_from_collector
    조건 5  test_previous_transform_is_linked_to_current_clash
    조건 6  test_parent_snapshot_object_is_reachable_downstream
    금지    test_no_automatic_reversal_is_produced
"""

from __future__ import annotations

from datetime import date

import pytest
from saju_manse_analysis.relations.hap_modes import resolve_branch_hap

from saju_api.services.manse_service import calculate
from saju_engines.branch_relation_collector import (
    BranchRelationKind,
    collect_branch_relation_instances,
)
from saju_engines.luck_relation_graph import (
    LINK_POTENTIALLY_DISRUPTED_BY,
    RelationNode,
    build_luck_node_index,
    build_relation_dependency_graph,
    edge_from_resolution,
    edges_from_branch_relations,
)
from saju_engines.relation_state_snapshot import (
    ResolutionStatus,
    build_relation_state_snapshot,
)
from saju_shared_types.birth_input import BirthInput

_NATAL = (
    RelationNode("natal.year.branch:卯", "natal", "year", "branch", "卯", "木"),
    RelationNode("natal.month.branch:未", "natal", "month", "branch", "未", "土"),
    RelationNode("natal.day.branch:戌", "natal", "day", "branch", "戌", "土"),
    RelationNode("natal.hour.branch:戌", "natal", "hour", "branch", "戌", "土"),
)
_HAI = RelationNode("daewoon.branch:亥", "daewoon", "", "branch", "亥", "水")
_SI = RelationNode("sewoon.branch:巳", "sewoon", "", "branch", "巳", "火")

#: 대운에서 성립한 삼합. tier=confirmed 는 **상태 고정용 fixture** 다 — 이 명식의 실제
#: resolver 출력은 tier=none 이며(0B 관측 3), 여기서 검증하려는 것은 판정이 아니라 보존이다.
_HARMONY = edge_from_resolution(
    relation_id="three_harmony:卯未亥@year+month+luck",
    relation_family="three_harmony:卯未亥",
    relation_type="three_harmony",
    member_node_ids=(
        "natal.year.branch:卯", "natal.month.branch:未", "daewoon.branch:亥",
    ),
    tier="confirmed", mode="transform", target_element="木",
    source_resolver="branch_hap",
)


def _daewoon_snapshot():
    """亥가 木으로 변환된 대운 snapshot."""
    natal = build_relation_state_snapshot(
        graph=build_relation_dependency_graph(nodes=_NATAL, resolved_relations=()),
        layer="natal", period_key="natal",
    )
    graph = build_relation_dependency_graph(
        nodes=(*_NATAL, _HAI), resolved_relations=(_HARMONY,),
    )
    return build_relation_state_snapshot(
        graph=graph, layer="daewoon", period_key="2003", previous_snapshot=natal,
    )


def _sewoon_graph():
    """巳가 들어온 세운 그래프. 충은 collector 가 만든다."""
    instances = collect_branch_relation_instances(nodes=(*_NATAL, _HAI, _SI))
    return instances, build_relation_dependency_graph(
        nodes=(*_NATAL, _HAI, _SI), resolved_relations=(_HARMONY,),
        disruptive_relations=edges_from_branch_relations(instances),
    )


def _hai_state(snapshot):
    return next(s for s in snapshot.element_states if s.node_id == _HAI.node_id)


# ── 조건 1: 글자 정체성이 층 사이에서 유지됨 ──────────────────────────────


def test_node_identity_is_stable_across_layers() -> None:
    """대운 snapshot 의 亥와 세운 그래프의 亥가 같은 node_id 여야 한다.

    문자 '亥' 만으로 이으면 같은 글자가 여러 자리에 있을 때 엉뚱한 자리에 붙는다.
    """
    prev = _hai_state(_daewoon_snapshot())
    _, graph = _sewoon_graph()
    current = next(n for n in graph.nodes if n.character == "亥")
    assert prev.node_id == current.node_id == "daewoon.branch:亥"


def test_same_character_in_two_luck_layers_is_rejected() -> None:
    """대운 未 + 세운 未 — resolver 어휘로는 구별할 수 없으므로 조용히 하나를 고르지 않는다.

    실측(P1-b1.5): dict 리터럴로 인덱스를 만들면 나중 것이 앞 것을 덮어써 대운 未의 참여가
    세운 未로 기록된다. 12년에 한 번 실제로 일어나는 배치라 예외 상황이 아니다.
    """
    nodes = (
        *_NATAL,
        RelationNode("daewoon.branch:未", "daewoon", "", "branch", "未", "土"),
        RelationNode("sewoon.branch:未", "sewoon", "", "branch", "未", "土"),
    )
    with pytest.raises(ValueError, match="자리·글자 키가 겹친다"):
        build_luck_node_index(nodes)


def test_distinct_luck_characters_index_cleanly() -> None:
    """글자가 다르면 층이 달라도 문제없다 — 위 예외가 정상 경로를 막지 않는다."""
    index = build_luck_node_index((*_NATAL, _HAI, _SI))
    assert index[("luck", "亥")] == "daewoon.branch:亥"
    assert index[("luck", "巳")] == "sewoon.branch:巳"
    assert index[("day", "戌")] != index[("hour", "戌")]


# ── 조건 2: 변환 전후 정보가 남아 있음 ────────────────────────────────────


def test_previous_state_retains_element_before_and_after() -> None:
    """`resolved_element=木` 만 있고 원래 水였다는 정보가 사라지면 환원을 표현할 수 없다."""
    prev = _hai_state(_daewoon_snapshot())
    assert prev.original_element == "水"
    assert prev.resolved_element == "木"
    assert prev.resolution_status is ResolutionStatus.TRANSFORMED


# ── 조건 3: 기존 변환의 근거 관계가 남아 있음 ─────────────────────────────


def test_previous_state_retains_governing_relation() -> None:
    """'과거에 木이었다' 만으로는 무엇이 깨졌는지 연결할 수 없다."""
    prev = _hai_state(_daewoon_snapshot())
    assert _HARMONY.relation_id in prev.governing_relation_ids


def test_relation_id_is_stable_across_luck_combinations() -> None:
    """근거 관계 ID 로 이으려면 층이 늘어도 ID 가 같아야 한다.

    실제 resolver 로 확인한다 — 손으로 만든 fixture 는 이 성질을 증명하지 못한다.
    """
    r = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1987, 8, 5), birth_time="21:00",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    ))
    assert r.pillars is not None

    def harmony_positions(luck: list[str]) -> tuple[str, ...]:
        hit = next(
            x for x in resolve_branch_hap(r.pillars, favorability={}, luck_branches=luck)
            if x.kind == "three_harmony"
        )
        return tuple(x for x in hit.positions)

    assert harmony_positions(["亥"]) == harmony_positions(["亥", "巳"])


# ── 조건 4: 현재 충이 위치별 인스턴스로 존재함 ────────────────────────────


def test_clash_instance_comes_from_collector() -> None:
    """손으로 만든 巳亥冲이 아니라 P1-b0 collector 결과여야 한다."""
    instances, graph = _sewoon_graph()
    clash = next(i for i in instances if i.kind is BranchRelationKind.CLASH)
    assert clash.member_node_ids == ("daewoon.branch:亥", "sewoon.branch:巳")
    assert clash.breaks_transformation is True
    edge = next(e for e in graph.edges if e.relation_id == clash.relation_id)
    assert _HAI.node_id in edge.member_node_ids


# ── 조건 5: 기존 변환과 현재 충의 연결 ────────────────────────────────────


def test_previous_transform_is_linked_to_current_clash() -> None:
    """P1-c 가 받을 입력이 여기서 조립 가능해야 한다.

    링크 방향은 (방해받는 쪽, 방해하는 쪽)으로 고정돼 있다 — P1-a 회귀가 지키는 불변이다.
    """
    prev = _hai_state(_daewoon_snapshot())
    instances, graph = _sewoon_graph()
    clash = next(i for i in instances if i.kind is BranchRelationKind.CLASH)

    dep = next(
        d for d in graph.relation_dependencies
        if d.link_type == LINK_POTENTIALLY_DISRUPTED_BY
    )
    subject_id, affecting_id = dep.relation_ids
    assert subject_id in prev.governing_relation_ids
    assert affecting_id == clash.relation_id
    assert prev.node_id in dep.shared_node_ids

    # P1-c 가 받을 후보. 설명용 구조이지 production DTO 가 아니다.
    candidate = {
        "node_id": prev.node_id,
        "original_element": prev.original_element,
        "previous_resolved_element": prev.resolved_element,
        "previous_status": prev.resolution_status.value,
        "governing_relation_id": subject_id,
        "disrupting_relation_id": affecting_id,
    }
    assert all(v is not None for v in candidate.values())


# ── 조건 6: 현재 상태가 과거 상태를 덮어쓰지 않음 ─────────────────────────


def test_parent_snapshot_object_is_reachable_downstream() -> None:
    """`parent_snapshot_id` 만으로는 부족하다 — 내부 저장소가 없어 내용을 찾을 수 없다.

    그래서 P1-b2 는 최종 snapshot 하나만 반환하면 안 되고, 이전·현재 객체를 함께 넘길 수
    있어야 한다. 여기서는 그 조립이 가능함을 확인한다.
    """
    daewoon = _daewoon_snapshot()
    _, graph = _sewoon_graph()
    sewoon = build_relation_state_snapshot(
        graph=graph, layer="sewoon", period_key="2003", previous_snapshot=daewoon,
    )
    assert sewoon.parent_snapshot_id == daewoon.snapshot_id

    chain = (daewoon, sewoon)
    assert chain[-1] is sewoon
    # 부모 객체에서 이전 변환 사실을 그대로 읽을 수 있다.
    assert _hai_state(chain[0]).resolution_status is ResolutionStatus.TRANSFORMED
    assert _hai_state(chain[0]).resolved_element == "木"


# ── 금지: 자동 환원 판정 ─────────────────────────────────────────────────


def test_no_automatic_reversal_is_produced() -> None:
    """충이 들어왔다고 P1-b1 이 스스로 환원을 판정하면 안 된다."""
    daewoon = _daewoon_snapshot()
    _, graph = _sewoon_graph()
    sewoon = build_relation_state_snapshot(
        graph=graph, layer="sewoon", period_key="2003", previous_snapshot=daewoon,
    )
    # 현재 상태가 무엇이어야 하는지는 **고정하지 않는다.** P1-b1 은 환원 판정기가 아니므로
    # ORIGINAL·UNCONFIRMED·TRANSFORMED 중 무엇이든 이 슬라이스의 결론이 아니다.
    statuses = {s.resolution_status for s in sewoon.element_states}
    assert all(s.value != "reversed" for s in statuses)
    assert not hasattr(ResolutionStatus, "REVERSED")

    # 금지되는 것은 과거 사실의 소실이다.
    assert _hai_state(sewoon).original_element == "水"
    assert _hai_state(daewoon).resolution_status is ResolutionStatus.TRANSFORMED
    assert _hai_state(daewoon).resolved_element == "木"
    assert _HARMONY.relation_id in _hai_state(daewoon).governing_relation_ids
